"""
Nox sessions for pokerena.

Run a single session:
    uv run nox -p 3.11 -s <session>

Run all sessions:
    uv run nox -p 3.11

Sessions
--------
pre-commit  -- run all pre-commit hooks against every file
fmt         -- check formatting (ruff format --check) and import order
lint        -- ruff lint check
tests       -- pytest without coverage (fast feedback)
coverage    -- pytest with coverage enforcement (fail_under=80)
"""

import nox

# Pin to 3.11 -- never run a matrix accidentally.
nox.options.sessions = ["pre-commit", "fmt", "lint", "tests", "coverage", "docs"]
nox.options.default_venv_backend = "uv"

PYTHON = "3.13"
SRC = "pokerena"
TESTS = "tests"


def _install(session: nox.Session) -> None:
    """Install the package and its runtime deps into the session venv."""
    session.run("uv", "pip", "install", "-e", ".", external=True)


def _install_dev(session: nox.Session, *extras: str) -> None:
    """Install the package plus selected dev dependencies."""
    _install(session)
    if extras:
        session.run("uv", "pip", "install", *extras, external=True)


@nox.session(python=PYTHON, name="pre-commit")
def pre_commit(session: nox.Session) -> None:
    """Run all pre-commit hooks against every tracked file."""
    session.run("uv", "pip", "install", "pre-commit", external=True)
    session.run("pre-commit", "run", "--all-files", external=True)


@nox.session(python=PYTHON)
def fmt(session: nox.Session) -> None:
    """Check code formatting and import order (no auto-fix)."""
    _install_dev(session, "ruff")
    # Format check
    session.run("ruff", "format", "--check", SRC, TESTS)
    # Import-sort check
    session.run("ruff", "check", "--select", "I", SRC, TESTS)


@nox.session(python=PYTHON)
def lint(session: nox.Session) -> None:
    """Run ruff lint over all source and test files."""
    _install_dev(session, "ruff")
    session.run("ruff", "check", SRC, TESTS)


@nox.session(python=PYTHON)
def tests(session: nox.Session) -> None:
    """Run the test suite without coverage (fast feedback)."""
    _install_dev(session, "pytest")
    session.run(
        "pytest",
        "--tb=short",
        "-q",
        # Clear the --cov addopts from pyproject.toml so pytest-cov is not
        # required in this session and the run stays fast.
        "--override-ini=addopts=",
        TESTS,
    )


@nox.session(python=PYTHON)
def coverage(session: nox.Session) -> None:
    """Run pytest with coverage and enforce the fail_under threshold."""
    _install_dev(session, "pytest", "pytest-cov")
    session.run(
        "pytest",
        "--tb=short",
        "-q",
        TESTS,
    )


@nox.session(python=PYTHON)
def docs(session: nox.Session) -> None:
    """Build the MkDocs documentation site.

    Pass -- serve to start a local live-reload server instead of building:
        uv run nox -p 3.11 -s docs -- serve
    """
    _install_dev(session, "mkdocs", "mkdocs-material", "mkdocstrings[python]", "mkdocs-click")
    if session.posargs and session.posargs[0] == "serve":
        session.run("mkdocs", "serve")
    else:
        session.run("mkdocs", "build", "--strict")
