from __future__ import annotations

from pathlib import Path

import typer

app = typer.Typer(add_completion=False)

_TEMPLATE = (
    'schema_version="bench.v1"\n'
    "[results]\n"
    'root="results"\n'
)

@app.callback()
def init_root(
    non_interactive: bool = typer.Option(False, "--non-interactive", help="Write defaults without prompts"),
    bench_dir: Path = typer.Option(Path("bench"), "--bench-dir", help="Directory to create bench files"),
) -> None:
    """
    Root command so `pytaf init --non-interactive` and `python -m pytaf.cli.init --non-interactive` both work.
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
    app()
