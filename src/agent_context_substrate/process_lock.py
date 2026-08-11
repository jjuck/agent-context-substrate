from __future__ import annotations

import errno
import hashlib
import math
import os
from pathlib import Path
import tempfile
import time
from types import TracebackType
from typing import BinaryIO

if os.name == "nt":
    import msvcrt
else:
    import fcntl


class LockTimeoutError(TimeoutError):
    """Raised when an inter-process lock cannot be acquired in time."""


def shared_wiki_writer_lock_path(wiki_root: Path | str) -> Path:
    normalized = str(Path(wiki_root).expanduser().resolve(strict=False)).casefold()
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return Path(tempfile.gettempdir()) / "agent-context-substrate" / "wiki-locks" / f"{digest}.lock"


class InterProcessFileLock:
    def __init__(
        self,
        path: Path | str,
        *,
        timeout_seconds: float = 10.0,
        poll_interval_seconds: float = 0.05,
    ) -> None:
        timeout = float(timeout_seconds)
        poll_interval = float(poll_interval_seconds)
        if not math.isfinite(timeout) or timeout < 0:
            raise ValueError("timeout_seconds must be finite and non-negative")
        if not math.isfinite(poll_interval) or poll_interval <= 0:
            raise ValueError("poll_interval_seconds must be finite and positive")
        self.path = Path(path)
        self.timeout_seconds = timeout
        self.poll_interval_seconds = poll_interval
        self._file: BinaryIO | None = None

    def acquire(self) -> "InterProcessFileLock":
        if self._file is not None:
            raise RuntimeError("lock instance is already acquired")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._file = self.path.open("a+b", buffering=0)
        self._ensure_lock_byte()
        deadline = time.monotonic() + self.timeout_seconds
        while True:
            try:
                self._lock_file()
                return self
            except OSError as exc:
                if exc.errno not in {errno.EACCES, errno.EAGAIN}:
                    self._close_file()
                    raise
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    self._close_file()
                    raise LockTimeoutError(
                        f"timed out after {self.timeout_seconds:g}s waiting for lock: {self.path}"
                    ) from exc
                time.sleep(min(self.poll_interval_seconds, remaining))

    def release(self) -> None:
        lock_file = self._file
        if lock_file is None:
            return
        self._file = None
        try:
            self._unlock_file(lock_file)
        finally:
            lock_file.close()

    def _ensure_lock_byte(self) -> None:
        assert self._file is not None
        if self._file.seek(0, os.SEEK_END) == 0:
            self._file.write(b"\0")
        self._file.seek(0)

    def _lock_file(self) -> None:
        assert self._file is not None
        self._file.seek(0)
        if os.name == "nt":
            msvcrt.locking(self._file.fileno(), msvcrt.LK_NBLCK, 1)
            return
        fcntl.flock(self._file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    @staticmethod
    def _unlock_file(lock_file: BinaryIO) -> None:
        lock_file.seek(0)
        if os.name == "nt":
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
            return
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    def _close_file(self) -> None:
        if self._file is None:
            return
        self._file.close()
        self._file = None

    def __enter__(self) -> "InterProcessFileLock":
        return self.acquire()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.release()
