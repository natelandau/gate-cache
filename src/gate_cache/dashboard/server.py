"""The dashboard HTTP server: a read-only JSON API plus the built frontend."""

from __future__ import annotations

import contextlib
import errno
import json
import math
import mimetypes
import re
import socket
import sqlite3
import threading
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qs, unquote, urlsplit

from gate_cache.console import say
from gate_cache.stats import config, queries
from gate_cache.stats.archive import Archive
from gate_cache.stats.queries import Filters

if TYPE_CHECKING:
    from collections.abc import Callable

HOST = "127.0.0.1"
NO_UI_MESSAGE = "This install has no dashboard UI. Install with: uv tool install gate-cache"

_MAX_LIMIT = 500
_OK = 200
_BAD_REQUEST = 400
_FORBIDDEN = 403
_NOT_FOUND = 404
_SERVER_ERROR = 500
_UNAVAILABLE = 503
_INTEGER_RE = re.compile(r"-?[0-9]+")
_PROBE_TIMEOUT = 0.2


class _BadRequestError(ValueError):
    """A query parameter is missing or malformed."""


def static_root() -> Path | None:
    """Return the packaged frontend directory, or None when this install has no UI."""
    root = Path(str(resources.files("gate_cache.dashboard") / "static"))
    return root if (root / "index.html").is_file() else None


def _time(params: dict[str, list[str]], key: str) -> float | None:
    """Return a time query parameter as Unix seconds, or None when absent.

    Accept Unix seconds or an ISO 8601 date or datetime; a value without an offset is UTC.
    """
    if key not in params:
        return None
    text = params[key][-1]
    if queries.NUMBER_RE.fullmatch(text):
        value = float(text)
        if not math.isfinite(value):
            msg = f"{key} must be a finite number"
            raise _BadRequestError(msg)
        return value
    try:
        moment = datetime.fromisoformat(text)
    except ValueError as error:
        msg = f"{key} must be Unix seconds or an ISO date"
        raise _BadRequestError(msg) from error
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.timestamp()


def _text(params: dict[str, list[str]], key: str) -> str | None:
    """Return a non-empty text query parameter, or None when absent or empty."""
    return params[key][-1] or None if key in params else None


def _filters(params: dict[str, list[str]]) -> Filters:
    """Build query filters from the common parameters."""
    return Filters(
        repo=_text(params, "repo"),
        start=_time(params, "from"),
        end=_time(params, "to"),
        tz=_text(params, "tz") or "UTC",
    )


def _open_reader(path: Path) -> sqlite3.Connection:
    """Open a read-only connection owned by the calling thread."""
    return sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)


class _Handler(BaseHTTPRequestHandler):
    """Route GET requests to the API or the static frontend."""

    server: DashboardServer  # ty: ignore[incompatible-mutable-override]
    _headers_sent = False

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        """Silence request logging."""

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self._headers_sent = True
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, payload: dict[str, Any]) -> None:
        self._send(status, json.dumps(payload).encode(), "application/json")

    def do_GET(self) -> None:
        """Serve one request."""
        self._headers_sent = False
        if self.headers.get("Host") not in self.server.allowed_hosts:
            self._json(_FORBIDDEN, {"error": "forbidden host"})
            return
        parts = urlsplit(self.path)
        is_api = parts.path.startswith("/api/")
        try:
            if is_api:
                self._api(parts.path, parse_qs(parts.query, keep_blank_values=True))
            else:
                self._static(parts.path)
        except Exception:  # noqa: BLE001
            # Never leak a traceback to the client; the connection may already be gone.
            if self._headers_sent:
                # A second status line would corrupt the response already under way.
                self.close_connection = True
                return
            with contextlib.suppress(OSError):
                if is_api:
                    self._json(_SERVER_ERROR, {"error": "internal error"})
                else:
                    self._send(_SERVER_ERROR, b"internal error", "text/plain; charset=utf-8")

    def _api(self, path: str, params: dict[str, list[str]]) -> None:
        route = path.removeprefix("/api/v1/") if path.startswith("/api/v1/") else None
        if route is None or route not in _ROUTES:
            self._json(_NOT_FOUND, {"error": f"unknown endpoint: {path}"})
            return
        try:
            body = _ROUTES[route](self.server, params)
        except (ValueError, OverflowError) as error:
            self._json(_BAD_REQUEST, {"error": str(error)})
        except sqlite3.Error as error:
            self._json(_SERVER_ERROR, {"error": f"archive unavailable: {error}"})
        else:
            self._json(_OK, body)

    def _static(self, path: str) -> None:
        root = self.server.static_dir
        if root is None:
            self._send(_UNAVAILABLE, NO_UI_MESSAGE.encode(), "text/plain; charset=utf-8")
            return
        base = root.resolve()
        target = base / "index.html"
        try:
            candidate = (base / unquote(path).lstrip("/")).resolve()
            if candidate.is_relative_to(base) and candidate.is_file():
                target = candidate
        except (OSError, ValueError):
            pass
        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if content_type.startswith("text/") or content_type.endswith(("javascript", "json")):
            content_type += "; charset=utf-8"
        self._send(_OK, target.read_bytes(), content_type)


def _query(
    server: DashboardServer, run: Callable[[sqlite3.Connection], dict[str, Any]]
) -> dict[str, Any]:
    """Run a query on a fresh read connection so no connection crosses threads."""
    conn = _open_reader(server.archive_file)
    try:
        return run(conn)
    finally:
        conn.close()


def _freshness(server: DashboardServer, _params: dict[str, list[str]]) -> dict[str, Any]:
    def run(conn: sqlite3.Connection) -> dict[str, Any]:
        meta = dict(conn.execute("SELECT key, value FROM meta").fetchall())
        last = meta.get("last_ingest")
        return {
            "ingest_count": int(meta.get("ingest_count") or 0),
            "last_ingest": float(last) if last is not None else None,
            "recording": config.stats_setting().enabled,
            "ingest_error": server.ingest_error,
        }

    return _query(server, run)


def _gate_detail(server: DashboardServer, params: dict[str, list[str]]) -> dict[str, Any]:
    name = _text(params, "name")
    if name is None:
        msg = "name is required"
        raise _BadRequestError(msg)
    filters = _filters(params)
    return _query(
        server,
        lambda c: queries.gate_detail(c, filters, repo=filters.repo, name=name),
    )


def _activity(server: DashboardServer, params: dict[str, list[str]]) -> dict[str, Any]:
    filters = _filters(params)
    text = params["limit"][-1] if "limit" in params else "100"
    if _INTEGER_RE.fullmatch(text) is None:
        msg = "limit must be an integer"
        raise _BadRequestError(msg)
    limit = max(1, min(int(text), _MAX_LIMIT))
    before = _text(params, "before")
    outcome = _text(params, "outcome")
    return _query(
        server,
        lambda c: queries.activity(c, filters, limit=limit, before=before, outcome=outcome),
    )


def _simple(
    func: Callable[[sqlite3.Connection, Filters], dict[str, Any]],
) -> Callable[[DashboardServer, dict[str, list[str]]], dict[str, Any]]:
    def route(server: DashboardServer, params: dict[str, list[str]]) -> dict[str, Any]:
        filters = _filters(params)
        return _query(server, lambda c: func(c, filters))

    return route


_ROUTES: dict[str, Callable[[DashboardServer, dict[str, list[str]]], dict[str, Any]]] = {
    "freshness": _freshness,
    "summary": _simple(queries.summary),
    "gates": _simple(queries.gates),
    "gate": _gate_detail,
    "repos": _simple(queries.repos),
    "activity": _activity,
    "flaky": _simple(queries.flaky),
}


def _accepts_connections(port: int) -> bool:
    """Return whether something already listens on the loopback port.

    Address reuse lets a bind to 127.0.0.1 succeed on macOS while another process listens on
    the wildcard address, so a connect probe catches what the bind misses.
    """
    try:
        with socket.create_connection((HOST, port), timeout=_PROBE_TIMEOUT):
            return True
    except OSError:
        return False


class DashboardServer(ThreadingHTTPServer):
    """A loopback-only server that ingests the inbox in the background."""

    daemon_threads = True

    def __init__(
        self, *, port: int, archive_file: Path, inbox: Path, static_dir: Path | None
    ) -> None:
        """Bind 127.0.0.1 on port; 0 picks a free port.

        Raises:
            OSError: If the port is already in use or cannot be bound.
        """
        if port and _accepts_connections(port):
            raise OSError(errno.EADDRINUSE, "Address already in use")
        super().__init__((HOST, port), _Handler)
        self.port: int = self.server_address[1]
        self.url = f"http://{HOST}:{self.port}"
        self.archive_file = archive_file
        self.inbox = inbox
        self.static_dir = static_dir
        self.allowed_hosts = {f"{HOST}:{self.port}", f"localhost:{self.port}"}
        self.ingest_error: str | None = None
        self._ingest_error_type: type[BaseException] | None = None
        self._stop = threading.Event()
        self._ingester: threading.Thread | None = None

    def start_ingest(self, interval: float = 1.0) -> None:
        """Ingest the inbox every interval seconds on a background thread."""

        def loop() -> None:
            # The connection is opened here because it belongs to the thread that uses it.
            archive: Archive | None = None
            try:
                while not self._stop.wait(interval):
                    try:
                        if archive is None:
                            archive = Archive.open(self.archive_file)
                        archive.ingest(self.inbox)
                    except Exception as error:  # noqa: BLE001
                        # The thread must outlive any failure so the next tick can recover.
                        self._record_ingest_error(error)
                    else:
                        self.ingest_error = None
                        self._ingest_error_type = None
            finally:
                if archive is not None:
                    archive.close()

        self._ingester = threading.Thread(target=loop, name="gate-cache-ingest", daemon=True)
        self._ingester.start()

    def _record_ingest_error(self, error: Exception) -> None:
        """Remember the latest ingest failure and report it once per kind of failure."""
        message = str(error) or type(error).__name__
        if type(error) is not self._ingest_error_type:
            say(f"dashboard ingest failed: {message}")
        self._ingest_error_type = type(error)
        self.ingest_error = message

    def stop_ingest(self) -> None:
        """Stop the ingest thread and wait for it to finish."""
        self._stop.set()
        if self._ingester is not None:
            self._ingester.join()

    def shutdown(self) -> None:
        """Stop the ingest thread and the serve loop; call only once serving has started."""
        self.stop_ingest()
        super().shutdown()


def make_server(
    *, port: int, archive_path: Path, inbox: Path, static_dir: Path | None
) -> DashboardServer:
    """Create a dashboard server bound to 127.0.0.1.

    Args:
        port: Port to bind; 0 picks a free port.
        archive_path: Location of the SQLite archive; each thread opens its own connection.
        inbox: Path of the live `events.jsonl`.
        static_dir: Directory of the built frontend, or None when absent.

    Returns:
        The bound server, not yet serving.
    """
    return DashboardServer(port=port, archive_file=archive_path, inbox=inbox, static_dir=static_dir)
