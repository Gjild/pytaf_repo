from __future__ import annotations

import json
from pathlib import Path
import time
from typing import Any

from .durability import atomic_open
from .win_durability import flush_dir_anchor_if_windows


def write_manifest(
    run_dir: Path,
    bench_cfg: dict[str, Any],
    *,
    broker_pid: int,
    relocated: bool,
    relocation_path: str,
    results_root_resolved: str,
    relocation_banner_shown: bool,
    latest_strategy: str,
    latest_created: bool,
    job_object_attached: bool,
    ipc_version: int,
    epoch_id: int,
    ipc_max_body_bytes: int,
    bulk_chunk_bytes: int,
    stale_acknowledged: bool,
    cloud_path_detected: bool,
    permission_denied_relocated: bool,
    parent_pid: int,
    shell_hint: str,
    echo_base_latency_ms: int,
    echo_size_kib_cap: int,
    trace_inline_max_bytes: int,
    clean_exit: bool,
    ack_order: list[int],
    ack_order_no_open: list[int],
    broker_lock_path: str,
    broker_lock_was_held: bool,
    termination_path: str,
    ipc_handshake_ok: bool,
    broker_diag: dict[str, Any],
) -> None:
    m: dict[str, Any] = {
        "schema": "manifest.v1",
        "run_uuid": run_dir.name,
        "bench_id": bench_cfg.get("bench_id", ""),
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "broker_pid": broker_pid,
        "parent_pid": parent_pid,
        "shell_hint": shell_hint,
        "relocated": bool(relocated),
        "relocation_path": relocation_path,
        "results_root_resolved": results_root_resolved,
        "relocation_banner_shown": relocation_banner_shown,
        "latest_link_created": latest_created,
        "latest_strategy": latest_strategy,
        "job_object_attached": bool(job_object_attached),
        "ipc_version": int(ipc_version),
        "epoch_id": int(epoch_id),
        "ipc_max_body_bytes": int(ipc_max_body_bytes),
        "bulk_chunk_bytes": int(bulk_chunk_bytes),
        "stale_acknowledged": bool(stale_acknowledged),
        "cloud_path_detected": bool(cloud_path_detected),
        "permission_denied_relocated": bool(permission_denied_relocated),
        "echo_base_latency_ms": int(echo_base_latency_ms),
        "echo_size_kib_cap": int(echo_size_kib_cap),
        "trace_inline_max_bytes": int(trace_inline_max_bytes),
        "clean_exit": bool(clean_exit),
        "ack_order": [int(x) for x in ack_order],
        "ack_order_no_open": [int(x) for x in ack_order_no_open],
        "broker_lock_path": broker_lock_path,
        "broker_lock_was_held": bool(broker_lock_was_held),
        "termination_path": termination_path,
        "ipc_handshake_ok": bool(ipc_handshake_ok),
        "broker_diag": broker_diag,
    }
    p = run_dir / "manifest.v1.json"
    with atomic_open(p, "wb") as f:
        f.write(json.dumps(m, indent=2).encode("utf-8"))
    flush_dir_anchor_if_windows(run_dir)
