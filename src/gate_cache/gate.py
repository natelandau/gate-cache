"""Run a gate command, skipping it when it already passed on the same tree."""

from __future__ import annotations

import contextlib
import json
import os
import shlex
import sys
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any

from gate_cache import __version__
from gate_cache.console import confirm_deletion, format_duration, kv, say, stdin_isatty
from gate_cache.env import CI_ENV, flag_on
from gate_cache.gate_lock import (
    GateLock,
    held_by_ancestor,
    held_env,
    lock_path,
    prune_locks,
    read_holder,
)
from gate_cache.markers import (
    RecordIndex,
    clear_markers,
    marker_dir,
    marker_duration,
    marker_exists,
    marker_path,
    miss_path,
    miss_record,
    prune_markers,
    scope_fields,
    write_marker,
    write_miss,
)
from gate_cache.runner import Terminated, raise_on_termination, run_child
from gate_cache.snapshot import git_common_dir, normalize_paths, take_snapshot, take_snapshots
from gate_cache.stats import config as stats_config
from gate_cache.stats import context as run_context
from gate_cache.stats.recorder import Event, Outcome, record_event
from gate_cache.wait_settings import WaitSettings, wait_settings

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from gate_cache.snapshot import Snapshot

DISABLE_ENV = "GATE_CACHE_DISABLE"
MAX_AGE_ENV = "GATE_CACHE_MAX_AGE_DAYS"
DEFAULT_MAX_AGE_DAYS = 30
_DISABLED_REASON = f"caching disabled by {DISABLE_ENV}"
_CI_REASON = f"caching disabled in CI ({DISABLE_ENV}=0 keeps it on)"
_NO_COMMON_DIR_REASON = "could not locate git directory"
_FILES_CHANGED = "files changed during the run"
FILES_CHANGED_NOTICE = f"{_FILES_CHANGED}, not recording pass"
REPORTED_FAILURE_REASON = "failed in another run, not rerun"


def disabled_reason(environ: Mapping[str, str] | None = None) -> str | None:
    """Explain why caching is off, so a gate runs every time and reports the cause.

    A non-empty GATE_CACHE_DISABLE decides: `0` or `false` keeps caching on and any other
    value turns it off. Otherwise CI decides, because a persistent CI runner keeps
    markers between jobs. Both read empty, `0`, and `false` in any case as off.

    Args:
        environ: Environment to read; defaults to the process environment.

    Returns:
        The message to show when caching is off, or None when caching is on.
    """
    env = os.environ if environ is None else environ
    disable = env.get(DISABLE_ENV, "")
    if disable.strip():
        return _DISABLED_REASON if flag_on(disable) else None
    if flag_on(env.get(CI_ENV, "")):
        return _CI_REASON
    return None


def marker_max_age_days(environ: Mapping[str, str] | None = None) -> int:
    """Read how many days a marker lives before pruning deletes it.

    An invalid value warns and falls back to the default, so a typo in the setting
    can never fail a gate.

    Args:
        environ: Environment to read; defaults to the process environment.

    Returns:
        The positive whole number of days from GATE_CACHE_MAX_AGE_DAYS, or 30 when it
        is unset, empty, or invalid.
    """
    value = (os.environ if environ is None else environ).get(MAX_AGE_ENV, "").strip()
    if not value:
        return DEFAULT_MAX_AGE_DAYS
    try:
        days = int(value)
    except ValueError:
        days = 0
    if days < 1:
        say(
            f"warning: {MAX_AGE_ENV}={value!r} is not a positive whole number of days, "
            f"using {DEFAULT_MAX_AGE_DAYS}"
        )
        return DEFAULT_MAX_AGE_DAYS
    return days


def _round(value: float | None, digits: int) -> float | None:
    """Round a measurement, keeping None."""
    return None if value is None else round(value, digits)


def _marker_age(marker: Path | None) -> float | None:
    """Return the seconds since a marker was written, or None when unknown."""
    if marker is None:
        return None
    try:
        return round(time.time() - marker.stat().st_mtime, 1)
    except OSError:
        return None


def _cwd() -> Path | None:
    """Return the resolved working directory, or None when it is gone."""
    try:
        return Path.cwd().resolve()
    except (OSError, RuntimeError):
        return None


class _Stats:
    """Collect and record the stats event of one gate run.

    Every lookup and measurement happens only while stats are on, so a gate with stats
    off does no extra work at all.
    """

    def __init__(self, setting: stats_config.StatsSetting | None) -> None:
        """Wrap the stats setting read for this run, or None when it could not be read."""
        self._setting = setting

    @classmethod
    def load(cls) -> _Stats:
        """Read the stats setting once for the run; never raise."""
        # Stats must not change a gate's result, even when the setting cannot be read.
        try:
            return cls(stats_config.stats_setting())
        except Exception:  # noqa: BLE001
            return cls(None)

    @property
    def enabled(self) -> bool:
        """Return whether this run records an event."""
        return self._setting is not None and self._setting.enabled

    def now(self) -> float | None:
        """Start an overhead measurement, or return None when stats are off."""
        return time.monotonic() if self.enabled else None

    @staticmethod
    def elapsed(started: float | None) -> float | None:
        """Return the seconds since a measurement from `now` started, or None without one."""
        return None if started is None else time.monotonic() - started

    def usage(self) -> run_context.ChildUsage | None:
        """Read child resource use before a command runs, or None when stats are off."""
        return run_context.child_usage() if self.enabled else None

    def usage_since(self, before: run_context.ChildUsage | None) -> dict[str, Any]:
        """Return the `cpu` and `max_rss` fields of the command that just exited.

        Call it right after the command exits, before gate-cache starts git again, so the
        numbers cover only the command.

        Args:
            before: The reading from `usage` taken just before the command ran.

        Returns:
            The two fields, or an empty dict when stats are off or rusage is unavailable.
        """
        if not self.enabled or before is None:
            return {}
        after = run_context.child_usage()
        if after is None:
            return {}
        return {"cpu": round(after.cpu - before.cpu, 3), "max_rss": after.max_rss}

    def common_dir(self, snapshot: Snapshot | None) -> Path | None:
        """Return the snapshot's git common directory, else look it up; never raise."""
        if not self.enabled:
            return None
        if snapshot is not None and snapshot.common_dir is not None:
            return snapshot.common_dir
        try:
            return git_common_dir()
        except Exception:  # noqa: BLE001
            return None

    def record(
        self,
        *,
        name: str,
        command: Sequence[str],
        worktree: Path | None,
        common_dir: Path | None,
        overhead: float | None = None,
        marker: Path | None = None,
        **fields: Any,
    ) -> None:
        """Record the run as a stats event when stats are on; never raise.

        Args:
            name: Gate name.
            command: Command and arguments of the gate.
            worktree: Top of the working tree, when known.
            common_dir: Git common directory, when known.
            overhead: Seconds spent before deciding, for a run that checked its cache.
            marker: The marker a skip used.
            **fields: The remaining Event fields.
        """
        if not self.enabled:
            return
        # Stats must not change a gate's result, even when building the event fails.
        try:
            context = self._context(
                name=name, command=command, worktree=worktree, common_dir=common_dir
            )
            event = Event(
                ts=time.time(),
                name=name,
                repo=str(common_dir) if common_dir is not None else None,
                overhead=_round(overhead, 3),
                marker_age=_marker_age(marker),
                **context,
                **fields,
            )
            record_event(event, setting=self._setting)
        except Exception:  # noqa: BLE001
            return

    @staticmethod
    def _context(
        *, name: str, command: Sequence[str], worktree: Path | None, common_dir: Path | None
    ) -> dict[str, Any]:
        """Gather where and how the gate ran, from files and the environment only."""
        import uuid

        cwd = _cwd()
        if worktree is None and cwd is not None:
            worktree = run_context.find_worktree(cwd)
        source = run_context.detect_source(os.environ, isatty=stdin_isatty())
        head = run_context.read_head(run_context.worktree_git_dir(worktree))
        url = run_context.config_remote_url(common_dir)
        joined = shlex.join(command)
        return {
            "id": uuid.uuid4().hex,
            "version": __version__,
            "trigger": source.trigger,
            "agent": source.agent,
            "hook_stage": source.hook_stage,
            "worktree": str(worktree) if worktree is not None else None,
            "subdir": run_context.relative_subdir(cwd, worktree=worktree)
            if cwd is not None
            else None,
            "branch": run_context.branch_from_head(head),
            "head": run_context.head_commit(head, common_dir=common_dir),
            "remote": run_context.normalize_remote(url) if url else None,
            "machine": run_context.machine_id(stats_config.state_dir()),
            "host": run_context.host_name(),
            "platform": sys.platform,
            # Without --name the name is the command line, so storing it again adds nothing.
            "command": joined if joined != name else None,
        }


@dataclass(frozen=True)
class _Attempt:
    """One run of a gate on a known snapshot, and how to record its outcome.

    Attributes:
        common_dir: Git common directory that holds the markers.
        name: Gate name.
        command: Command and arguments that run.
        snapshot: The snapshot the run is keyed on.
        key: The snapshot's key, known to be set.
    """

    common_dir: Path
    name: str
    command: Sequence[str]
    snapshot: Snapshot
    key: str

    @property
    def marker(self) -> Path:
        """Return the marker path of the key and name."""
        return marker_path(self.common_dir, self.key, self.name)

    @property
    def miss(self) -> Path:
        """Return the miss record path of the key and name."""
        return miss_path(self.common_dir, self.key, self.name)

    @property
    def lock_file(self) -> Path:
        """Return the gate lock file of the key and name."""
        return lock_path(self.common_dir, self.key, self.name)

    def record_pass(self, duration: float) -> None:
        """Write the marker and drop any earlier miss; a failure only warns.

        Args:
            duration: Seconds the command ran, stored for later skips to report.
        """
        path = self.marker
        try:
            write_marker(
                path,
                tree=self.key,
                name=self.name,
                command=self.command,
                paths=self.snapshot.paths,
                full_tree=self.snapshot.tree,
                duration=duration,
            )
        except OSError as error:
            say(f"warning: could not record pass: {error}")
            return
        with contextlib.suppress(OSError):
            self.miss.unlink(missing_ok=True)

    def record_miss(self, *, exit_code: int, reason: str) -> None:
        """Record that the gate ran on the key without passing, so status can report it."""
        # Reporting is best effort: nothing about a miss record may change the exit code.
        path = self.miss
        try:
            write_miss(
                path,
                tree=self.key,
                name=self.name,
                command=self.command,
                exit_code=exit_code,
                reason=reason,
                paths=self.snapshot.paths,
                full_tree=self.snapshot.tree,
            )
        except Exception as error:  # noqa: BLE001
            say(f"warning: could not record miss: {error}")

    def prune(self) -> None:
        """Delete old markers, miss records, and free lock files; both prunes ignore errors."""
        max_age_days = marker_max_age_days()
        prune_markers(marker_dir(self.common_dir), max_age_days=max_age_days)
        prune_locks(self.common_dir, max_age_days=max_age_days)

    def record_if_unchanged(self, duration: float) -> bool:
        """Record the pass only when the run left the content it was keyed on untouched.

        Args:
            duration: Seconds the command ran.

        Returns:
            True when the pass was recorded, False when the keyed content changed.
        """
        # A command that rewrote keyed files or left new files behind did not pass on `key`.
        if take_snapshot(paths=self.snapshot.paths).key == self.key:
            # The command passed on unchanged content however the marker write goes.
            try:
                self.record_pass(duration)
            except Exception as error:  # noqa: BLE001
                say(f"warning: could not record pass: {error}")
            return True
        say(FILES_CHANGED_NOTICE)
        self.record_miss(exit_code=0, reason=_FILES_CHANGED)
        return False


@dataclass(frozen=True)
class _Wait:
    """A wait for another run that held the gate lock.

    Attributes:
        started: Wall-clock time the wait began; older miss records are not this wait's.
        holder: Where the awaited run runs, for messages.
    """

    started: float
    holder: str


@dataclass(frozen=True)
class _Acquired:
    """The outcome of taking a gate lock.

    Attributes:
        lock: The held lock, or None when the run goes ahead without it.
        wait: The wait for another run, or None when this attempt did not wait.
    """

    lock: GateLock | None
    wait: _Wait | None = None


@dataclass
class _GateRun:
    """One cached run of a gate: the marker check, any wait for another run, and the outcome.

    Attributes:
        name: Gate name.
        command: Command and arguments to run.
        stats: Stats recording for this run.
        started: Start of the overhead measurement, or None when stats are off.
        wait: The wait settings, or None to read them when a wait first needs them.
        waited: Seconds spent blocked on other runs, or None when the run never waited.
        wait_timed_out: Whether a wait ended at the timeout.
        ran: The attempt whose command ran to completion, so its directory gets pruned.
    """

    name: str
    command: Sequence[str]
    stats: _Stats
    started: float | None = None
    wait: WaitSettings | None = None
    waited: float | None = None
    wait_timed_out: bool = False
    ran: _Attempt | None = None

    def run(self, snapshot: Snapshot) -> int:
        """Skip on a recorded pass, else run the command, waiting for a run with the same key.

        Args:
            snapshot: The snapshot of the content about to be tested.

        Returns:
            The command's exit code, 0 for a skip, or a reported exit code of another run.
        """
        code = self._run(snapshot)
        # Pruning waits until the lock is released, so it never delays a waiting run.
        if self.ran is not None:
            self.ran.prune()
        return code

    def _run(self, snapshot: Snapshot) -> int:
        """Decide, taking the gate lock first unless the run ends before that."""
        while True:
            attempt = self._attempt(snapshot)
            if isinstance(attempt, int):
                return attempt
            acquired = self._acquire(attempt.lock_file)
            if acquired.lock is None:
                if acquired.wait is None:
                    # A run that skipped the lock still lists it, so a nested call never
                    # waits on another run that this run did not wait for.
                    with held_env(attempt.lock_file):
                        return self._execute(attempt)
                # The wait ended without the lock; run unlocked on the content as it is now.
                return self._run_unlocked(take_snapshot(paths=snapshot.paths))
            with acquired.lock as lock:
                # A lock file keeps the last holder's record, so replace it before any check.
                lock.write_holder(snapshot.root)
                # Files can change during a long wait, so a run that waited looks again.
                fresh = (
                    take_snapshot(paths=snapshot.paths) if acquired.wait is not None else snapshot
                )
                if fresh.key != attempt.key:
                    # Never hold the lock of a key this run is not running.
                    snapshot = fresh
                    continue
                return self._run_locked(replace(attempt, snapshot=fresh), acquired.wait)

    def _attempt(self, snapshot: Snapshot) -> _Attempt | int:
        """Return the attempt on a snapshot, or the exit code when the run ends before locking.

        A snapshot without a key or git directory runs without the cache, and a recorded
        pass skips.
        """
        key = snapshot.key
        if key is None:
            return self.run_uncached(snapshot.reason or "tree unknown", snapshot, resolve_repo=True)
        common_dir = snapshot.common_dir
        if common_dir is None:
            return self.run_uncached(_NO_COMMON_DIR_REASON, snapshot)
        attempt = _Attempt(
            common_dir=common_dir, name=self.name, command=self.command, snapshot=snapshot, key=key
        )
        if marker_exists(attempt.marker):
            return self._skip(attempt)
        return attempt

    def _run_unlocked(self, snapshot: Snapshot) -> int:
        """Run without the lock after a wait that ended without it."""
        attempt = self._attempt(snapshot)
        if isinstance(attempt, int):
            return attempt
        # The awaited holder may still run; a nested call must not wait on it again.
        with held_env(attempt.lock_file):
            return self._execute(attempt)

    def _acquire(self, lock_file: Path) -> _Acquired:
        """Take the gate lock, waiting while another run holds it.

        Every wait of one run shares a single budget of `timeout` seconds, so a key that
        changes during a wait cannot stack waits.

        Args:
            lock_file: The lock file of the key and name.

        Returns:
            The held lock, or no lock when the run goes ahead without it: a parent process
            holds it, it cannot be taken, waiting is off, or the wait timed out. The wait
            is set whenever the run waited, however the wait ended.
        """
        if held_by_ancestor(lock_file):
            return _Acquired(lock=None)
        # Taken before the lock check, so a miss the holder writes right after counts.
        began = time.time()
        try:
            lock = GateLock.try_acquire(lock_file)
        except OSError as error:
            say(f"warning: could not lock {self.name}: {error}")
            return _Acquired(lock=None)
        if lock is not None:
            return _Acquired(lock=lock)
        settings = self._settings()
        if settings.timeout == 0:
            return _Acquired(lock=None)

        holder, since = _describe_holder(lock_file)
        wait = _Wait(started=began, holder=holder)
        remaining = max(settings.timeout - (self.waited or 0.0), 0.0)
        wait_began = time.monotonic()
        try:
            with raise_on_termination():
                # Announced only once the handlers are in, so a signal sent on seeing it is caught.
                say(f"{self.name} is running in {holder}{since}, waiting")
                lock = GateLock.wait(lock_file, timeout=remaining)
        except OSError as error:
            say(f"warning: could not lock {self.name}: {error}")
            return _Acquired(lock=None, wait=wait)
        finally:
            self.waited = (self.waited or 0.0) + time.monotonic() - wait_began
        if lock is None:
            self.wait_timed_out = True
            say(
                f"{self.name} still running in {holder} after "
                f"{format_duration(settings.timeout)}, running anyway"
            )
        return _Acquired(lock=lock, wait=wait)

    def _run_locked(self, attempt: _Attempt, wait: _Wait | None) -> int:
        """Decide and run while holding the lock, so other runs with the key wait on this one.

        Args:
            attempt: The run on the current snapshot.
            wait: The wait that led to the lock, if any.

        Returns:
            The exit code of the run.
        """
        # Another run may have recorded a pass after the first marker check.
        if marker_exists(attempt.marker):
            return self._skip(attempt)
        if wait is not None:
            reported = self._reported_failure(attempt, wait)
            if reported is not None:
                return reported
        with held_env(attempt.lock_file):
            return self._execute(attempt)

    def _reported_failure(self, attempt: _Attempt, wait: _Wait) -> int | None:
        """Report the failure of the awaited run instead of running again, when asked to.

        Args:
            attempt: The run on the current snapshot.
            wait: The wait for the awaited run.

        Returns:
            The awaited run's exit code, or None when this run must run the command.
        """
        if self._settings().failed != "report":
            return None
        try:
            # Miss timestamps have whole-second resolution; the file time is finer.
            if attempt.miss.stat().st_mtime < wait.started:
                return None
        except OSError:
            return None
        record = miss_record(attempt.common_dir, attempt.key, self.name)
        code = record.get("exit_code") if record is not None else None
        # A miss with exit 0 means files changed during the run, not a failure.
        if not isinstance(code, int) or isinstance(code, bool) or code == 0:
            return None
        say(
            f"{self.name} failed on {attempt.snapshot.label} in {wait.holder} "
            f"(exit {code}), not running again"
        )
        self._record(
            attempt.snapshot,
            common_dir=attempt.common_dir,
            overhead=self._overhead(),
            outcome="fail",
            exit_code=code,
            reason=REPORTED_FAILURE_REASON,
            reported=True,
        )
        return code

    def _skip(self, attempt: _Attempt) -> int:
        """Report and record a skip on the attempt's marker."""
        path, snapshot = attempt.marker, attempt.snapshot
        duration = marker_duration(path)
        saved = f" (saved {format_duration(duration)})" if duration is not None else ""
        say(f"{self.name} already passed on {snapshot.label}, skipping{saved}")
        self._record(
            snapshot,
            common_dir=attempt.common_dir,
            overhead=self._overhead(),
            marker=path,
            outcome="skip",
            saved=duration,
        )
        return 0

    def _execute(self, attempt: _Attempt) -> int:
        """Run the command on the attempt's snapshot, then record its pass or miss."""
        overhead = self._overhead()
        before = self.stats.usage()
        result = run_child(self.command)
        usage = self.stats.usage_since(before)
        if result.interrupted:
            return result.exit_code
        self.ran = attempt
        outcome: Outcome = "fail"
        if result.exit_code != 0:
            attempt.record_miss(exit_code=result.exit_code, reason=f"exit code {result.exit_code}")
        else:
            outcome = "pass_unrecorded"
            # Recording is best effort: nothing after a passing run may change its exit code.
            try:
                if attempt.record_if_unchanged(result.duration):
                    outcome = "pass"
            except Exception as error:  # noqa: BLE001
                say(f"warning: could not record pass: {error}")
        self._record(
            attempt.snapshot,
            common_dir=attempt.common_dir,
            overhead=overhead,
            **usage,
            outcome=outcome,
            duration=result.duration,
            exit_code=result.exit_code,
        )
        return result.exit_code

    def run_uncached(
        self,
        reason: str,
        snapshot: Snapshot | None,
        *,
        paths: Sequence[str] = (),
        resolve_repo: bool = False,
    ) -> int:
        """Explain why caching is off, then run the command and record the run.

        Args:
            reason: Why caching is off, printed and stored.
            snapshot: The snapshot taken before caching turned out to be off, if any.
            paths: Normalized pathspecs of the gate, when there is no snapshot.
            resolve_repo: Look up the git common directory for the event, because the
                caller has not tried to.

        Returns:
            The command's exit code.
        """
        say(f"{reason}, running without cache")
        before = self.stats.usage()
        result = run_child(self.command)
        usage = self.stats.usage_since(before)
        if result.interrupted:
            return result.exit_code
        self._record(
            snapshot,
            common_dir=self.stats.common_dir(snapshot) if resolve_repo else None,
            paths=paths,
            **usage,
            outcome="uncached",
            duration=result.duration,
            exit_code=result.exit_code,
            reason=reason,
        )
        return result.exit_code

    def _record(
        self,
        snapshot: Snapshot | None,
        *,
        common_dir: Path | None,
        paths: Sequence[str] = (),
        **fields: Any,
    ) -> None:
        """Record the run's stats event; the outcome fields not given are None.

        Args:
            snapshot: The snapshot the run used, if any; it gives the worktree, tree,
                and paths.
            common_dir: Git common directory, when known.
            paths: Normalized pathspecs of the gate, when there is no snapshot.
            **fields: The fields that differ by outcome, plus `overhead` and `marker`.
        """
        self.stats.record(
            name=self.name,
            command=self.command,
            worktree=snapshot.root if snapshot is not None else None,
            common_dir=common_dir,
            tree=snapshot.key if snapshot is not None else None,
            paths=tuple(snapshot.paths if snapshot is not None else paths),
            **{"duration": None, "saved": None, "exit_code": None, "reason": None, **fields},
            waited=_round(self.waited, 3),
            wait_timed_out=self.wait_timed_out,
        )

    def _settings(self) -> WaitSettings:
        """Return the wait settings, reading the config file on first use only."""
        if self.wait is None:
            self.wait = wait_settings()
        return self.wait

    def _overhead(self) -> float | None:
        """Return the seconds spent deciding, without the time spent waiting."""
        overhead = self.stats.elapsed(self.started)
        if overhead is None or self.waited is None:
            return overhead
        return max(overhead - self.waited, 0.0)


def _describe_holder(lock_file: Path) -> tuple[str, str]:
    """Return where the run holding a lock runs, and a note of how long ago it started.

    Args:
        lock_file: The held lock file.

    Returns:
        The holder's worktree, or "another process" when unknown, and a " (started ...
        ago)" note, or "" when the holder record cannot be read.
    """
    info = read_holder(lock_file)
    if info is None:
        return "another process", ""
    since = f" (started {format_duration(max(time.time() - info.started, 0.0))} ago)"
    return info.worktree or "another process", since


def run_gate(
    name: str,
    command: Sequence[str],
    paths: Sequence[str] = (),
    *,
    wait: WaitSettings | None = None,
) -> int:
    """Run a gate command unless it already passed on the content about to be tested.

    A run that finds another run with the same key in progress waits for it, then skips
    on its pass.

    Args:
        name: Gate name that, with the key, identifies a recorded pass.
        command: Command and arguments to run.
        paths: Git pathspecs that scope the key to the files the gate reads. Empty keys
            on the whole tree.
        wait: How long to wait for another run and what to do when it failed. None reads
            the config file.

    Returns:
        The command's exit code, 0 when a recorded pass lets it skip, or the exit code of
        the awaited run when the wait settings report its failure.
    """
    stats = _Stats.load()
    reason = disabled_reason()
    if reason is not None:
        return _GateRun(name=name, command=command, stats=stats).run_uncached(
            reason, None, paths=normalize_paths(paths), resolve_repo=True
        )

    gate_run = _GateRun(name=name, command=command, stats=stats, started=stats.now(), wait=wait)
    try:
        return gate_run.run(take_snapshot(paths=paths))
    except Terminated as stop:
        # Like an interrupted command run, a run stopped while waiting records nothing.
        return stop.exit_code


def gate_status(
    name: str | None = None, *, as_json: bool = False, paths: Sequence[str] = ()
) -> int:
    """Print whether a gate would skip, or list the gates that ran, without running anything.

    Args:
        name: Gate name to look up. When None, list every gate that passed or missed on
            the current tree.
        as_json: Print one JSON object to stdout instead of text.
        paths: Pathspecs of a scoped gate to look up with name. Ignored without name.

    Returns:
        0 when a recorded pass exists for the gate, or for at least one gate when
        listing, and 1 otherwise.
    """
    reason = disabled_reason()
    if reason is not None:
        if as_json:
            empty = (
                _named_report(name, paths=paths)
                if name is not None
                else {"passed": [], "missed": []}
            )
            _print_json({"enabled": False, "tree": None, "reason": reason, **empty})
        else:
            say(reason)
        return 1

    if name is None:
        return _list_gates(as_json=as_json)
    snapshot = take_snapshot(paths=paths)
    common_dir = snapshot.common_dir if snapshot.known else None
    return _named_status(name, snapshot, common_dir, as_json=as_json)


def _print_json(data: Mapping[str, Any]) -> None:
    """Print a status report as JSON on stdout, unwrapped so it parses as is."""
    print(json.dumps(data, indent=2))  # noqa: T201


def _unknown_reason(snapshot: Snapshot, common_dir: Path | None) -> str | None:
    """Return why markers cannot be looked up, or None when they can."""
    if not snapshot.known:
        return snapshot.reason or "tree unknown"
    if common_dir is None:
        return _NO_COMMON_DIR_REASON
    return None


def _named_report(
    name: str,
    *,
    marker: str | None = None,
    hit: bool = False,
    last_run: dict[str, Any] | None = None,
    duration: float | None = None,
    paths: Sequence[str] = (),
    full_tree: str | None = None,
) -> dict[str, Any]:
    """Build the per-gate keys of a `status --name --json` report.

    Both the disabled and the enabled report call this, so they always carry the same keys.
    """
    return {
        "name": name,
        "marker": marker,
        "result": "hit" if hit else "miss",
        "last_run": last_run,
        "duration": duration,
        **scope_fields(paths, full_tree),
    }


def _miss_summary(record: Mapping[str, Any]) -> dict[str, Any]:
    """Pick the fields of a miss record that describe the run."""
    return {
        "exit_code": record.get("exit_code"),
        "reason": record.get("reason"),
        "timestamp": record.get("timestamp"),
    }


def _named_status(name: str, snapshot: Snapshot, common_dir: Path | None, *, as_json: bool) -> int:
    """Print whether one gate would skip on the snapshot's key."""
    key = snapshot.key
    path: Path | None = None
    hit = False
    last_run: dict[str, Any] | None = None
    duration: float | None = None
    if key is not None and common_dir is not None:
        path = marker_path(common_dir, key, name)
        hit = marker_exists(path)
        duration = marker_duration(path) if hit else None
        record = None if hit else miss_record(common_dir, key, name)
        last_run = _miss_summary(record) if record is not None else None
    reason = _unknown_reason(snapshot, common_dir)

    if as_json:
        _print_json(
            {
                "enabled": True,
                "name": name,
                "tree": key,
                "reason": reason,
                **_named_report(
                    name,
                    marker=str(path) if path is not None else None,
                    hit=hit,
                    last_run=last_run,
                    duration=duration,
                    paths=snapshot.paths,
                    full_tree=snapshot.tree,
                ),
            }
        )
        return 0 if hit else 1

    if path is not None:
        marker = str(path)
    elif key is not None:
        marker = f"none: {reason}"
    else:
        marker = "none"
    rows = {"name": name}
    if snapshot.paths:
        rows["paths"] = " ".join(snapshot.paths)
    if snapshot.paths:
        rows["scope"] = snapshot.scope if snapshot.scope is not None else f"unknown: {reason}"
    rows["tree"] = snapshot.tree if snapshot.tree is not None else f"unknown: {reason}"
    rows |= {"marker": marker, "result": "hit" if hit else "miss"}
    if duration is not None:
        rows["duration"] = format_duration(duration)
    if last_run is not None:
        rows["last run"] = str(last_run["reason"])
    kv(rows)
    return 0 if hit else 1


def _list_gates(*, as_json: bool) -> int:
    """Print the gates that passed or missed on the current tree, or on their paths' content."""
    # Scoped gates are found by recomputing each recorded path set's scope, all from one staging.
    common_dir = git_common_dir()
    index = RecordIndex.load(common_dir) if common_dir is not None else None
    path_sets = index.scoped_path_sets() if index is not None else []
    snapshot, *scoped = take_snapshots([(), *path_sets])
    tree = snapshot.tree
    if tree is None:
        common_dir = None
    passed: list[str] = []
    missed: list[dict[str, Any]] = []
    if tree is not None and index is not None:
        keys = [tree, *(s.scope for s in scoped if s.scope is not None)]
        passed = index.passed_names(*keys)
        missed = [{"name": r["name"], **_miss_summary(r)} for r in index.missed_records(*keys)]
    code = 0 if passed else 1

    if as_json:
        _print_json(
            {
                "enabled": True,
                "tree": tree,
                "reason": _unknown_reason(snapshot, common_dir),
                "passed": passed,
                "missed": missed,
            }
        )
        return code

    if tree is None:
        kv({"tree": f"unknown: {snapshot.reason}"})
        return 1
    if common_dir is None:
        kv({"tree": tree, "passed": f"unknown: {_NO_COMMON_DIR_REASON}"})
        return 1
    if not passed and not missed:
        kv({"tree": tree})
        print("No gates match the current tree")  # noqa: T201
        return 1
    rows = {"tree": tree}
    if passed:
        rows["passed"] = ", ".join(passed)
    if missed:
        rows["missed"] = ", ".join(
            f"{m['name']} ({m['reason']})" if m["reason"] else m["name"] for m in missed
        )
    kv(rows)
    return code


def clear_cache(*, confirmed: bool = False) -> int:
    """Delete every marker for the current repository, after the user confirms.

    Args:
        confirmed: Skip the confirmation prompt, as `--yes` does for scripts.

    Returns:
        0 on success, 1 outside a git repository, when the user does not confirm, or when
        markers cannot be removed.
    """
    common_dir = git_common_dir()
    if common_dir is None:
        say("not a git repository")
        return 1
    warning = [
        "this permanently deletes every recorded pass for this repository.",
        f"markers: {marker_dir(common_dir)}",
        "Every gate runs again in full, even on code that already passed.",
        "Recorded run stats are not affected.",
    ]
    if not confirmed and not confirm_deletion("clear markers", warning):
        return 1
    try:
        count = clear_markers(common_dir)
    except OSError as error:
        say(f"could not clear markers: {error}")
        return 1
    say(f"removed {count} marker{'' if count == 1 else 's'}")
    return 0
