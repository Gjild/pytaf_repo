import pytaf


def test_version_present() -> None:
    assert hasattr(pytaf, "__version__")
