import os

from typer.testing import CliRunner

from pytaf.cli.main import app


def test_cli_help_displays() -> None:
    r = CliRunner().invoke(app, ["--help"])
    assert r.exit_code == 0
    assert "init" in r.stdout


def test_init_creates_bench_and_cal() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem():
        r = runner.invoke(app, ["init", "--non-interactive"])
        assert r.exit_code == 0
        assert os.path.exists("bench/bench.local.toml")
        assert os.path.isdir("bench/cal")
