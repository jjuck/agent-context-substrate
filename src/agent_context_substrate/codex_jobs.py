from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
import json
import math
from pathlib import Path
import sqlite3
import time
from typing import Literal, TypeAlias, cast
from uuid import uuid4


JobStatus: TypeAlias = Literal[
    "queued",
    "leased",
    "retry",
    "completed",
    "dead_letter",
    "superseded",
]
RolloutFingerprint: TypeAlias = dict[str, int | str]
_JOB_STATUSES = {"queued", "leased", "retry", "completed", "dead_letter", "superseded"}


@dataclass(frozen=True)
class CodexJob:
    id: int
    thread_id: str
    rollout_fingerprint: str
    config_digest: str
    payload: dict[str, object]
    status: JobStatus
    created_at: float
    updated_at: float
    available_at: float
    attempt_count: int
    lease_owner: str | None
    lease_token: str | None
    lease_expires_at: float | None
    last_error: str
    completed_at: float | None


@dataclass(frozen=True)
class QueueHealth:
    total_count: int
    queued_count: int
    leased_count: int
    retry_count: int
    completed_count: int
    dead_letter_count: int
    superseded_count: int
    oldest_pending_age_seconds: float | None

    @property
    def pending_count(self) -> int:
        return self.queued_count + self.leased_count + self.retry_count

    @property
    def counts(self) -> dict[str, int]:
        return {
            "queued": self.queued_count,
            "leased": self.leased_count,
            "retry": self.retry_count,
            "completed": self.completed_count,
            "dead_letter": self.dead_letter_count,
            "superseded": self.superseded_count,
        }


def default_codex_jobs_path(project_root: Path | str) -> Path:
    return Path(project_root) / "data" / "index" / "codex_jobs.sqlite3"


def encode_rollout_fingerprint(fingerprint: Mapping[str, int | str]) -> str:
    normalized = _normalize_rollout_fingerprint(fingerprint)
    return json.dumps(normalized, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def decode_rollout_fingerprint(encoded: str) -> RolloutFingerprint:
    try:
        payload = json.loads(encoded)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError("rollout fingerprint must be a valid JSON object") from exc
    if not isinstance(payload, dict):
        raise ValueError("rollout fingerprint must be a JSON object")
    return _normalize_rollout_fingerprint(payload)


class CodexJobQueue:
    def __init__(self, path: Path | str, *, busy_timeout_ms: int = 5_000) -> None:
        if busy_timeout_ms <= 0:
            raise ValueError("busy_timeout_ms must be greater than zero")
        self.path = Path(path)
        self.busy_timeout_ms = busy_timeout_ms
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def enqueue(
        self,
        *,
        thread_id: str,
        rollout_fingerprint: str,
        config_digest: str,
        payload: Mapping[str, object] | None = None,
        now: float | None = None,
    ) -> CodexJob:
        _require_text(thread_id, "thread_id")
        _require_text(rollout_fingerprint, "rollout_fingerprint")
        _require_text(config_digest, "config_digest")
        timestamp = _resolve_time(now)
        payload_json = json.dumps(
            dict(payload or {}),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        with self._transaction() as connection:
            existing = connection.execute(
                """
                SELECT * FROM codex_jobs
                WHERE thread_id = ? AND rollout_fingerprint = ? AND config_digest = ?
                """,
                (thread_id, rollout_fingerprint, config_digest),
            ).fetchone()
            if existing is not None:
                return _job_from_row(existing)
            connection.execute(
                """
                UPDATE codex_jobs
                SET status = 'superseded', updated_at = ?, lease_owner = NULL,
                    lease_token = NULL, lease_expires_at = NULL
                WHERE thread_id = ? AND status IN ('queued', 'retry')
                """,
                (timestamp, thread_id),
            )
            cursor = connection.execute(
                """
                INSERT INTO codex_jobs (
                    thread_id, rollout_fingerprint, config_digest, payload_json,
                    status, created_at, updated_at, available_at
                ) VALUES (?, ?, ?, ?, 'queued', ?, ?, ?)
                """,
                (
                    thread_id,
                    rollout_fingerprint,
                    config_digest,
                    payload_json,
                    timestamp,
                    timestamp,
                    timestamp,
                ),
            )
            row = connection.execute(
                "SELECT * FROM codex_jobs WHERE id = ?",
                (cursor.lastrowid,),
            ).fetchone()
        if row is None:
            raise RuntimeError("enqueued Codex job could not be read back")
        return _job_from_row(row)

    def claim(
        self,
        *,
        worker_id: str,
        lease_seconds: float,
        now: float | None = None,
    ) -> CodexJob | None:
        _require_text(worker_id, "worker_id")
        _require_non_negative_number(lease_seconds, "lease_seconds", allow_zero=False)
        timestamp = _resolve_time(now)
        lease_token = uuid4().hex
        with self._transaction() as connection:
            candidate = connection.execute(
                """
                SELECT candidate.id
                FROM codex_jobs AS candidate
                WHERE (
                    (candidate.status IN ('queued', 'retry') AND candidate.available_at <= ?)
                    OR (
                        candidate.status = 'leased'
                        AND candidate.lease_expires_at IS NOT NULL
                        AND candidate.lease_expires_at <= ?
                    )
                )
                AND NOT EXISTS (
                    SELECT 1
                    FROM codex_jobs AS active
                    WHERE active.thread_id = candidate.thread_id
                      AND active.id <> candidate.id
                      AND active.status = 'leased'
                      AND active.lease_expires_at > ?
                )
                ORDER BY candidate.created_at, candidate.id
                LIMIT 1
                """,
                (timestamp, timestamp, timestamp),
            ).fetchone()
            if candidate is None:
                return None
            job_id = int(candidate["id"])
            connection.execute(
                """
                UPDATE codex_jobs
                SET status = 'leased', updated_at = ?, attempt_count = attempt_count + 1,
                    lease_owner = ?, lease_token = ?, lease_expires_at = ?
                WHERE id = ?
                """,
                (timestamp, worker_id, lease_token, timestamp + lease_seconds, job_id),
            )
            row = connection.execute(
                "SELECT * FROM codex_jobs WHERE id = ?",
                (job_id,),
            ).fetchone()
        if row is None:
            raise RuntimeError("claimed Codex job could not be read back")
        return _job_from_row(row)

    def get(self, job_id: int) -> CodexJob:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM codex_jobs WHERE id = ?",
                (job_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"Unknown Codex job id: {job_id}")
        return _job_from_row(row)

    def list_jobs(self, *, status: JobStatus | None = None, limit: int = 20) -> list[CodexJob]:
        if status is not None and status not in _JOB_STATUSES:
            raise ValueError(f"unsupported Codex job status: {status}")
        if limit <= 0:
            raise ValueError("limit must be greater than zero")
        query = "SELECT * FROM codex_jobs"
        parameters: tuple[object, ...]
        if status is None:
            parameters = (limit,)
        else:
            query += " WHERE status = ?"
            parameters = (status, limit)
        query += " ORDER BY created_at DESC, id DESC LIMIT ?"
        with self._connection() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [_job_from_row(row) for row in rows]

    def requeue_dead_letter(self, job_id: int, *, now: float | None = None) -> bool:
        timestamp = _resolve_time(now)
        with self._transaction() as connection:
            cursor = connection.execute(
                """
                UPDATE codex_jobs
                SET status = 'queued', updated_at = ?, available_at = ?,
                    attempt_count = 0, lease_owner = NULL, lease_token = NULL,
                    lease_expires_at = NULL, completed_at = NULL
                WHERE id = ? AND status = 'dead_letter'
                """,
                (timestamp, timestamp, job_id),
            )
        return cursor.rowcount == 1

    def renew(
        self,
        job_id: int,
        lease_token: str | None,
        *,
        lease_seconds: float,
        now: float | None = None,
    ) -> bool:
        _require_non_negative_number(lease_seconds, "lease_seconds", allow_zero=False)
        timestamp = _resolve_time(now)
        if not lease_token:
            return False
        with self._transaction() as connection:
            cursor = connection.execute(
                """
                UPDATE codex_jobs
                SET updated_at = ?, lease_expires_at = ?
                WHERE id = ? AND status = 'leased' AND lease_token = ?
                  AND lease_expires_at > ?
                """,
                (timestamp, timestamp + lease_seconds, job_id, lease_token, timestamp),
            )
        return cursor.rowcount == 1

    def complete(
        self,
        job_id: int,
        lease_token: str | None,
        *,
        now: float | None = None,
    ) -> bool:
        timestamp = _resolve_time(now)
        if not lease_token:
            return False
        with self._transaction() as connection:
            cursor = connection.execute(
                """
                UPDATE codex_jobs
                SET status = 'completed', updated_at = ?, completed_at = ?,
                    lease_owner = NULL, lease_token = NULL, lease_expires_at = NULL,
                    last_error = ''
                WHERE id = ? AND status = 'leased' AND lease_token = ?
                  AND lease_expires_at > ?
                """,
                (timestamp, timestamp, job_id, lease_token, timestamp),
            )
        return cursor.rowcount == 1

    def retry(
        self,
        job_id: int,
        lease_token: str | None,
        *,
        error: str,
        delay_seconds: float,
        now: float | None = None,
    ) -> bool:
        _require_non_negative_number(delay_seconds, "delay_seconds", allow_zero=True)
        timestamp = _resolve_time(now)
        if not lease_token:
            return False
        with self._transaction() as connection:
            cursor = connection.execute(
                """
                UPDATE codex_jobs
                SET status = 'retry', updated_at = ?, available_at = ?, last_error = ?,
                    lease_owner = NULL, lease_token = NULL, lease_expires_at = NULL
                WHERE id = ? AND status = 'leased' AND lease_token = ?
                  AND lease_expires_at > ?
                """,
                (
                    timestamp,
                    timestamp + delay_seconds,
                    error,
                    job_id,
                    lease_token,
                    timestamp,
                ),
            )
        return cursor.rowcount == 1

    def defer(
        self,
        job_id: int,
        lease_token: str | None,
        *,
        error: str,
        delay_seconds: float,
        now: float | None = None,
    ) -> bool:
        """Release a temporary-contention lease without charging an attempt."""
        _require_non_negative_number(delay_seconds, "delay_seconds", allow_zero=True)
        timestamp = _resolve_time(now)
        if not lease_token:
            return False
        with self._transaction() as connection:
            cursor = connection.execute(
                """
                UPDATE codex_jobs
                SET status = 'retry', updated_at = ?, available_at = ?, last_error = ?,
                    attempt_count = CASE
                        WHEN attempt_count > 0 THEN attempt_count - 1
                        ELSE 0
                    END,
                    lease_owner = NULL, lease_token = NULL, lease_expires_at = NULL
                WHERE id = ? AND status = 'leased' AND lease_token = ?
                  AND lease_expires_at > ?
                """,
                (
                    timestamp,
                    timestamp + delay_seconds,
                    error,
                    job_id,
                    lease_token,
                    timestamp,
                ),
            )
        return cursor.rowcount == 1

    def dead_letter(
        self,
        job_id: int,
        lease_token: str | None,
        *,
        error: str,
        now: float | None = None,
    ) -> bool:
        timestamp = _resolve_time(now)
        if not lease_token:
            return False
        with self._transaction() as connection:
            cursor = connection.execute(
                """
                UPDATE codex_jobs
                SET status = 'dead_letter', updated_at = ?, last_error = ?,
                    lease_owner = NULL, lease_token = NULL, lease_expires_at = NULL
                WHERE id = ? AND status = 'leased' AND lease_token = ?
                  AND lease_expires_at > ?
                """,
                (timestamp, error, job_id, lease_token, timestamp),
            )
        return cursor.rowcount == 1

    def health(self, *, now: float | None = None) -> QueueHealth:
        timestamp = _resolve_time(now)
        with self._connection() as connection:
            rows = connection.execute("SELECT status, COUNT(*) AS count FROM codex_jobs GROUP BY status").fetchall()
            oldest_row = connection.execute(
                """
                SELECT MIN(created_at) AS oldest_created_at
                FROM codex_jobs
                WHERE status IN ('queued', 'leased', 'retry')
                """
            ).fetchone()
        counts = {str(row["status"]): int(row["count"]) for row in rows}
        oldest_created_at = oldest_row["oldest_created_at"] if oldest_row is not None else None
        oldest_age = None if oldest_created_at is None else max(0.0, timestamp - float(oldest_created_at))
        return QueueHealth(
            total_count=sum(counts.values()),
            queued_count=counts.get("queued", 0),
            leased_count=counts.get("leased", 0),
            retry_count=counts.get("retry", 0),
            completed_count=counts.get("completed", 0),
            dead_letter_count=counts.get("dead_letter", 0),
            superseded_count=counts.get("superseded", 0),
            oldest_pending_age_seconds=oldest_age,
        )

    def _initialize(self) -> None:
        with self._connection() as connection:
            self._enable_wal(connection)
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS codex_jobs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        thread_id TEXT NOT NULL,
                        rollout_fingerprint TEXT NOT NULL,
                        config_digest TEXT NOT NULL,
                        payload_json TEXT NOT NULL,
                        status TEXT NOT NULL CHECK (
                            status IN (
                                'queued', 'leased', 'retry', 'completed',
                                'dead_letter', 'superseded'
                            )
                        ),
                        created_at REAL NOT NULL,
                        updated_at REAL NOT NULL,
                        available_at REAL NOT NULL,
                        attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
                        lease_owner TEXT,
                        lease_token TEXT,
                        lease_expires_at REAL,
                        last_error TEXT NOT NULL DEFAULT '',
                        completed_at REAL,
                        UNIQUE (thread_id, rollout_fingerprint, config_digest)
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE INDEX IF NOT EXISTS codex_jobs_claim_idx
                    ON codex_jobs (status, available_at, lease_expires_at, created_at, id)
                    """
                )
                connection.execute(
                    """
                    CREATE INDEX IF NOT EXISTS codex_jobs_thread_status_idx
                    ON codex_jobs (thread_id, status)
                    """
                )
                connection.commit()
            except BaseException:
                connection.rollback()
                raise

    def _enable_wal(self, connection: sqlite3.Connection) -> None:
        deadline = time.monotonic() + (self.busy_timeout_ms / 1_000)
        connection.execute("PRAGMA busy_timeout = 50")
        try:
            while True:
                try:
                    row = connection.execute("PRAGMA journal_mode = WAL").fetchone()
                except sqlite3.OperationalError as exc:
                    if "locked" not in str(exc).lower() or time.monotonic() >= deadline:
                        raise
                    time.sleep(0.01)
                    continue
                if row is not None and str(row[0]).lower() == "wal":
                    return
                if time.monotonic() >= deadline:
                    raise sqlite3.OperationalError("could not enable SQLite WAL mode")
                time.sleep(0.01)
        finally:
            connection.execute(f"PRAGMA busy_timeout = {self.busy_timeout_ms}")

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(
            self.path,
            timeout=self.busy_timeout_ms / 1_000,
            isolation_level=None,
        )
        connection.row_factory = sqlite3.Row
        connection.execute(f"PRAGMA busy_timeout = {self.busy_timeout_ms}")
        connection.execute("PRAGMA synchronous = FULL")
        try:
            yield connection
        finally:
            connection.close()

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                yield connection
                connection.commit()
            except BaseException:
                connection.rollback()
                raise


def _job_from_row(row: sqlite3.Row) -> CodexJob:
    payload = json.loads(str(row["payload_json"]))
    if not isinstance(payload, dict):
        raise ValueError(f"Codex job {row['id']} has a non-object payload")
    return CodexJob(
        id=int(row["id"]),
        thread_id=str(row["thread_id"]),
        rollout_fingerprint=str(row["rollout_fingerprint"]),
        config_digest=str(row["config_digest"]),
        payload={str(key): value for key, value in payload.items()},
        status=cast(JobStatus, str(row["status"])),
        created_at=float(row["created_at"]),
        updated_at=float(row["updated_at"]),
        available_at=float(row["available_at"]),
        attempt_count=int(row["attempt_count"]),
        lease_owner=None if row["lease_owner"] is None else str(row["lease_owner"]),
        lease_token=None if row["lease_token"] is None else str(row["lease_token"]),
        lease_expires_at=None if row["lease_expires_at"] is None else float(row["lease_expires_at"]),
        last_error=str(row["last_error"]),
        completed_at=None if row["completed_at"] is None else float(row["completed_at"]),
    )


def _require_text(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


def _normalize_rollout_fingerprint(fingerprint: Mapping[object, object]) -> RolloutFingerprint:
    if not fingerprint:
        raise ValueError("rollout fingerprint must not be empty")
    normalized: RolloutFingerprint = {}
    for key, value in fingerprint.items():
        if not isinstance(key, str) or not key:
            raise ValueError("rollout fingerprint keys must be non-empty strings")
        if isinstance(value, bool) or not isinstance(value, (int, str)):
            raise ValueError("rollout fingerprint values must be strings or integers")
        normalized[key] = value
    return normalized


def _require_non_negative_number(value: float, name: str, *, allow_zero: bool) -> None:
    if not math.isfinite(value) or value < 0 or (not allow_zero and value == 0):
        qualifier = "non-negative" if allow_zero else "greater than zero"
        raise ValueError(f"{name} must be a finite number {qualifier}")


def _resolve_time(value: float | None) -> float:
    timestamp = time.time() if value is None else value
    if not math.isfinite(timestamp):
        raise ValueError("now must be finite")
    return float(timestamp)
