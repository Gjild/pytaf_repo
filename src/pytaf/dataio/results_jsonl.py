from __future__ import annotations

from contextlib import ExitStack
import os
from pathlib import Path
from typing import Any

import msgspec

from .win_durability import flush_dir_anchor_if_windows


class ResultsWriter:
    """
    Persistent JSONL writer. File handle is intentionally kept open for the
    lifetime of the writer; managed by ExitStack. The open() call is annotated.
    """
    def __init__(self, root: Path):
        self._enc = msgspec.json.Encoder()
        self._path = root / "results.v1.jsonl"
        self._stack = ExitStack()
        self._f = self._stack.enter_context(  
            open(self._path, "wb", buffering=0) # noqa: SIM115
        )

    def emit(self, row: dict[str, Any]) -> None:
        self._f.write(self._enc.encode(row))
        self._f.write(b"\n")
        self._f.flush()

    def close(self) -> None:
        self._f.flush()
        os.fsync(self._f.fileno())
        self._stack.close()
        flush_dir_anchor_if_windows(self._path.parent)
