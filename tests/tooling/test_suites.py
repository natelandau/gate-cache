"""Tests that each test suite runs for every file it depends on, and for no other."""

from __future__ import annotations

import ast
from functools import cache
from typing import TYPE_CHECKING

import pytest

from tests.conftest import ROOT, git
from tests.tooling import load_duties

if TYPE_CHECKING:
    from pathlib import Path

SRC = ROOT / "src"
TEST_DIRS = ("tests/core/", "tests/server/", "tests/tooling/")
# The `dashboard` command is the one way into the dashboard, and the server suite owns it.
ALLOWED_CORE_IMPORTS = {("src/gate_cache/cli.py", "gate_cache.dashboard.app")}


@cache
def _files(suite: str) -> frozenset[str]:
    """Return the tracked files a suite's pathspecs match, as git and gate-cache match them."""
    pathspecs = load_duties().SUITES[suite]
    listing = git("ls-files", "-z", "--", *pathspecs, cwd=ROOT)
    return frozenset(name for name in listing.split("\0") if name)


def _suites_with(path: str) -> set[str]:
    return {suite for suite in load_duties().SUITES if path in _files(suite)}


def _module_file(module: str) -> Path | None:
    """Return the source file of a gate_cache module, or None when it is not one."""
    base = SRC.joinpath(*module.split("."))
    for candidate in (base.with_suffix(".py"), base / "__init__.py"):
        if candidate.is_file():
            return candidate
    return None


def _imports(path: Path) -> set[str]:
    """Return every gate_cache module that a file imports, at any depth of its code."""
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module)
            # `from gate_cache import scratch` imports the submodule `gate_cache.scratch`
            found.update(
                f"{node.module}.{alias.name}"
                for alias in node.names
                if _module_file(f"{node.module}.{alias.name}") is not None
            )
    return {name for name in found if name.split(".")[0] == "gate_cache"}


def _relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


ALL = {"core", "server", "frontend", "tooling"}


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        # The gate and the dashboard both read stats
        ("src/gate_cache/stats/archive.py", {"core", "server", "tooling"}),
        # Tooling runs on every source and test change for its import and layout checks
        ("src/gate_cache/dashboard/server.py", {"server", "tooling"}),
        ("src/gate_cache/cli.py", {"core", "tooling"}),
        ("src/gate_cache/runner.py", {"core", "tooling"}),
        ("tests/core/test_cli.py", {"core", "tooling"}),
        # A core test runs the shell snippets in this page
        ("docs/reference/marker-format.md", {"core"}),
        ("frontend/package.json", {"frontend"}),
        ("tests/conftest.py", {"core", "server", "tooling"}),
        # These change how every suite runs
        ("uv.lock", ALL),
        ("duties.py", ALL),
        ("pyproject.toml", ALL),
    ],
)
def test_change_runs_the_suites_that_depend_on_it(path: str, expected: set[str]) -> None:
    """A change runs every suite that depends on the file, and no other."""
    assert _suites_with(path) == expected


def test_server_tests_never_call_the_cli() -> None:
    """CLI parsing is tested in core, since a CLI change never runs server."""
    for path in (ROOT / "tests" / "server").rglob("test_*.py"):
        assert "invoke(" not in path.read_text(encoding="utf-8"), _relative(path)


def test_no_relative_imports() -> None:
    """The import checks resolve only absolute imports, so a relative one would hide an edge."""
    for path in (SRC / "gate_cache").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        relative = [n.lineno for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.level]
        assert not relative, f"{_relative(path)}: {relative}"


def test_every_test_file_has_a_suite() -> None:
    """A test file outside the suite folders would never run in CI."""
    for path in (ROOT / "tests").rglob("test_*.py"):
        owners = [prefix for prefix in TEST_DIRS if _relative(path).startswith(prefix)]
        assert len(owners) == 1, _relative(path)


def test_server_paths_cover_dashboard_imports() -> None:
    """Every module the dashboard or its tests reach is in the server paths, so a change runs server."""
    pending = [
        *(SRC / "gate_cache" / "dashboard").rglob("*.py"),
        *(ROOT / "tests" / "server").rglob("*.py"),
    ]
    reached: set[Path] = set()
    while pending:
        path = pending.pop()
        if path in reached:
            continue
        reached.add(path)
        pending.extend(
            file for module in _imports(path) if (file := _module_file(module)) is not None
        )
    missing = {_relative(path) for path in reached} - _files("server")
    assert not missing, f"add to the server paths in duties.py: {sorted(missing)}"


def test_core_never_imports_dashboard() -> None:
    """Core code and tests stay out of the dashboard package, so a dashboard change never needs core."""
    core_sources = (name for name in _files("core") if name.endswith(".py"))
    crossings = {
        (name, module)
        for name in core_sources
        for module in _imports(ROOT / name)
        if module.startswith("gate_cache.dashboard")
    }
    assert crossings == ALLOWED_CORE_IMPORTS
