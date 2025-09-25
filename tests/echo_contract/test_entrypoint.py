from importlib.metadata import entry_points


def test_console_script_registered() -> None:
    eps = entry_points(group="console_scripts")
    assert any(ep.name == "pytaf" for ep in eps)
