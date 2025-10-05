from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

app = typer.Typer(add_completion=False)


_TEMPLATE = (
    'schema_version="bench.v1"\n'
    "[results]\n"
    'root="results"\n'
)


@app.callback(invoke_without_command=True)
def init_root(
    non_interactive: Annotated[
        bool, typer.Option("--non-interactive", help="Write defaults without prompts")
    ] = False,
    bench_dir: Annotated[Path, typer.Option("--bench-dir", help="Directory to create bench files")] = Path("bench"),
) -> None:
    """
    Initialize a bench directory with a minimal local config.
    """
    bench_dir.mkdir(parents=True, exist_ok=True)
    (bench_dir / "cal").mkdir(exist_ok=True)
    target = bench_dir / "bench.local.toml"

    if target.exists() and not non_interactive:
        typer.echo(f"{target} already exists. Use --non-interactive to overwrite.")
        raise typer.Exit(0)

    target.write_text(_TEMPLATE, encoding="utf-8")
    typer.echo(f"Wrote {target}")


if __name__ == "__main__":
    # Allow: python -m pytaf.cli.init
    app()
