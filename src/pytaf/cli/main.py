from __future__ import annotations

import typer
from rich.console import Console

from pytaf.cli import init as init_mod

# Force group semantics and show help when no args are passed
app = typer.Typer(add_completion=False, no_args_is_help=True)
console = Console()


# 👇 NEW: dummy callback to force Typer to require explicit subcommands even if only one exists
@app.callback()  # type: ignore[misc]
def _root_callback() -> None:
    """
    Root command group for PyTAF.
    This exists to force 'group' semantics so 'pytaf init' works even if 'init' is
    currently the only subcommand.
    """
    # Intentionally no body; do not print from here to keep help clean.
    return


@app.command("init")  # type: ignore[misc]
def cmd_init(
    non_interactive: bool = typer.Option(
        False, "--non-interactive", help="Write bench.local.toml without prompts"
    ),
) -> None:
    init_mod.run(non_interactive=non_interactive)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
