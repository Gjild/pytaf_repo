from __future__ import annotations
import os
from pathlib import Path

IS_WIN = (os.name == "nt")

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
        self._fh = None

    @property
    def path(self) -> Path:
        return self._path

    def acquire_exclusive(self) -> None:
        if self._fh is not None:
            return
        self._fh = open(self._path, "a+b")
        try:
            if IS_WIN:
                import msvcrt
                try:
                    msvcrt.locking(self._fh.fileno(), msvcrt.LK_NBLCK, 1)
                except OSError:
                    msvcrt.locking(self._fh.fileno(), msvcrt.LK_LOCK, 1)
                    msvcrt.locking(self._fh.fileno(), msvcrt.LK_UNLCK, 1)
                    msvcrt.locking(self._fh.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self._fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except Exception as e:
            try:
                self._fh.close()
            except Exception:
                pass
            self._fh = None
            raise e

    def release(self) -> None:
        if self._fh is None:
            return
        try:
            if IS_WIN:
                import msvcrt
                try:
                    msvcrt.locking(self._fh.fileno(), msvcrt.LK_UNLCK, 1)
                except Exception:
                    pass
            else:
                import fcntl
                try:
                    fcntl.flock(self._fh.fileno(), fcntl.LOCK_UN)
                except Exception:
                    pass
        finally:
            try:
                self._fh.close()
            except Exception:
                pass
            self._fh = None

def try_nonblocking_exclusive_lock(path: Path) -> bool:
    """
    Attempt to acquire an exclusive, non-blocking lock on `path`.
    Returns True if lock acquired (i.e., no one holds it), False if already locked.
    """
    fh = open(path, "a+b")
    try:
        if IS_WIN:
            import msvcrt
            try:
                msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
                msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
                fh.close()
                return True
            except OSError:
                fh.close()
                return False
        else:
            import fcntl
            try:
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
                fh.close()
                return True
            except BlockingIOError:
                fh.close()
                return False
    except Exception:
        try:
            fh.close()
        except Exception:
            pass
        return False
