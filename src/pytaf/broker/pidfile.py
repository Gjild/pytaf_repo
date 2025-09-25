from __future__ import annotations

from contextlib import suppress
from pathlib import Path


def write_pidfile(run_uuid: str, pid: int, dir_: Path) -> Path:
    p = dir_ / f"{run_uuid}.pid"
    p.write_text(str(pid), encoding="utf-8")
    return p

def remove_pidfile(dir_: Path) -> None:
    for f in dir_.glob("*.pid"):
        with suppress(OSError):
            f.unlink()
