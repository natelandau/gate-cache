"""Shared fixtures that isolate git from the developer's configuration."""

import dataclasses
import io
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from collections.abc import Callable, Iterator, Sequence
from pathlib import Path
from typing import Any

import pytest
from rich.console import Console, RenderableType

from gate_cache import cli, snapshot
from gate_cache import config as core_config
from gate_cache import git as git_module
from gate_cache.commands.theme import THEME
from gate_cache.gate_lock import HELD_ENV
from gate_cache.git import GitResult
from gate_cache.markers import MISS_SUFFIX, marker_dir
from gate_cache.spot_check import SPOT_CHECK_ENV
from gate_cache.stats import config as stats_config
from gate_cache.stats.archive import Archive

ROOT = Path(__file__).resolve().parent.parent

BASE = 1_699_920_000.0  # midnight UTC
DAY = 86400.0
REPO_A = "/x/proj/.git"
REPO_B = "/x/other/.git"


def rendered_text(renderable: RenderableType, *, width: int = 120) -> str:
    """Return the plain text a person sees for a rich renderable on a terminal `width` wide."""
    console = Console(file=io.StringIO(), record=True, width=width, theme=THEME)
    console.print(renderable)
    return console.export_text()


def insert(
    conn: sqlite3.Connection,
    ts: float,
    outcome: str = "pass",
    *,
    repo: str | None = REPO_A,
    name: str = "lint",
    tree: str | None = "t1",
    paths: Sequence[str] = ("src",),
    duration: float | None = None,
    saved: float | None = None,
    reason: str | None = None,
    overhead: float | None = None,
    waited: float | None = None,
    wait_known: bool = False,
    reported: bool = False,
    wait_timed_out: bool = False,
    spot_check: bool = False,
    exit_code: int | None = None,
    raw: dict[str, object] | None = None,
) -> None:
    """Insert one event row."""
    conn.execute(
        "INSERT INTO events (line_hash, ts, repo, name, tree, paths, outcome, duration, saved,"
        " reason, overhead, waited, wait_known, reported, wait_timed_out, exit_code, raw,"
        " spot_check) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            f"h{conn.total_changes}-{ts}",
            ts,
            repo,
            name,
            tree,
            json.dumps(list(paths)),
            outcome,
            duration,
            saved,
            reason,
            overhead,
            waited,
            wait_known,
            reported,
            wait_timed_out,
            exit_code,
            json.dumps(raw) if raw is not None else None,
            spot_check,
        ),
    )
    conn.commit()


def insert_results(
    conn: sqlite3.Connection,
    results: dict[str, tuple[str, float | None]],
    *,
    repo: str | None = REPO_A,
    gate: str = "test",
) -> None:
    """Attach per-test results to the newest event, as name -> (outcome, duration)."""
    (event_id,) = conn.execute("SELECT MAX(id) FROM events").fetchone()
    for name, (outcome, duration) in results.items():
        conn.execute(
            "INSERT INTO tests (repo, gate, name) SELECT ?, ?, ? WHERE NOT EXISTS"
            " (SELECT 1 FROM tests WHERE repo IS ? AND gate = ? AND name = ?)",
            (repo, gate, name, repo, gate, name),
        )
        (test_id,) = conn.execute(
            "SELECT id FROM tests WHERE repo IS ? AND gate = ? AND name = ?", (repo, gate, name)
        ).fetchone()
        conn.execute(
            "INSERT INTO test_results (event_id, test_id, outcome, duration) VALUES (?, ?, ?, ?)",
            (event_id, test_id, outcome, duration),
        )
    conn.commit()


@pytest.fixture
def empty_conn(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    """Provide the connection of an empty archive."""
    with Archive.open(tmp_path / "a.sqlite3") as arch:
        yield arch.connection


@pytest.fixture
def conn(empty_conn: sqlite3.Connection) -> sqlite3.Connection:
    """Provide an archive with two repos, three gates, one flaky tree."""
    insert(empty_conn, BASE + 100, "skip", saved=100.0)
    insert(empty_conn, BASE + 200, "skip", saved=50.0)
    insert(empty_conn, BASE + 300, "skip", saved=None)
    insert(empty_conn, BASE + 400, "fail", name="test", tree="t2", duration=5.0)
    insert(empty_conn, BASE + 500, "pass", name="test", tree="t2", duration=30.0)
    insert(empty_conn, BASE + DAY + 100, "uncached", repo=REPO_B, tree=None)
    return empty_conn


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


_GIT_REPO_ENV = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_COMMON_DIR",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
)


@pytest.fixture(autouse=True)
def isolate_user_dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the stats data and the XDG config and state homes under tmp_path.

    platformdirs prefers the XDG variables over HOME, so a developer who exports them
    would otherwise let a test, or a subprocess it starts, reach real stats and config.

    Returns:
        The stats data directory.
    """
    # A git hook exports these for the repository being committed. Left in place, a test's
    # `git init` in a temporary directory reinitializes that repository instead.
    for var in _GIT_REPO_ENV:
        monkeypatch.delenv(var, raising=False)
    data = tmp_path / "gate-cache-data"
    monkeypatch.setenv(stats_config.DATA_DIR_ENV, str(data))
    for var in ("XDG_CONFIG_HOME", "XDG_STATE_HOME"):
        monkeypatch.setenv(var, str(tmp_path / "xdg" / var.lower()))
    return data


@pytest.fixture(autouse=True)
def _no_held_locks(monkeypatch: pytest.MonkeyPatch) -> None:
    """Clear the held-locks variable that a gate-cache run wrapping the test suite sets."""
    monkeypatch.delenv(HELD_ENV, raising=False)


@pytest.fixture(autouse=True)
def _no_spot_checks(monkeypatch: pytest.MonkeyPatch) -> None:
    """Turn random spot checks off, so a test that expects a skip never runs the command."""
    monkeypatch.setenv(SPOT_CHECK_ENV, "0")


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
    for var in ("CI", "GATE_CACHE_DISABLE"):
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
    """Route snapshot's git calls, git_common_dir's included, through HANDLER; a None answer runs the real git.

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
    monkeypatch.setattr(git_module, "run_git", run_git)
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


def write_config(path: Path, text: str) -> Path:
    """Write a config file at path, creating its directory, and return the path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture
def stats_dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    """Point the stats config file and state directory under tmp_path; return both."""
    config_file = tmp_path / "cfg" / "config.toml"
    state = tmp_path / "state"
    monkeypatch.setattr(core_config, "config_path", lambda: config_file)
    monkeypatch.setenv(stats_config.DATA_DIR_ENV, str(state))
    monkeypatch.delenv(stats_config.STATS_ENV, raising=False)
    monkeypatch.delenv("CI", raising=False)
    return config_file, state


@pytest.fixture
def stats_on(stats_dirs: tuple[Path, Path]) -> None:
    """Turn stats recording on through the config file."""
    config_file = stats_dirs[0]
    config_file.parent.mkdir(parents=True, exist_ok=True)
    config_file.write_text("stats_enabled = true\n", encoding="utf-8")


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
