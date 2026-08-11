from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from agent_context_substrate.codex_jobs import (
    CodexJobQueue,
    decode_rollout_fingerprint,
    encode_rollout_fingerprint,
)


def _enqueue(
    queue: CodexJobQueue,
    *,
    thread_id: str = "thread-1",
    fingerprint: str = "fingerprint-1",
    now: float = 100.0,
):
    return queue.enqueue(
        thread_id=thread_id,
        rollout_fingerprint=fingerprint,
        config_digest="config-1",
        payload={"thread_id": thread_id},
        now=now,
    )


def test_concurrent_initialization_and_enqueue_are_safe(tmp_path: Path) -> None:
    database_path = tmp_path / "nested" / "codex_jobs.sqlite3"

    def initialize_and_enqueue(index: int) -> int:
        queue = CodexJobQueue(database_path)
        return _enqueue(queue, thread_id=f"thread-{index}", now=float(index)).id

    with ThreadPoolExecutor(max_workers=8) as executor:
        job_ids = list(executor.map(initialize_and_enqueue, range(12)))

    health = CodexJobQueue(database_path).health(now=20.0)
    assert len(set(job_ids)) == 12
    assert health.queued_count == 12
    assert health.total_count == 12


def test_enqueue_is_idempotent_for_the_same_thread_fingerprint_and_config(tmp_path: Path) -> None:
    queue = CodexJobQueue(tmp_path / "jobs.sqlite3")

    first = _enqueue(queue)
    duplicate = queue.enqueue(
        thread_id="thread-1",
        rollout_fingerprint="fingerprint-1",
        config_digest="config-1",
        payload={"replacement": "must not overwrite the original"},
        now=200.0,
    )

    assert duplicate.id == first.id
    assert duplicate.payload == {"thread_id": "thread-1"}
    assert queue.health(now=200.0).total_count == 1


def test_latest_enqueue_supersedes_older_queued_and_retry_jobs(tmp_path: Path) -> None:
    queue = CodexJobQueue(tmp_path / "jobs.sqlite3")
    first = _enqueue(queue, fingerprint="fingerprint-1", now=100.0)
    second = _enqueue(queue, fingerprint="fingerprint-2", now=110.0)

    claimed = queue.claim(worker_id="worker-1", lease_seconds=30.0, now=110.0)
    assert claimed is not None
    assert claimed.id == second.id
    assert queue.retry(claimed.id, claimed.lease_token, error="temporary", delay_seconds=5.0, now=111.0)

    third = _enqueue(queue, fingerprint="fingerprint-3", now=112.0)

    assert queue.get(first.id).status == "superseded"
    assert queue.get(second.id).status == "superseded"
    assert queue.get(third.id).status == "queued"


def test_latest_enqueue_does_not_replace_a_job_that_is_already_leased(tmp_path: Path) -> None:
    queue = CodexJobQueue(tmp_path / "jobs.sqlite3")
    first = _enqueue(queue, fingerprint="fingerprint-1")
    claimed = queue.claim(worker_id="worker-1", lease_seconds=30.0, now=100.0)
    assert claimed is not None

    latest = _enqueue(queue, fingerprint="fingerprint-2", now=101.0)

    assert queue.get(first.id).status == "leased"
    assert queue.get(latest.id).status == "queued"


def test_only_one_worker_can_claim_a_ready_job(tmp_path: Path) -> None:
    database_path = tmp_path / "jobs.sqlite3"
    _enqueue(CodexJobQueue(database_path))

    def claim(worker_number: int):
        return CodexJobQueue(database_path).claim(
            worker_id=f"worker-{worker_number}",
            lease_seconds=30.0,
            now=100.0,
        )

    with ThreadPoolExecutor(max_workers=8) as executor:
        claims = list(executor.map(claim, range(8)))

    claimed_jobs = [job for job in claims if job is not None]
    assert len(claimed_jobs) == 1
    assert claimed_jobs[0].attempt_count == 1


def test_expired_lease_is_reclaimed_and_rejects_the_stale_lease_token(tmp_path: Path) -> None:
    queue = CodexJobQueue(tmp_path / "jobs.sqlite3")
    original = _enqueue(queue)

    first_claim = queue.claim(worker_id="worker-1", lease_seconds=10.0, now=100.0)
    before_expiry = queue.claim(worker_id="worker-2", lease_seconds=10.0, now=109.0)
    reclaimed = queue.claim(worker_id="worker-2", lease_seconds=10.0, now=111.0)

    assert first_claim is not None
    assert before_expiry is None
    assert reclaimed is not None
    assert reclaimed.id == original.id
    assert reclaimed.attempt_count == 2
    assert reclaimed.lease_token != first_claim.lease_token
    assert queue.complete(original.id, first_claim.lease_token, now=112.0) is False
    assert queue.complete(original.id, reclaimed.lease_token, now=112.0) is True
    assert queue.get(original.id).status == "completed"


def test_renew_extends_an_active_lease_and_allows_later_completion(tmp_path: Path) -> None:
    queue = CodexJobQueue(tmp_path / "jobs.sqlite3")
    _enqueue(queue)
    claimed = queue.claim(worker_id="worker-1", lease_seconds=10.0, now=100.0)
    assert claimed is not None

    renewed = queue.renew(
        claimed.id,
        claimed.lease_token,
        lease_seconds=20.0,
        now=105.0,
    )

    stored = queue.get(claimed.id)
    assert renewed is True
    assert stored.lease_expires_at == pytest.approx(125.0)
    assert stored.updated_at == pytest.approx(105.0)
    assert queue.complete(claimed.id, claimed.lease_token, now=120.0) is True


def test_renew_rejects_nonleased_stale_and_expired_leases(tmp_path: Path) -> None:
    queue = CodexJobQueue(tmp_path / "jobs.sqlite3")
    queued = _enqueue(queue)
    assert queue.renew(queued.id, "not-a-lease", lease_seconds=10.0, now=99.0) is False

    claimed = queue.claim(worker_id="worker-1", lease_seconds=10.0, now=100.0)
    assert claimed is not None

    assert queue.renew(claimed.id, "stale-token", lease_seconds=20.0, now=101.0) is False
    assert queue.renew(claimed.id, claimed.lease_token, lease_seconds=20.0, now=110.0) is False
    assert queue.get(claimed.id).lease_expires_at == pytest.approx(110.0)


def test_retry_waits_until_its_schedule_and_can_then_complete(tmp_path: Path) -> None:
    queue = CodexJobQueue(tmp_path / "jobs.sqlite3")
    _enqueue(queue)
    first_claim = queue.claim(worker_id="worker-1", lease_seconds=30.0, now=100.0)
    assert first_claim is not None

    retried = queue.retry(
        first_claim.id,
        first_claim.lease_token,
        error="Codex CLI unavailable",
        delay_seconds=20.0,
        now=101.0,
    )

    assert retried is True
    assert queue.claim(worker_id="worker-2", lease_seconds=30.0, now=120.9) is None
    second_claim = queue.claim(worker_id="worker-2", lease_seconds=30.0, now=121.0)
    assert second_claim is not None
    assert second_claim.attempt_count == 2
    assert second_claim.last_error == "Codex CLI unavailable"
    assert queue.complete(second_claim.id, second_claim.lease_token, now=122.0)


def test_defer_releases_the_lease_without_consuming_an_attempt(tmp_path: Path) -> None:
    queue = CodexJobQueue(tmp_path / "jobs.sqlite3")
    _enqueue(queue)
    first_claim = queue.claim(worker_id="worker-1", lease_seconds=30.0, now=100.0)
    assert first_claim is not None
    assert first_claim.attempt_count == 1

    deferred = queue.defer(
        first_claim.id,
        first_claim.lease_token,
        error="finalize lock is busy",
        delay_seconds=20.0,
        now=101.0,
    )

    stored = queue.get(first_claim.id)
    assert deferred is True
    assert stored.status == "retry"
    assert stored.attempt_count == 0
    assert stored.last_error == "finalize lock is busy"
    assert queue.claim(worker_id="worker-2", lease_seconds=30.0, now=120.9) is None
    second_claim = queue.claim(worker_id="worker-2", lease_seconds=30.0, now=121.0)
    assert second_claim is not None
    assert second_claim.attempt_count == 1


def test_dead_letter_is_terminal(tmp_path: Path) -> None:
    queue = CodexJobQueue(tmp_path / "jobs.sqlite3")
    _enqueue(queue)
    claimed = queue.claim(worker_id="worker-1", lease_seconds=30.0, now=100.0)
    assert claimed is not None

    transitioned = queue.dead_letter(
        claimed.id,
        claimed.lease_token,
        error="retry budget exhausted",
        now=101.0,
    )

    stored = queue.get(claimed.id)
    assert transitioned is True
    assert stored.status == "dead_letter"
    assert stored.last_error == "retry budget exhausted"
    assert queue.claim(worker_id="worker-2", lease_seconds=30.0, now=1_000.0) is None


def test_dead_letter_can_be_explicitly_requeued_with_a_fresh_attempt_budget(tmp_path: Path) -> None:
    queue = CodexJobQueue(tmp_path / "jobs.sqlite3")
    job = _enqueue(queue)
    claimed = queue.claim(worker_id="worker-1", lease_seconds=30.0, now=100.0)
    assert claimed is not None
    assert queue.dead_letter(claimed.id, claimed.lease_token, error="terminal", now=101.0)

    assert queue.requeue_dead_letter(job.id, now=200.0) is True

    stored = queue.get(job.id)
    assert stored.status == "queued"
    assert stored.attempt_count == 0
    assert stored.last_error == "terminal"
    reclaimed = queue.claim(worker_id="worker-2", lease_seconds=30.0, now=200.0)
    assert reclaimed is not None and reclaimed.id == job.id


def test_list_jobs_filters_status_newest_first(tmp_path: Path) -> None:
    queue = CodexJobQueue(tmp_path / "jobs.sqlite3")
    _enqueue(queue, thread_id="first", now=100.0)
    latest = _enqueue(queue, thread_id="second", now=200.0)

    jobs = queue.list_jobs(status="queued", limit=1)

    assert [job.id for job in jobs] == [latest.id]


def test_health_reports_status_counts_and_oldest_pending_age(tmp_path: Path) -> None:
    queue = CodexJobQueue(tmp_path / "jobs.sqlite3")
    retry_job = _enqueue(queue, thread_id="retry", now=100.0)
    retry_claim = queue.claim(worker_id="worker-1", lease_seconds=30.0, now=100.0)
    assert retry_claim is not None and retry_claim.id == retry_job.id
    assert queue.retry(retry_job.id, retry_claim.lease_token, error="later", delay_seconds=100.0, now=101.0)

    dead_job = _enqueue(queue, thread_id="dead", now=110.0)
    dead_claim = queue.claim(worker_id="worker-1", lease_seconds=30.0, now=110.0)
    assert dead_claim is not None and dead_claim.id == dead_job.id
    assert queue.dead_letter(dead_job.id, dead_claim.lease_token, error="terminal", now=111.0)

    _enqueue(queue, thread_id="oldest-queued", now=120.0)

    superseded = _enqueue(queue, thread_id="latest", fingerprint="old", now=130.0)
    latest = _enqueue(queue, thread_id="latest", fingerprint="new", now=131.0)
    health = queue.health(now=150.0)

    assert queue.get(superseded.id).status == "superseded"
    assert queue.get(latest.id).status == "queued"
    assert health.queued_count == 2
    assert health.retry_count == 1
    assert health.leased_count == 0
    assert health.completed_count == 0
    assert health.dead_letter_count == 1
    assert health.superseded_count == 1
    assert health.pending_count == 3
    assert health.total_count == 5
    assert health.oldest_pending_age_seconds == pytest.approx(50.0)


def test_rollout_fingerprint_encoding_is_canonical_and_round_trips() -> None:
    first = {"rollout_path": "세션/rollout.jsonl", "mtime_ns": 42, "size": 7}
    reordered = {"size": 7, "rollout_path": "세션/rollout.jsonl", "mtime_ns": 42}

    encoded = encode_rollout_fingerprint(first)

    assert encoded == encode_rollout_fingerprint(reordered)
    assert decode_rollout_fingerprint(encoded) == first


@pytest.mark.parametrize("invalid", ['["not-an-object"]', '{"size":true}'])
def test_rollout_fingerprint_decoder_rejects_invalid_payloads(invalid: str) -> None:
    with pytest.raises(ValueError, match="rollout fingerprint"):
        decode_rollout_fingerprint(invalid)


@pytest.mark.parametrize(
    ("operation", "expected_message"),
    [
        (lambda queue: _enqueue(queue, thread_id=""), "thread_id"),
        (
            lambda queue: queue.claim(worker_id="worker", lease_seconds=0.0),
            "lease_seconds",
        ),
        (
            lambda queue: queue.renew(1, "token", lease_seconds=0.0),
            "lease_seconds",
        ),
    ],
)
def test_invalid_queue_inputs_are_rejected(tmp_path: Path, operation, expected_message: str) -> None:
    queue = CodexJobQueue(tmp_path / "jobs.sqlite3")

    with pytest.raises(ValueError, match=expected_message):
        operation(queue)
