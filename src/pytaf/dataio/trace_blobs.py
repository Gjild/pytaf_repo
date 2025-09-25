from __future__ import annotations

import hashlib
from pathlib import Path

from .win_durability import flush_dir_anchor_if_windows


def put_blob(root: Path, data: bytes) -> tuple[str, Path]:
    h = hashlib.sha256(data).hexdigest()
    dir_ = root / "trace_blobs"
    dir_.mkdir(exist_ok=True)
    p = dir_ / f"{h}.bin"
    if not p.exists():
        p.write_bytes(data)
        flush_dir_anchor_if_windows(dir_)
    return h, p
