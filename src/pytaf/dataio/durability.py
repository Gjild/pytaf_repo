from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager, suppress
import os
from pathlib import Path
from typing import IO


@contextmanager
def atomic_open(path: Path, mode: str = "wb") -> Iterator[IO[bytes]]:
    tmp = path.with_suffix(path.suffix + ".tmp")
    # Keep file descriptor open via context manager
    with open(tmp, mode) as f:
        try:
            yield f
            f.flush()
            os.fsync(f.fileno())
        finally:
            # The replace should only happen on successful writes (i.e., after yield)
            pass
    os.replace(tmp, path)
    with suppress(Exception):
        dirfd = os.open(os.fspath(path.parent), os.O_DIRECTORY)
        try:
            os.fsync(dirfd)
        finally:
            os.close(dirfd)
    with suppress(Exception):
        tmp.unlink(missing_ok=True)
