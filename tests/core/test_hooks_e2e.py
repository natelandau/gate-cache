"""End-to-end tests that run the hook under prek and pre-commit."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tests.conftest import ROOT, Counter, git

pytestmark = pytest.mark.e2e

RUNNERS = ["prek", "pre-commit"]
_HOME_VARS = {"prek": "PREK_HOME", "pre-commit": "PRE_COMMIT_HOME"}
_CI = os.environ.get("CI", "").strip().lower() in {"1", "true", "yes"}


def _require(runner: str) -> None:
    if shutil.which(runner) is not None:
        return
    # A missing runner must not silently shrink CI coverage.
    if _CI:
        pytest.fail(f"{runner} is not installed")
    pytest.skip(f"{runner} is not installed")


def _isolate_homes(monkeypatch: pytest.MonkeyPatch, home: Path) -> None:
    for var in _HOME_VARS.values():
        monkeypatch.setenv(var, str(home))


def _install_hook(git_repo: Path, hook_repo: tuple[Path, str], args: list[str]) -> None:
    """Commit a config that runs the gate-cache hook with args."""
    repo_path, sha = hook_repo
    config = (
        "repos:\n"
        f"  - repo: {repo_path}\n"
        f"    rev: {sha}\n"
        "    hooks:\n"
        "      - id: gate-cache\n"
        f"        args: {json.dumps(args)}\n"
    )
    (git_repo / ".pre-commit-config.yaml").write_text(config, encoding="utf-8")
    git("add", ".pre-commit-config.yaml", cwd=git_repo)
    git("commit", "-q", "-m", "add config", cwd=git_repo)


def _run_hook(runner: str, git_repo: Path) -> subprocess.CompletedProcess[str]:
    """Run every hook on all files, as a developer or an agent would."""
    return subprocess.run(  # noqa: S603
        [runner, "run", "--all-files", "--verbose"],
        cwd=git_repo,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.fixture(scope="session")
def hook_repo(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, str]:
    """Build a committed copy of the project to serve as the hook repository."""
    root = tmp_path_factory.mktemp("hook-repo")
    for name in ("pyproject.toml", "README.md", "LICENSE", ".pre-commit-hooks.yaml"):
        shutil.copy2(ROOT / name, root / name)
    shutil.copytree(ROOT / "src", root / "src", ignore=shutil.ignore_patterns("__pycache__"))
    isolated = tmp_path_factory.mktemp("hook-repo-git")
    env = {
        **os.environ,
        "HOME": str(isolated),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": str(isolated / "gitconfig"),
    }
    for var in ("GIT_DIR", "GIT_INDEX_FILE", "GIT_WORK_TREE"):
        env.pop(var, None)
    identity = ["-c", "user.name=Test", "-c", "user.email=test@example.com"]
    for args in (
        ["init", "-q", "-b", "main"],
        ["add", "-A"],
        [*identity, "-c", "commit.gpgsign=false", "commit", "-q", "-m", "hook"],
    ):
        subprocess.run(["git", *args], cwd=root, env=env, check=True, capture_output=True)  # noqa: S603, S607
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],  # noqa: S607
        cwd=root,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    return root, sha


@pytest.fixture(scope="session")
def runner_homes(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    """Provide a cache home per runner so hook environments are built once."""
    return {name: tmp_path_factory.mktemp(f"{name}-home") for name in RUNNERS}


@pytest.mark.parametrize("runner", RUNNERS)
def test_manifest_validates(
    runner: str, runner_homes: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Both runners accept the hook manifest."""
    _require(runner)
    _isolate_homes(monkeypatch, runner_homes[runner])
    result = subprocess.run(  # noqa: S603
        [runner, "validate-manifest", str(ROOT / ".pre-commit-hooks.yaml")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("runner", RUNNERS)
def test_hook_runs_then_skips(
    runner: str,
    runner_homes: dict[str, Path],
    git_repo: Path,
    counter: Counter,
    monkeypatch: pytest.MonkeyPatch,
    request: pytest.FixtureRequest,
) -> None:
    """The second run on an unchanged tree skips the gate command."""
    _require(runner)
    # Requested lazily so a missing runner skips before the hook repository is built.
    repo_path, sha = request.getfixturevalue("hook_repo")
    _isolate_homes(monkeypatch, runner_homes[runner])
    args = ["--name", "check", "--", sys.executable, *counter.argv()[1:]]
    _install_hook(git_repo=git_repo, hook_repo=(repo_path, sha), args=args)

    first = _run_hook(runner=runner, git_repo=git_repo)
    assert first.returncode == 0, first.stdout + first.stderr
    assert counter.count == 1
    assert "check already passed on tree" not in first.stdout + first.stderr

    second = _run_hook(runner=runner, git_repo=git_repo)
    assert second.returncode == 0, second.stdout + second.stderr
    assert counter.count == 1
    assert "check already passed on tree" in second.stdout + second.stderr


@pytest.mark.parametrize("runner", RUNNERS)
def test_hook_command_finds_the_users_tools(
    runner: str,
    runner_homes: dict[str, Path],
    git_repo: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    request: pytest.FixtureRequest,
) -> None:
    """A bare tool name in the hook's args finds the user's copy, outside the hook's Python env."""
    _require(runner)
    repo_path, sha = request.getfixturevalue("hook_repo")
    _isolate_homes(monkeypatch, runner_homes[runner])
    # The hook env's bin/ holds a gate-cache script, so a user tool by that name shows
    # which one a bare name resolves to. A shell script keeps the project free of Python.
    user_bin = tmp_path / "user-bin"
    user_bin.mkdir()
    seen = tmp_path / "seen"
    tool = user_bin / "gate-cache"
    tool.write_text(
        f'#!/bin/sh\nprintf "%s" "${{VIRTUAL_ENV-unset}}" > "{seen}"\n', encoding="utf-8"
    )
    tool.chmod(0o755)
    monkeypatch.setenv("PATH", f"{user_bin}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.delenv("VIRTUAL_ENV", raising=False)
    _install_hook(
        git_repo=git_repo, hook_repo=(repo_path, sha), args=["--name", "probe", "--", "gate-cache"]
    )

    result = _run_hook(runner=runner, git_repo=git_repo)
    assert result.returncode == 0, result.stdout + result.stderr
    assert seen.read_text(encoding="utf-8") == "unset"
