from __future__ import annotations
import os
from pathlib import Path
from typing import Any, Dict
import msgspec
from .win_durability import flush_dir_anchor_if_windows

class ResultsWriter:
    def __init__(self, root: Path):
        self._enc = msgspec.json.Encoder()
        self._path = root / "results.v1.jsonl"
        self._f = open(self._path, "wb", buffering=0)

    def emit(self, row: Dict[str, Any]) -> None:
        self._f.write(self._enc.encode(row)); self._f.write(b"\n")
        self._f.flush()

    def close(self) -> None:
        self._f.flush(); os.fsync(self._f.fileno()); self._f.close()
        flush_dir_anchor_if_windows(self._path.parent)
