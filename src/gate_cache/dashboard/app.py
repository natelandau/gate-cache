"""Entry point for the `dashboard` command."""

from __future__ import annotations

import sqlite3
import threading
import webbrowser
from dataclasses import dataclass
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from gate_cache.dashboard import server as server_module
from gate_cache.dashboard.server import static_root
from gate_cache.stats import config
from gate_cache.stats.archive import ARCHIVE_NAME, Archive, ArchiveVersionError
from gate_cache.stats.lock import InstanceLock, running_url
from gate_cache.stats.recorder import INBOX_NAME

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

DASHBOARD_RUNNING = "dashboard already running at {url}"
DASHBOARD_BUSY = (
    "dashboard already running, or stats clear or a stats report is in progress. "
    "A report ends in a moment, so try again."
)


class DashboardError(Exception):
    """The dashboard could not start; the message says why."""


@dataclass(frozen=True)
class DashboardStart:
    """What the dashboard command reports once it knows where the dashboard is.

    Attributes:
        url: Address of the dashboard, or None when another process holds the lock without one.
        port: Port of the dashboard, or None when url is None.
        already_running: True when a dashboard was already serving at url.
        busy: True when the lock is held and no address is published.
        recording: Whether stats recording is on.
    """

    url: str | None
    port: int | None
    already_running: bool
    busy: bool
    recording: bool


def _bind(port: int | None, state: Path, static_dir: Path) -> server_module.DashboardServer:
    """Bind the server, falling back to a free port only when no port was requested."""
    wanted = config.DASHBOARD_PORT if port is None else port
    try:
        return _make(wanted, state, static_dir)
    except OSError as error:
        if port is not None:
            message = f"could not listen on 127.0.0.1:{port}: {error.strerror or error}"
            raise DashboardError(message) from error
    try:
        return _make(0, state, static_dir)
    except OSError as error:
        message = f"could not listen on 127.0.0.1: {error.strerror or error}"
        raise DashboardError(message) from error


def _make(port: int, state: Path, static_dir: Path) -> server_module.DashboardServer:
    return server_module.make_server(
        port=port,
        archive_path=state / ARCHIVE_NAME,
        inbox=state / INBOX_NAME,
        static_dir=static_dir,
    )


def _port_of(url: str | None) -> int | None:
    """Return the port in a published URL, or None when there is none or the file is corrupt."""
    if url is None:
        return None
    try:
        return urlsplit(url).port
    except ValueError:
        return None


def run_dashboard(
    *, port: int | None, open_browser: bool, on_start: Callable[[DashboardStart], None]
) -> None:
    """Serve the dashboard until interrupted.

    Args:
        port: Port to bind, or None for the default dashboard port with a free-port fallback.
        open_browser: Whether to open the dashboard in the default browser.
        on_start: Called once, when serving begins or when another process already holds the
            dashboard, so the caller can report where it is.

    Raises:
        DashboardError: When the dashboard cannot start.
    """
    state = config.state_dir()
    try:
        lock = InstanceLock.acquire(state)
    except OSError as error:
        message = f"could not use {state}: {error.strerror or error}"
        raise DashboardError(message) from error
    if lock is None:
        url = running_url(state)
        # The lock without a URL is a dashboard still starting, `stats clear` at its prompt,
        # or `stats report` reading the record.
        on_start(
            DashboardStart(
                url=url,
                port=_port_of(url),
                already_running=url is not None,
                busy=url is None,
                recording=config.stats_setting().enabled,
            )
        )
        if url and open_browser:
            webbrowser.open(url)
        return
    try:
        _serve(lock, state=state, port=port, open_browser=open_browser, on_start=on_start)
    finally:
        lock.release()


def _serve(
    lock: InstanceLock,
    *,
    state: Path,
    port: int | None,
    open_browser: bool,
    on_start: Callable[[DashboardStart], None],
) -> None:
    """Run the server on the locked data directory while holding the instance lock."""
    static_dir = static_root()
    if static_dir is None:
        raise DashboardError(server_module.no_ui_message())
    try:
        with Archive.open(state / ARCHIVE_NAME) as archive:
            server = _bind(port, state, static_dir)
            try:
                lock.write_url(server.url)
                archive.ingest(state / INBOX_NAME)
            except (OSError, sqlite3.Error) as error:
                server.server_close()
                raise DashboardError(str(error)) from error
            except BaseException:
                server.server_close()
                raise
    except (ArchiveVersionError, sqlite3.Error, OSError) as error:
        raise DashboardError(str(error)) from error
    _run_server(server, open_browser=open_browser, on_start=on_start)


def _wait(thread: threading.Thread) -> None:
    """Block until the serve thread ends; the short join keeps Ctrl-C responsive."""
    while thread.is_alive():
        thread.join(0.5)


def _run_server(
    server: server_module.DashboardServer,
    *,
    open_browser: bool,
    on_start: Callable[[DashboardStart], None],
) -> None:
    """Serve until Ctrl-C, then shut down."""
    thread: threading.Thread | None = None
    try:
        server.start_ingest()
        on_start(
            DashboardStart(
                url=server.url,
                port=urlsplit(server.url).port,
                already_running=False,
                busy=False,
                recording=config.stats_setting().enabled,
            )
        )
        if open_browser:
            webbrowser.open(server.url)
        serving = threading.Thread(target=server.serve_forever, daemon=True)
        serving.start()
        thread = serving
        _wait(thread)
    except KeyboardInterrupt:
        pass
    finally:
        # The base shutdown waits for serve_forever, so it would hang if serving never began.
        if thread is None:
            server.stop_ingest()
        else:
            server.shutdown()
        server.server_close()
