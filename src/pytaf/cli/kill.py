from __future__ import annotations

import os
from pathlib import Path
import signal
from typing import Any

import typer

from pytaf.util.lockfile import try_nonblocking_exclusive_lock

app = typer.Typer(add_completion=False)

# ---- Typer option singletons to satisfy ruff B008
RUN_DIR_OPT = typer.Option(None, "--run-dir", exists=False, dir_okay=True, file_okay=False)
BENCH_OPT = typer.Option(None, "--bench", help="Bench TOML to resolve results root for --last-run")
LAST_RUN_OPT = typer.Option(False, "--last-run", help="Target the most recent run_* in results root")
# -------------------------------------------------

def _find_last_run(root: Path) -> Path | None:
    runs = [p for p in root.glob("run_*") if p.is_dir()]
    return max(runs, key=lambda p: p.stat().st_mtime) if runs else None

def _looks_like_broker_linux(pid: int) -> bool:
    try:
        cmdline = Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\x00", b" ").decode("utf-8", "replace")
        return "-m pytaf.broker" in cmdline
    except Exception:
        return False

def _looks_like_broker_windows(pid: int) -> bool:
    try:
        import ctypes as c
        import ctypes.wintypes as w
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        windll: Any = c.windll  # type: ignore[attr-defined]
        h = windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not h:
            return False
        try:
            size = w.DWORD(32767)
            buf = c.create_unicode_buffer(size.value)
            if not windll.kernel32.QueryFullProcessImageNameW(h, 0, buf, c.byref(size)):
                return False
            exe = buf.value.lower()
            return exe.endswith(("\\python.exe", "\\pythonw.exe"))
        finally:
            windll.kernel32.CloseHandle(h)
    except Exception:
        return False

def _send_ctrl_break_windows(pid: int) -> bool:
    try:
        os.kill(pid, signal.CTRL_BREAK_EVENT)  # type: ignore[attr-defined]
        return True
    except Exception:
        return False

@app.command()
def main(
    run_dir: Path | None = RUN_DIR_OPT,
    bench: Path | None = BENCH_OPT,
    last_run: bool = LAST_RUN_OPT,
) -> None:
    target: Path | None = None
    if run_dir:
        target = run_dir
    elif last_run:
        if not bench:
            typer.echo("ConfigError(22): --last-run requires --bench to resolve results root")
            raise typer.Exit(22)
        try:
            import tomllib
            with bench.open("rb") as f:
                cfg = tomllib.load(f)
        except Exception as e:
            typer.echo(f"ConfigError(22): {e}")
            raise typer.Exit(22) from e
        if "results" not in cfg or "root" not in cfg["results"]:
            typer.echo('ConfigError(22): missing [results].root')
            raise typer.Exit(22)
        base = bench.parent.resolve()
        declared_root = Path(cfg["results"]["root"])
        results_root = (declared_root if declared_root.is_absolute() else (base / declared_root)).resolve()
        target = _find_last_run(results_root)
        if not target:
            typer.echo("AbortBySignal(31): No runs found")
            raise typer.Exit(31)
    else:
        typer.echo("ConfigError(22): Provide --run-dir or --last-run with --bench")
        raise typer.Exit(22)

    if not target.exists():
        typer.echo("AbortBySignal(31): Run dir not found")
        raise typer.Exit(31)

    pidf = next(target.glob("*.pid"), None)
    pid_val: int | None = None
    if pidf:
        try:
            pid_val = int(pidf.read_text("utf-8").strip())
        except Exception as e:
            typer.echo(f"ConfigError(22): Bad pidfile: {e}")
            raise typer.Exit(22) from e
    else:
        man = target / "manifest.v1.json"
        if man.exists():
            try:
                import json
                pid_val = int(json.loads(man.read_text("utf-8")).get("broker_pid", 0))
            except Exception:
                pid_val = None

    if not pid_val or pid_val <= 0:
        typer.echo("AbortBySignal(31): No broker pid found")
        raise typer.Exit(31)

    lock_path = target / "broker.lock"
    if try_nonblocking_exclusive_lock(lock_path):
        typer.echo(
            f"RefusedByPolicy(34): Broker lock not held; refusing to signal. Lock checked at {lock_path}"
        )
        raise typer.Exit(34)

    looks_ok = _looks_like_broker_windows(pid_val) if os.name == "nt" else _looks_like_broker_linux(pid_val)
    if not looks_ok:
        typer.echo(
            f"Warning: PID {pid_val} did not match broker heuristic; proceeding due to valid lock {lock_path}."
        )

    try:
        if os.name == "nt":
            sent = _send_ctrl_break_windows(pid_val)
            if not sent:
                os.kill(pid_val, signal.SIGTERM)
            typer.echo(f"Sent CTRL_BREAK/TERM to broker pid {pid_val}")
        else:
            os.kill(pid_val, signal.SIGTERM)
            typer.echo(f"Sent TERM to broker pid {pid_val}")
    except Exception as e:
        typer.echo(f"TransportError(23): {e}")
        raise typer.Exit(23) from e