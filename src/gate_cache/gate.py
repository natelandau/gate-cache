"""Run a gate command, skipping it when it already passed on the same tree."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from nclutils import pp

from gate_cache.console import say
from gate_cache.markers import (
    clear_markers,
    marker_path,
    passed_names,
    prune_markers,
    write_marker,
)
from gate_cache.runner import run_child
from gate_cache.snapshot import Snapshot, git_common_dir, take_snapshot

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from pathlib import Path

DISABLE_ENV = "GATE_CACHE_DISABLE"
MAX_AGE_ENV = "GATE_CACHE_MAX_AGE_DAYS"
DEFAULT_MAX_AGE_DAYS = 30
_DISABLED_REASON = f"caching disabled by {DISABLE_ENV}"
_NO_COMMON_DIR_REASON = "could not locate git directory"


def cache_disabled(environ: Mapping[str, str] | None = None) -> bool:
    """Report whether GATE_CACHE_DISABLE turns caching off.

    Args:
        environ: Environment to read; defaults to the process environment.

    Returns:
        True when the variable is set to any non-empty value other than `0`.
    """
    value = (os.environ if environ is None else environ).get(DISABLE_ENV, "")
    return value not in {"", "0"}


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


def _marker_exists(path: Path) -> bool:
    """Return True only when the marker is known to exist."""
    try:
        return path.exists()
    except OSError:
        return False


def _run_uncached(reason: str, command: Sequence[str]) -> int:
    """Explain why caching is off, then run the command."""
    say(f"{reason}, running without cache")
    return run_child(command).exit_code


def _record_pass(path: Path, *, tree: str, name: str, command: Sequence[str]) -> None:
    """Write the marker and prune old ones; a failure only warns."""
    try:
        write_marker(path, tree=tree, name=name, command=command)
    except OSError as error:
        say(f"warning: could not record pass: {error}")
        return
    prune_markers(path.parent, max_age_days=marker_max_age_days())


def _record_if_unchanged(path: Path, *, tree: str, name: str, command: Sequence[str]) -> None:
    """Record the pass only when the run left the tree it was keyed on untouched."""
    # A command that rewrote tracked files or left new files behind did not pass on `tree`.
    if take_snapshot().tree == tree:
        _record_pass(path, tree=tree, name=name, command=command)
    else:
        say("files changed during the run, not recording pass")


def run_gate(name: str, command: Sequence[str]) -> int:
    """Run a gate command unless it already passed on the tree about to be tested.

    Args:
        name: Gate name that, with the tree, identifies a recorded pass.
        command: Command and arguments to run.

    Returns:
        The command's exit code, or 0 when a recorded pass lets it skip.
    """
    if cache_disabled():
        return _run_uncached(_DISABLED_REASON, command)

    snapshot = take_snapshot()
    tree = snapshot.tree
    if tree is None:
        return _run_uncached(snapshot.reason or "tree unknown", command)

    common_dir = git_common_dir()
    if common_dir is None:
        return _run_uncached(_NO_COMMON_DIR_REASON, command)

    path = marker_path(common_dir, tree, name)
    if _marker_exists(path):
        say(f"{name} already passed on tree {tree[:12]}, skipping")
        return 0

    result = run_child(command)
    if result.interrupted or result.exit_code != 0:
        return result.exit_code

    # Recording is best effort: nothing after a passing run may change its exit code.
    try:
        _record_if_unchanged(path, tree=tree, name=name, command=command)
    except Exception as error:  # noqa: BLE001
        say(f"warning: could not record pass: {error}")
    return result.exit_code


def gate_status(name: str | None = None) -> int:
    """Print whether a gate would skip, or list every gate that would, without running.

    Args:
        name: Gate name to look up. When None, list every gate with a recorded pass on
            the current tree.

    Returns:
        0 when a recorded pass exists for the gate, or for at least one gate when
        listing, and 1 otherwise.
    """
    if cache_disabled():
        say(_DISABLED_REASON)
        return 1

    snapshot = take_snapshot()
    if name is None:
        return _list_passed(snapshot)

    tree = snapshot.tree
    path: Path | None = None
    marker = "none"
    if tree is not None:
        common_dir = git_common_dir()
        if common_dir is None:
            marker = f"none: {_NO_COMMON_DIR_REASON}"
        else:
            path = marker_path(common_dir, tree, name)
            marker = str(path)
    hit = path is not None and _marker_exists(path)

    pp.kv(
        {
            "name": name,
            "tree": tree if tree is not None else f"unknown: {snapshot.reason}",
            "marker": marker,
            "result": "hit" if hit else "miss",
        }
    )
    return 0 if hit else 1


def _list_passed(snapshot: Snapshot) -> int:
    """Print the gates with a recorded pass on the snapshot's tree."""
    if snapshot.tree is None:
        pp.kv({"tree": f"unknown: {snapshot.reason}"})
        return 1
    common_dir = git_common_dir()
    if common_dir is None:
        pp.kv({"tree": snapshot.tree, "gates": f"unknown: {_NO_COMMON_DIR_REASON}"})
        return 1
    names = passed_names(common_dir, snapshot.tree)
    if not names:
        pp.kv({"tree": snapshot.tree})
        pp.console().print("No gates match the current tree", markup=False, highlight=False)
        return 1
    pp.kv({"tree": snapshot.tree, "gates": ", ".join(names)})
    return 0


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
