"""Entry point for the `dashboard` command."""

from __future__ import annotations

import sqlite3
import threading
import webbrowser
from typing import TYPE_CHECKING

from gate_cache.console import say
from gate_cache.dashboard import server as server_module
from gate_cache.dashboard.server import static_root
from gate_cache.stats import config
from gate_cache.stats.archive import Archive, ArchiveVersionError, archive_path
from gate_cache.stats.lock import InstanceLock, running_url
from gate_cache.stats.recorder import inbox_path

if TYPE_CHECKING:
    from pathlib import Path

DEFAULT_PORT = 7878


def _bind(port: int | None, static_dir: Path) -> server_module.DashboardServer | None:
    """Bind the server, falling back to a free port only when no port was requested."""
    wanted = DEFAULT_PORT if port is None else port
    try:
        return _make(wanted, static_dir)
    except OSError as error:
        if port is not None:
            say(f"could not listen on 127.0.0.1:{port}: {error.strerror or error}")
            return None
    try:
        return _make(0, static_dir)
    except OSError as error:
        say(f"could not listen on 127.0.0.1: {error.strerror or error}")
        return None


def _make(port: int, static_dir: Path) -> server_module.DashboardServer:
    return server_module.make_server(
        port=port, archive_path=archive_path(), inbox=inbox_path(), static_dir=static_dir
    )


def run_dashboard(*, port: int | None, open_browser: bool) -> int:
    """Serve the dashboard until interrupted.

    Args:
        port: Port to bind, or None for 7878 with a free-port fallback.
        open_browser: Whether to open the dashboard in the default browser.

    Returns:
        The process exit code.
    """
    state = config.state_dir()
    try:
        lock = InstanceLock.acquire(state)
    except OSError as error:
        say(f"could not use {state}: {error.strerror or error}")
        return 1
    if lock is None:
        url = running_url(state)
        # The lock without a URL is a dashboard still starting or `stats clear` at its prompt.
        say(
            f"dashboard already running at {url}"
            if url
            else "dashboard already running, or stats clear is in progress"
        )
        if url and open_browser:
            webbrowser.open(url)
        return 0
    try:
        return _serve(lock, port=port, open_browser=open_browser)
    finally:
        lock.release()


def _serve(lock: InstanceLock, *, port: int | None, open_browser: bool) -> int:
    """Run the server while holding the instance lock."""
    static_dir = static_root()
    if static_dir is None:
        say(server_module.NO_UI_MESSAGE)
        return 1
    try:
        with Archive.open(archive_path()) as archive:
            server = _bind(port, static_dir)
            if server is None:
                return 1
            try:
                lock.write_url(server.url)
                archive.ingest(inbox_path())
            except (OSError, sqlite3.Error) as error:
                say(str(error))
                server.server_close()
                return 1
            except BaseException:
                server.server_close()
                raise
    except (ArchiveVersionError, sqlite3.Error, OSError) as error:
        say(str(error))
        return 1
    return _run_server(server, open_browser=open_browser)


def _wait(thread: threading.Thread) -> None:
    """Block until the serve thread ends; the short join keeps Ctrl-C responsive."""
    while thread.is_alive():
        thread.join(0.5)


def _run_server(server: server_module.DashboardServer, *, open_browser: bool) -> int:
    """Serve until Ctrl-C, then shut down."""
    thread: threading.Thread | None = None
    try:
        server.start_ingest()
        say(f"gate-cache dashboard at {server.url} (Ctrl-C to stop)")
        if not config.stats_setting().enabled:
            say("recording is off; turn it on with: gate-cache stats on")
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
    return 0
