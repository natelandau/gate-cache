"""Run a gate command, skipping it when it already passed on the same tree."""

from __future__ import annotations

import contextlib
import json
import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from gate_cache.console import kv, say
from gate_cache.markers import (
    RecordIndex,
    clear_markers,
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
from gate_cache.snapshot import git_common_dir, take_snapshot, take_snapshots

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from pathlib import Path

    from gate_cache.snapshot import Snapshot

DISABLE_ENV = "GATE_CACHE_DISABLE"
CI_ENV = "CI"
MAX_AGE_ENV = "GATE_CACHE_MAX_AGE_DAYS"
DEFAULT_MAX_AGE_DAYS = 30
_DISABLED_REASON = f"caching disabled by {DISABLE_ENV}"
_CI_REASON = f"caching disabled in CI ({DISABLE_ENV}=0 keeps it on)"
_NO_COMMON_DIR_REASON = "could not locate git directory"
_FILES_CHANGED = "files changed during the run"


def _flag_on(value: str) -> bool:
    """Read an on/off variable the way CI systems set CI, so `false` means off."""
    return value.strip().lower() not in {"", "0", "false"}


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
        return _DISABLED_REASON if _flag_on(disable) else None
    if _flag_on(env.get(CI_ENV, "")):
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


def _run_uncached(reason: str, command: Sequence[str]) -> int:
    """Explain why caching is off, then run the command."""
    say(f"{reason}, running without cache")
    return run_child(command).exit_code


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

    def record_pass(self) -> None:
        """Write the marker, drop any earlier miss, and prune old files; a failure only warns."""
        path = marker_path(self.common_dir, self.key, self.name)
        try:
            write_marker(
                path,
                tree=self.key,
                name=self.name,
                command=self.command,
                paths=self.snapshot.paths,
                full_tree=self.snapshot.tree,
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

    def record_if_unchanged(self) -> None:
        """Record the pass only when the run left the content it was keyed on untouched."""
        # A command that rewrote keyed files or left new files behind did not pass on `key`.
        if take_snapshot(paths=self.snapshot.paths).key == self.key:
            self.record_pass()
        else:
            say(f"{_FILES_CHANGED}, not recording pass")
            self.record_miss(exit_code=0, reason=_FILES_CHANGED)


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
    reason = disabled_reason()
    if reason is not None:
        return _run_uncached(reason, command)

    snapshot = take_snapshot(paths=paths)
    key = snapshot.key
    if key is None:
        return _run_uncached(snapshot.reason or "tree unknown", command)

    common_dir = git_common_dir()
    if common_dir is None:
        return _run_uncached(_NO_COMMON_DIR_REASON, command)

    if marker_exists(marker_path(common_dir, key, name)):
        say(f"{name} already passed on {snapshot.label}, skipping")
        return 0

    attempt = _Attempt(
        common_dir=common_dir, name=name, command=command, snapshot=snapshot, key=key
    )
    result = run_child(command)
    if result.interrupted:
        return result.exit_code
    if result.exit_code != 0:
        attempt.record_miss(exit_code=result.exit_code, reason=f"exit code {result.exit_code}")
    else:
        # Recording is best effort: nothing after a passing run may change its exit code.
        try:
            attempt.record_if_unchanged()
        except Exception as error:  # noqa: BLE001
            say(f"warning: could not record pass: {error}")
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
                {"name": name, "marker": None, "result": "miss", "last_run": None}
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
    common_dir = git_common_dir() if snapshot.known else None
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
    if key is not None and common_dir is not None:
        path = marker_path(common_dir, key, name)
        hit = marker_exists(path)
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
                "marker": str(path) if path is not None else None,
                "result": "hit" if hit else "miss",
                "last_run": last_run,
                **scope_fields(snapshot.paths, snapshot.tree),
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


def clear_cache() -> int:
    """Delete every marker for the current repository.

    Returns:
        0 on success, 1 outside a git repository or when markers cannot be removed.
    """
    common_dir = git_common_dir()
    if common_dir is None:
        say("not a git repository")
        return 1
    try:
        count = clear_markers(common_dir)
    except OSError as error:
        say(f"could not clear markers: {error}")
        return 1
    say(f"removed {count} marker{'' if count == 1 else 's'}")
    return 0
