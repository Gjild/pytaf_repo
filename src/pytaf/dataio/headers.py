from __future__ import annotations
from pathlib import Path
import json, platform, time, os
from .win_durability import flush_dir_anchor_if_windows
from .durability import atomic_open

def write_headers(run_dir: Path, bench_cfg: dict, *, ipc_version: int, epoch_id: int, ipc_handshake_ok: bool) -> None:
    hdr = {
        "schema": "results.header.v1",
        "run_uuid": run_dir.name,
        "bench_id": bench_cfg.get("bench_id", ""),
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "os": platform.platform(),
        "python": platform.python_version(),
        "shell_hint": _shell_hint(),
        "ipc_version": int(ipc_version),
        "epoch_id": int(epoch_id),
        "ipc_handshake_ok": bool(ipc_handshake_ok),
        "relocation_banner": bench_cfg.get("relocation_banner", False),
    }
    p = run_dir / "results.header.json"
    with atomic_open(p, "wb") as f:
        f.write(json.dumps(hdr, indent=2).encode("utf-8"))
    flush_dir_anchor_if_windows(run_dir)

def _shell_hint() -> str:
    return (platform.system() + " " + (os.environ.get("SHELL") or os.environ.get("ComSpec") or "")).strip()
