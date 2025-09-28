from __future__ import annotations
import os
from contextlib import contextmanager
from pathlib import Path

@contextmanager
def atomic_open(path: Path, mode="wb"):
    tmp = path.with_suffix(path.suffix + ".tmp")
    f = open(tmp, mode)
    try:
        yield f
        f.flush(); os.fsync(f.fileno())
        os.replace(tmp, path)
        try:
            dirfd = os.open(os.fspath(path.parent), os.O_DIRECTORY)
            os.fsync(dirfd); os.close(dirfd)
        except Exception:
            pass
    finally:
        try: tmp.unlink(missing_ok=True)
        except Exception: pass
