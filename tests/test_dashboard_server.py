"""Tests for the dashboard HTTP server and its instance lock."""

import http.client
import json
import socket
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from gate_cache.dashboard import server as server_module
from gate_cache.dashboard.lock import InstanceLock, running_url
from gate_cache.dashboard.server import DashboardServer, make_server
from gate_cache.stats.archive import Archive, archive_path
from gate_cache.stats.recorder import Event, inbox_path

STATIC = Path(__file__).parent / "fixtures" / "static"


def _event(ts: float) -> Event:
    return Event(
        ts=ts,
        repo="/r/.git",
        name="lint",
        tree="abc",
        paths=(),
        outcome="pass",
        duration=1.0,
        saved=None,
        exit_code=0,
        reason=None,
    )


def _serve(server: DashboardServer) -> Iterator[DashboardServer]:
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


@pytest.fixture
def archive(stats_dirs: tuple[Path, Path]) -> Iterator[Archive]:
    """Open the archive in the state directory."""
    with Archive.open(archive_path()) as opened:
        yield opened


@pytest.fixture
def server(archive: Archive) -> Iterator[DashboardServer]:
    """Serve the stub frontend on a free port."""
    yield from _serve(
        make_server(port=0, archive_path=archive_path(), inbox=inbox_path(), static_dir=STATIC)
    )


@pytest.fixture
def bare_server(archive: Archive) -> Iterator[DashboardServer]:
    """Serve without a frontend."""
    yield from _serve(
        make_server(port=0, archive_path=archive_path(), inbox=inbox_path(), static_dir=None)
    )


def fetch(
    srv: DashboardServer, path: str, host: str | None = None
) -> tuple[int, dict[str, str], bytes]:
    """GET path with an optional Host header; return status, headers, body."""
    conn = http.client.HTTPConnection("127.0.0.1", srv.port, timeout=5)
    try:
        conn.putrequest("GET", path, skip_host=True)
        conn.putheader("Host", host or f"127.0.0.1:{srv.port}")
        conn.endheaders()
        resp = conn.getresponse()
        return resp.status, dict(resp.getheaders()), resp.read()
    finally:
        conn.close()


def get(srv: DashboardServer, path: str, host: str | None = None) -> tuple[int, dict]:
    """GET a JSON path."""
    status, _, body = fetch(srv, path, host)
    return status, json.loads(body)


def text(srv: DashboardServer, path: str) -> str:
    """GET a path and return the body as text."""
    return fetch(srv, path)[2].decode()


def test_api_summary_shape(server: DashboardServer) -> None:
    """Summary returns the query body."""
    status, body = get(server, "/api/v1/summary")
    assert status == 200
    assert set(body) >= {"time_saved", "skip_rate", "daily"}


@pytest.mark.parametrize(
    "path", ["gates", "repos", "activity", "flaky", "freshness", "gate?name=lint"]
)
def test_api_endpoints_respond(server: DashboardServer, path: str) -> None:
    """Every endpoint answers 200 JSON with no-store caching."""
    status, headers, body = fetch(server, f"/api/v1/{path}")
    assert status == 200
    assert isinstance(json.loads(body), dict)
    assert headers["Cache-Control"] == "no-store"
    assert headers["Content-Type"] == "application/json"


def test_bad_host_rejected(server: DashboardServer) -> None:
    """A foreign Host header is refused before routing."""
    assert get(server, "/api/v1/summary", host="evil.example:80")[0] == 403
    assert fetch(server, "/", host="evil.example:80")[0] == 403


def test_localhost_host_ok(server: DashboardServer) -> None:
    """Localhost with the right port is accepted."""
    assert fetch(server, "/", host=f"localhost:{server.port}")[0] == 200


def test_unknown_api_404_json(server: DashboardServer) -> None:
    """An unknown API path is a JSON 404."""
    status, body = get(server, "/api/v1/nope")
    assert status == 404
    assert "error" in body
    assert get(server, "/api/other")[0] == 404


def test_spa_fallback(server: DashboardServer) -> None:
    """An unknown page path serves index.html."""
    assert '<div id="app">' in text(server, "/gates")


def test_static_asset(server: DashboardServer) -> None:
    """An existing asset is served with its own content type."""
    status, headers, body = fetch(server, "/assets/app.js")
    assert status == 200
    assert body.decode().startswith("//")
    assert "javascript" in headers["Content-Type"]


@pytest.mark.parametrize("path", ["/../../etc/passwd", "/%2e%2e/%2e%2e/etc/passwd", "/a%00b"])
def test_traversal_blocked(server: DashboardServer, path: str) -> None:
    """Paths outside the static root fall back to index.html."""
    assert '<div id="app">' in text(server, path)


def test_no_cors(server: DashboardServer) -> None:
    """No CORS header is ever sent."""
    assert "Access-Control-Allow-Origin" not in fetch(server, "/api/v1/summary")[1]


@pytest.mark.parametrize(
    "query",
    [
        "summary?from=abc",
        "summary?to=nan",
        "summary?tz=Nope/Zone",
        "activity?limit=x",
        "activity?before=garbage",
        "activity?before=1.0:99999999999999999999",
        "activity?before=1_0:1",
        "activity?limit=1_0",
        "activity?limit=%2010",
        "activity?limit=1.5",
        "activity?outcome=exploded",
        "summary?from=1_0",
        "summary?from=%201",
        "summary?to=inf",
        "summary?to=1e400",
        "summary?from=2023-13-40",
        "gate",
    ],
)
def test_bad_query_400(server: DashboardServer, query: str) -> None:
    """Malformed parameters are a JSON 400."""
    status, body = get(server, f"/api/v1/{query}")
    assert status == 400
    assert "error" in body


def test_activity_limit_clamped(server: DashboardServer) -> None:
    """An out-of-range limit is clamped, not rejected."""
    assert get(server, "/api/v1/activity?limit=0")[0] == 200
    assert get(server, "/api/v1/activity?limit=100000")[0] == 200


def test_activity_outcome_filter(server: DashboardServer, archive: Archive) -> None:
    """The outcome parameter keeps only events with that outcome."""
    archive.connection.executemany(
        "INSERT INTO events (line_hash, ts, name, paths, outcome) VALUES (?, ?, 'lint', '[]', ?)",
        [("h1", 1000.0, "pass"), ("h2", 1001.0, "fail"), ("h3", 1002.0, "skip")],
    )
    archive.connection.commit()
    status, body = get(server, "/api/v1/activity?outcome=fail")
    assert status == 200
    assert [e["outcome"] for e in body["events"]] == ["fail"]


def test_activity_limit_capped(server: DashboardServer, archive: Archive) -> None:
    """The server clamps a large limit to a 500-event page."""
    archive.connection.executemany(
        "INSERT INTO events (line_hash, ts, name, paths, outcome) VALUES (?, ?, 'lint', '[]', 'pass')",
        [(f"h{i}", 1000.0 + i) for i in range(501)],
    )
    archive.connection.commit()
    status, body = get(server, "/api/v1/activity?limit=9999")
    assert status == 200
    assert len(body["events"]) == 500


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("1699920000", 1_699_920_000.0),
        ("1699920000.5", 1_699_920_000.5),
        ("2023-11-14", 1_699_920_000.0),
        ("2023-11-14T00:00:00", 1_699_920_000.0),
        ("2023-11-14T01:00:00+01:00", 1_699_920_000.0),
    ],
)
def test_time_accepts_unix_or_iso(text: str, expected: float) -> None:
    """Range bounds take Unix seconds or an ISO date, reading a bare date as UTC midnight."""
    assert server_module._time({"from": [text]}, "from") == expected


def test_iso_range_filters(server: DashboardServer, archive: Archive) -> None:
    """An ISO range selects the same events as the equivalent Unix range."""
    archive.connection.executemany(
        "INSERT INTO events (line_hash, ts, name, paths, outcome) VALUES (?, ?, 'lint', '[]', 'pass')",
        [("in", 1_699_920_000.0 + 60), ("out", 1_699_920_000.0 - 60)],
    )
    archive.connection.commit()
    iso = get(server, "/api/v1/summary?from=2023-11-14&to=2023-11-15")[1]
    unix = get(server, "/api/v1/summary?from=1699920000&to=1700006400")[1]
    assert iso["runs"] == unix["runs"] == 1


def test_error_after_headers_closes_without_500(
    server: DashboardServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failure after the headers went out closes the connection instead of writing a 500."""
    real = server_module._Handler.end_headers

    def failing(self: server_module._Handler) -> None:
        real(self)
        msg = "late failure"
        raise RuntimeError(msg)

    monkeypatch.setattr(server_module._Handler, "end_headers", failing)
    with socket.create_connection(("127.0.0.1", server.port), timeout=5) as sock:
        sock.sendall(
            f"GET /api/v1/summary HTTP/1.1\r\nHost: 127.0.0.1:{server.port}\r\n\r\n".encode()
        )
        data = b""
        while chunk := sock.recv(65536):
            data += chunk
    assert data.startswith(b"HTTP/1.0 200")
    assert b" 500 " not in data


def test_headers_flag_resets_per_request(
    server: DashboardServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A handler reused for a second request still sends a 500 when its route fails."""
    handler = object.__new__(server_module._Handler)
    handler._headers_sent = True
    handler.server = server
    handler.path = "/api/v1/summary"
    handler.headers = {"Host": f"127.0.0.1:{server.port}"}  # ty: ignore[invalid-assignment]
    sent: list[int] = []
    monkeypatch.setattr(server_module._Handler, "_api", MagicMock(side_effect=RuntimeError("boom")))
    monkeypatch.setattr(
        server_module._Handler, "_json", lambda self, status, payload: sent.append(status)
    )
    handler.do_GET()
    assert sent == [500]


def test_ingest_error_reported_once_per_kind(
    archive: Archive, capsys: pytest.CaptureFixture[str]
) -> None:
    """Changing error text does not repeat the console line; a new error type does."""
    srv = make_server(port=0, archive_path=archive_path(), inbox=inbox_path(), static_dir=None)
    try:
        srv._record_ingest_error(RuntimeError("busy 1"))
        srv._record_ingest_error(RuntimeError("busy 2"))
        srv._record_ingest_error(OSError("disk full"))
    finally:
        srv.server_close()
    err = capsys.readouterr().err
    assert err.count("dashboard ingest failed") == 2
    assert "busy 2" not in err
    assert srv.ingest_error == "disk full"


def test_port_taken_on_wildcard_is_refused(archive: Archive) -> None:
    """A port another process holds on every interface counts as taken."""
    with socket.socket() as taken:
        taken.bind(("0.0.0.0", 0))  # noqa: S104
        taken.listen()
        port = taken.getsockname()[1]
        with pytest.raises(OSError, match="in use"):
            make_server(port=port, archive_path=archive_path(), inbox=inbox_path(), static_dir=None)


def test_no_ui_503(bare_server: DashboardServer) -> None:
    """Without a frontend, non-API paths explain how to install one."""
    status, _, body = fetch(bare_server, "/")
    assert status == 503
    assert b"no dashboard UI" in body
    assert get(bare_server, "/api/v1/summary")[0] == 200


def test_freshness_counter_advances(
    server: DashboardServer, archive: Archive, stats_dirs: tuple[Path, Path]
) -> None:
    """Ingests made on another connection are visible to readers."""
    inbox = inbox_path()
    inbox.parent.mkdir(parents=True, exist_ok=True)
    before = get(server, "/api/v1/freshness")[1]
    assert before["ingest_count"] == 0
    assert before["last_ingest"] is None
    assert before["recording"] is False
    assert before["ingest_error"] is None
    counts = []
    for ts in (1000.0, 1001.0):
        inbox.write_bytes(_event(ts).to_line())
        archive.ingest(inbox)
        archive.ingest(inbox, now=time.time() + 3)
        counts.append(get(server, "/api/v1/freshness")[1]["ingest_count"])
    assert counts == [1, 2]


def test_background_ingest_rotates_the_inbox(
    server: DashboardServer, stats_dirs: tuple[Path, Path]
) -> None:
    """The ingest thread picks up the live inbox, and shutdown stops it."""
    inbox = inbox_path()
    inbox.parent.mkdir(parents=True, exist_ok=True)
    inbox.write_bytes(_event(1.0).to_line())
    server.start_ingest(interval=0.01)
    stop = threading.Event()
    for _ in range(300):
        if not inbox.exists():
            break
        stop.wait(0.01)
    assert not inbox.exists()


def test_lock_is_exclusive(tmp_path: Path) -> None:
    """A held lock blocks a second acquire until released."""
    first = InstanceLock.acquire(tmp_path)
    assert first is not None
    assert InstanceLock.acquire(tmp_path) is None
    first.write_url("http://127.0.0.1:1")
    assert running_url(tmp_path) == "http://127.0.0.1:1"
    first.release()
    assert running_url(tmp_path) is None
    second = InstanceLock.acquire(tmp_path)
    assert second is not None
    second.release()
    second.release()


def test_stale_url_removed_on_acquire(tmp_path: Path) -> None:
    """A URL left by a crashed dashboard does not survive a fresh acquire."""
    (tmp_path / "dashboard.url").write_text("http://stale")
    lock = InstanceLock.acquire(tmp_path)
    assert lock is not None
    assert running_url(tmp_path) is None
    lock.release()


def test_stale_url_unlink_failure_releases_fd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An error removing the stale URL raises without leaving the lock held."""
    (tmp_path / "dashboard.url").write_text("x")
    real = Path.unlink

    def fail(self: Path, missing_ok: bool = False) -> None:  # noqa: FBT002
        if self.name == "dashboard.url":
            raise PermissionError(13, "denied")
        real(self, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", fail)
    with pytest.raises(OSError, match="denied"):
        InstanceLock.acquire(tmp_path)
    monkeypatch.setattr(Path, "unlink", real)
    again = InstanceLock.acquire(tmp_path)
    assert again is not None
    again.release()


def test_ingest_failure_is_reported_and_recovers(
    server: DashboardServer,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The ingest thread survives failures, reports them, and clears the error on success."""
    failing = threading.Event()
    failing.set()
    real = Archive.ingest

    def flaky(self: Archive, inbox: Path, *, now: float | None = None) -> int:
        if failing.is_set():
            msg = "disk on fire"
            raise RuntimeError(msg)
        return real(self, inbox, now=now)

    monkeypatch.setattr(Archive, "ingest", flaky)
    server.start_ingest(interval=0.01)
    wait = threading.Event()
    for _ in range(300):
        if get(server, "/api/v1/freshness")[1]["ingest_error"] == "disk on fire":
            break
        wait.wait(0.01)
    assert get(server, "/api/v1/freshness")[1]["ingest_error"] == "disk on fire"
    failing.clear()
    for _ in range(300):
        if get(server, "/api/v1/freshness")[1]["ingest_error"] is None:
            break
        wait.wait(0.01)
    assert get(server, "/api/v1/freshness")[1]["ingest_error"] is None
    assert capsys.readouterr().err.count("dashboard ingest failed: disk on fire") == 1


def test_route_exception_is_internal_error(
    server: DashboardServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unexpected route failure returns a generic 500 without detail."""

    def boom(*_args: object) -> dict:
        msg = "secret detail"
        raise RuntimeError(msg)

    monkeypatch.setitem(server_module._ROUTES, "summary", boom)
    status, _, body = fetch(server, "/api/v1/summary")
    assert status == 500
    assert json.loads(body) == {"error": "internal error"}
    assert b"secret" not in body


def test_static_read_failure_is_500_text(server: DashboardServer, tmp_path: Path) -> None:
    """A static file that cannot be read returns a plain 500."""
    (tmp_path / "ui" / "index.html").mkdir(parents=True)
    server.static_dir = tmp_path / "ui"
    status, headers, body = fetch(server, "/")
    assert status == 500
    assert body == b"internal error"
    assert headers["Content-Type"].startswith("text/plain")
