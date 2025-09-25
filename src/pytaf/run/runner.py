from __future__ import annotations

from contextlib import suppress
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from typing import Any
import uuid

from pytaf.broker import ipc
from pytaf.broker.ipc import now_mono_ns
from pytaf.broker.pidfile import remove_pidfile, write_pidfile
from pytaf.dataio import headers, layout, manifest
from pytaf.dataio.export_csv import CsvDual
from pytaf.dataio.results_jsonl import ResultsWriter
from pytaf.dataio.trace_raw_jsonl import TraceWriter

IS_WIN = (os.name == "nt")

def _make_run_dir(root: Path) -> Path:
    run_id = uuid.uuid4().hex[:12]
    stamp = time.strftime("%Y%m%d_%H%M%S")
    run_dir = root / f"run_{stamp}_{run_id}"
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_dir


def _is_windows_reparse_point(path: Path) -> bool:
    if not IS_WIN or not path.exists():
        return False
    try:
        out = subprocess.run(
            ["cmd", "/c", "fsutil", "reparsepoint", "query", str(path)],
            capture_output=True,
            text=True,
        )
        return out.returncode == 0
    except Exception:
        return False


def _latest_link(root: Path, run_dir: Path) -> tuple[bool, str]:
    tgt = root / "latest"
    strategy = "none"
    created = False
    if IS_WIN:
        if tgt.exists() and _is_windows_reparse_point(tgt):
            with suppress(Exception):
                subprocess.run(
                    ["cmd", "/c", "rmdir", str(tgt)],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
        if not tgt.exists():
            try:
                subprocess.run(
                    ["cmd", "/c", "mklink", "/J", str(tgt), str(run_dir)],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                strategy = "junction"
                created = True
            except Exception:
                (root / "LATEST.txt").write_text(str(run_dir), encoding="utf-8")
                strategy = "file"
                created = True
        else:
            (root / "LATEST.txt").write_text(str(run_dir), encoding="utf-8")
            strategy = "file"
            created = True
    else:
        with suppress(Exception):
            if tgt.exists() or tgt.is_symlink():
                tgt.unlink()
        try:
            os.symlink(run_dir.name, tgt, target_is_directory=True)
            strategy = "symlink"
            created = True
        except Exception:
            (root / "LATEST.txt").write_text(str(run_dir.name), encoding="utf-8")
            strategy = "file"
            created = True
    return created, strategy


def _spawn_broker(env: dict[str, str]) -> tuple[subprocess.Popen[bytes], object | None, bool]:
    creationflags = 0
    job = None
    stderr = None if os.environ.get("PYTAF_DEBUG") == "1" else subprocess.DEVNULL
    attached = False
    if IS_WIN:
        from pytaf.broker.jobobjects_win import (
            CREATE_NEW_PROCESS_GROUP,
            assign_process,
            create_kill_on_close_job,
        )
        creationflags = CREATE_NEW_PROCESS_GROUP
        proc = subprocess.Popen(
            [sys.executable, "-m", "pytaf.broker"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=stderr,
            creationflags=creationflags,
            env=env,
            text=False,
        )
        try:
            job = create_kill_on_close_job()
            handle = getattr(proc, "_handle", None)
            if handle is not None:
                assign_process(job, int(handle))
                attached = True
        except Exception:
            attached = False
        return proc, job, attached
    else:
        proc = subprocess.Popen(
            [sys.executable, "-m", "pytaf.broker"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=stderr,
            env=env,
            text=False,
        )
        return proc, None, True


def run(
    resolved_results_root: Path, bench_cfg: dict[str, Any], relocation_meta: dict[str, Any]
) -> int:
    run_dir = _make_run_dir(resolved_results_root)
    created, latest_strategy = _latest_link(resolved_results_root, run_dir)

    broker_lock_path = str(run_dir / "broker.lock")

    proc: subprocess.Popen[bytes] | None = None
    job: object | None = None
    job_attached = False
    termination_path = "unknown"
    try:
        env = dict(os.environ)
        env["PYTAF_BROKER_LOCK"] = broker_lock_path

        proc, job, job_attached = _spawn_broker(env)
        assert proc is not None and proc.stdin and proc.stdout
        w_parent = proc.stdin.fileno()
        r_parent = proc.stdout.fileno()

        ipc.write_msg(w_parent, {"op": "ping", "epoch_id": 0, "op_id": 1})
        ping = ipc.read_msg(r_parent)
        epoch_id = int(ping.get("epoch_id", 0))
        ipc_version = int(ping.get("ipc_version", 1))
        broker_diag: dict[str, Any] = ping.get("diag") or {}
        broker_lock_was_held = bool(broker_diag.get("lock_was_held", True))
        ipc_handshake_ok = bool(ping.get("ok", True) if isinstance(ping, dict) else True)

        headers.write_headers(
            run_dir,
            bench_cfg,
            ipc_version=ipc_version,
            epoch_id=epoch_id,
            ipc_handshake_ok=ipc_handshake_ok,
        )

        bulk_chunk_bytes = int(os.environ.get("PYTAF_BULK_CHUNK", "16384"))
        ipc_max_body_bytes = int(os.environ.get("PYTAF_IPC_MAX_BODY", "8388608"))
        echo_base_latency_ms = int(os.environ.get("PYTAF_ECHO_BASE_LAT_MS", "1"))
        echo_size_kib_cap = int(os.environ.get("PYTAF_ECHO_SIZE_KIB_CAP", "100"))
        trace_inline_max_bytes = int(os.environ.get("PYTAF_TRACE_INLINE_MAX", "256"))

        _ = write_pidfile(run_uuid=run_dir.name, pid=proc.pid, dir_=run_dir)

        uri = "pytaf+echo://local"
        ipc.write_msg(
            w_parent,
            {"op": "open", "epoch_id": epoch_id, "op_id": 2, "resource": uri, "lane": "control"},
        )
        _ = ipc.read_msg(r_parent)

        bulk_payload = b"x" * (64 * 1024)
        try:
            ipc.write_msg(
                w_parent,
                {
                    "op": "xact",
                    "epoch_id": epoch_id,
                    "op_id": 3,
                    "resource": uri,
                    "lane": "bulk",
                    "payload": bulk_payload,
                },
            )
        except ValueError:
            print("IPCBodyTooLarge(24): bulk payload exceeded PYTAF_IPC_MAX_BODY", file=sys.stderr)
            _terminate_broker(proc, job)
            remove_pidfile(run_dir)
            layout.write_layout(run_dir)
            return 24

        ipc.write_msg(
            w_parent,
            {
                "op": "xact",
                "epoch_id": epoch_id,
                "op_id": 4,
                "resource": uri,
                "lane": "control",
                "payload": b"*IDN?",
            },
        )
        ipc.write_msg(
            w_parent,
            {
                "op": "xact",
                "epoch_id": epoch_id,
                "op_id": 7,
                "resource": uri,
                "lane": "control",
                "payload": b"*IDN?",
            },
        )

        ack_a = ipc.read_msg(r_parent)
        ack_b = ipc.read_msg(r_parent)
        ack_c = ipc.read_msg(r_parent)
        ack_ids = [
            int(ack_a.get("op_id", 0)),
            int(ack_b.get("op_id", 0)),
            int(ack_c.get("op_id", 0)),
        ]
        ack_ids_no_open = ack_ids[:]

        ipc.write_msg(
            w_parent,
            {"op": "close", "epoch_id": epoch_id, "op_id": 5, "resource": uri, "lane": "control"},
        )
        _ = ipc.read_msg(r_parent)

        rw = ResultsWriter(run_dir)
        cw = CsvDual(run_dir)
        tw = TraceWriter(run_dir)
        ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        control_preempted_bulk = 1 if (ack_ids[0] in (4, 7) and ack_ids[2] == 3) else 0

        rw.emit({"name": "probe_ok", "value": 1, "unit": "", "timestamp": ts})
        rw.emit(
            {"name": "ack_order_1", "value": float(ack_ids[0] or 0), "unit": "", "timestamp": ts}
        )
        rw.emit(
            {"name": "ack_order_2", "value": float(ack_ids[1] or 0), "unit": "", "timestamp": ts}
        )
        rw.emit(
            {"name": "ack_order_3", "value": float(ack_ids[2] or 0), "unit": "", "timestamp": ts}
        )
        rw.emit(
            {
                "name": "control_preempted_bulk",
                "value": float(control_preempted_bulk),
                "unit": "",
                "timestamp": ts,
            }
        )

        # Determine first control payload, ensure type is bytes
        _first = ack_a if ack_ids[0] in (4, 7) else (ack_b if ack_ids[1] in (4, 7) else ack_c)
        raw_payload = _first.get("payload")
        first_control_payload: bytes = (
            raw_payload if isinstance(raw_payload, bytes) else bytes(raw_payload or b"")
        )
        tw.tx(now_mono_ns(), uri, b"*IDN?")
        tw.rx(now_mono_ns(), uri, first_control_payload)
        large_demo = b"A" * 1024
        tw.tx(now_mono_ns(), uri, large_demo)
        tw.rx(now_mono_ns(), uri, large_demo)
        cw.row("probe_ok", 1.0, "", ts)
        rw.close()
        cw.close()
        tw.close()

        exit_code, termination_path = _ladder_terminate(proc, job)
        clean_exit = exit_code == 0

        if clean_exit:
            remove_pidfile(run_dir)

        manifest.write_manifest(
            run_dir,
            bench_cfg,
            broker_pid=proc.pid,
            relocated=bool(relocation_meta.get("relocated", False)),
            relocation_path=str(relocation_meta.get("relocation_path", "")),
            results_root_resolved=str(resolved_results_root),
            relocation_banner_shown=bool(relocation_meta.get("banner_shown", False)),
            latest_strategy=latest_strategy,
            latest_created=created,
            job_object_attached=bool(job_attached),
            ipc_version=ipc_version,
            epoch_id=epoch_id,
            ipc_max_body_bytes=ipc_max_body_bytes,
            bulk_chunk_bytes=bulk_chunk_bytes,
            stale_acknowledged=bool(relocation_meta.get("stale_acknowledged", False)),
            cloud_path_detected=bool(relocation_meta.get("cloud_path_detected", False)),
            permission_denied_relocated=bool(
                relocation_meta.get("permission_denied_relocated", False)
            ),
            parent_pid=os.getpid(),
            shell_hint=_shell_hint_for_manifest(),
            echo_base_latency_ms=echo_base_latency_ms,
            echo_size_kib_cap=echo_size_kib_cap,
            trace_inline_max_bytes=trace_inline_max_bytes,
            clean_exit=clean_exit,
            ack_order=[int(x or 0) for x in ack_ids],
            ack_order_no_open=[int(x or 0) for x in ack_ids_no_open],
            broker_lock_path=broker_lock_path,
            broker_lock_was_held=bool(broker_lock_was_held),
            termination_path=termination_path,
            ipc_handshake_ok=ipc_handshake_ok,
            broker_diag=broker_diag,
        )

        layout.write_layout(run_dir)

        ok = (
            (ack_ids[0] in (4, 7))
            and (ack_ids[1] in (4, 7))
            and (ack_ids[2] == 3)
            and (ack_ids[0] == 4)
        )
        return (0 if ok else 1) if clean_exit else exit_code
    finally:
        if IS_WIN and job is not None:
            try:
                from pytaf.broker.jobobjects_win import close_handle

                close_handle(job)
            except Exception:
                pass


def _shell_hint_for_manifest() -> str:
    return (os.name + " " + (os.environ.get("SHELL") or os.environ.get("COMSPEC") or "")).strip()


def _ladder_terminate(proc: subprocess.Popen[bytes], job: object | None) -> tuple[int, str]:
    try:
        proc.wait(timeout=1.5)
        return proc.returncode or 0, "wait"
    except Exception:
        pass

    if IS_WIN:
        try:
            proc.send_signal(signal.CTRL_BREAK_EVENT)  # type: ignore[attr-defined]
            proc.wait(timeout=2.5)
            return proc.returncode or 0, "ctrl_break"
        except Exception:
            pass
        try:
            if job is not None:
                from pytaf.broker.jobobjects_win import terminate_job

                terminate_job(job, 1)
                proc.wait(timeout=3)
                return proc.returncode or 1, "job_kill"
        except Exception:
            pass
        proc.kill()
        proc.wait(timeout=3)
        return proc.returncode or 1, "kill"
    else:
        for sig, to, name in ((signal.SIGINT, 2.5, "sigint"), (signal.SIGTERM, 1.5, "sigterm")):
            try:
                proc.send_signal(sig)
                proc.wait(timeout=to)
                return proc.returncode or 0, name
            except Exception:
                pass
        proc.kill()
        proc.wait(timeout=3)
        return proc.returncode or 1, "sigkill"


def _terminate_broker(proc: subprocess.Popen[bytes], job: object | None) -> None:
    try:
        proc.terminate()
        proc.wait(timeout=2)
    except Exception:
        try:
            if IS_WIN and job is not None:
                from pytaf.broker.jobobjects_win import terminate_job

                terminate_job(job, 1)
                proc.wait(timeout=2)
            else:
                proc.kill()
                proc.wait(timeout=2)
        except Exception:
            pass
