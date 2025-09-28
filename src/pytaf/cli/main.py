from __future__ import annotations
import typer

app = typer.Typer(no_args_is_help=True, add_completion=False)

@app.callback()
def _root() -> None:
    return None

from pytaf.cli import init as init_mod
from pytaf.cli import run as run_mod
from pytaf.cli import kill as kill_mod
from pytaf.cli import version as version_mod

app.add_typer(init_mod.app, name="init")
app.add_typer(run_mod.app, name="run")
app.add_typer(kill_mod.app, name="kill")
# Wire version as a direct command so `pytaf version` prints the version string.
app.command("version")(version_mod.show_version)

def main() -> None:
    app()
