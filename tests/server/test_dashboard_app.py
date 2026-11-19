"""Tests for the dashboard command."""

import inspect
import socket
import sqlite3
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from gate_cache.dashboard import app
from gate_cache.stats.archive import Archive, archive_path
from gate_cache.stats.lock import InstanceLock
from gate_cache.stats.recorder import inbox_path

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
    assert app.DASHBOARD_RUNNING.format(url="http://127.0.0.1:7878") in capsys.readouterr().err
    opener.assert_called_once_with("http://127.0.0.1:7878")


def test_dashboard_during_stats_clear_prompt(
    stats_dirs: tuple[Path, Path], opener: MagicMock, capsys: pytest.CaptureFixture[str]
) -> None:
    """A dashboard started while `stats clear` holds the lock names every possible holder."""
    held = InstanceLock.acquire(stats_dirs[1])
    assert held is not None
    try:
        assert app.run_dashboard(port=0, open_browser=True) == 0
    finally:
        held.release()
    assert app.DASHBOARD_BUSY in capsys.readouterr().err
    opener.assert_not_called()


def test_second_dashboard_no_browser(lock: InstanceLock, opener: MagicMock) -> None:
    """--no-browser suppresses opening the running dashboard."""
    try:
        assert app.run_dashboard(port=0, open_browser=False) == 0
    finally:
        lock.release()
    opener.assert_not_called()


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
    assert "dashboard UI" in capsys.readouterr().err
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
    monkeypatch.setattr(app.config, "DASHBOARD_PORT", _taken_port())
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


def test_run_dashboard_accepts_the_cli_arguments() -> None:
    """The `dashboard` command calls run_dashboard with these keywords, and core never reruns for it."""
    inspect.signature(app.run_dashboard).bind(port=9000, open_browser=False)
