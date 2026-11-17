"""Tests for the `stats clear` command."""

from collections.abc import Callable
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from gate_cache.stats import clear
from gate_cache.stats.archive import Archive, archive_path
from gate_cache.stats.lock import InstanceLock
from tests.conftest import invoke


@pytest.fixture
def lock(stats_dirs: tuple[Path, Path]) -> InstanceLock:
    """Hold the instance lock as a running dashboard would."""
    held = InstanceLock.acquire(stats_dirs[1])
    assert held is not None
    held.write_url("http://127.0.0.1:7878")
    return held


def test_stats_clear_refuses_while_running(
    lock: InstanceLock, capsys: pytest.CaptureFixture[str]
) -> None:
    """Clearing is refused while the dashboard holds the lock."""
    Archive.open(archive_path()).close()
    try:
        assert clear.stats_clear() == 1
    finally:
        lock.release()
    assert archive_path().exists()
    assert "stop the dashboard" in capsys.readouterr().err


def test_stats_clear_deletes(
    stats_dirs: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    """Clearing removes the inbox, processing files, and the archive with its WAL files."""
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
    assert clear.stats_clear(confirmed=True) == 0
    assert "cleared stats" in capsys.readouterr().err
    assert [p.name for p in state.iterdir() if p.name != "dashboard.lock"] == []


def test_stats_clear_removes_machine_id_temp_files(stats_dirs: tuple[Path, Path]) -> None:
    """Clearing removes temp files a killed run left behind and keeps the machine ID."""
    state = stats_dirs[1]
    state.mkdir(parents=True)
    (state / "machine-id").write_text(f"{'a' * 32}\n")
    (state / f".machine-id.123.{'c' * 32}").write_text("x")
    (state / f".machine-id.456.{'d' * 32}").write_text("")
    assert clear.stats_clear(confirmed=True) == 0
    assert sorted(p.name for p in state.iterdir() if p.name != "dashboard.lock") == ["machine-id"]
    assert (state / "machine-id").read_text() == f"{'a' * 32}\n"


@pytest.fixture
def seeded(stats_dirs: tuple[Path, Path]) -> Path:
    """Write an inbox so a test can see whether clearing deleted it."""
    state = stats_dirs[1]
    state.mkdir(parents=True)
    (state / "events.jsonl").write_text("x")
    return state


def test_stats_clear_keeps_stats_unless_confirmed(
    seeded: Path, answer: Callable[[str | None], None], capsys: pytest.CaptureFixture[str]
) -> None:
    """Declining the prompt deletes nothing, and the warning names the data directory."""
    answer("no")
    assert clear.stats_clear() == 1
    assert (seeded / "events.jsonl").exists()
    assert f"data: {seeded}" in capsys.readouterr().err


def test_stats_clear_deletes_when_yes_typed(
    seeded: Path, answer: Callable[[str | None], None], capsys: pytest.CaptureFixture[str]
) -> None:
    """Typing yes at the prompt clears the stats."""
    answer("yes")
    assert clear.stats_clear() == 0
    assert not (seeded / "events.jsonl").exists()
    assert "cleared stats" in capsys.readouterr().err


def test_stats_clear_ctrl_c_keeps_stats_and_releases_lock(
    seeded: Path, answer: Callable[[str | None], None]
) -> None:
    """Ctrl-C at the prompt keeps the stats and frees the dashboard lock."""
    answer("^C")
    with pytest.raises(KeyboardInterrupt):
        clear.stats_clear()
    assert (seeded / "events.jsonl").exists()
    held = InstanceLock.acquire(seeded)
    assert held is not None
    held.release()


def test_stats_clear_refuses_before_prompting_while_running(
    lock: InstanceLock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A running dashboard is reported before the user is asked anything."""
    asked = MagicMock(return_value=False)
    monkeypatch.setattr(clear, "confirm_deletion", asked)
    try:
        assert clear.stats_clear() == 1
    finally:
        lock.release()
    asked.assert_not_called()


def test_stats_clear_reports_os_error(
    stats_dirs: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A delete failure is reported with exit code 1."""
    state = stats_dirs[1]
    state.mkdir(parents=True)
    (state / "events.jsonl").write_text("x")
    real = Path.unlink

    def fail(self: Path, missing_ok: bool = False) -> None:  # noqa: FBT002
        if self.name == "events.jsonl":
            raise PermissionError(13, "denied")
        real(self, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", fail)
    assert clear.stats_clear(confirmed=True) == 1
    assert "could not clear stats: denied" in capsys.readouterr().err
    monkeypatch.setattr(Path, "unlink", real)
    held = InstanceLock.acquire(state)
    assert held is not None
    held.release()


def test_cli_stats_clear_routes(monkeypatch: pytest.MonkeyPatch) -> None:
    """`stats clear` dispatches to stats_clear."""
    stub = MagicMock(return_value=0)
    monkeypatch.setattr(clear, "stats_clear", stub)
    assert invoke(monkeypatch, "stats", "clear") == 0
    stub.assert_called_once_with(confirmed=False)


def test_cli_stats_clear_yes_skips_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    """`stats clear --yes` and `-y` clear without asking."""
    stub = MagicMock(return_value=0)
    monkeypatch.setattr(clear, "stats_clear", stub)
    assert invoke(monkeypatch, "stats", "clear", "--yes") == 0
    assert invoke(monkeypatch, "stats", "clear", "-y") == 0
    assert stub.call_args_list == [((), {"confirmed": True})] * 2


def test_cli_stats_yes_needs_clear(monkeypatch: pytest.MonkeyPatch) -> None:
    """--yes with any action other than clear is a usage error."""
    for args in (("--yes",), ("on", "--yes"), ("off", "-y")):
        assert invoke(monkeypatch, "stats", *args) == 2
