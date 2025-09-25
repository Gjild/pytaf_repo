from __future__ import annotations

import typer

from pytaf.cli import init as init_mod, kill as kill_mod, run as run_mod, version as version_mod

app = typer.Typer(no_args_is_help=True, add_completion=False)

@app.callback()
def _root() -> None:
    return None

app.add_typer(init_mod.app, name="init")
app.add_typer(run_mod.app, name="run")
app.add_typer(kill_mod.app, name="kill")
app.command("version")(version_mod.show_version)

def main() -> None:
    app()
