from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .durability import atomic_open
from .win_durability import flush_dir_anchor_if_windows


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_layout(run_dir: Path) -> None:
    files = []
    for p in sorted(run_dir.rglob("*")):
        if p.is_file():
            files.append(
                {
                    "path": str(p.relative_to(run_dir)),
                    "bytes": p.stat().st_size,
                    "sha256": _sha256(p),
                }
            )
    out = run_dir / "layout.v1.json"
    with atomic_open(out, "wb") as f:
        f.write(json.dumps(files, indent=2).encode("utf-8"))
    flush_dir_anchor_if_windows(run_dir)
