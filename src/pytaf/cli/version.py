from __future__ import annotations

import typer

from pytaf import __version__


def show_version() -> None:
    typer.echo(__version__)
