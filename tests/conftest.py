"""Shared fixtures that isolate git from the developer's configuration."""

import subprocess
import sys
from pathlib import Path

import pytest


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


@pytest.fixture
def git_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Isolate git from user and system config; return the temp HOME."""
    home = tmp_path / "home"
    home.mkdir()
    empty_config = tmp_path / "empty.gitconfig"
    empty_config.write_text("")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(empty_config))
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
