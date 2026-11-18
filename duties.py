"""Duty tasks for the project."""

from __future__ import annotations

import os
import re
import sys
import tomllib
from pathlib import Path
from typing import TYPE_CHECKING

from duty import duty
from rich.console import Console

sys.path.append(str(Path(__file__).parent / "scripts"))
from dist_check import check_dists

if TYPE_CHECKING:
    from duty.context import Context


console = Console()
PYPROJECT = Path("pyproject.toml")
PY_SRC_PATHS = (Path(_) for _ in ("src/", "tests/", "duties.py", "scripts/") if Path(_).exists())
PY_SRC_LIST = tuple(str(_) for _ in PY_SRC_PATHS)
# ruff formats Python fences in Markdown, so format the same docs the prek ruff-format hook sees
FORMAT_LIST = (*PY_SRC_LIST, *(_ for _ in ("docs/", "README.md") if Path(_).exists()))
CI = os.environ.get("CI", "").strip().lower() in {"1", "true", "yes"}
PROJECT_ROOT = Path(__file__).parent
# A change to any of these can break every suite, since every CI job runs through them
SHARED = ("duties.py", ".github/actions/", "pyproject.toml", "uv.lock", ".python-version")
PY_SHARED = ("tests/conftest.py", "tests/__init__.py")
# What each test suite depends on. The gates and the CI `paths:` filters both come from this,
# and tests/tooling/test_workflows.py fails when the two disagree.
SUITES: dict[str, tuple[str, ...]] = {
    "core": (
        "src/gate_cache/",
        ":(exclude)src/gate_cache/dashboard/",
        ".pre-commit-hooks.yaml",
        "docs/reference/marker-format.md",
        "tests/core/",
        ".github/workflows/tests-core.yml",
        *PY_SHARED,
        *SHARED,
    ),
    "server": (
        "src/gate_cache/dashboard/",
        "src/gate_cache/stats/",
        "src/gate_cache/config.py",
        "src/gate_cache/console.py",
        "src/gate_cache/env.py",
        "src/gate_cache/__init__.py",
        "tests/server/",
        ".github/workflows/tests-server.yml",
        *PY_SHARED,
        *SHARED,
    ),
    # The Node version changes what the frontend gates run on, so it scopes them too
    "frontend": ("frontend/", ".node-version", ".github/workflows/tests-frontend.yml", *SHARED),
    # Tooling tests check the import boundary and the suite layout, so they read src/ and tests/
    "tooling": (
        "src/gate_cache/",
        "tests/",
        ".github/workflows/",
        "scripts/",
        ".pre-commit-config.yaml",
        "codecov.yml",
        *SHARED,
    ),
}
VERSION = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]["version"]


def strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences from a string.

    Args:
        text (str): String to remove ANSI escape sequences from.

    Returns:
        str: String without ANSI escape sequences.
    """
    ansi_chars = re.compile(r"(\x9B|\x1B\[)[0-?]*[ -\/]*[@-~]")

    # Replace [ with \[ so rich doesn't interpret output as style tags
    return ansi_chars.sub("", text).replace("[", r"\[")


def gated(name: str, cmd: list[str], paths: tuple[str, ...] = ()) -> list[str]:
    """Wrap a gate command in gate-cache so it skips on a tree where it already passed.

    Args:
        name (str): Marker name for the gate.
        cmd (list[str]): Command to run.
        paths (tuple[str, ...]): Pathspecs that scope the gate's tree; empty keys on the whole tree.

    Returns:
        list[str]: The command prefixed with the gate-cache invocation.
    """
    scope = [arg for path in paths for arg in ("--path", path)]
    return ["gate-cache", "--name", name, *scope, "--", *cmd]


def pyprefix(title: str) -> str:
    """Add a prefix to the title if CI is true.

    Returns:
        str: Title with prefix if CI is true.
    """
    if CI:
        prefix = f"(python{sys.version_info.major}.{sys.version_info.minor})"
        return f"{prefix:14}{title}"
    return title


@duty(silent=True)
def clean(ctx: Context) -> None:
    """Clean the project."""
    ctx.run("rm -rf .coverage*")
    ctx.run("rm -rf .cache")
    ctx.run("rm -rf build")
    ctx.run("rm -rf dist")
    ctx.run("rm -rf pip-wheel-metadata")
    ctx.run("find . -type d -name __pycache__ | xargs rm -rf")
    ctx.run("find . -name '.DS_Store' -delete")


@duty
def ruff(ctx: Context) -> None:
    """Check the code quality with ruff."""
    ctx.run(
        gated("ruff", ["ruff", "check", "--config", "pyproject.toml", "--no-fix", *PY_SRC_LIST]),
        title=pyprefix("code quality check"),
    )


@duty
def format(ctx: Context) -> None:  # noqa: A001
    """Format the code with ruff."""
    ctx.run(
        gated("format", ["ruff", "format", "--check", "--config", "pyproject.toml", *FORMAT_LIST]),
        title=pyprefix("code formatting"),
    )


@duty
def ty(ctx: Context) -> None:
    """Check the code with ty."""
    ctx.run(
        gated("ty", ["ty", "check", "src/", "tests/"]),
        title="ty check",
    )


@duty
def typos(ctx: Context) -> None:
    """Check the code with typos."""
    ctx.run(
        gated("typos", ["typos", "--config", ".typos.toml"]),
        title=pyprefix("typos check"),
    )


@duty(skip_if=CI, skip_reason="skip prek in CI environments")
def prek(ctx: Context) -> None:
    """Run prek hooks."""
    ctx.run(
        "PREK_SKIP=ty,pytest,ruff-check gate-cache --name prek -- prek run --all-files",
        title=pyprefix("prek hooks"),
    )


AGENT_GUIDE_PAGE = PROJECT_ROOT / "docs" / "reference" / "agent-guide.md"
# The site build reads these, plus the skill guide and version that the agent guide page renders
DOCS_PATHS = (
    "docs/",
    "zensical.toml",
    "src/gate_cache/agent/skill.md",
    "src/gate_cache/__init__.py",
    "duties.py",
)


def write_agent_guide() -> None:
    """Render the `gate-cache --skill` guide as a docs page, so the site shows what agents read."""
    from gate_cache import __version__
    from gate_cache.cli import agent_text

    text = agent_text("skill.md")
    if text.startswith("---\n"):
        text = text.split("\n---\n", 1)[1]
    body = re.sub(r"\A\s*# [^\n]*\n", "", text)
    header = (
        "---\nicon: lucide/bot-message-square\n---\n\n"
        "# Agent guide\n\n"
        "A coding agent reads this guide when it runs `gate-cache --skill`. The guide tells the "
        "agent what the messages of gate-cache mean, how to write and check a gate, and which "
        f"actions to leave to you. This copy matches gate-cache {__version__}.\n"
    )
    AGENT_GUIDE_PAGE.write_text(header + body, encoding="utf-8")


@duty
def docs_check(ctx: Context) -> None:
    """Build the documentation site in strict mode, so a broken link or page fails."""
    write_agent_guide()
    ctx.run(
        gated(
            "docs",
            ["uv", "run", "--group", "docs", "zensical", "build", "--strict", "--clean"],
            paths=DOCS_PATHS,
        ),
        title="docs build",
    )


@duty(pre=[ruff, format, ty, typos, prek, docs_check], capture=CI)
def lint(ctx: Context) -> None:
    """Run all linting duties."""


@duty(capture=CI)
def update(ctx: Context) -> None:
    """Update the project."""
    ctx.run(["uv", "lock", "--upgrade"], title="update uv lock")
    ctx.run(["uv", "sync"], title="update uv sync")
    ctx.run(["prek", "autoupdate"], title="prek autoupdate")
    ctx.run(["uvx", "uv-upx", "upgrade", "run"], title="uv-upx upgrade")


def _pytest_cmd(target: str, cov_config: str | None, *extra: str) -> list[str]:
    """Build the pytest command for a test target, with coverage when given a coverage config."""
    cmd = ["pytest", target, "-c", "pyproject.toml", "--color=yes"]
    if cov_config is not None:
        cmd += ["--cov", f"--cov-config={cov_config}", "--cov-report=xml", "--cov-report=term"]
    return [*cmd, *extra]


def _pytest_suite(ctx: Context, suite: str, *, coverage: bool) -> None:
    """Run one Python test suite, skipping it when nothing in its paths changed since it passed."""
    cov_config = f"tests/{suite}/coverage.toml" if coverage else None
    ctx.run(
        gated(f"test-{suite}", _pytest_cmd(f"tests/{suite}", cov_config), paths=SUITES[suite]),
        title=pyprefix(f"{suite} tests"),
        capture=CI,
    )


@duty
def test_core(ctx: Context) -> None:
    """Test the gate and the CLI."""
    _pytest_suite(ctx, "core", coverage=True)


@duty
def test_server(ctx: Context) -> None:
    """Test the Python server behind the dashboard."""
    _pytest_suite(ctx, "server", coverage=True)


@duty
def test_tooling(ctx: Context) -> None:
    """Test the build scripts, and that CI runs each suite for the files it depends on."""
    _pytest_suite(ctx, "tooling", coverage=False)


def _frontend_deps_stale(frontend: Path) -> bool:
    """Report whether `node_modules` is missing or older than `package-lock.json`."""
    # npm writes this hidden lockfile on every install, so its age is the install's age.
    installed = frontend / "node_modules" / ".package-lock.json"
    if not installed.is_file():
        return True
    return installed.stat().st_mtime < (frontend / "package-lock.json").stat().st_mtime


def _frontend_deps(ctx: Context) -> None:
    """Install the frontend dependencies when they are missing or out of date."""
    if _frontend_deps_stale(PROJECT_ROOT / "frontend"):
        ctx.run(["npm", "ci", "--prefix", "frontend"], title="frontend dependencies")


@duty
def frontend_test(ctx: Context) -> None:
    """Run the dashboard frontend unit tests."""
    _frontend_deps(ctx)
    ctx.run(
        gated(
            "frontend-test",
            ["npm", "--prefix", "frontend", "run", "test"],
            paths=SUITES["frontend"],
        ),
        title="frontend tests",
    )


@duty()
def test(ctx: Context, *cli_args: str) -> None:
    """Run every test suite, or with arguments, run pytest over all Python tests."""
    if not cli_args:
        for suite in (test_core, test_server, test_tooling, frontend_test):
            suite(ctx)
        return
    cmd = _pytest_cmd("tests/", "pyproject.toml", *cli_args)
    # A marker covers the name, not the arguments, so a filtered pass never writes one
    ctx.run(cmd, title=pyprefix("Running tests - this may take a while"), capture=CI)


@duty
def frontend_check(ctx: Context) -> None:
    """Type-check the dashboard frontend with svelte-check."""
    _frontend_deps(ctx)
    ctx.run(
        gated(
            "frontend-check",
            ["npm", "--prefix", "frontend", "run", "check"],
            paths=SUITES["frontend"],
        ),
        title="frontend check",
    )


@duty
def frontend_build(ctx: Context) -> None:
    """Build the dashboard frontend into the package's static directory."""
    _frontend_deps(ctx)
    # Never gated: the output is git-ignored, so a marker cannot tell which tree built it
    ctx.run(["npm", "--prefix", "frontend", "run", "build"], title="frontend build")


@duty
def docs(ctx: Context, addr: str = "localhost:8010") -> None:
    """Serve the documentation site with live reload.

    Args:
        ctx (Context): Duty context.
        addr (str): Address and port to serve on.
    """
    write_agent_guide()
    ctx.run(
        ["uv", "run", "--group", "docs", "zensical", "serve", "--dev-addr", addr],
        title=f"serve docs at http://{addr}",
        capture=False,
    )


@duty
def dist_check(ctx: Context, *paths: str) -> None:  # noqa: ARG001
    """Fail unless each wheel and sdist ships the dashboard UI and agent guides, and wheels fit the size budget.

    Args:
        ctx (Context): Duty context.
        paths (str): Distribution paths or glob patterns, such as `dist/*`.
    """
    lines, problems = check_dists(paths)
    for line in lines:
        console.print(line)
    if problems:
        for problem in problems:
            console.print(problem)
        raise SystemExit(1)
