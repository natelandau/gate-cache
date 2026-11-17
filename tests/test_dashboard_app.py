"""Tests for the dashboard and stats clear commands."""

import socket
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import closing
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from gate_cache.dashboard import app
from gate_cache.dashboard.lock import InstanceLock
from gate_cache.stats.archive import Archive, archive_path
from gate_cache.stats.recorder import inbox_path
from tests.test_cli import invoke

STATIC = Path(__file__).parent / "fixtures" / "static"


@pytest.fixture
def opener(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Replace the browser launcher."""
    mock = MagicMock()
    monkeypatch.setattr(app.webbrowser, "open", mock)
    return mock


@pytest.fixture
def lock(stats_dirs: tuple[Path, Path]) -> InstanceLock:
    """Hold the instance lock as a running dashboard would."""
    held = InstanceLock.acquire(stats_dirs[1])
    assert held is not None
    held.write_url("http://127.0.0.1:7878")
    return held


def test_second_dashboard_reports_running(
    lock: InstanceLock, opener: MagicMock, capsys: pytest.CaptureFixture[str]
) -> None:
    """A second dashboard prints the running URL, opens it, and exits 0."""
    try:
        assert app.run_dashboard(port=0, open_browser=True) == 0
    finally:
        lock.release()
    assert "already running at http://127.0.0.1:7878" in capsys.readouterr().err
    opener.assert_called_once_with("http://127.0.0.1:7878")


def test_dashboard_during_stats_clear_prompt(
    stats_dirs: tuple[Path, Path], opener: MagicMock, capsys: pytest.CaptureFixture[str]
) -> None:
    """A dashboard started while `stats clear` holds the lock names both possible holders."""
    held = InstanceLock.acquire(stats_dirs[1])
    assert held is not None
    try:
        assert app.run_dashboard(port=0, open_browser=True) == 0
    finally:
        held.release()
    assert "already running, or stats clear is in progress" in capsys.readouterr().err
    opener.assert_not_called()


def test_second_dashboard_no_browser(lock: InstanceLock, opener: MagicMock) -> None:
    """--no-browser suppresses opening the running dashboard."""
    try:
        assert app.run_dashboard(port=0, open_browser=False) == 0
    finally:
        lock.release()
    opener.assert_not_called()


def test_stats_clear_refuses_while_running(
    lock: InstanceLock, capsys: pytest.CaptureFixture[str]
) -> None:
    """Clearing is refused while the dashboard holds the lock."""
    Archive.open(archive_path()).close()
    try:
        assert app.stats_clear() == 1
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
    assert app.stats_clear(confirmed=True) == 0
    assert "cleared stats" in capsys.readouterr().err
    assert [p.name for p in state.iterdir() if p.name != "dashboard.lock"] == []


def test_stats_clear_removes_machine_id_temp_files(stats_dirs: tuple[Path, Path]) -> None:
    """Clearing removes temp files a killed run left behind and keeps the machine ID."""
    state = stats_dirs[1]
    state.mkdir(parents=True)
    (state / "machine-id").write_text(f"{'a' * 32}\n")
    (state / f".machine-id.123.{'c' * 32}").write_text("x")
    (state / f".machine-id.456.{'d' * 32}").write_text("")
    assert app.stats_clear(confirmed=True) == 0
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
    assert app.stats_clear() == 1
    assert (seeded / "events.jsonl").exists()
    assert f"data: {seeded}" in capsys.readouterr().err


def test_stats_clear_deletes_when_yes_typed(
    seeded: Path, answer: Callable[[str | None], None], capsys: pytest.CaptureFixture[str]
) -> None:
    """Typing yes at the prompt clears the stats."""
    answer("yes")
    assert app.stats_clear() == 0
    assert not (seeded / "events.jsonl").exists()
    assert "cleared stats" in capsys.readouterr().err


def test_stats_clear_ctrl_c_keeps_stats_and_releases_lock(
    seeded: Path, answer: Callable[[str | None], None]
) -> None:
    """Ctrl-C at the prompt keeps the stats and frees the dashboard lock."""
    answer("^C")
    with pytest.raises(KeyboardInterrupt):
        app.stats_clear()
    assert (seeded / "events.jsonl").exists()
    held = InstanceLock.acquire(seeded)
    assert held is not None
    held.release()


def test_stats_clear_refuses_before_prompting_while_running(
    lock: InstanceLock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A running dashboard is reported before the user is asked anything."""
    asked = MagicMock(return_value=False)
    monkeypatch.setattr(app, "confirm_deletion", asked)
    try:
        assert app.stats_clear() == 1
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
    assert app.stats_clear(confirmed=True) == 1
    assert "could not clear stats: denied" in capsys.readouterr().err
    monkeypatch.setattr(Path, "unlink", real)
    held = InstanceLock.acquire(state)
    assert held is not None
    held.release()


def test_unusable_state_dir_exit_1(
    stats_dirs: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    """A state directory that cannot be created is reported, not raised."""
    stats_dirs[1].write_text("a file, not a directory")
    assert app.run_dashboard(port=0, open_browser=False) == 1
    assert "could not use" in capsys.readouterr().err


def test_fallback_bind_failure_exit_1(
    stats_dirs: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """When even a free port cannot be bound, the dashboard reports it and exits 1."""
    monkeypatch.setattr(app, "static_root", lambda: STATIC)
    monkeypatch.setattr(app.server_module, "make_server", MagicMock(side_effect=OSError(1, "nope")))
    assert app.run_dashboard(port=None, open_browser=False) == 1
    assert "could not listen on 127.0.0.1: nope" in capsys.readouterr().err


def test_startup_failure_closes_the_socket(
    stats_dirs: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A failure after binding closes the server socket and exits 1."""
    monkeypatch.setattr(app, "static_root", lambda: STATIC)
    monkeypatch.setattr(InstanceLock, "write_url", MagicMock(side_effect=OSError(1, "ro")))
    created = []
    real = app.server_module.make_server

    def spy(**kwargs: object) -> object:
        created.append(real(**kwargs))  # ty: ignore[invalid-argument-type]
        return created[-1]

    monkeypatch.setattr(app.server_module, "make_server", spy)
    assert app.run_dashboard(port=0, open_browser=False) == 1
    assert created[0].socket.fileno() == -1
    assert "ro" in capsys.readouterr().err


def _spy_servers(monkeypatch: pytest.MonkeyPatch) -> list:
    """Record every server the dashboard creates."""
    created: list = []
    real = app.server_module.make_server

    def spy(**kwargs: object) -> object:
        created.append(real(**kwargs))  # ty: ignore[invalid-argument-type]
        return created[-1]

    monkeypatch.setattr(app.server_module, "make_server", spy)
    return created


def test_unexpected_startup_error_closes_the_socket(
    stats_dirs: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Any exception after binding closes the server socket before it propagates."""
    monkeypatch.setattr(app, "static_root", lambda: STATIC)
    monkeypatch.setattr(Archive, "ingest", MagicMock(side_effect=RuntimeError("boom")))
    created = _spy_servers(monkeypatch)
    with pytest.raises(RuntimeError, match="boom"):
        app.run_dashboard(port=0, open_browser=False)
    assert created[0].socket.fileno() == -1


def test_run_failure_before_serving_shuts_down(
    stats_dirs: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch, opener: MagicMock
) -> None:
    """A failure before the serve loop starts still stops ingest and closes the socket."""
    monkeypatch.setattr(app, "static_root", lambda: STATIC)
    opener.side_effect = RuntimeError("no browser")
    created = _spy_servers(monkeypatch)
    with pytest.raises(RuntimeError, match="no browser"):
        app.run_dashboard(port=0, open_browser=True)
    assert created[0].socket.fileno() == -1
    assert created[0]._ingester is not None
    assert not created[0]._ingester.is_alive()


def test_serve_thread_start_failure_does_not_hang(
    stats_dirs: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A serve thread that fails to start still stops ingest and closes the socket."""
    monkeypatch.setattr(app, "static_root", lambda: STATIC)
    monkeypatch.setattr(
        app.threading.Thread, "start", MagicMock(side_effect=RuntimeError("no threads"))
    )
    stop_ingest = MagicMock()
    monkeypatch.setattr(app.server_module.DashboardServer, "start_ingest", MagicMock())
    monkeypatch.setattr(app.server_module.DashboardServer, "stop_ingest", stop_ingest)
    created = _spy_servers(monkeypatch)
    with pytest.raises(RuntimeError, match="no threads"):
        app.run_dashboard(port=0, open_browser=False)
    stop_ingest.assert_called_once()
    assert created[0].socket.fileno() == -1


def test_explicit_port_taken_on_wildcard_exit_1(
    stats_dirs: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """An explicit port another process holds on every interface is an error."""
    monkeypatch.setattr(app, "static_root", lambda: STATIC)
    with socket.socket() as taken:
        taken.bind(("0.0.0.0", 0))  # noqa: S104
        taken.listen()
        port = taken.getsockname()[1]
        assert app.run_dashboard(port=port, open_browser=False) == 1
    assert f"could not listen on 127.0.0.1:{port}" in capsys.readouterr().err


def test_no_ui_exit_1(
    stats_dirs: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Without a built frontend the dashboard refuses to start."""
    monkeypatch.setattr(app, "static_root", lambda: None)
    assert app.run_dashboard(port=0, open_browser=False) == 1
    assert "no dashboard UI" in capsys.readouterr().err
    assert InstanceLock.acquire(stats_dirs[1]) is not None


def test_explicit_port_in_use_exit_1(
    stats_dirs: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """An explicit port that is taken is an error, not a fallback."""
    monkeypatch.setattr(app, "static_root", lambda: STATIC)
    with socket.socket() as taken:
        taken.bind(("127.0.0.1", 0))
        taken.listen()
        port = taken.getsockname()[1]
        assert app.run_dashboard(port=port, open_browser=False) == 1
    assert f"could not listen on 127.0.0.1:{port}" in capsys.readouterr().err


def test_default_port_in_use_falls_back(
    stats_dirs: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    opener: MagicMock,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """With no explicit port, a taken default falls back to a free port and serves."""
    monkeypatch.setattr(app, "static_root", lambda: STATIC)
    monkeypatch.setattr(app, "DEFAULT_PORT", _taken_port())
    monkeypatch.setattr(app, "_wait", _interrupt)
    assert app.run_dashboard(port=None, open_browser=True) == 0
    err = capsys.readouterr().err
    assert "gate-cache dashboard at http://127.0.0.1:" in err
    assert "recording is off" in err
    opener.assert_called_once()
    assert inbox_path().parent.exists()


_HOLDERS: list[socket.socket] = []


def _taken_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen()
    _HOLDERS.append(sock)
    return sock.getsockname()[1]


def _interrupt(thread: object) -> None:
    raise KeyboardInterrupt


@pytest.fixture(autouse=True)
def _close_holders() -> Iterator[None]:
    yield
    while _HOLDERS:
        _HOLDERS.pop().close()


def test_newer_archive_exit_1(
    stats_dirs: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """An archive from a newer gate-cache is reported, not crashed on."""
    monkeypatch.setattr(app, "static_root", lambda: STATIC)
    Archive.open(archive_path()).close()
    with closing(sqlite3.connect(archive_path())) as conn, conn:
        conn.execute("UPDATE meta SET value = '999' WHERE key = 'schema_version'")
    assert app.run_dashboard(port=0, open_browser=False) == 1
    assert "newer than the supported version" in capsys.readouterr().err


def test_cli_rejects_bad_port(monkeypatch: pytest.MonkeyPatch) -> None:
    """A non-numeric or out-of-range port is a usage error."""
    for bad in ("0x", "0", "70000"):
        assert invoke(monkeypatch, "dashboard", "--port", bad) == 2


def test_cli_dashboard_routes(monkeypatch: pytest.MonkeyPatch) -> None:
    """The dashboard command passes its options through."""
    run = MagicMock(return_value=0)
    monkeypatch.setattr(app, "run_dashboard", run)
    assert invoke(monkeypatch, "dashboard", "--port", "9000", "--no-browser") == 0
    run.assert_called_once_with(port=9000, open_browser=False)


def test_cli_stats_clear_routes(monkeypatch: pytest.MonkeyPatch) -> None:
    """`stats clear` dispatches to stats_clear."""
    clear = MagicMock(return_value=0)
    monkeypatch.setattr(app, "stats_clear", clear)
    assert invoke(monkeypatch, "stats", "clear") == 0
    clear.assert_called_once_with(confirmed=False)


def test_cli_stats_clear_yes_skips_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    """`stats clear --yes` and `-y` clear without asking."""
    clear = MagicMock(return_value=0)
    monkeypatch.setattr(app, "stats_clear", clear)
    assert invoke(monkeypatch, "stats", "clear", "--yes") == 0
    assert invoke(monkeypatch, "stats", "clear", "-y") == 0
    assert clear.call_args_list == [((), {"confirmed": True})] * 2


def test_cli_stats_yes_needs_clear(monkeypatch: pytest.MonkeyPatch) -> None:
    """--yes with any action other than clear is a usage error."""
    for args in (("--yes",), ("on", "--yes"), ("off", "-y")):
        assert invoke(monkeypatch, "stats", *args) == 2
