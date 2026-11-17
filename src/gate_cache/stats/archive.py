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

if TYPE_CHECKING:
    from pathlib import Path
    from types import TracebackType

SCHEMA_VERSION = 3
RETENTION_DAYS = 365
SETTLE_SECONDS = 2.0
ARCHIVE_NAME = "stats.sqlite3"

_PROCESSING_RE = re.compile(r"^events\.(\d+)\.processing$")
_SECONDS_PER_DAY = 86400
_NS_PER_SECOND = 1_000_000_000
_INT64_MAX = 2**63 - 1
_INT64_MIN = -(2**63)

_SCHEMA = """
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
    wait_timed_out INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS events_repo_ts ON events (repo, ts);
CREATE INDEX IF NOT EXISTS events_repo_name_ts ON events (repo, name, ts);
CREATE INDEX IF NOT EXISTS events_ts ON events (ts);
"""

_INSERT = (
    "INSERT OR IGNORE INTO events "
    "(line_hash, ts, repo, name, tree, paths, outcome, duration, saved, exit_code, reason, raw,"
    " overhead, waited, wait_known, reported, wait_timed_out) "
    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
)

# Columns added in version 3, which an older archive fills from the raw line of each row.
_WAIT_VERSION = 3
_WAIT_COLUMNS = (
    ("overhead", "REAL"),
    ("waited", "REAL"),
    ("wait_known", "INTEGER NOT NULL DEFAULT 0"),
    ("reported", "INTEGER NOT NULL DEFAULT 0"),
    ("wait_timed_out", "INTEGER NOT NULL DEFAULT 0"),
)
_BACKFILL = (
    "UPDATE events SET overhead = ?, waited = ?, wait_known = ?, reported = ?,"
    " wait_timed_out = ? WHERE id = ?"
)
_BACKFILL_BATCH = 1000


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
    if "raw" not in columns:
        # Rows from before version 2 keep a NULL raw line.
        connection.execute("ALTER TABLE events ADD COLUMN raw TEXT")
    for column, kind in _WAIT_COLUMNS:
        if column not in columns:
            connection.execute(f"ALTER TABLE events ADD COLUMN {column} {kind}")
    # Keyed on the version, not the columns, so a backfill cut short runs again.
    if stored is None or stored < _WAIT_VERSION:
        _backfill(connection)


def _backfill(connection: sqlite3.Connection) -> None:
    """Fill the version 3 columns from each row's raw line, with the same rules as ingest."""
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
                updates.append((*_wait_fields(data), event_id))
        connection.executemany(_BACKFILL, updates)
        last = rows[-1][0]


class Archive:
    """A SQLite store of gate runs.

    Only one process may ingest at a time; the dashboard lock guarantees that. A connection
    belongs to the thread that opened it, so each thread opens its own archive.
    """

    def __init__(self, connection: sqlite3.Connection) -> None:
        """Wrap an open connection whose schema already exists."""
        self._connection = connection

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
            with contextlib.suppress(OSError):
                path.unlink(missing_ok=True)
        return added

    def _ingest_safely(self, path: Path, *, delete: bool = True) -> int:
        """Ingest one file, leaving it for a later cycle when it cannot be read or stored."""
        try:
            return self._ingest_file(path, delete=delete)
        except (OSError, sqlite3.Error):
            # One bad file must not stop the others or the inbox rotation.
            self._connection.rollback()
            return 0

    def ingest(self, inbox: Path, *, now: float | None = None) -> int:
        """Move events from the inbox into the archive.

        Settled `events.*.processing` files are read first. The live inbox is then renamed so
        that writers still holding it finish into a file the next cycle ingests. A live inbox
        that has not changed for the settle window is also read in the same cycle, but kept
        until it settles under its new name.

        Args:
            inbox: Path of the live `events.jsonl`.
            now: Unix time for the settle check; defaults to the current time.

        Returns:
            The number of events added.
        """
        now = time.time() if now is None else now
        added = 0
        for path in sorted(inbox.parent.glob("events.*.processing")):
            match = _PROCESSING_RE.match(path.name)
            if match is None:
                continue
            if now - int(match.group(1)) / _NS_PER_SECOND >= SETTLE_SECONDS:
                added += self._ingest_safely(path)
        try:
            settled = now - inbox.stat().st_mtime >= SETTLE_SECONDS
            renamed = inbox.with_name(f"events.{time.time_ns()}.processing")
            inbox.rename(renamed)
        except FileNotFoundError:
            pass
        else:
            if settled:
                # A writer that opened the inbox before the rename can still append, so the file
                # stays for the settled pass, which picks up late lines and deletes it.
                added += self._ingest_safely(renamed, delete=False)
        if added:
            count = int(self.meta("ingest_count") or 0) + 1
            self._set_meta("ingest_count", str(count))
            self._set_meta("last_ingest", str(now))
            self._connection.commit()
            self.prune(now=now)
        return added

    def prune(self, *, now: float | None = None) -> int:
        """Delete events older than the retention window.

        Args:
            now: Unix time to measure from; defaults to the current time.

        Returns:
            The number of events deleted.
        """
        now = time.time() if now is None else now
        cursor = self._connection.execute(
            "DELETE FROM events WHERE ts < ?", (now - RETENTION_DAYS * _SECONDS_PER_DAY,)
        )
        self._connection.commit()
        return cursor.rowcount
