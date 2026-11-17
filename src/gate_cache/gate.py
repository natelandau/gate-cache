"""Run a gate command, skipping it when it already passed on the same tree."""

from __future__ import annotations

import contextlib
import json
import os
import shlex
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from gate_cache import __version__
from gate_cache.console import confirm_deletion, format_duration, kv, say, stdin_isatty
from gate_cache.env import CI_ENV, flag_on
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
from gate_cache.runner import run_child
from gate_cache.snapshot import git_common_dir, normalize_paths, take_snapshot, take_snapshots
from gate_cache.stats import config as stats_config
from gate_cache.stats import context as run_context
from gate_cache.stats.recorder import Event, Outcome, record_event

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


def _run_uncached(
    reason: str,
    command: Sequence[str],
    *,
    name: str,
    paths: Sequence[str],
    stats: _Stats,
    resolve_repo: bool = False,
    snapshot: Snapshot | None = None,
) -> int:
    """Explain why caching is off, then run the command and record the run.

    Args:
        reason: Why caching is off, printed and stored.
        command: Command and arguments to run.
        name: Gate name.
        paths: Normalized pathspecs of the gate.
        stats: Stats recording for this run.
        resolve_repo: Look up the git common directory for the event, because the caller
            has not tried to.
        snapshot: The snapshot taken before caching turned out to be off, if any.

    Returns:
        The command's exit code.
    """
    say(f"{reason}, running without cache")
    before = stats.usage()
    result = run_child(command)
    usage = stats.usage_since(before)
    if result.interrupted:
        return result.exit_code
    stats.record(
        name=name,
        command=command,
        worktree=snapshot.root if snapshot is not None else None,
        common_dir=stats.common_dir(snapshot) if resolve_repo else None,
        **usage,
        tree=snapshot.key if snapshot is not None else None,
        paths=tuple(paths),
        outcome="uncached",
        duration=result.duration,
        saved=None,
        exit_code=result.exit_code,
        reason=reason,
    )
    return result.exit_code


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

    def record_pass(self, duration: float) -> None:
        """Write the marker, drop any earlier miss, and prune old files; a failure only warns.

        Args:
            duration: Seconds the command ran, stored for later skips to report.
        """
        path = marker_path(self.common_dir, self.key, self.name)
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
            miss_path(self.common_dir, self.key, self.name).unlink(missing_ok=True)
        prune_markers(path.parent, max_age_days=marker_max_age_days())

    def record_miss(self, *, exit_code: int, reason: str) -> None:
        """Record that the gate ran on the key without passing, so status can report it."""
        # Reporting is best effort: nothing about a miss record may change the exit code.
        try:
            path = miss_path(self.common_dir, self.key, self.name)
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
            prune_markers(path.parent, max_age_days=marker_max_age_days())
        except Exception as error:  # noqa: BLE001
            say(f"warning: could not record miss: {error}")

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
        say(f"{_FILES_CHANGED}, not recording pass")
        self.record_miss(exit_code=0, reason=_FILES_CHANGED)
        return False


def run_gate(name: str, command: Sequence[str], paths: Sequence[str] = ()) -> int:
    """Run a gate command unless it already passed on the content about to be tested.

    Args:
        name: Gate name that, with the key, identifies a recorded pass.
        command: Command and arguments to run.
        paths: Git pathspecs that scope the key to the files the gate reads. Empty keys
            on the whole tree.

    Returns:
        The command's exit code, or 0 when a recorded pass lets it skip.
    """
    stats = _Stats.load()
    reason = disabled_reason()
    if reason is not None:
        return _run_uncached(
            reason,
            command,
            name=name,
            paths=normalize_paths(paths),
            stats=stats,
            resolve_repo=True,
        )

    started = stats.now()
    snapshot = take_snapshot(paths=paths)
    key = snapshot.key
    if key is None:
        return _run_uncached(
            snapshot.reason or "tree unknown",
            command,
            name=name,
            paths=snapshot.paths,
            stats=stats,
            resolve_repo=True,
            snapshot=snapshot,
        )

    common_dir = snapshot.common_dir
    if common_dir is None:
        return _run_uncached(
            _NO_COMMON_DIR_REASON,
            command,
            name=name,
            paths=snapshot.paths,
            stats=stats,
            snapshot=snapshot,
        )

    path = marker_path(common_dir, key, name)
    hit = marker_exists(path)
    overhead = stats.elapsed(started)
    if hit:
        duration = marker_duration(path)
        saved = f" (saved {format_duration(duration)})" if duration is not None else ""
        say(f"{name} already passed on {snapshot.label}, skipping{saved}")
        stats.record(
            name=name,
            command=command,
            worktree=snapshot.root,
            common_dir=common_dir,
            overhead=overhead,
            marker=path,
            tree=key,
            paths=snapshot.paths,
            outcome="skip",
            duration=None,
            saved=duration,
            exit_code=None,
            reason=None,
        )
        return 0

    attempt = _Attempt(
        common_dir=common_dir, name=name, command=command, snapshot=snapshot, key=key
    )
    before = stats.usage()
    result = run_child(command)
    usage = stats.usage_since(before)
    if result.interrupted:
        return result.exit_code
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
    stats.record(
        name=name,
        command=command,
        worktree=snapshot.root,
        common_dir=common_dir,
        overhead=overhead,
        **usage,
        tree=key,
        paths=snapshot.paths,
        outcome=outcome,
        duration=result.duration,
        saved=None,
        exit_code=result.exit_code,
        reason=None,
    )
    return result.exit_code


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
