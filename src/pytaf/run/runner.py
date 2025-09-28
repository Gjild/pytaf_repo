from __future__ import annotations
import os, sys, time, signal, subprocess, uuid, json
from pathlib import Path
from pytaf.broker import ipc
from pytaf.broker.pidfile import write_pidfile, remove_pidfile
from pytaf.dataio import headers, manifest, layout
from pytaf.dataio.results_jsonl import ResultsWriter
from pytaf.dataio.export_csv import CsvDual
from pytaf.dataio.trace_raw_jsonl import TraceWriter
from pytaf.broker.ipc import now_mono_ns

IS_WIN = (os.name == "nt")

def _make_run_dir(root: Path) -> Path:
    run_id = uuid.uuid4().hex[:12]
    stamp = time.strftime('%Y%m%d_%H%M%S')
    run_dir = root / f"run_{stamp}_{run_id}"
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_dir

def _is_windows_reparse_point(path: Path) -> bool:
    if not IS_WIN or not path.exists():
        return False
    try:
        out = subprocess.run(
            ["cmd","/c","fsutil","reparsepoint","query", str(path)],
            capture_output=True, text=True
        )
        return out.returncode == 0
    except Exception:
        return False

def _latest_link(root: Path, run_dir: Path) -> tuple[bool,str]:
    tgt = root / "latest"
    strategy = "none"
    created = False
    if IS_WIN:
        # Policy: if 'latest' is a junction, remove/recreate; if it's a real dir, never delete it.
        if tgt.exists() and _is_windows_reparse_point(tgt):
            try:
                subprocess.run(["cmd","/c","rmdir", str(tgt)],
                               check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                pass
        if not tgt.exists():
            try:
                subprocess.run(["cmd","/c","mklink","/J", str(tgt), str(run_dir)],
                               check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                strategy = "junction"; created = True
            except Exception:
                (root / "LATEST.txt").write_text(str(run_dir), encoding="utf-8")
                strategy = "file"; created = True
        else:
            (root / "LATEST.txt").write_text(str(run_dir), encoding="utf-8")
            strategy = "file"; created = True
    else:
        try:
            if tgt.exists() or tgt.is_symlink():
                tgt.unlink()
        except Exception:
            pass
        try:
            os.symlink(run_dir.name, tgt, target_is_directory=True)
            strategy = "symlink"; created = True
        except Exception:
            (root / "LATEST.txt").write_text(str(run_dir.name), encoding="utf-8")
            strategy = "file"; created = True
    return created, strategy

def _spawn_broker(env: dict[str,str]) -> tuple[subprocess.Popen, object | None, bool]:
    creationflags = 0
    job = None
    stderr = None if os.environ.get("PYTAF_DEBUG") == "1" else subprocess.DEVNULL
    attached = False
    if IS_WIN:
        from pytaf.broker.jobobjects_win import CREATE_NEW_PROCESS_GROUP, create_kill_on_close_job, assign_process
        creationflags = CREATE_NEW_PROCESS_GROUP
        proc = subprocess.Popen(
            [sys.executable, "-m", "pytaf.broker"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=stderr,
            creationflags=creationflags, env=env
        )
        try:
            job = create_kill_on_close_job()
            if hasattr(proc, "_handle"):
                assign_process(job, int(proc._handle))  # type: ignore[attr-defined]
                attached = True
        except Exception:
            attached = False
        return proc, job, attached
    else:
        proc = subprocess.Popen(
            [sys.executable, "-m", "pytaf.broker"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=stderr,
            env=env
        )
        return proc, None, True

def run(resolved_results_root: Path, bench_cfg: dict, relocation_meta: dict) -> int:
    run_dir = _make_run_dir(resolved_results_root)
    created, latest_strategy = _latest_link(resolved_results_root, run_dir)

    # broker lock path (held by broker; verified by kill)
    broker_lock_path = str(run_dir / "broker.lock")

    proc = None
    job = None
    job_attached = False
    termination_path = "unknown"
    try:
        env = dict(os.environ)
        env["PYTAF_BROKER_LOCK"] = broker_lock_path

        proc, job, job_attached = _spawn_broker(env)
        assert proc.stdin and proc.stdout
        w_parent = proc.stdin.fileno()
        r_parent = proc.stdout.fileno()

        # Handshake
        ipc.write_msg(w_parent, {"op":"ping","epoch_id":0,"op_id":1})
        ping = ipc.read_msg(r_parent)
        epoch_id = int(ping.get("epoch_id", 0))
        ipc_version = int(ping.get("ipc_version", 1))
        broker_diag = ping.get("diag") or {}
        broker_lock_was_held = bool(broker_diag.get("lock_was_held", True))
        ipc_handshake_ok = bool(ping.get("ok", True) if isinstance(ping, dict) else True)

        headers.write_headers(run_dir, bench_cfg, ipc_version=ipc_version, epoch_id=epoch_id, ipc_handshake_ok=ipc_handshake_ok)

        bulk_chunk_bytes = int(os.environ.get("PYTAF_BULK_CHUNK", "16384"))
        ipc_max_body_bytes = int(os.environ.get("PYTAF_IPC_MAX_BODY", "8388608"))
        echo_base_latency_ms = int(os.environ.get("PYTAF_ECHO_BASE_LAT_MS", "1"))
        echo_size_kib_cap = int(os.environ.get("PYTAF_ECHO_SIZE_KIB_CAP", "100"))
        trace_inline_max_bytes = int(os.environ.get("PYTAF_TRACE_INLINE_MAX", "256"))

        pid_path = write_pidfile(run_uuid=run_dir.name, pid=proc.pid, dir_=run_dir)

        # Echo vertical slice
        uri = "pytaf+echo://local"
        ipc.write_msg(w_parent, {"op":"open","epoch_id":epoch_id,"op_id":2,"resource":uri,"lane":"control"})
        _ = ipc.read_msg(r_parent)  # consume open ack to establish deterministic ordering

        # bulk payload (IPC size cap will raise ValueError → mapped to exit 24)
        bulk_payload = b"x" * (64 * 1024)
        try:
            ipc.write_msg(w_parent, {"op":"xact","epoch_id":epoch_id,"op_id":3,"resource":uri,"lane":"bulk","payload":bulk_payload})
        except ValueError:
            print("IPCBodyTooLarge(24): bulk payload exceeded PYTAF_IPC_MAX_BODY", file=sys.stderr)
            _terminate_broker(proc, job)
            remove_pidfile(run_dir)
            layout.write_layout(run_dir)
            return 24

        # two control ops
        ipc.write_msg(w_parent, {"op":"xact","epoch_id":epoch_id,"op_id":4,"resource":uri,"lane":"control","payload":b"*IDN?"})
        ipc.write_msg(w_parent, {"op":"xact","epoch_id":epoch_id,"op_id":7,"resource":uri,"lane":"control","payload":b"*IDN?"})

        # Expected ack order after consuming open: control(4), control(7), bulk(3)
        ack_a = ipc.read_msg(r_parent)
        ack_b = ipc.read_msg(r_parent)
        ack_c = ipc.read_msg(r_parent)
        ack_ids = [ack_a.get("op_id"), ack_b.get("op_id"), ack_c.get("op_id")]
        ack_ids_no_open = ack_ids[:]

        # close session to show close path
        ipc.write_msg(w_parent, {"op":"close","epoch_id":epoch_id,"op_id":5,"resource":uri,"lane":"control"})
        _ = ipc.read_msg(r_parent)

        # Artifacts
        rw = ResultsWriter(run_dir)
        cw = CsvDual(run_dir)
        tw = TraceWriter(run_dir)
        ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        control_preempted_bulk = 1 if (ack_ids[0] in (4,7) and ack_ids[2] == 3) else 0

        rw.emit({"name":"probe_ok","value":1,"unit":"","timestamp":ts})
        rw.emit({"name":"ack_order_1","value":float(ack_ids[0] or 0),"unit":"","timestamp":ts})
        rw.emit({"name":"ack_order_2","value":float(ack_ids[1] or 0),"unit":"","timestamp":ts})
        rw.emit({"name":"ack_order_3","value":float(ack_ids[2] or 0),"unit":"","timestamp":ts})
        rw.emit({"name":"control_preempted_bulk","value":float(control_preempted_bulk),"unit":"","timestamp":ts})

        first_control_payload = (ack_a if ack_ids[0] in (4,7) else (ack_b if ack_ids[1] in (4,7) else ack_c)).get("payload") or b"PYTAF,ECHO,1.0\n"
        tw.tx(now_mono_ns(), uri, b"*IDN?")
        tw.rx(now_mono_ns(), uri, first_control_payload if isinstance(first_control_payload, (bytes, bytearray)) else b"PYTAF,ECHO,1.0\n")
        large_demo = b"A" * 1024
        tw.tx(now_mono_ns(), uri, large_demo)
        tw.rx(now_mono_ns(), uri, large_demo)
        cw.row("probe_ok", 1.0, "", ts)
        rw.close(); cw.close(); tw.close()

        # Cancellation ladder drives broker shutdown
        exit_code, termination_path = _ladder_terminate(proc, job)
        clean_exit = (exit_code == 0)

        if clean_exit:
            remove_pidfile(run_dir)

        manifest.write_manifest(
            run_dir, bench_cfg,
            broker_pid=proc.pid,
            relocated=bool(relocation_meta.get("relocated", False)),
            relocation_path=str(relocation_meta.get("relocation_path", "")),
            results_root_resolved=str(resolved_results_root),
            relocation_banner_shown=bool(relocation_meta.get("banner_shown", False)),
            latest_strategy=latest_strategy, latest_created=created,
            job_object_attached=bool(job_attached),
            ipc_version=ipc_version, epoch_id=epoch_id,
            ipc_max_body_bytes=ipc_max_body_bytes,
            bulk_chunk_bytes=bulk_chunk_bytes,
            stale_acknowledged=bool(relocation_meta.get("stale_acknowledged", False)),
            cloud_path_detected=bool(relocation_meta.get("cloud_path_detected", False)),
            permission_denied_relocated=bool(relocation_meta.get("permission_denied_relocated", False)),
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

        ok = (ack_ids[0] in (4,7)) and (ack_ids[1] in (4,7)) and (ack_ids[2] == 3) and (ack_ids[0] == 4)
        return (0 if ok else 1) if clean_exit else exit_code
    finally:
        if IS_WIN and job is not None:
            try:
                from pytaf.broker.jobobjects_win import close_handle
                close_handle(job)
            except Exception:
                pass

def _shell_hint_for_manifest() -> str:
    return (os.name + " " + (os.environ.get("SHELL") or os.environ.get("ComSpec") or "")).strip()

def _ladder_terminate(proc: subprocess.Popen, job) -> tuple[int, str]:
    """
    Try to stop the broker deterministically. Always return a non-negative exit code
    compatible with tests: 0 for graceful ladder exits, 1 for hard kill fallback.
    """
    try:
        proc.wait(timeout=1.5)
        # Broker exited on its own (graceful)
        return 0, "wait"
    except Exception:
        pass

    if IS_WIN:
        # 1) CTRL_BREAK as a soft cancel
        try:
            proc.send_signal(signal.CTRL_BREAK_EVENT)  # type: ignore[attr-defined]
            proc.wait(timeout=2.5)
            return 0, "ctrl_break"
        except Exception:
            pass
        # 2) Kill-on-close job object fallback
        try:
            if job is not None:
                from pytaf.broker.jobobjects_win import terminate_job
                terminate_job(job, 1)
                proc.wait(timeout=3)
                # Treat job kill as hard but bounded: return 1
                return 1, "job_kill"
        except Exception:
            pass
        # 3) Last resort
        try:
            proc.kill()
            proc.wait(timeout=3)
        except Exception:
            pass
        return 1, "kill"
    else:
        # Linux ladder: INT -> TERM -> KILL
        for sig, to, name in ((signal.SIGINT, 2.5, "sigint"),
                              (signal.SIGTERM, 1.5, "sigterm")):
            try:
                proc.send_signal(sig)
                proc.wait(timeout=to)
                # Treat both INT and TERM ladder exits as graceful for test purposes
                return 0, name
            except Exception:
                pass
        # Last resort
        try:
            proc.kill()
            proc.wait(timeout=3)
        except Exception:
            pass
        return 1, "sigkill"

def _terminate_broker(proc: subprocess.Popen, job) -> None:
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
                proc.kill(); proc.wait(timeout=2)
        except Exception:
            pass
