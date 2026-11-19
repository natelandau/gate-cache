"""Tests for deleting recorded stats."""

import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from gate_cache.stats.archive import Archive, archive_path
from gate_cache.stats.clear import StatsInUseError, StatsSummary, clear_stats
from gate_cache.stats.junit import TESTS_DIR_NAME
from gate_cache.stats.lock import InstanceLock
from tests.conftest import REPO_A, REPO_B, archived_repos, insert


def _yes(_summary: StatsSummary) -> bool:
    return True


def _runs(repo: str | None = None) -> int:
    """Count the archived runs of one repo, or of every repo when repo is None."""
    return sum(repo is None or found == repo for found in archived_repos())


@pytest.fixture
def lock(stats_dirs: tuple[Path, Path]) -> InstanceLock:
    """Hold the instance lock as a running dashboard would."""
    held = InstanceLock.acquire(stats_dirs[1])
    assert held is not None
    held.write_url("http://127.0.0.1:7878")
    return held


def test_stats_clear_refuses_while_running(lock: InstanceLock) -> None:
    """Clearing is refused, before any prompt, while the dashboard holds the lock."""
    Archive.open(archive_path()).close()
    confirm = MagicMock(return_value=True)
    try:
        with pytest.raises(StatsInUseError):
            clear_stats(repo=None, decide=confirm)
    finally:
        lock.release()
    assert archive_path().exists()
    confirm.assert_not_called()


def test_stats_clear_deletes(stats_dirs: tuple[Path, Path]) -> None:
    """Clearing removes the inbox, processing files, per-run test files, and the archive."""
    state = stats_dirs[1]
    Archive.open(archive_path()).close()
    names = [
        "events.jsonl",
        "events.1.processing",
        "events.2.processing",
        "stats.sqlite3-wal",
        "stats.sqlite3-shm",
    ]
    for name in names:
        (state / name).write_text("x")
    (state / TESTS_DIR_NAME).mkdir()
    (state / TESTS_DIR_NAME / "abc.json").write_text("[]")
    (state / TESTS_DIR_NAME / ".abc.x.tmp").write_text("[")
    assert clear_stats(repo=None, decide=_yes).deleted
    assert [
        p.name for p in state.iterdir() if p.name not in {"dashboard.lock", TESTS_DIR_NAME}
    ] == []
    assert list((state / TESTS_DIR_NAME).iterdir()) == []


def test_stats_clear_ignores_test_file_written_meanwhile(
    stats_dirs: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A per-run test file a gate run writes during clearing does not fail the clear."""
    state = stats_dirs[1]
    folder = state / TESTS_DIR_NAME
    folder.mkdir(parents=True)
    (folder / "abc.json").write_text("[]")
    real = Path.unlink

    def unlink_then_write(self: Path, *, missing_ok: bool = False) -> None:
        real(self, missing_ok=missing_ok)
        if self.name == "abc.json":
            (folder / "def.json").write_text("[]")

    monkeypatch.setattr(Path, "unlink", unlink_then_write)
    assert clear_stats(repo=None, decide=_yes).deleted
    assert [p.name for p in folder.iterdir()] == ["def.json"]


def test_stats_clear_removes_machine_id_temp_files(stats_dirs: tuple[Path, Path]) -> None:
    """Clearing removes temp files a killed run left behind and keeps the machine ID."""
    state = stats_dirs[1]
    state.mkdir(parents=True)
    (state / "machine-id").write_text(f"{'a' * 32}\n")
    (state / f".machine-id.123.{'c' * 32}").write_text("x")
    (state / f".machine-id.456.{'d' * 32}").write_text("")
    assert clear_stats(repo=None, decide=_yes).deleted
    assert sorted(p.name for p in state.iterdir() if p.name != "dashboard.lock") == ["machine-id"]
    assert (state / "machine-id").read_text() == f"{'a' * 32}\n"


@pytest.fixture
def seeded(stats_dirs: tuple[Path, Path]) -> Path:
    """Archive runs of two repos, the first one an hour earlier, and return the state folder."""
    stats_dirs[1].mkdir(parents=True)
    now = time.time()
    with Archive.open(archive_path()) as archive:
        insert(archive.connection, now - 3600, repo=REPO_A, name="lint")
        insert(archive.connection, now - 60, repo=REPO_A, name="test")
        insert(archive.connection, now - 60, repo=REPO_B, name="lint")
    return stats_dirs[1]


@pytest.mark.parametrize(("repo", "runs", "gates", "repos"), [(REPO_A, 2, 2, 1), (None, 3, 2, 2)])
def test_stats_clear_summary_counts_what_goes(
    seeded: Path, repo: str | None, runs: int, gates: int, repos: int
) -> None:
    """The summary counts the runs, gates, and repos in scope, and their time range."""
    seen: list[StatsSummary] = []

    def decline(summary: StatsSummary) -> bool:
        seen.append(summary)
        return False

    assert clear_stats(repo=repo, decide=decline).deleted is False
    (summary,) = seen
    assert (summary.runs, summary.gates, summary.repos) == (runs, gates, repos)
    assert summary.first is not None
    assert summary.last is not None
    assert summary.last - summary.first == pytest.approx(3540, abs=1)
    assert _runs() == 3


def test_stats_clear_of_one_repo_keeps_the_others(seeded: Path) -> None:
    """Clearing one repo deletes its runs and keeps every other repo's runs."""
    assert clear_stats(repo=REPO_A, decide=_yes).deleted
    assert _runs(REPO_A) == 0
    assert _runs(REPO_B) == 1


def test_stats_clear_of_a_repo_without_runs_asks_nothing(seeded: Path) -> None:
    """A repo with no runs has nothing to delete, so the question is never asked."""
    decide = MagicMock(return_value=True)
    result = clear_stats(repo="/x/none/.git", decide=decide)
    assert result.summary.runs == 0
    assert result.deleted is False
    decide.assert_not_called()


def test_stats_clear_ctrl_c_keeps_stats_and_releases_lock(seeded: Path) -> None:
    """Ctrl-C at the prompt keeps the stats and frees the dashboard lock."""

    def interrupt(_summary: StatsSummary) -> bool:
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        clear_stats(repo=None, decide=interrupt)
    assert _runs() == 3
    held = InstanceLock.acquire(seeded)
    assert held is not None
    held.release()


def test_stats_clear_raises_os_error_and_releases_lock(
    stats_dirs: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A delete failure propagates and the lock is freed."""
    state = stats_dirs[1]
    state.mkdir(parents=True)
    (state / "events.jsonl").write_text("x")
    real = Path.unlink

    def fail(self: Path, missing_ok: bool = False) -> None:  # noqa: FBT002
        if self.name == "events.jsonl":
            raise PermissionError(13, "denied")
        real(self, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", fail)
    with pytest.raises(OSError, match="denied"):
        clear_stats(repo=None, decide=_yes)
    monkeypatch.setattr(Path, "unlink", real)
    held = InstanceLock.acquire(state)
    assert held is not None
    held.release()
