"""Tests for the SQLite archive and inbox ingest."""

import hashlib
import os
import sqlite3
import time
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path
from typing import IO, Any

import pytest

from gate_cache.stats import archive as archive_module
from gate_cache.stats.archive import RETENTION_DAYS, Archive, archive_path
from gate_cache.stats.recorder import Event

DAY = 86400.0


def make_event(ts: float, name: str = "lint", outcome: str = "pass") -> Event:
    """Build an event with the given timestamp."""
    return Event(
        ts=ts,
        repo="/r/.git",
        name=name,
        tree="abc",
        paths=("src", "tests"),
        outcome=outcome,  # ty: ignore[invalid-argument-type]
        duration=1.5,
        saved=None,
        exit_code=0,
        reason=None,
    )


def count(arch: Archive) -> int:
    """Count stored events."""
    return arch.connection.execute("SELECT COUNT(*) FROM events").fetchone()[0]


@pytest.fixture
def inbox(tmp_path: Path) -> Path:
    """Return an inbox path inside a fresh state directory."""
    state = tmp_path / "state"
    state.mkdir()
    return state / "events.jsonl"


@pytest.fixture
def arch(tmp_path: Path) -> Iterator[Archive]:
    """Open an archive and close it afterwards."""
    with Archive.open(tmp_path / "a.sqlite3") as opened:
        yield opened


def processing_files(inbox: Path) -> list[Path]:
    """List the renamed inbox files."""
    return list(inbox.parent.glob("events.*.processing"))


def test_archive_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """The archive lives in the state directory."""
    monkeypatch.setenv(archive_module.config.DATA_DIR_ENV, str(tmp_path))
    assert archive_path() == tmp_path / "stats.sqlite3"


def test_ingest_two_cycles(arch: Archive, inbox: Path) -> None:
    """The first cycle renames the inbox, the settled second cycle ingests it."""
    now = time.time()
    inbox.write_bytes(b"".join(make_event(now - i).to_line() for i in range(3)))
    assert arch.ingest(inbox, now=now) == 0
    assert not inbox.exists()
    assert len(processing_files(inbox)) == 1
    assert arch.ingest(inbox, now=now + 3) == 3
    assert processing_files(inbox) == []
    assert arch.meta("ingest_count") == "1"
    assert arch.meta("last_ingest") is not None
    row = arch.connection.execute("SELECT paths, tree, saved FROM events LIMIT 1").fetchone()
    assert row == ('["src","tests"]', "abc", None)


def test_ingest_without_inbox(arch: Archive, inbox: Path) -> None:
    """A missing inbox adds nothing and leaves the counters alone."""
    assert arch.ingest(inbox) == 0
    assert arch.meta("ingest_count") is None


def test_unsettled_file_is_left(arch: Archive, inbox: Path) -> None:
    """A renamed file younger than the settle window is not read yet."""
    now = time.time()
    inbox.write_bytes(make_event(now).to_line())
    arch.ingest(inbox, now=now)
    assert arch.ingest(inbox, now=now + 1) == 0
    assert len(processing_files(inbox)) == 1


def test_late_append_into_renamed_file_is_kept(arch: Archive, inbox: Path) -> None:
    """A write through a descriptor opened before the rename still lands."""
    now = time.time()
    inbox.write_bytes(make_event(now - 1).to_line())
    fd = os.open(inbox, os.O_WRONLY | os.O_APPEND)
    try:
        arch.ingest(inbox, now=now)
        os.write(fd, make_event(now - 2, name="test").to_line())
    finally:
        os.close(fd)
    assert arch.ingest(inbox, now=now + 3) == 2
    names = sorted(r[0] for r in arch.connection.execute("SELECT name FROM events"))
    assert names == ["lint", "test"]


def test_crash_between_commit_and_delete_does_not_duplicate(arch: Archive, inbox: Path) -> None:
    """Re-ingesting an identical copy of an already ingested file adds nothing."""
    now = time.time()
    data = make_event(now).to_line()
    inbox.write_bytes(data)
    arch.ingest(inbox, now=now)
    assert arch.ingest(inbox, now=now + 3) == 1
    copy = inbox.parent / f"events.{int((now - 10) * 1e9)}.processing"
    copy.write_bytes(data)
    assert arch.ingest(inbox, now=now + 3) == 0
    assert count(arch) == 1
    assert processing_files(inbox) == []


def test_malformed_lines_skipped(arch: Archive, inbox: Path) -> None:
    """Only a well-formed version 1 line is stored."""
    now = time.time()
    good = make_event(now).to_line()
    bad_version = good.replace(b'"v":1', b'"v":2')
    bad_outcome = good.replace(b'"pass"', b"7")
    bad_paths = good.replace(b'["src","tests"]', b'"src"')
    bad_ts = good.replace(b'"ts":%s' % repr(now).encode(), b'"ts":"x"')
    inbox.write_bytes(
        b"not json\n[]\n\n" + bad_version + bad_outcome + bad_paths + bad_ts + b"\xff\xfe\n" + good
    )
    arch.ingest(inbox, now=now)
    assert arch.ingest(inbox, now=now + 3) == 1
    assert count(arch) == 1


def test_trailing_partial_line_is_parsed(arch: Archive, inbox: Path) -> None:
    """A final line without a newline is still ingested."""
    now = time.time()
    inbox.write_bytes(make_event(now).to_line().rstrip(b"\n"))
    arch.ingest(inbox, now=now)
    assert arch.ingest(inbox, now=now + 3) == 1


def test_identical_lines_dedupe(arch: Archive, inbox: Path) -> None:
    """Identical lines hash alike and are stored once."""
    now = time.time()
    line = make_event(now).to_line()
    inbox.write_bytes(line * 2)
    arch.ingest(inbox, now=now)
    assert arch.ingest(inbox, now=now + 3) == 1
    stored = arch.connection.execute("SELECT line_hash FROM events").fetchone()[0]
    assert stored == hashlib.sha256(line.rstrip(b"\n")).hexdigest()


def test_retention(arch: Archive, inbox: Path) -> None:
    """Events older than the retention window are dropped."""
    assert RETENTION_DAYS == 365
    now = time.time()
    inbox.write_bytes(
        make_event(now - 366 * DAY, name="old").to_line()
        + make_event(now - 364 * DAY, name="new").to_line()
    )
    arch.ingest(inbox, now=now)
    arch.ingest(inbox, now=now + 3)
    names = [r[0] for r in arch.connection.execute("SELECT name FROM events")]
    assert names == ["new"]


def test_prune_returns_deleted_count(arch: Archive, inbox: Path) -> None:
    """Prune reports how many rows it removed."""
    now = time.time()
    inbox.write_bytes(make_event(now - 10 * DAY).to_line())
    arch.ingest(inbox, now=now)
    arch.ingest(inbox, now=now + 3)
    assert arch.prune(now=now) == 0
    assert arch.prune(now=now + 400 * DAY) == 1


def test_schema_version(tmp_path: Path) -> None:
    """A new archive records its schema version and uses WAL."""
    arch = Archive.open(tmp_path / "a.sqlite3")
    try:
        assert arch.meta("schema_version") == "3"
        assert arch.connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    finally:
        arch.close()


def test_reopen_keeps_data(tmp_path: Path, inbox: Path) -> None:
    """Reopening an archive keeps its rows and version."""
    now = time.time()
    path = tmp_path / "a.sqlite3"
    inbox.write_bytes(make_event(now).to_line())
    with Archive.open(path) as first:
        first.ingest(inbox, now=now)
        first.ingest(inbox, now=now + 3)
    with Archive.open(path) as second:
        assert count(second) == 1
        assert second.meta("schema_version") == str(archive_module.SCHEMA_VERSION)


def poison_lines(now: float) -> list[bytes]:
    """Build lines that are valid JSON or not but that SQLite cannot store."""
    good = make_event(now).to_line().rstrip(b"\n")
    ts = repr(now).encode()
    return [
        good.replace(b'"ts":' + ts, b'"ts":99999999999999999999999'),
        good.replace(b'"exit_code":0', b'"exit_code":99999999999999999999999'),
        good.replace(b'"name":"lint"', b'"name":"\\ud800"'),
        good.replace(b'"src"', b'"\\ud800"'),
        good.replace(b'"ts":' + ts, b'"ts":Infinity'),
        good.replace(b'"duration":1.5', b'"duration":NaN'),
        good.replace(b'"duration":1.5', b'"duration":-Infinity'),
        b"[" * 200000,
    ]


def test_poison_lines_skipped_and_inbox_rotated(arch: Archive, inbox: Path) -> None:
    """Unstorable lines are skipped, valid ones kept, and the inbox still rotates."""
    now = time.time()
    good = make_event(now).to_line()
    inbox.write_bytes(b"\n".join([*poison_lines(now), good.rstrip(b"\n")]) + b"\n")
    arch.ingest(inbox, now=now)
    # Second cycle ingests the file and rotates a fresh, unsettled inbox in the same call.
    inbox.write_bytes(make_event(now - 5, name="later").to_line())
    os.utime(inbox, (now + 2, now + 2))
    assert arch.ingest(inbox, now=now + 3) == 1
    assert not inbox.exists()
    assert len(processing_files(inbox)) == 1
    assert processing_files(inbox)[0].exists()
    assert count(arch) == 1


def test_row_rejects_unstorable_values() -> None:
    """Validation drops every poison line before it reaches SQLite."""
    for line in poison_lines(time.time()):
        assert archive_module._row(line) is None


def test_failing_file_does_not_block_others(
    arch: Archive, inbox: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A file that cannot be read stays for later while others and rotation proceed."""
    now = time.time()
    bad = inbox.parent / f"events.{int((now - 10) * 1e9)}.processing"
    bad.write_bytes(make_event(now, name="bad").to_line())
    ok = inbox.parent / f"events.{int((now - 9) * 1e9)}.processing"
    ok.write_bytes(make_event(now, name="ok").to_line())
    inbox.write_bytes(make_event(now, name="live").to_line())
    os.utime(inbox, (now + 2, now + 2))
    real = Path.open

    def flaky(self: Path, mode: str = "r") -> IO[Any]:
        if self == bad:
            msg = "denied"
            raise PermissionError(msg)
        return real(self, mode)

    monkeypatch.setattr(Path, "open", flaky)
    assert arch.ingest(inbox, now=now + 3) == 1
    assert bad.exists()
    assert not ok.exists()
    assert not inbox.exists()
    monkeypatch.undo()
    assert arch.ingest(inbox, now=now + 3) == 2
    assert not bad.exists()


def test_newer_schema_is_refused(tmp_path: Path) -> None:
    """An archive written by a newer schema cannot be opened."""
    path = tmp_path / "a.sqlite3"
    with Archive.open(path) as first:
        first.connection.execute(
            "UPDATE meta SET value = ? WHERE key = 'schema_version'",
            (str(archive_module.SCHEMA_VERSION + 1),),
        )
        first.connection.commit()
    with pytest.raises(archive_module.ArchiveVersionError, match="newer"):
        Archive.open(path)


def test_settled_inbox_ingested_in_one_cycle(arch: Archive, inbox: Path) -> None:
    """A live inbox older than the settle window is read in one call but kept until it settles."""
    now = time.time()
    inbox.write_bytes(b"".join(make_event(now - i).to_line() for i in range(2)))
    os.utime(inbox, (now - 10, now - 10))
    assert arch.ingest(inbox, now=now) == 2
    assert not inbox.exists()
    assert len(processing_files(inbox)) == 1
    assert arch.meta("ingest_count") == "1"
    assert arch.ingest(inbox, now=now + 3) == 0
    assert processing_files(inbox) == []
    assert arch.meta("ingest_count") == "1"
    assert count(arch) == 2


def test_late_append_after_immediate_ingest_is_kept(arch: Archive, inbox: Path) -> None:
    """A write through a descriptor held across an immediate ingest lands on the next cycle."""
    now = time.time()
    inbox.write_bytes(make_event(now - 1).to_line())
    os.utime(inbox, (now - 10, now - 10))
    fd = os.open(inbox, os.O_WRONLY | os.O_APPEND)
    try:
        assert arch.ingest(inbox, now=now) == 1
        os.write(fd, make_event(now - 2, name="late").to_line())
    finally:
        os.close(fd)
    assert arch.ingest(inbox, now=now + 3) == 1
    assert arch.meta("ingest_count") == "2"
    names = sorted(r[0] for r in arch.connection.execute("SELECT name FROM events"))
    assert names == ["late", "lint"]
    assert processing_files(inbox) == []


def test_failed_delete_still_counts(
    arch: Archive, inbox: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A file that cannot be deleted after commit still counts its added events."""
    now = time.time()
    path = inbox.parent / f"events.{int((now - 10) * 1e9)}.processing"
    path.write_bytes(make_event(now).to_line())

    def denied(self: Path, *, missing_ok: bool = False) -> None:
        msg = "denied"
        raise PermissionError(msg)

    monkeypatch.setattr(Path, "unlink", denied)
    assert arch.ingest(inbox, now=now) == 1
    assert arch.meta("ingest_count") == "1"
    assert path.exists()
    monkeypatch.undo()
    assert arch.ingest(inbox, now=now) == 0
    assert count(arch) == 1
    assert not path.exists()


def test_sqlite_error_rolls_back_and_continues(
    arch: Archive, inbox: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A SQLite error on one file leaves it, ingests the others, and keeps the connection."""
    now = time.time()
    bad = inbox.parent / f"events.{int((now - 10) * 1e9)}.processing"
    bad.write_bytes(make_event(now, name="bad").to_line())
    ok = inbox.parent / f"events.{int((now - 9) * 1e9)}.processing"
    ok.write_bytes(make_event(now, name="ok").to_line())
    real = Archive._ingest_file

    def failing(self: Archive, path: Path, *, delete: bool = True) -> int:
        if path == bad:
            msg = "database is locked"
            raise sqlite3.OperationalError(msg)
        return real(self, path, delete=delete)

    monkeypatch.setattr(Archive, "_ingest_file", failing)
    assert arch.ingest(inbox, now=now) == 1
    assert bad.exists()
    assert not ok.exists()
    assert count(arch) == 1
    monkeypatch.undo()
    assert arch.ingest(inbox, now=now) == 1
    assert count(arch) == 2


@pytest.mark.parametrize("value", ["abc", "1.5", ""])
def test_unreadable_schema_version_is_refused(tmp_path: Path, value: str) -> None:
    """A non-integer schema version raises the version error, not a ValueError."""
    path = tmp_path / "a.sqlite3"
    with Archive.open(path) as first:
        first.connection.execute("UPDATE meta SET value = ? WHERE key = 'schema_version'", (value,))
        first.connection.commit()
    with pytest.raises(archive_module.ArchiveVersionError, match="unreadable"):
        Archive.open(path)


def test_newer_schema_is_left_untouched(tmp_path: Path) -> None:
    """Refusing a newer archive changes neither its journal mode nor its tables."""
    path = tmp_path / "a.sqlite3"
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)")
    connection.execute(
        "INSERT INTO meta VALUES ('schema_version', ?)", (str(archive_module.SCHEMA_VERSION + 1),)
    )
    connection.commit()
    connection.close()
    with pytest.raises(archive_module.ArchiveVersionError, match="newer"):
        Archive.open(path)
    connection = sqlite3.connect(path)
    try:
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
        tables = {r[0] for r in connection.execute("SELECT name FROM sqlite_master")}
        assert "events" not in tables
    finally:
        connection.close()


V1_SCHEMA = """
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE events (
    id INTEGER PRIMARY KEY,
    line_hash TEXT UNIQUE NOT NULL,
    ts REAL NOT NULL,
    repo TEXT,
    name TEXT NOT NULL,
    tree TEXT,
    paths TEXT NOT NULL,
    outcome TEXT NOT NULL,
    duration REAL,
    saved REAL,
    exit_code INTEGER,
    reason TEXT
);
INSERT INTO meta VALUES ('schema_version', '1');
INSERT INTO events (line_hash, ts, repo, name, tree, paths, outcome)
    VALUES ('h1', 1.0, '/r/.git', 'old', 'abc', '[]', 'pass');
"""


def test_new_archive_has_raw_column(arch: Archive) -> None:
    """A fresh archive stores the raw column at the current schema version."""
    columns = {r[1] for r in arch.connection.execute("PRAGMA table_info(events)")}
    assert "raw" in columns
    assert arch.meta("schema_version") == str(archive_module.SCHEMA_VERSION)


@pytest.mark.parametrize(
    "schema",
    [
        V1_SCHEMA,
        V1_SCHEMA.replace("INSERT INTO meta VALUES ('schema_version', '1');", ""),
        V1_SCHEMA.replace("INSERT INTO meta VALUES ('schema_version', '1');", "").replace(
            "CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);", ""
        ),
    ],
    ids=["versioned", "no-version-row", "no-meta-table"],
)
def test_v1_archive_is_migrated(tmp_path: Path, inbox: Path, schema: str) -> None:
    """Opening a version 1 archive, stamped or not, adds the raw column and keeps its rows."""
    path = tmp_path / "a.sqlite3"
    connection = sqlite3.connect(path)
    now = time.time()
    connection.executescript(schema)
    connection.execute("UPDATE events SET ts = ?", (now - 10,))
    connection.commit()
    connection.close()
    line = make_event(now).to_line()
    inbox.write_bytes(line)
    with Archive.open(path) as arch:
        assert arch.meta("schema_version") == "3"
        assert arch.connection.execute("SELECT name, raw FROM events").fetchall() == [("old", None)]
        arch.ingest(inbox, now=now)
        arch.ingest(inbox, now=now + 3)
        rows = arch.connection.execute("SELECT name, raw FROM events ORDER BY ts").fetchall()
    assert rows == [("old", None), ("lint", line.rstrip(b"\n").decode())]
    with Archive.open(path) as reopened:
        assert count(reopened) == 2


def test_raw_keeps_unknown_keys(arch: Archive, inbox: Path) -> None:
    """A key the columns do not hold survives in the raw line."""
    now = time.time()
    line = make_event(now).to_line().replace(b'"v":1,', b'"v":1,"future":{"x":[1,2]},')
    inbox.write_bytes(line)
    arch.ingest(inbox, now=now)
    assert arch.ingest(inbox, now=now + 3) == 1
    raw = arch.connection.execute("SELECT raw FROM events").fetchone()[0]
    assert raw == line.rstrip(b"\n").decode()
    assert '"future":{"x":[1,2]}' in raw


def test_non_utf8_line_is_skipped(arch: Archive, inbox: Path) -> None:
    """A JSON line in UTF-16 is skipped, so every stored row keeps its raw text."""
    now = time.time()
    line = make_event(now).to_line().rstrip(b"\n").decode().encode("utf-16") + b"\n"
    inbox.write_bytes(line + make_event(now + 1).to_line())
    arch.ingest(inbox, now=now)
    assert arch.ingest(inbox, now=now + 3) == 1
    assert arch.connection.execute("SELECT raw IS NOT NULL FROM events").fetchone()[0] == 1


def test_unknown_outcome_is_kept(arch: Archive, inbox: Path) -> None:
    """A line from a newer version with an unknown outcome is stored as is."""
    now = time.time()
    inbox.write_bytes(make_event(now).to_line().replace(b'"pass"', b'"novel"'))
    arch.ingest(inbox, now=now)
    assert arch.ingest(inbox, now=now + 3) == 1
    assert arch.connection.execute("SELECT outcome FROM events").fetchone()[0] == "novel"


def _timings(arch: Archive) -> list[tuple[Any, ...]]:
    """Return the overhead, waited, wait_known, reported, and wait_timed_out columns, oldest first."""
    return arch.connection.execute(
        "SELECT overhead, waited, wait_known, reported, wait_timed_out FROM events ORDER BY ts"
    ).fetchall()


def test_ingest_stores_timings(arch: Archive, inbox: Path) -> None:
    """Ingest copies overhead and waited into columns and notes whether waits were recorded."""
    now = time.time()
    waited = replace(make_event(now), overhead=0.25, waited=3.5, reported=True, wait_timed_out=True)
    no_wait = replace(make_event(now + 1), overhead=0.1)
    # An event from before gate-cache recorded waits has no `waited` key at all.
    old = make_event(now + 2).to_line().replace(b',"waited":null', b"")
    inbox.write_bytes(waited.to_line() + no_wait.to_line() + old)
    arch.ingest(inbox, now=now)
    arch.ingest(inbox, now=now + 3)
    assert _timings(arch) == [(0.25, 3.5, 1, 1, 1), (0.1, None, 1, 0, 0), (None, None, 0, 0, 0)]


@pytest.mark.parametrize("value", ["-1", '"5"', "true", "1e999"])
def test_bad_timing_is_dropped_not_the_run(arch: Archive, inbox: Path, value: str) -> None:
    """A timing that is negative, not a number, or not finite is stored as NULL."""
    now = time.time()
    line = make_event(now).to_line().replace(b'"overhead":null', f'"overhead":{value}'.encode())
    inbox.write_bytes(line)
    arch.ingest(inbox, now=now)
    assert arch.ingest(inbox, now=now + 3) == 1
    assert _timings(arch) == [(None, None, 1, 0, 0)]


def test_v2_archive_backfills_timings(tmp_path: Path) -> None:
    """Opening a version 2 archive adds the timing columns and fills them from raw."""
    path = tmp_path / "a.sqlite3"
    connection = sqlite3.connect(path)
    connection.executescript(
        V1_SCHEMA.replace("reason TEXT\n", "reason TEXT,\n    raw TEXT\n").replace(
            "'schema_version', '1'", "'schema_version', '2'"
        )
    )
    rows = [
        ("h2", 2.0, '{"v":1,"overhead":0.5,"waited":2}'),
        ("h3", 3.0, '{"v":1,"overhead":0.5,"waited":null}'),
        ("h4", 4.0, '{"v":1,"overhead":-1,"waited":1e999,"reported":true}'),
        ("h5", 5.0, "not json"),
    ]
    connection.executemany(
        "INSERT INTO events (line_hash, ts, name, paths, outcome, raw)"
        " VALUES (?, ?, 'x', '[]', 'pass', ?)",
        rows,
    )
    connection.commit()
    connection.close()
    with Archive.open(path) as arch:
        assert arch.meta("schema_version") == "3"
        assert _timings(arch) == [
            (None, None, 0, 0, 0),
            (0.5, 2.0, 1, 0, 0),
            (0.5, None, 1, 0, 0),
            (None, None, 1, 1, 0),
            (None, None, 0, 0, 0),
        ]
