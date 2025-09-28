from __future__ import annotations
from pathlib import Path
from typing import List

def scan_stale_tmps(root: Path) -> List[Path]:
    """
    Shallow sweeps of root + common Phase 1 subdirs.
    """
    patterns = [
        "*.tmp",
        "*.partial",
        "results.v1.jsonl.tmp",
        "trace.raw.v1.jsonl.tmp",
        "manifest.v1.json.tmp",
        "layout.v1.json.tmp",
        "data.excel.csv.tmp",
        "data.raw.csv.tmp",
    ]
    found: list[Path] = []
    for pat in patterns:
        found.extend(root.glob(pat))
    for sub, pats in (("export", ["*.tmp","data.excel.csv.tmp","data.raw.csv.tmp"]),
                      ("trace_blobs", ["*.partial","*.tmp"])):
        d = root / sub
        if d.exists():
            for pat in pats:
                found.extend(d.glob(pat))
    return found
