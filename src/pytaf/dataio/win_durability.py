from __future__ import annotations

import os
from pathlib import Path

IS_WIN = os.name == "nt"


def flush_dir_anchor_if_windows(path: Path) -> None:
    if not IS_WIN:
        return
    try:
        anchor = path / ".dur_anchor"
        with open(anchor, "a+b") as f:
            f.seek(0, os.SEEK_SET)
            f.write(b"\x00")
            f.truncate(1)
            f.flush()
            os.fsync(f.fileno())
    except Exception:
        pass
