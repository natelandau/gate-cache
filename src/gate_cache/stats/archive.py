"""Archive recorded gate runs in SQLite and ingest them from the inbox."""

from __future__ import annotations

import contextlib
import hashlib
import json
import math
import re
import sqlite3
import time
from typing import TYPE_CHECKING, Any, Self

from gate_cache.stats import config
from gate_cache.stats.junit import TESTS_DIR_NAME

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path
    from types import TracebackType

SCHEMA_VERSION = 6
RETENTION_DAYS = 365
TEST_RETENTION_DAYS = 90
# How long a per-run test file may wait for its event, or a temp file for its rename, before
# ingest treats it as left by a killed run and deletes it.
ORPHAN_GRACE_SECONDS = 3600
SETTLE_SECONDS = 2.0
# How often ingest rescans an unchanged per-run test folder when no events arrived.
TESTS_RESCAN_SECONDS = 60
ARCHIVE_NAME = "stats.sqlite3"

_PROCESSING_RE = re.compile(r"^events\.(\d+)\.processing$")
_SECONDS_PER_DAY = 86400
_NS_PER_SECOND = 1_000_000_000
_INT64_MAX = 2**63 - 1
_INT64_MIN = -(2**63)

# The gate a run counts toward in stats. A name with no whitespace that holds `@` is a gate
# plus a key, such as `test@v22.1.0` or `test@3f2a9c`: the key changes the cache key, while
# stats keep every key's runs under the part before the first `@`. A command line has
# spaces, so an argument such as `npx eslint@9` never merges two commands into one gate.
# The dashboard reads the result from each event's `gate` field rather than repeating the rule;
# frontend/src/lib/gates.ts isCommandLine must match the whitespace set below.
_GATE_WHITESPACE = " \t\n\v\f\r"
GATE_EXPRESSION = (
    "CASE WHEN instr(name, '@') > 1 AND instr(name, '@') < length(name)"
    f" AND name NOT GLOB '*[' || char({', '.join(str(ord(c)) for c in _GATE_WHITESPACE)}) || ']*'"
    " THEN substr(name, 1, instr(name, '@') - 1) ELSE name END"
)
_GATE_COLUMN = f"gate TEXT GENERATED ALWAYS AS ({GATE_EXPRESSION}) VIRTUAL"


def gate_of(name: str) -> str:
    """Return the gate a run name counts toward in stats, by the rule of `GATE_EXPRESSION`.

    Use it to check a name in Python the same way the archive groups it.
    """
    at = name.find("@")
    if 0 < at < len(name) - 1 and not any(c in _GATE_WHITESPACE for c in name):
        return name[:at]
    return name


_SCHEMA = f"""
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS events (
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
    reason TEXT,
    raw TEXT,
    overhead REAL,
    waited REAL,
    wait_known INTEGER NOT NULL DEFAULT 0,
    reported INTEGER NOT NULL DEFAULT 0,
    wait_timed_out INTEGER NOT NULL DEFAULT 0,
    event_uid TEXT,
    spot_check INTEGER NOT NULL DEFAULT 0,
    {_GATE_COLUMN}
);
CREATE INDEX IF NOT EXISTS events_repo_ts ON events (repo, ts);
CREATE INDEX IF NOT EXISTS events_repo_gate_ts ON events (repo, gate, ts);
CREATE INDEX IF NOT EXISTS events_ts ON events (ts);
CREATE INDEX IF NOT EXISTS events_event_uid ON events (event_uid);
CREATE TABLE IF NOT EXISTS tests (
    id INTEGER PRIMARY KEY,
    repo TEXT,
    gate TEXT NOT NULL,
    name TEXT NOT NULL,
    UNIQUE (repo, gate, name)
);
CREATE TABLE IF NOT EXISTS test_results (
    event_id INTEGER NOT NULL,
    test_id INTEGER NOT NULL,
    outcome TEXT NOT NULL,
    duration REAL
);
CREATE INDEX IF NOT EXISTS test_results_test_id ON test_results (test_id);
CREATE INDEX IF NOT EXISTS test_results_event_id ON test_results (event_id);
"""

_INSERT = (
    "INSERT OR IGNORE INTO events "
    "(line_hash, ts, repo, name, tree, paths, outcome, duration, saved, exit_code, reason, raw,"
    " overhead, waited, wait_known, reported, wait_timed_out, event_uid, spot_check) "
    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
)

# Columns added after version 1, which an older archive fills from the raw line of each row.
# Rows from before version 2 keep a NULL raw line.
_ADDED_COLUMNS = (
    ("raw", "TEXT"),
    ("overhead", "REAL"),
    ("waited", "REAL"),
    ("wait_known", "INTEGER NOT NULL DEFAULT 0"),
    ("reported", "INTEGER NOT NULL DEFAULT 0"),
    ("wait_timed_out", "INTEGER NOT NULL DEFAULT 0"),
    ("event_uid", "TEXT"),
    ("spot_check", "INTEGER NOT NULL DEFAULT 0"),
)
_WAIT_VERSION = 3
_BACKFILL_WAIT = (
    "UPDATE events SET overhead = ?, waited = ?, wait_known = ?, reported = ?,"
    " wait_timed_out = ? WHERE id = ?"
)
_UID_VERSION = 5
_BACKFILL_UID = (
    "UPDATE events SET event_uid = json_extract(raw, '$.id')"
    " WHERE event_uid IS NULL AND json_valid(raw) AND json_type(raw, '$.id') = 'text'"
)
# An older gate-cache can ingest a newer event and drop the flag, so migration fills the
# column from each row's raw line.
_SPOT_CHECK_VERSION = 6
_BACKFILL_SPOT_CHECK = (
    "UPDATE events SET spot_check = 1 WHERE spot_check = 0 AND raw IS NOT NULL"
    " AND CASE WHEN json_valid(raw) THEN json_type(raw, '$.spot_check') END = 'true'"
)
_BACKFILL_BATCH = 1000
# The per-test cutoff of the last prune, below which no event holds results.
_TESTS_PRUNED_KEY = "tests_pruned_before"


def tests_since(now: float) -> float:
    """Return the oldest event time whose per-test results are still kept."""
    return now - TEST_RETENTION_DAYS * _SECONDS_PER_DAY


def archive_path() -> Path:
    """Return the path of the SQLite archive."""
    return config.state_dir() / ARCHIVE_NAME


class ArchiveVersionError(RuntimeError):
    """Raised when an archive was written by a newer schema than this version supports."""


def _is_int(value: object) -> bool:
    """Return whether value is an integer that SQLite can store, excluding booleans."""
    return (
        isinstance(value, int) and not isinstance(value, bool) and _INT64_MIN <= value <= _INT64_MAX
    )


def _is_number(value: object) -> bool:
    """Return whether value is a finite number SQLite can store, excluding booleans."""
    if isinstance(value, float):
        return math.isfinite(value)
    return _is_int(value)


def _is_text(value: object) -> bool:
    """Return whether value is a string that encodes as UTF-8."""
    if not isinstance(value, str):
        return False
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def _seconds(value: object) -> float | None:
    """Return value as a timing in seconds, or None when it is missing or not a valid timing."""
    if not _is_number(value) or not isinstance(value, int | float):
        return None
    return float(value) if value >= 0 else None


def _wait_fields(data: dict[str, Any]) -> tuple[float | None, float | None, bool, bool, bool]:
    """Return the overhead, waited, wait_known, reported, and wait_timed_out columns of an event.

    `wait_known` tells a run that did not wait (the event has `waited`, as null) from one that
    a gate-cache recorded before it recorded waits (the event has no `waited`). A bad timing
    becomes None, so it drops only itself and the run still counts.
    """
    return (
        _seconds(data.get("overhead")),
        _seconds(data.get("waited")),
        "waited" in data,
        data.get("reported") is True,
        data.get("wait_timed_out") is True,
    )


def _event_uid(data: dict[str, Any]) -> str | None:
    """Return the event's random id, which names its per-run test file, or None."""
    uid = data.get("id")
    return uid if _is_text(uid) else None


def _test_row(row: object) -> tuple[str, str, float | None] | None:
    """Validate one `[name, outcome, duration]` row of a per-run test file, or return None."""
    if not isinstance(row, list) or len(row) != 3:  # noqa: PLR2004
        return None
    name, outcome, duration = row
    # An outcome from a newer gate-cache is stored; the queries count only known ones.
    if not _is_text(name) or not _is_text(outcome):
        return None
    if not _optional(duration, check=_is_number):
        return None
    return name, outcome, _seconds(duration)


def _stored_float(value: str | None) -> float | None:
    """Return a float stored in the meta table, or None when it is unset or unreadable."""
    if value is None:
        return None
    try:
        number = float(value)
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def _discard(path: Path) -> None:
    """Delete a file if it exists, leaving it for a later cycle when the delete fails."""
    with contextlib.suppress(OSError):
        path.unlink(missing_ok=True)


def _optional(value: object, *, check: Any) -> bool:  # noqa: ANN401
    """Return whether value is None or passes the check."""
    return value is None or bool(check(value))


def _row(raw: bytes) -> tuple[Any, ...] | None:
    """Validate one inbox line and return its insert parameters, or None to skip it."""
    try:
        # Decode first: json.loads also accepts UTF-16 and UTF-32 bytes, which gate-cache
        # never writes and the archive could not keep as text.
        text = raw.decode("utf-8")
        data = json.loads(text)
    except (ValueError, RecursionError):
        return None
    if not isinstance(data, dict) or data.get("v") != 1:
        return None
    paths = data.get("paths")
    valid = (
        _is_number(data.get("ts"))
        and _is_text(data.get("name"))
        # An outcome from a newer gate-cache is stored; the queries count only known ones.
        and _is_text(data.get("outcome"))
        and isinstance(paths, list)
        and all(_is_text(p) for p in paths)
        and _optional(data.get("repo"), check=_is_text)
        and _optional(data.get("tree"), check=_is_text)
        and _optional(data.get("reason"), check=_is_text)
        and _optional(data.get("duration"), check=_is_number)
        and _optional(data.get("saved"), check=_is_number)
        and _optional(data.get("exit_code"), check=_is_int)
    )
    if not valid:
        return None
    return (
        hashlib.sha256(raw).hexdigest(),
        data["ts"],
        data.get("repo"),
        data["name"],
        data.get("tree"),
        json.dumps(paths, separators=(",", ":")),
        data["outcome"],
        data.get("duration"),
        data.get("saved"),
        data.get("exit_code"),
        data.get("reason"),
        text,
        *_wait_fields(data),
        _event_uid(data),
        data.get("spot_check") is True,
    )


def _check_version(connection: sqlite3.Connection, *, path: Path) -> int | None:
    """Return the stored schema version, or None for a new archive.

    Raises:
        ArchiveVersionError: If the stored version is unreadable or newer than this code.
    """
    has_meta = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'meta'"
    ).fetchone()
    if has_meta is None:
        return None
    stored = connection.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()
    if stored is None:
        return None
    value = stored[0]
    if not isinstance(value, str) or re.fullmatch(r"\d+", value) is None:
        msg = f"archive {path} has an unreadable schema version {value!r}"
        raise ArchiveVersionError(msg)
    if int(value) > SCHEMA_VERSION:
        msg = (
            f"archive {path} has schema version {value}, newer than the "
            f"supported version {SCHEMA_VERSION}; upgrade gate-cache"
        )
        raise ArchiveVersionError(msg)
    return int(value)


def _migrate(connection: sqlite3.Connection, *, stored: int | None) -> None:
    """Bring an older archive's tables up to the current schema, keeping every row.

    Args:
        connection: The open archive.
        stored: The schema version the archive records, or None when it records none.
    """
    columns = {row[1] for row in connection.execute("PRAGMA table_info(events)")}
    if not columns:
        return
    for column, kind in _ADDED_COLUMNS:
        if column not in columns:
            connection.execute(f"ALTER TABLE events ADD COLUMN {column} {kind}")
    # PRAGMA table_info leaves out generated columns, so ask table_xinfo.
    if "gate" not in {row[1] for row in connection.execute("PRAGMA table_xinfo(events)")}:
        connection.execute(f"ALTER TABLE events ADD COLUMN {_GATE_COLUMN}")
    connection.execute("DROP INDEX IF EXISTS events_repo_name_ts")
    # Keyed on the version, not the columns, so a backfill cut short runs again.
    if stored is None or stored < _WAIT_VERSION:
        _backfill(connection, update=_BACKFILL_WAIT, fields=_wait_fields)
    if stored is None or stored < _UID_VERSION:
        connection.execute(_BACKFILL_UID)
    if stored is None or stored < _SPOT_CHECK_VERSION:
        connection.execute(_BACKFILL_SPOT_CHECK)


def _backfill(
    connection: sqlite3.Connection,
    *,
    update: str,
    fields: Callable[[dict[str, Any]], tuple[Any, ...]],
) -> None:
    """Fill added columns from each row's raw line, with the same rules as ingest.

    Args:
        connection: The open archive.
        update: An UPDATE statement whose last parameter is the row id.
        fields: Return the other parameters from a row's parsed raw line.
    """
    last = 0
    while rows := connection.execute(
        "SELECT id, raw FROM events WHERE id > ? AND raw IS NOT NULL ORDER BY id LIMIT ?",
        (last, _BACKFILL_BATCH),
    ).fetchall():
        updates: list[tuple[Any, ...]] = []
        for event_id, raw in rows:
            try:
                data = json.loads(raw)
            except (ValueError, RecursionError):
                continue
            if isinstance(data, dict):
                updates.append((*fields(data), event_id))
        connection.executemany(update, updates)
        last = rows[-1][0]


class Archive:
    """A SQLite store of gate runs.

    Only one process may ingest at a time; the dashboard lock guarantees that. A connection
    belongs to the thread that opened it, so each thread opens its own archive.
    """

    def __init__(self, connection: sqlite3.Connection) -> None:
        """Wrap an open connection whose schema already exists."""
        self._connection = connection
        # The tests folder's mtime and the time of the last full scan of it.
        self._tests_scan: tuple[int, float] | None = None

    @classmethod
    def open(cls, path: Path) -> Archive:
        """Open the archive at path, creating the file and schema when missing.

        Args:
            path: Location of the SQLite file.

        Returns:
            The open archive.
        """
        path.parent.mkdir(mode=config.STATE_DIR_MODE, parents=True, exist_ok=True)
        connection = sqlite3.connect(path)
        try:
            # Check the version before WAL or schema changes so a newer archive is left untouched.
            stored = _check_version(connection, path=path)
            connection.execute("PRAGMA journal_mode=WAL")
            # An archive without a version row can still hold an older events table, and
            # _migrate is a no-op on a current or missing one.
            if stored is None or stored < SCHEMA_VERSION:
                _migrate(connection, stored=stored)
            connection.executescript(_SCHEMA)
            connection.execute(
                "INSERT INTO meta (key, value) VALUES ('schema_version', ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (str(SCHEMA_VERSION),),
            )
            connection.commit()
        except (sqlite3.Error, ArchiveVersionError):
            connection.close()
            raise
        return cls(connection)

    def __enter__(self) -> Self:
        """Return the archive for use in a with block."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Close the archive."""
        self.close()

    def close(self) -> None:
        """Close the database connection."""
        self._connection.close()

    @property
    def connection(self) -> sqlite3.Connection:
        """The underlying connection, for queries."""
        return self._connection

    def meta(self, key: str) -> str | None:
        """Return a value from the meta table, or None when unset."""
        row = self._connection.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return None if row is None else row[0]

    def _set_meta(self, key: str, value: str) -> None:
        """Store a meta value without committing."""
        self._connection.execute(
            "INSERT INTO meta (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )

    def _ingest_file(self, path: Path, *, delete: bool = True) -> int:
        """Insert the valid lines of one renamed inbox file, delete it if asked, and count adds."""
        try:
            handle = path.open("rb")
        except FileNotFoundError:
            return 0
        added = 0
        with handle:
            for line in handle:
                raw = line.removesuffix(b"\n")
                row = _row(raw) if raw.strip() else None
                if row is None:
                    continue
                try:
                    added += self._connection.execute(_INSERT, row).rowcount
                except (OverflowError, ValueError, sqlite3.InterfaceError, sqlite3.DataError):
                    # A value SQLite cannot bind drops only its own line.
                    continue
        self._connection.commit()
        # Deleting only after the commit means a crash or a failed delete re-reads the file,
        # and the hash dedupes it.
        if delete:
            _discard(path)
        return added

    def _ingest_safely(self, path: Path, *, delete: bool = True) -> int:
        """Ingest one file, leaving it for a later cycle when it cannot be read or stored."""
        try:
            return self._ingest_file(path, delete=delete)
        except (OSError, sqlite3.Error):
            # One bad file must not stop the others or the inbox rotation.
            self._connection.rollback()
            return 0

    def _ingest_processing(self, state: Path, *, now: float, fresh: bool) -> tuple[int, bool]:
        """Read the renamed inbox files, deleting each once it has settled.

        Returns:
            The events added, and whether any file stays with lines still to come.
        """
        added = 0
        pending = False
        for path in sorted(state.glob("events.*.processing")):
            match = _PROCESSING_RE.match(path.name)
            if match is None:
                continue
            if now - int(match.group(1)) / _NS_PER_SECOND >= SETTLE_SECONDS:
                added += self._ingest_safely(path)
            elif fresh:
                # Each event is one append, so a line still being written fails to parse and
                # is skipped, and the line hash keeps the settled re-read from duplicating.
                added += self._ingest_safely(path, delete=False)
            # A file that failed to ingest, or has not settled, stays with lines still to come.
            pending = pending or path.exists()
        return added, pending

    def ingest(self, inbox: Path, *, now: float | None = None, fresh: bool = False) -> int:
        """Move events from the inbox into the archive.

        Settled `events.*.processing` files are read first. The live inbox is then renamed so
        that writers still holding it finish into a file the next cycle ingests. A live inbox
        that has not changed for the settle window is also read in the same cycle, but kept
        until it settles under its new name.

        Args:
            inbox: Path of the live `events.jsonl`.
            now: Unix time for the settle check; defaults to the current time.
            fresh: Also read the files that have not settled, and keep them for the settled
                pass. A one-off reader that must see a run that just ended sets it.

        Returns:
            The number of events added.
        """
        now = time.time() if now is None else now
        # pending: whether some event lines stay unread this cycle, so a test file's event may
        # still come.
        added, pending = self._ingest_processing(inbox.parent, now=now, fresh=fresh)
        try:
            settled = now - inbox.stat().st_mtime >= SETTLE_SECONDS
            renamed = inbox.with_name(f"events.{time.time_ns()}.processing")
            inbox.rename(renamed)
        except FileNotFoundError:
            pass
        else:
            if settled or fresh:
                # A writer that opened the inbox before the rename can still append, so the file
                # stays for the settled pass, which picks up late lines and deletes it.
                added += self._ingest_safely(renamed, delete=False)
            if not settled:
                pending = True
        if added:
            count = int(self.meta("ingest_count") or 0) + 1
            self._set_meta("ingest_count", str(count))
            self._set_meta("last_ingest", str(now))
            self._connection.commit()
        tests_added = self._ingest_tests(
            inbox.parent / TESTS_DIR_NAME,
            now=now,
            delete_orphans=not pending,
            events_added=added > 0,
        )
        if added or tests_added:
            self.prune(now=now)
        return added

    def _ingest_tests(
        self, folder: Path, *, now: float, delete_orphans: bool, events_added: bool
    ) -> int:
        """Store the settled per-run test files whose events are archived, and count the rows.

        Args:
            folder: The folder of per-run test files.
            now: Unix time for the settle and grace checks.
            delete_orphans: Delete files left by killed runs. False while some event lines stay
                unread, since an old file's event can sit in them.
            events_added: Whether this cycle archived events, whose files may now be stored.

        Returns:
            The number of test results added.
        """
        added = 0
        for path in self._tests_to_scan(folder, now=now, events_added=events_added):
            try:
                age = now - path.stat().st_mtime
            except OSError:
                continue
            past_grace = age >= ORPHAN_GRACE_SECONDS
            if path.name.startswith("."):
                if path.suffix == ".tmp" and delete_orphans and past_grace:
                    _discard(path)
                continue
            if path.suffix != ".json" or age < SETTLE_SECONDS:
                continue
            try:
                added += self._ingest_test_file(
                    path, orphan=delete_orphans and past_grace, since=tests_since(now)
                )
            except OSError:
                # One bad file must not stop the others, and one that stays unreadable past
                # the grace period would otherwise be retried forever.
                self._connection.rollback()
                if past_grace:
                    _discard(path)
            except sqlite3.Error:
                self._connection.rollback()
        return added

    def _tests_to_scan(self, folder: Path, *, now: float, events_added: bool) -> list[Path]:
        """Return the tests folder's entries to scan this cycle, sorted, and record the scan.

        A cycle that added no events skips an unchanged folder until the rescan interval
        passes, so that settle and grace ages still progress.
        """
        try:
            # Taken before the listing, so a file added during the scan changes it and is seen.
            mtime = folder.stat().st_mtime_ns
            if (
                not events_added
                and self._tests_scan is not None
                and self._tests_scan[0] == mtime
                and now - self._tests_scan[1] < TESTS_RESCAN_SECONDS
            ):
                return []
            self._tests_scan = (mtime, now)
            return sorted(folder.iterdir())
        except OSError:
            return []

    def _ingest_test_file(self, path: Path, *, orphan: bool, since: float) -> int:
        """Store one per-run test file once its event is archived, then delete it.

        Args:
            path: The file, named after its event's id.
            orphan: Delete the file when its event is not archived.
            since: The oldest event time whose results are kept; an older event's file is
                deleted unread, since prune would not reach its rows.

        Returns:
            The number of test results added.
        """
        event = self._connection.execute(
            "SELECT id, repo, gate, ts FROM events WHERE event_uid = ? ORDER BY id LIMIT 1",
            (path.stem,),
        ).fetchone()
        if event is None:
            if orphan:
                _discard(path)
            return 0
        event_id, repo, gate, ts = event
        added = 0
        stored = self._connection.execute(
            "SELECT 1 FROM test_results WHERE event_id = ? LIMIT 1", (event_id,)
        ).fetchone()
        if stored is None and ts >= since:
            added = self._store_test_rows(
                self._read_test_file(path), event_id=event_id, repo=repo, gate=gate
            )
            self._connection.commit()
        # Deleting only after the commit means a crash re-reads the file, and the stored rows
        # for its event keep it from being added twice.
        _discard(path)
        return added

    def _store_test_rows(
        self,
        rows: list[tuple[str, str, float | None]],
        *,
        event_id: int,
        repo: str | None,
        gate: str,
    ) -> int:
        """Insert one run's test results, adding any test the gate has not seen, and count them."""
        if not rows:
            return 0
        names = list(dict.fromkeys(name for name, _, _ in rows))
        self._connection.executemany(
            "INSERT INTO tests (repo, gate, name) SELECT ?, ?, ? WHERE NOT EXISTS"
            " (SELECT 1 FROM tests WHERE repo IS ? AND gate = ? AND name = ?)",
            [(repo, gate, name, repo, gate, name) for name in names],
        )
        # One read of the gate's tests beats a lookup per name; a run lists most of them.
        ids: dict[str, int] = dict(
            self._connection.execute(
                "SELECT name, id FROM tests WHERE repo IS ? AND gate = ?", (repo, gate)
            ).fetchall()
        )
        self._connection.executemany(
            "INSERT INTO test_results (event_id, test_id, outcome, duration) VALUES (?, ?, ?, ?)",
            [(event_id, ids[name], outcome, duration) for name, outcome, duration in rows],
        )
        return len(rows)

    @staticmethod
    def _read_test_file(path: Path) -> list[tuple[str, str, float | None]]:
        """Return the valid rows of a per-run test file, or none when it is not a JSON list."""
        try:
            data = json.loads(path.read_bytes().decode("utf-8"))
        except (ValueError, RecursionError):
            return []
        if not isinstance(data, list):
            return []
        return [row for row in map(_test_row, data) if row is not None]

    def prune(self, *, now: float | None = None) -> int:
        """Delete events and per-test results older than their retention windows.

        Args:
            now: Unix time to measure from; defaults to the current time.

        Returns:
            The number of events deleted.
        """
        now = time.time() if now is None else now
        cutoff = tests_since(now)
        # Ingest stores no results for an event older than the cutoff, so only events that
        # crossed it since the last prune can hold any. Bounding the range keeps this from
        # reading every older event on each cycle.
        lower = _stored_float(self.meta(_TESTS_PRUNED_KEY))
        # Results go before events, so no result outlives its event.
        results = self._connection.execute(
            "DELETE FROM test_results"
            " WHERE event_id IN (SELECT id FROM events WHERE ts < ? AND ts >= ?)",
            (cutoff, -math.inf if lower is None else lower),
        )
        self._set_meta(_TESTS_PRUNED_KEY, repr(cutoff))
        if results.rowcount:
            # This scans every test, so it runs only when results were removed.
            self._connection.execute(
                "DELETE FROM tests WHERE id NOT IN (SELECT test_id FROM test_results)"
            )
        cursor = self._connection.execute(
            "DELETE FROM events WHERE ts < ?", (now - RETENTION_DAYS * _SECONDS_PER_DAY,)
        )
        self._connection.commit()
        return cursor.rowcount
