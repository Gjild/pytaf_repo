from __future__ import annotations

from contextlib import suppress
import os
from pathlib import Path
from typing import IO, Any

IS_WIN: bool = os.name == "nt"

# Best-effort import; use `Any` to silence missing attributes in type stubs.
try:  # pragma: no cover
    import msvcrt as _msvcrt
    MSVCRT: Any | None = _msvcrt
except Exception:  # pragma: no cover
    MSVCRT = None


class BrokerLock:
    """
    Single-byte advisory lock held exclusively by the broker while alive.
    Presence == broker alive for kill safety checks.
    """
    def __init__(self, path: str) -> None:
        self._path: Path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if not self._path.exists():
            self._path.write_bytes(b"")
        self._fh: IO[bytes] | None = None

    @property
    def path(self) -> Path:
        return self._path

    def acquire_exclusive(self) -> None:
        if self._fh is not None:
            return
        fh: IO[bytes] = open(self._path, "a+b")  # noqa: SIM115 (long-lived)
        try:
            if IS_WIN and MSVCRT is not None:
                # Lock 1 byte non-blocking; use Any to avoid stub attribute errors.
                MSVCRT.locking(fh.fileno(), MSVCRT.LK_NBLCK, 1)
            else:
                import fcntl  # lazy import for POSIX
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            self._fh = fh
        except Exception:
            try:
                fh.close()
            finally:
                pass
            raise

    def release(self) -> None:
        fh = self._fh
        if fh is None:
            return
        try:
            if IS_WIN and MSVCRT is not None:
                MSVCRT.locking(fh.fileno(), MSVCRT.LK_UNLCK, 1)
            else:
                import fcntl  # lazy import
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        finally:
            try:
                fh.close()
            finally:
                self._fh = None


def try_nonblocking_exclusive_lock(path: Path) -> bool:
    """
    Attempt to acquire an exclusive, non-blocking lock on `path`.
    Returns True if lock acquired (i.e., no one holds it), False if already locked.
    """
    fh: IO[bytes] = open(path, "a+b")  # noqa: SIM115
    try:
        if IS_WIN and MSVCRT is not None:
            try:
                MSVCRT.locking(fh.fileno(), MSVCRT.LK_NBLCK, 1)
                MSVCRT.locking(fh.fileno(), MSVCRT.LK_UNLCK, 1)
                return True
            except Exception:
                return False
        else:
            import fcntl
            try:
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
                return True
            except BlockingIOError:
                return False
    finally:
        with suppress(Exception):
            fh.close()
