"""Tests for the dashboard HTTP server."""

import http.client
import json
import os
import socket
import threading
import time
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path
from unittest.mock import MagicMock
from urllib.parse import quote

import pytest

from gate_cache.dashboard import server as server_module
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
    "path",
    [
        "gates",
        "hourly",
        "reasons",
        "coalescing",
        "repos",
        "breakdown?by=source",
        "activity",
        "flaky",
        "slowdowns",
        "spent",
        "freshness",
        "gate?name=lint&repo=-",
    ],
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
    status, headers, _ = fetch(server, "/", host="evil.example:80")
    assert status == 403
    assert headers["Cache-Control"] == "no-store"


def test_localhost_host_ok(server: DashboardServer) -> None:
    """Localhost with the right port is accepted."""
    assert fetch(server, "/", host=f"localhost:{server.port}")[0] == 200


def test_unknown_api_404_json(server: DashboardServer) -> None:
    """An unknown API path is a JSON 404."""
    status, headers, body = fetch(server, "/api/v1/nope")
    assert status == 404
    assert headers["Cache-Control"] == "no-store"
    assert "error" in json.loads(body)
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


def test_hashed_asset_is_immutable(server: DashboardServer) -> None:
    """A file under assets/ is cached for a year without revalidation."""
    status, headers, _ = fetch(server, "/assets/app.js")
    assert status == 200
    assert headers["Cache-Control"] == "public, max-age=31536000, immutable"


@pytest.mark.parametrize(
    ("path", "marker"),
    [
        ("/", b'<div id="app">'),
        ("/gates", b'<div id="app">'),
        ("/favicon.svg", b"<svg"),
    ],
    ids=["index", "spa-fallback", "unhashed-file"],
)
def test_unhashed_static_revalidates(server: DashboardServer, path: str, marker: bytes) -> None:
    """index.html and files outside assets/ revalidate on every load."""
    status, headers, body = fetch(server, path)
    assert status == 200
    assert marker in body
    assert headers["Cache-Control"] == "no-cache"


def test_missing_asset_404(server: DashboardServer) -> None:
    """A missing file under assets/ is a 404, not index.html served as a script."""
    status, headers, body = fetch(server, "/assets/missing.js")
    assert status == 404
    assert body == b"not found"
    assert headers["Cache-Control"] == "no-store"


@pytest.mark.parametrize("path", ["/../../etc/passwd", "/%2e%2e/%2e%2e/etc/passwd", "/a%00b"])
def test_traversal_blocked(server: DashboardServer, path: str) -> None:
    """Paths outside the static root fall back to index.html."""
    assert '<div id="app">' in text(server, path)


def _assert_page_headers(headers: dict[str, str]) -> None:
    assert headers["Content-Security-Policy"] == server_module.CONTENT_SECURITY_POLICY
    assert headers["X-Frame-Options"] == "DENY"
    assert headers["Referrer-Policy"] == "no-referrer"
    assert headers["X-Content-Type-Options"] == "nosniff"


@pytest.mark.parametrize(
    ("path", "host"),
    [
        ("/", None),
        ("/gates", None),
        ("/assets/app.js", None),
        ("/assets/missing.js", None),
        ("/", "evil.example"),
    ],
    ids=["index", "spa-fallback", "asset", "missing-asset", "forbidden-host"],
)
def test_page_security_headers(server: DashboardServer, path: str, host: str | None) -> None:
    """Every response outside the API carries the browser security headers."""
    _assert_page_headers(fetch(server, path, host)[1])


def test_stdlib_error_security_headers(server: DashboardServer) -> None:
    """Errors the stdlib writes, such as 501 for an unsupported method, carry the headers."""
    conn = http.client.HTTPConnection("127.0.0.1", server.port, timeout=5)
    try:
        conn.request("POST", "/", headers={"Host": f"127.0.0.1:{server.port}"})
        resp = conn.getresponse()
        resp.read()
        assert resp.status == 501
        _assert_page_headers(dict(resp.getheaders()))
    finally:
        conn.close()


def test_csp_allows_no_inline_script() -> None:
    """The policy never lets a script run from inline code or eval."""
    policy = server_module.CONTENT_SECURITY_POLICY
    assert "unsafe-inline" not in policy
    assert "unsafe-eval" not in policy
    assert "frame-ancestors 'none'" in policy


@pytest.mark.parametrize("path", ["/api/v1/summary", "/api/v1/nope"], ids=["ok", "not-found"])
def test_api_headers(server: DashboardServer, path: str) -> None:
    """API responses carry nosniff but no page policy."""
    _, headers, _ = fetch(server, path)
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert "Content-Security-Policy" not in headers
    assert "X-Frame-Options" not in headers
    assert "Referrer-Policy" not in headers


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
        "breakdown",
        "breakdown?by=tool",
        "spent?status=bad",
        "activity?group=branch",
        "activity?key=%5B%5D",
        "activity?group=branch&key=main",
        "activity?group=tool&key=%5Bnull%5D",
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


def test_repeated_repo_param(server: DashboardServer, archive: Archive) -> None:
    """Repeated repo params select several repos; - selects the unknown repo."""
    archive.connection.executemany(
        "INSERT INTO events (line_hash, ts, repo, name, paths, outcome)"
        " VALUES (?, ?, ?, 'lint', '[]', 'pass')",
        [("h1", 1000.0, "/r/a/.git"), ("h2", 1001.0, "/r/b/.git"), ("h3", 1002.0, None)],
    )
    archive.connection.commit()
    _, body = get(server, "/api/v1/repos?repo=/r/a/.git&repo=-")
    assert {r["repo"] for r in body["repos"]} == {"/r/a/.git", None}


def test_repo_params_dedup_and_drop_empty(server: DashboardServer, archive: Archive) -> None:
    """Repeated repo params collapse to one, and an empty one selects nothing extra."""
    assert server_module._repos({"repo": ["/r/a/.git", "/r/a/.git", "", "-"]}) == (
        "/r/a/.git",
        None,
    )
    archive.connection.executemany(
        "INSERT INTO events (line_hash, ts, repo, name, paths, outcome)"
        " VALUES (?, ?, ?, 'lint', '[]', 'pass')",
        [("h1", 1000.0, "/r/a/.git"), ("h2", 1001.0, "/r/b/.git")],
    )
    archive.connection.commit()
    _, body = get(server, "/api/v1/repos?repo=/r/a/.git&repo=/r/a/.git&repo=")
    assert [(r["repo"], r["runs"]) for r in body["repos"]] == [("/r/a/.git", 1)]


def test_gate_unknown_repo(server: DashboardServer, archive: Archive) -> None:
    """repo=- selects the gate's events recorded without a repo."""
    archive.connection.executemany(
        "INSERT INTO events (line_hash, ts, repo, name, paths, outcome)"
        " VALUES (?, ?, ?, 'lint', '[]', 'pass')",
        [("h1", 1000.0, None), ("h2", 1001.0, "/r/a/.git"), ("h3", 1002.0, None)],
    )
    archive.connection.commit()
    status, body = get(server, "/api/v1/gate?name=lint&repo=-")
    assert status == 200
    assert body["repo"] is None
    assert [e["ts"] for e in body["recent"]] == [1002.0, 1000.0]


def test_activity_reason_filter(server: DashboardServer, archive: Archive) -> None:
    """The reason parameter keeps only events recorded with that reason."""
    archive.connection.executemany(
        "INSERT INTO events (line_hash, ts, name, paths, outcome, reason)"
        " VALUES (?, ?, 'lint', '[]', 'uncached', ?)",
        [("h1", 1000.0, "a b&c"), ("h2", 1001.0, "other"), ("h3", 1002.0, None)],
    )
    archive.connection.commit()
    status, body = get(server, "/api/v1/activity?reason=a%20b%26c")
    assert status == 200
    assert [e["reason"] for e in body["events"]] == ["a b&c"]


def test_api_coalescing_and_net_saved(server: DashboardServer, archive: Archive) -> None:
    """Ingested wait and overhead timings reach the summary and the coalescing endpoint."""
    now = time.time()
    events = [
        replace(_event(now - 30), outcome="skip", saved=60.0, overhead=0.5, waited=10.0),
        replace(_event(now - 20), overhead=0.5),
    ]
    inbox_path().write_bytes(b"".join(e.to_line() for e in events))
    archive.ingest(inbox_path(), now=now)
    archive.ingest(inbox_path(), now=now + 3)
    summary = get(server, "/api/v1/summary")[1]
    assert summary["net_saved"] == pytest.approx(60.0 - 1.0 - 10.0)
    assert summary["cost_unknown_runs"] == 0
    status, body = get(server, "/api/v1/coalescing")
    assert status == 200
    assert (body["waited"], body["skipped"], body["total_wait"]) == (1, 1, 10.0)


def test_gate_requires_repo(server: DashboardServer) -> None:
    """The gate endpoint rejects a request without repo."""
    status, body = get(server, "/api/v1/gate?name=lint")
    assert status == 400
    assert "repo" in body["error"]


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
    status, headers, body = fetch(bare_server, "/")
    assert status == 503
    assert b"dashboard UI" in body
    assert headers["Cache-Control"] == "no-store"
    assert headers["Content-Security-Policy"] == server_module.CONTENT_SECURITY_POLICY
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
    status, headers, body = fetch(server, "/api/v1/summary")
    assert status == 500
    assert headers["Cache-Control"] == "no-store"
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
    assert headers["Cache-Control"] == "no-store"


def test_breakdown_row_drills_into_activity(server: DashboardServer, archive: Archive) -> None:
    """A breakdown row's key, sent back as group and key, lists that row's runs."""
    archive.connection.executemany(
        "INSERT INTO events (line_hash, ts, repo, name, paths, outcome, raw)"
        " VALUES (?, ?, '/r/a/.git', 'lint', '[]', 'pass', ?)",
        [
            ("h1", 1000.0, json.dumps({"trigger": "agent", "agent": "claude-code"})),
            ("h2", 1001.0, json.dumps({"trigger": "ci"})),
            ("h3", 1002.0, None),
        ],
    )
    archive.connection.commit()
    status, body = get(server, "/api/v1/breakdown?by=source&repo=/r/a/.git")
    assert status == 200
    assert body["by"] == "source"
    by_label = {row["label"]: row for row in body["rows"]}
    assert set(by_label) == {"Agent: claude-code", "CI", "No source recorded"}
    key = quote(by_label["Agent: claude-code"]["key"])
    _, page = get(server, f"/api/v1/activity?group=source&key={key}")
    assert [e["ts"] for e in page["events"]] == [1000.0]


def test_activity_weekday_hour_filter(server: DashboardServer, archive: Archive) -> None:
    """The weekday and hour parameters keep only events in that local hour."""
    # 1970-01-04 was a Sunday; 3600 s is 01:00 UTC on Thursday 1970-01-01.
    sunday_0105 = 3 * 86400 + 3900.0
    archive.connection.executemany(
        "INSERT INTO events (line_hash, ts, name, paths, outcome) VALUES (?, ?, 'lint', '[]', 'pass')",
        [("h1", sunday_0105), ("h2", sunday_0105 + 3600), ("h3", 3900.0)],
    )
    archive.connection.commit()
    status, body = get(server, "/api/v1/activity?weekday=0&hour=1&tz=UTC")
    assert status == 200
    assert [e["ts"] for e in body["events"]] == [sunday_0105]


@pytest.mark.parametrize(
    ("query", "word"),
    [
        ("weekday=1", "hour"),
        ("hour=1", "hour"),
        ("weekday=x&hour=1", "weekday"),
        ("hour=25&weekday=1", "hour"),
    ],
)
def test_activity_rejects_bad_slot(server: DashboardServer, query: str, word: str) -> None:
    """A lone, non-integer, or out-of-range weekday or hour is a bad request."""
    status, body = get(server, f"/api/v1/activity?{query}")
    assert status == 400
    assert word in body["error"]


def test_activity_gate_filter(server: DashboardServer, archive: Archive) -> None:
    """The gate and gate_repo parameters keep one gate; gate_repo=- is the unknown repo."""
    archive.connection.executemany(
        "INSERT INTO events (line_hash, ts, repo, name, paths, outcome)"
        " VALUES (?, ?, ?, ?, '[]', 'pass')",
        [("h1", 1.0, None, "lint"), ("h2", 2.0, "/r/.git", "lint"), ("h3", 3.0, None, "test")],
    )
    archive.connection.commit()
    status, body = get(server, "/api/v1/activity?gate=lint&gate_repo=-")
    assert status == 200
    assert [e["ts"] for e in body["events"]] == [1.0]


def test_activity_gate_requires_repo(server: DashboardServer) -> None:
    """A gate filter without gate_repo is a bad request."""
    status, body = get(server, "/api/v1/activity?gate=lint")
    assert status == 400
    assert "gate_repo" in body["error"]


def test_activity_flaky_filter(server: DashboardServer, archive: Archive) -> None:
    """flaky=1 keeps only runs on trees that both failed and passed."""
    archive.connection.executemany(
        "INSERT INTO events (line_hash, ts, name, tree, paths, outcome)"
        " VALUES (?, ?, 'lint', ?, '[]', ?)",
        [("h1", 1.0, "t1", "fail"), ("h2", 2.0, "t1", "pass"), ("h3", 3.0, "t2", "pass")],
    )
    archive.connection.commit()
    status, body = get(server, "/api/v1/activity?flaky=1")
    assert status == 200
    assert [e["ts"] for e in body["events"]] == [2.0, 1.0]


def _fake_exe(directory: Path) -> Path:
    directory.mkdir(parents=True)
    exe = directory / "gate-cache"
    exe.write_text("#!/bin/sh\n")
    exe.chmod(0o755)
    return exe


def test_no_ui_message_source_checkout(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """From a source checkout, the message names the checkout and the build duty."""
    monkeypatch.setattr(server_module, "_source_checkout", lambda: tmp_path)
    monkeypatch.setenv("PATH", "")
    message = server_module.no_ui_message()
    assert f"source checkout at {tmp_path}" in message
    assert "uv run duty frontend_build" in message
    assert "full path" not in message


def test_no_ui_message_source_build(monkeypatch: pytest.MonkeyPatch) -> None:
    """Outside a checkout, the message points to a release install."""
    monkeypatch.setattr(server_module, "_source_checkout", lambda: None)
    monkeypatch.setenv("PATH", "")
    message = server_module.no_ui_message()
    assert "built from source" in message
    assert "uv tool install gate-cache" in message


def test_no_ui_message_names_other_installs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Executables of other installs are listed once; the running install's own is not."""
    prefix = tmp_path / "venv"
    own = _fake_exe(prefix / "bin")
    other = _fake_exe(tmp_path / "tool" / "bin")
    link_dir = tmp_path / "links"
    link_dir.mkdir()
    (link_dir / "gate-cache").symlink_to(other)
    monkeypatch.setattr(server_module.sys, "prefix", str(prefix))
    monkeypatch.setattr(server_module, "_source_checkout", lambda: None)
    monkeypatch.setenv("PATH", os.pathsep.join([str(own.parent), str(link_dir), str(other.parent)]))
    message = server_module.no_ui_message()
    assert str(own) not in message
    assert f"by its full path: {link_dir / 'gate-cache'}" in message
    assert str(other) not in message


def test_source_checkout_detected() -> None:
    """The tests run from the source checkout, which holds the frontend."""
    root = server_module._source_checkout()
    assert root is not None
    assert (root / "frontend" / "package.json").is_file()
