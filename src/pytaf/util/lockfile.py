from __future__ import annotations

from contextlib import suppress
import os
from pathlib import Path
from typing import IO, Any

IS_WIN = os.name == "nt"


class BrokerLock:
    """
    Single-byte advisory lock held exclusively by the broker while alive.
    Presence == broker alive for kill safety checks.
    """

    def __init__(self, path: str):
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if not self._path.exists():
            self._path.write_bytes(b"")
        self._fh: IO[Any] | None = None

    @property
    def path(self) -> Path:
        return self._path

    def acquire_exclusive(self) -> None:
        if self._fh is not None:
            return
        self._fh = open(self._path, "a+b") # noqa: SIM115
        try:
            if IS_WIN:
                import msvcrt

                try:
                    msvcrt.locking(self._fh.fileno(), msvcrt.LK_NBLCK, 1)  # type: ignore[attr-defined]
                except OSError:
                    msvcrt.locking(self._fh.fileno(), msvcrt.LK_LOCK, 1)  # type: ignore[attr-defined]
                    msvcrt.locking(self._fh.fileno(), msvcrt.LK_UNLCK, 1)  # type: ignore[attr-defined]
                    msvcrt.locking(self._fh.fileno(), msvcrt.LK_NBLCK, 1)  # type: ignore[attr-defined]
            else:
                import fcntl

                fcntl.flock(self._fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except Exception as e:
            if self._fh:
                with suppress(Exception):
                    self._fh.close()
            self._fh = None
            raise e

    def release(self) -> None:
        if self._fh is None:
            return
        try:
            if IS_WIN:
                import msvcrt

                with suppress(Exception):
                    msvcrt.locking(self._fh.fileno(), msvcrt.LK_UNLCK, 1)  # type: ignore[attr-defined]
            else:
                import fcntl

                with suppress(Exception):
                    fcntl.flock(self._fh.fileno(), fcntl.LOCK_UN)
        finally:
            with suppress(Exception):
                self._fh.close()
            self._fh = None


def try_nonblocking_exclusive_lock(path: Path) -> bool:
    """
    Attempt to acquire an exclusive, non-blocking lock on `path`.
    Returns True if lock acquired (i.e., no one holds it), False if already locked.
    """
    try:
        with open(path, "a+b") as fh:
            if IS_WIN:
                import msvcrt

                try:
                    msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)  # type: ignore[attr-defined]
                    msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)  # type: ignore[attr-defined]
                    return True
                except OSError:
                    return False
            else:
                import fcntl

                try:
                    fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
                    return True
                except BlockingIOError:
                    return False
    except Exception:
        return False