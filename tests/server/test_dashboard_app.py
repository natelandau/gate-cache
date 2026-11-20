"""Tests for the dashboard command."""

import dataclasses
import inspect
import socket
import sqlite3
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from gate_cache.dashboard import app
from gate_cache.dashboard.app import DashboardError, DashboardStart
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


def test_second_dashboard_reports_running(lock: InstanceLock, opener: MagicMock) -> None:
    """A second dashboard reports the running URL and opens it."""
    starts: list[DashboardStart] = []
    try:
        app.run_dashboard(port=0, open_browser=True, on_start=starts.append)
    finally:
        lock.release()
    assert [(s.url, s.port, s.already_running, s.busy) for s in starts] == [
        ("http://127.0.0.1:7878", 7878, True, False)
    ]
    opener.assert_called_once_with("http://127.0.0.1:7878")


def test_dashboard_during_stats_clear_prompt(
    stats_dirs: tuple[Path, Path], opener: MagicMock
) -> None:
    """A dashboard started while another process holds the lock with no address is busy."""
    held = InstanceLock.acquire(stats_dirs[1])
    assert held is not None
    starts: list[DashboardStart] = []
    try:
        app.run_dashboard(port=0, open_browser=True, on_start=starts.append)
    finally:
        held.release()
    assert [(s.url, s.port, s.already_running, s.busy) for s in starts] == [
        (None, None, False, True)
    ]
    opener.assert_not_called()


def test_second_dashboard_no_browser(lock: InstanceLock, opener: MagicMock) -> None:
    """--no-browser suppresses opening the running dashboard."""
    try:
        app.run_dashboard(port=0, open_browser=False, on_start=lambda _: None)
    finally:
        lock.release()
    opener.assert_not_called()


def test_unusable_state_dir_exit_1(stats_dirs: tuple[Path, Path]) -> None:
    """A state directory that cannot be created is reported, not raised."""
    stats_dirs[1].write_text("a file, not a directory")
    with pytest.raises(DashboardError) as raised:
        app.run_dashboard(port=0, open_browser=False, on_start=_no_start)
    assert "could not use" in str(raised.value)


def test_fallback_bind_failure_exit_1(
    stats_dirs: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When even a free port cannot be bound, the dashboard reports it and exits 1."""
    monkeypatch.setattr(app, "static_root", lambda: STATIC)
    monkeypatch.setattr(app.server_module, "make_server", MagicMock(side_effect=OSError(1, "nope")))
    with pytest.raises(DashboardError) as raised:
        app.run_dashboard(port=None, open_browser=False, on_start=_no_start)
    assert "could not listen on 127.0.0.1: nope" in str(raised.value)


def test_startup_failure_closes_the_socket(
    stats_dirs: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
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
    with pytest.raises(DashboardError) as raised:
        app.run_dashboard(port=0, open_browser=False, on_start=_no_start)
    assert created[0].socket.fileno() == -1
    assert "ro" in str(raised.value)


def _no_start(_: DashboardStart) -> None:
    """Fail when the dashboard reports a start it should not have reached."""
    pytest.fail("the dashboard started")


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
        app.run_dashboard(port=0, open_browser=False, on_start=_no_start)
    assert created[0].socket.fileno() == -1


def test_run_failure_before_serving_shuts_down(
    stats_dirs: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch, opener: MagicMock
) -> None:
    """A failure before the serve loop starts still stops ingest and closes the socket."""
    monkeypatch.setattr(app, "static_root", lambda: STATIC)
    opener.side_effect = RuntimeError("no browser")
    created = _spy_servers(monkeypatch)
    with pytest.raises(RuntimeError, match="no browser"):
        app.run_dashboard(port=0, open_browser=True, on_start=lambda _: None)
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
        app.run_dashboard(port=0, open_browser=False, on_start=lambda _: None)
    stop_ingest.assert_called_once()
    assert created[0].socket.fileno() == -1


def test_explicit_port_taken_on_wildcard_exit_1(
    stats_dirs: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An explicit port another process holds on every interface is an error."""
    monkeypatch.setattr(app, "static_root", lambda: STATIC)
    with socket.socket() as taken:
        taken.bind(("0.0.0.0", 0))  # noqa: S104
        taken.listen()
        port = taken.getsockname()[1]
        with pytest.raises(DashboardError) as raised:
            app.run_dashboard(port=port, open_browser=False, on_start=_no_start)
    assert f"could not listen on 127.0.0.1:{port}" in str(raised.value)


def test_no_ui_exit_1(
    stats_dirs: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without a built frontend the dashboard refuses to start."""
    monkeypatch.setattr(app, "static_root", lambda: None)
    with pytest.raises(DashboardError) as raised:
        app.run_dashboard(port=0, open_browser=False, on_start=_no_start)
    assert "dashboard UI" in str(raised.value)
    assert InstanceLock.acquire(stats_dirs[1]) is not None


def test_explicit_port_in_use_exit_1(
    stats_dirs: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An explicit port that is taken is an error, not a fallback."""
    monkeypatch.setattr(app, "static_root", lambda: STATIC)
    with socket.socket() as taken:
        taken.bind(("127.0.0.1", 0))
        taken.listen()
        port = taken.getsockname()[1]
        with pytest.raises(DashboardError) as raised:
            app.run_dashboard(port=port, open_browser=False, on_start=_no_start)
    assert f"could not listen on 127.0.0.1:{port}" in str(raised.value)


def test_default_port_in_use_falls_back(
    stats_dirs: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    opener: MagicMock,
) -> None:
    """With no explicit port, a taken default falls back to a free port and serves."""
    monkeypatch.setattr(app, "static_root", lambda: STATIC)
    monkeypatch.setattr(app.config, "DASHBOARD_PORT", _taken_port())
    monkeypatch.setattr(app, "_wait", _interrupt)
    starts: list[DashboardStart] = []
    app.run_dashboard(port=None, open_browser=True, on_start=starts.append)
    assert len(starts) == 1
    assert starts[0].url is not None
    assert starts[0].url.startswith("http://127.0.0.1:")
    assert not starts[0].already_running
    assert not starts[0].recording
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
) -> None:
    """An archive from a newer gate-cache is reported, not crashed on."""
    monkeypatch.setattr(app, "static_root", lambda: STATIC)
    Archive.open(archive_path()).close()
    with closing(sqlite3.connect(archive_path())) as conn, conn:
        conn.execute("UPDATE meta SET value = '999' WHERE key = 'schema_version'")
    with pytest.raises(DashboardError) as raised:
        app.run_dashboard(port=0, open_browser=False, on_start=_no_start)
    assert "newer than the supported version" in str(raised.value)


def test_run_dashboard_accepts_the_cli_arguments() -> None:
    """The `dashboard` command calls run_dashboard with these keywords, and core never reruns for it."""
    inspect.signature(app.run_dashboard).bind(port=9000, open_browser=False, on_start=print)


@pytest.mark.parametrize(
    "published",
    [
        "http://127.0.0.1:notaport",
        "http://127.0.0.1:99999/",
        "file:///etc/passwd",
        "http://example.com:7878/",
    ],
)
def test_published_url_other_than_loopback_is_never_opened(
    stats_dirs: tuple[Path, Path], lock: InstanceLock, opener: MagicMock, published: str
) -> None:
    """Only a loopback HTTP address in the URL file reaches the browser."""
    (stats_dirs[1] / "dashboard.url").write_text(published, encoding="utf-8")
    starts: list[DashboardStart] = []
    try:
        app.run_dashboard(port=0, open_browser=True, on_start=starts.append)
    finally:
        lock.release()
    assert [(s.url, s.port, s.busy) for s in starts] == [(None, None, True)]
    opener.assert_not_called()


def test_the_dashboard_command_contract() -> None:
    """The names the `dashboard` command reads from this module stay available."""
    fields = {field.name for field in dataclasses.fields(DashboardStart)}
    assert fields == {"url", "port", "already_running", "busy", "recording"}
    assert issubclass(DashboardError, Exception)
    assert "{url}" in app.DASHBOARD_RUNNING
    assert isinstance(app.DASHBOARD_BUSY, str)
