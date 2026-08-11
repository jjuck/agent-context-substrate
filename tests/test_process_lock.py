import multiprocessing
from pathlib import Path
import time
from typing import Any

import pytest

from agent_context_substrate.process_lock import InterProcessFileLock, LockTimeoutError


def _attempt_lock_in_child(lock_path: str, result_queue: Any) -> None:
    try:
        with InterProcessFileLock(lock_path, timeout_seconds=0.15, poll_interval_seconds=0.01):
            result_queue.put("acquired")
    except LockTimeoutError:
        result_queue.put("timed-out")


def test_context_manager_creates_lock_file_in_missing_parent(tmp_path: Path) -> None:
    lock_path = tmp_path / "nested" / "worker.lock"

    with InterProcessFileLock(lock_path):
        assert lock_path.is_file()


def test_second_lock_times_out_while_first_lock_is_held(tmp_path: Path) -> None:
    lock_path = tmp_path / "worker.lock"

    with InterProcessFileLock(lock_path):
        started_at = time.monotonic()
        with pytest.raises(LockTimeoutError, match="worker.lock"):
            with InterProcessFileLock(lock_path, timeout_seconds=0.08, poll_interval_seconds=0.01):
                pytest.fail("contending lock must not be acquired")

    elapsed = time.monotonic() - started_at
    assert 0.06 <= elapsed < 1.0


def test_context_manager_releases_lock_when_body_raises(tmp_path: Path) -> None:
    lock_path = tmp_path / "worker.lock"

    with pytest.raises(RuntimeError, match="body failed"):
        with InterProcessFileLock(lock_path):
            raise RuntimeError("body failed")

    with InterProcessFileLock(lock_path, timeout_seconds=0):
        pass


def test_child_process_times_out_while_parent_holds_lock(tmp_path: Path) -> None:
    lock_path = tmp_path / "worker.lock"
    context = multiprocessing.get_context("spawn")
    result_queue = context.Queue()
    child = context.Process(target=_attempt_lock_in_child, args=(str(lock_path), result_queue))

    with InterProcessFileLock(lock_path):
        child.start()
        child.join(timeout=5)

    if child.is_alive():
        child.terminate()
        child.join(timeout=5)
        pytest.fail("child process did not finish within 5 seconds")
    assert child.exitcode == 0
    assert result_queue.get(timeout=1) == "timed-out"


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"timeout_seconds": -0.01}, "timeout_seconds"),
        ({"timeout_seconds": float("inf")}, "timeout_seconds"),
        ({"poll_interval_seconds": 0}, "poll_interval_seconds"),
        ({"poll_interval_seconds": float("nan")}, "poll_interval_seconds"),
    ],
)
def test_wait_configuration_must_be_finite_and_bounded(
    tmp_path: Path,
    kwargs: dict[str, float],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        InterProcessFileLock(tmp_path / "worker.lock", **kwargs)
