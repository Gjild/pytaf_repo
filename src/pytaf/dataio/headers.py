from __future__ import annotations

import json
import os
from pathlib import Path
import platform
import time
from typing import Any

from .durability import atomic_open
from .win_durability import flush_dir_anchor_if_windows


def write_headers(
    run_dir: Path,
    bench_cfg: dict[str, Any],
    *,
    ipc_version: int,
    epoch_id: int,
    ipc_handshake_ok: bool | None = None,  # NEW: optional flag
) -> None:
    hdr: dict[str, Any] = {
        "schema": "results.header.v1",
        "run_uuid": run_dir.name,
        "bench_id": str(bench_cfg.get("bench_id", "")),
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "os": platform.platform(),
        "python": platform.python_version(),
        "shell_hint": _shell_hint(),
        "ipc_version": int(ipc_version),
        "epoch_id": int(epoch_id),
    }
    if ipc_handshake_ok is not None:
        hdr["ipc_handshake_ok"] = bool(ipc_handshake_ok)

    p = run_dir / "results.header.json"
    with atomic_open(p, "wb") as f:
        f.write(json.dumps(hdr, indent=2).encode("utf-8"))
    flush_dir_anchor_if_windows(run_dir)

def _shell_hint() -> str:
    # COMSPEC is the standard env var name; SHELL on POSIX.
    return (platform.system() + " " + (os.environ.get("SHELL") or os.environ.get("COMSPEC") or "")).strip()
