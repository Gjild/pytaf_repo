import nox


@nox.session(venv_backend="none")  # type: ignore[misc]
def tests(session: nox.Session) -> None:
    session.run("uv", "run", "pytest", "-q", external=True)


@nox.session(venv_backend="none")  # type: ignore[misc]
def lint(session: nox.Session) -> None:
    session.run("uv", "run", "ruff", "check", "--fix", ".", external=True)
    session.run("uv", "run", "ruff", "format", "--check", ".", external=True)
    session.run("uv", "run", "mypy", "src", external=True)
