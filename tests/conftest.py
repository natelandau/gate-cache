"""Shared fixtures that isolate git from the developer's configuration."""

import dataclasses
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from gate_cache import cli, snapshot
from gate_cache.git import GitResult
from gate_cache.markers import MISS_SUFFIX, marker_dir
from gate_cache.stats import config as stats_config

ROOT = Path(__file__).resolve().parent.parent


def git(*args: str, cwd: Path) -> str:
    """Run git in cwd and return stripped stdout."""
    result = subprocess.run(  # noqa: S603
        ["git", *args],  # noqa: S607
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def invoke(monkeypatch: pytest.MonkeyPatch, *args: str) -> int:
    """Run main() with the given arguments and return the exit code."""
    monkeypatch.setattr(sys, "argv", ["gate-cache", *args])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    code = exc.value.code
    assert isinstance(code, int)
    return code


@pytest.fixture
def git_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Isolate git from user and system config; return the temp HOME."""
    home = tmp_path / "home"
    home.mkdir()
    global_config = tmp_path / "global.gitconfig"
    # Commits spawn detached auto-maintenance, which races tests that inspect .git.
    global_config.write_text("[maintenance]\n\tauto = false\n[gc]\n\tauto = 0\n")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(global_config))
    # platformdirs rejects a runtime dir that is not private, then falls back to the real one.
    runtime = tmp_path / "run"
    runtime.mkdir(mode=0o700)
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(runtime))
    # CI and GATE_CACHE_DISABLE turn caching off, which would hide every cache hit.
    for var in ("GIT_DIR", "GIT_INDEX_FILE", "GIT_WORK_TREE", "CI", "GATE_CACHE_DISABLE"):
        monkeypatch.delenv(var, raising=False)
    return home


@pytest.fixture
def git_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, git_env: Path) -> Path:
    """Create a committed repo with a tracked file and gitignore, and chdir into it."""
    repo = tmp_path / "repo"
    repo.mkdir()
    git("init", "-q", "-b", "main", cwd=repo)
    git("config", "user.name", "Test", cwd=repo)
    git("config", "user.email", "test@example.com", cwd=repo)
    git("config", "commit.gpgsign", "false", cwd=repo)
    (repo / "a.txt").write_text("a\n")
    (repo / ".gitignore").write_text("ignored.txt\n")
    git("add", "a.txt", ".gitignore", cwd=repo)
    git("commit", "-q", "-m", "initial", cwd=repo)
    monkeypatch.chdir(repo)
    return repo


_COUNTER_SCRIPT = """\
import sys

with open(sys.argv[1], "a", encoding="utf-8") as counter:
    counter.write("run\\n")
if len(sys.argv) > 3:
    with open(sys.argv[3], "a", encoding="utf-8") as touched:
        touched.write("touched\\n")
sys.exit(int(sys.argv[2]))
"""


class Counter:
    """A gate command that records each run in a file outside the repo."""

    def __init__(self, root: Path) -> None:
        root.mkdir(parents=True, exist_ok=True)
        self._script = root / "count.py"
        self._script.write_text(_COUNTER_SCRIPT, encoding="utf-8")
        self._file = root / "count.txt"

    def argv(self, exit_code: int = 0, touch: Path | None = None) -> list[str]:
        """Return a command that counts a run, optionally appends to touch, then exits."""
        args = [sys.executable, str(self._script), str(self._file), str(exit_code)]
        if touch is not None:
            args.append(str(touch))
        return args

    @property
    def count(self) -> int:
        """Return how many times the command has run."""
        if not self._file.exists():
            return 0
        return len(self._file.read_text(encoding="utf-8").splitlines())


@pytest.fixture
def counter(tmp_path: Path) -> Counter:
    """Provide a counting gate command whose files never make the repo dirty."""
    return Counter(tmp_path / "bin")


def add_submodule(repo: Path, tmp_path: Path, name: str = "sub") -> Path:
    """Commit a submodule cloned from a local repo and return its checkout path."""
    upstream = tmp_path / f"{name}-upstream"
    upstream.mkdir()
    git("init", "-q", "-b", "main", cwd=upstream)
    git(
        "-c", "user.name=Test", "-c", "user.email=test@example.com",
        "commit", "-q", "--allow-empty", "-m", "one",
        cwd=upstream,
    )  # fmt: skip
    # Git refuses to clone a submodule from a local path unless the file protocol is allowed.
    git("-c", "protocol.file.allow=always", "submodule", "add", "-q", str(upstream), name, cwd=repo)
    git("commit", "-q", "-m", "add submodule", cwd=repo)
    return repo / name


def expected_tree(repo: Path) -> str:
    """Return the tree `git add -A` would produce, without touching the real index."""
    index = repo / git("rev-parse", "--git-path", "index", cwd=repo)
    scratch = index.with_name("expected-index")
    if index.exists():
        shutil.copy2(index, scratch)
    env = {**os.environ, "GIT_INDEX_FILE": str(scratch)}
    try:
        subprocess.run(["git", "add", "-A"], cwd=repo, env=env, check=True)  # noqa: S607
        return subprocess.run(
            ["git", "write-tree"],  # noqa: S607
            cwd=repo,
            env=env,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    finally:
        scratch.unlink(missing_ok=True)


def intercept_run_git(
    monkeypatch: pytest.MonkeyPatch,
    handler: Callable[[tuple[str, ...], dict[str, Any]], GitResult | None],
) -> list[tuple[str, ...]]:
    """Route snapshot's git calls through HANDLER; a None answer runs the real git.

    Returns:
        The arguments of every git call, in order, filled in as they happen.
    """
    calls: list[tuple[str, ...]] = []
    real_run_git = snapshot.run_git

    def run_git(*args: str, **kwargs: Any) -> GitResult:
        calls.append(args)
        answer = handler(args, kwargs)
        return real_run_git(*args, **kwargs) if answer is None else answer

    monkeypatch.setattr(snapshot, "run_git", run_git)
    return calls


def hide_common_dir(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make every snapshot the gate takes report no git common directory."""
    real_take_snapshot = snapshot.take_snapshot

    def take_snapshot(*args: Any, **kwargs: Any) -> snapshot.Snapshot:
        return dataclasses.replace(real_take_snapshot(*args, **kwargs), common_dir=None)

    monkeypatch.setattr("gate_cache.gate.take_snapshot", take_snapshot)


def markers(repo: Path) -> list[Path]:
    """Return the pass markers in the repo's marker directory."""
    directory = marker_dir(repo / ".git")
    if not directory.is_dir():
        return []
    return sorted(path for path in directory.iterdir() if path.suffix != MISS_SUFFIX)


def misses(repo: Path) -> list[Path]:
    """Return the miss records in the repo's marker directory."""
    directory = marker_dir(repo / ".git")
    return sorted(directory.glob(f"*{MISS_SUFFIX}")) if directory.is_dir() else []


def read_records(paths: list[Path]) -> list[dict[str, object]]:
    """Parse the JSON content of marker or miss record files."""
    return [json.loads(path.read_text()) for path in paths]


@pytest.fixture
def stats_dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    """Point the stats config file and state directory under tmp_path; return both."""
    config_file = tmp_path / "cfg" / "config.toml"
    state = tmp_path / "state"
    monkeypatch.setattr(stats_config, "config_path", lambda: config_file)
    monkeypatch.setattr(stats_config, "state_dir", lambda: state)
    monkeypatch.delenv(stats_config.STATS_ENV, raising=False)
    monkeypatch.delenv("CI", raising=False)
    return config_file, state


@pytest.fixture
def stats_on(stats_dirs: tuple[Path, Path]) -> None:
    """Turn stats recording on through the config file."""
    config_file = stats_dirs[0]
    config_file.parent.mkdir(parents=True, exist_ok=True)
    config_file.write_text("[stats]\nenabled = true\n", encoding="utf-8")


@pytest.fixture
def answer(monkeypatch: pytest.MonkeyPatch) -> Callable[[str | None], None]:
    """Make stdin a terminal and set what the user types; None ends input, ^C presses Ctrl-C."""

    def set_answer(text: str | None) -> None:
        def read() -> str:
            if text is None:
                raise EOFError
            if text == "^C":
                raise KeyboardInterrupt
            return text

        monkeypatch.setattr("gate_cache.console.stdin_isatty", lambda: True)
        monkeypatch.setattr("builtins.input", read)

    return set_answer
