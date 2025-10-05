from __future__ import annotations

import errno
import os
from pathlib import Path
import tomllib
from typing import Annotated, Any

import typer

from pytaf.run.runner import run as run_cmd
from pytaf.util.cloud_paths import ensure_local_results_root
from pytaf.util.fs import scan_stale_tmps

app = typer.Typer(add_completion=False)


@app.callback(invoke_without_command=True)
def run_root(
    bench: Annotated[Path, typer.Option("--bench", help="Bench TOML path")] = Path("bench/bench.local.toml"),
    acknowledge_stale: Annotated[
        bool, typer.Option("--acknowledge-stale", help="Proceed if stale temp files exist in results root")
    ] = False,
) -> None:
    """
    Run the Phase 1 echo vertical slice and emit durable artifacts.
    """
    try:
        with bench.open("rb") as f:
            cfg = tomllib.load(f)
    except Exception as e:
        typer.echo(f"ConfigError(22): {e}")
        raise typer.Exit(22) from e

    if "results" not in cfg or "root" not in cfg["results"]:
        typer.echo("ConfigError(22): missing [results].root")
        raise typer.Exit(22)

    base = bench.parent.resolve()
    declared_root = Path(cfg["results"]["root"])
    resolved_declared = (declared_root if declared_root.is_absolute() else (base / declared_root)).resolve()

    # Cloud-path relocation (name-based heuristics).
    resolved_root, relocated_cloud, relto_cloud, cloud_detected = ensure_local_results_root(resolved_declared)
    banner_shown = False
    relocation_path = ""
    if relocated_cloud:
        typer.echo(f"RELOCATED: results root moved from cloud path to {relto_cloud}")
        banner_shown = True
        relocation_path = str(relto_cloud)

    # Stale temp gate.
    stale = scan_stale_tmps(resolved_root)
    if stale and not acknowledge_stale:
        typer.echo("Stale temporary files detected in results root:")
        for p in stale[:20]:
            typer.echo(f"  - {p.name}")
        typer.echo("Refusing to run. Re-run with --acknowledge-stale to proceed.")
        raise typer.Exit(28)

    # Writability probe; on denial relocate to a machine-local cache.
    relocated_runtime = False
    permission_denied_relocated = False
    if not os.access(resolved_root, os.W_OK):
        try:
            probedir = resolved_root / "_probe"
            probedir.mkdir(exist_ok=True)
            testfile = probedir / "write_test.tmp"
            testfile.write_text("ok", encoding="utf-8")
            testfile.unlink(missing_ok=True)
            probedir.rmdir()
        except (PermissionError, OSError) as e:
            if isinstance(e, PermissionError) or getattr(e, "errno", None) in (
                errno.EACCES,
                errno.EPERM,
            ):
                if os.name == "nt":
                    relto = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "PyTAF" / "cache"
                else:
                    relto = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "pytaf"
                relto.mkdir(parents=True, exist_ok=True)
                typer.echo(f"RELOCATED: results root redirected to {relto}")
                banner_shown = True
                resolved_root = relto
                relocated_runtime = True
                permission_denied_relocated = True
                relocation_path = str(relto)
            else:
                typer.echo(f"TransportError(23): write probe failed: {e}")
                raise typer.Exit(23) from e

    cfg["results"]["root"] = str(resolved_root)

    meta: dict[str, Any] = {
        "relocated": bool(relocated_cloud or relocated_runtime),
        "relocation_path": relocation_path,
        "banner_shown": banner_shown,
        "stale_acknowledged": bool(acknowledge_stale),
        "cloud_path_detected": bool(cloud_detected),
        "permission_denied_relocated": bool(permission_denied_relocated),
    }

    code = run_cmd(resolved_root, cfg, meta)
    raise typer.Exit(code)


if __name__ == "__main__":
    # Allow: python -m pytaf.cli.run
    app()