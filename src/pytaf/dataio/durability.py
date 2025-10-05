from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager, suppress
import os
from pathlib import Path
from typing import IO, Any


@contextmanager
def atomic_open(path: Path, mode: str = "wb") -> Generator[IO[Any], None, None]:
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        with open(tmp, mode) as f:
            yield f
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        with suppress(Exception):
            dirfd = os.open(os.fspath(path.parent), os.O_DIRECTORY)
            os.fsync(dirfd)
            os.close(dirfd)
    finally:
        with suppress(Exception):
            tmp.unlink(missing_ok=True)