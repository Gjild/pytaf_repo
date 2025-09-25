from __future__ import annotations

import sys
from pathlib import Path

import tomli_w
from platformdirs import user_data_dir
from rich.console import Console

console = Console()


def _default_results_root() -> str:
    return str(Path(user_data_dir("pytaf", "rf_automation_team")).resolve())


TEMPLATE = {
    "schema_version": "bench.v1",
    "bench_id": "local_bench",
    "project": "scratch",
    "results": {
        "root": _default_results_root(),
        "excel_safe_csv": True,
    },
    "resources": {},
    "aliases": {},
}


def run(non_interactive: bool = False) -> None:
    bench_dir = Path("bench")
    bench_dir.mkdir(exist_ok=True, parents=True)
    path = bench_dir / "bench.local.toml"
    if path.exists():
        console.print(f"[yellow]bench.local.toml already exists at {path}[/yellow]")
        sys.exit(0)
    with path.open("wb") as f:
        tomli_w.dump(TEMPLATE, f)
    (bench_dir / "cal").mkdir(exist_ok=True)
    console.print(f"[green]Wrote {path} and created bench/cal/.[/green]")
