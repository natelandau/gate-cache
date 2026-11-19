"""Append one event per gate run to the stats inbox."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any, Literal

from gate_cache.stats import config

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

Outcome = Literal["skip", "pass", "pass_unrecorded", "fail", "uncached"]

MAX_LINE_BYTES = 4096
INBOX_NAME = "events.jsonl"
# Fields with no bound on their length that an over-long line drops before it cuts anything
# the event is keyed on.
_DROPPABLE = ("worktree", "subdir", "branch", "remote", "hook_stage", "reason")
_INBOX_MODE = 0o600


@dataclass(frozen=True)
class Event:
    """One gate run, as stored in the inbox.

    Attributes:
        ts: Unix time the run finished.
        repo: Git common directory, or None when unknown.
        name: Gate name.
        tree: Key the run was cached on, or None when caching was off or the tree unknown.
        paths: Pathspecs that scoped the key.
        outcome: What the run did.
        duration: Seconds the command ran, or None when it did not run.
        saved: Seconds a skip saved, when known.
        exit_code: The command's exit code, or None when it did not run.
        reason: Why caching was off, for an uncached run.
        version: gate-cache version that recorded the run.
        trigger: What started the run: hook, agent, ci, terminal, or other.
        worktree: Absolute top of the working tree the gate ran in.
        branch: Checked-out branch, or None when detached or unknown.
        remote: Normalized URL of the repository's origin or first remote.
        machine: Random ID that stays the same for every run on this machine.
        host: Host name, a display label that can change.
        overhead: Seconds gate-cache spent before deciding to skip or run.
        command: The command line, when the gate name is not the command line.
        id: Random ID of this event, for merging archives later.
        head: Commit that HEAD pointed to.
        marker_age: Seconds since the marker a skip used was written.
        cpu: User plus system CPU seconds the command used.
        max_rss: Peak resident memory of the command, in bytes.
        subdir: Working directory relative to the top of the working tree.
        hook_stage: Git hook stage, when a hook manager ran the gate.
        agent: Name of the coding agent that ran the gate.
        platform: `sys.platform` of the machine.
        command_truncated: Whether `command` was dropped to fit the line limit.
        name_truncated: Whether `name` was cut to a prefix to fit the line limit.
        waited: Seconds the run waited for another run of the same gate.
        wait_timed_out: Whether the wait ended at the timeout.
        reported: Whether the run reported the failure of the run it waited for instead
            of running the command.
        junit: Number of tests stored from the run's JUnit reports, or why none were read:
            `missing`, `stale`, or `invalid`. None when the run read no report.
        junit_truncated: Whether the stored tests were cut at the per-run limit.
        junit_problem: When some reports were read, the worst status of those that were not.
        spot_check: Whether the run executed the command where a recorded pass would
            have let it skip.
    """

    ts: float
    repo: str | None
    name: str
    tree: str | None
    paths: tuple[str, ...]
    outcome: Outcome
    duration: float | None
    saved: float | None
    exit_code: int | None
    reason: str | None
    version: str | None = None
    trigger: str | None = None
    worktree: str | None = None
    branch: str | None = None
    remote: str | None = None
    machine: str | None = None
    host: str | None = None
    overhead: float | None = None
    command: str | None = None
    id: str | None = None
    head: str | None = None
    marker_age: float | None = None
    cpu: float | None = None
    max_rss: int | None = None
    subdir: str | None = None
    hook_stage: str | None = None
    agent: str | None = None
    platform: str | None = None
    command_truncated: bool = False
    name_truncated: bool = False
    waited: float | None = None
    wait_timed_out: bool = False
    reported: bool = False
    junit: int | str | None = None
    junit_truncated: bool = False
    junit_problem: str | None = None
    spot_check: bool = False

    def _encode(self, paths: list[str], *, truncated: bool, name: str | None = None) -> bytes:
        """Encode the event as one newline-terminated JSON line.

        Args:
            paths: The paths to store.
            truncated: Whether to set `paths_truncated`.
            name: A cut name to store in place of `name`, which also sets `name_truncated`.

        Returns:
            The encoded line.
        """
        data: dict[str, Any] = {
            "v": 1,
            "ts": self.ts,
            "repo": self.repo,
            "name": self.name if name is None else name,
            "tree": self.tree,
            "paths": paths,
            "outcome": self.outcome,
            "duration": self.duration,
            "saved": self.saved,
            "exit_code": self.exit_code,
            "reason": self.reason,
            "version": self.version,
            "trigger": self.trigger,
            "worktree": self.worktree,
            "branch": self.branch,
            "remote": self.remote,
            "machine": self.machine,
            "host": self.host,
            "overhead": self.overhead,
            "command": self.command,
            "id": self.id,
            "head": self.head,
            "marker_age": self.marker_age,
            "cpu": self.cpu,
            "max_rss": self.max_rss,
            "subdir": self.subdir,
            "hook_stage": self.hook_stage,
            "agent": self.agent,
            "platform": self.platform,
            "waited": self.waited,
            "junit": self.junit,
        }
        if self.junit_truncated:
            data["junit_truncated"] = True
        if self.junit_problem is not None:
            data["junit_problem"] = self.junit_problem
        if self.wait_timed_out:
            data["wait_timed_out"] = True
        if self.reported:
            data["reported"] = True
        if self.spot_check:
            data["spot_check"] = True
        if self.command_truncated:
            data["command_truncated"] = True
        if self.name_truncated or name is not None:
            data["name_truncated"] = True
        if truncated:
            data["paths_truncated"] = True
        return json.dumps(data, separators=(",", ":")).encode("utf-8") + b"\n"

    def to_line(self) -> bytes:
        """Encode the event as one JSON line of at most MAX_LINE_BYTES.

        A line that is too long drops `host`, then drops `command` and sets
        `command_truncated`. When the line still does not fit without any paths, it drops
        `worktree`, `subdir`, `branch`, `remote`, `hook_stage`, and `reason`, then `repo`
        if even an empty name would not fit, then keeps the longest prefix of `name` that
        fits and sets `name_truncated`. Last, it keeps the longest prefix of `paths` that
        fits and sets `paths_truncated`.

        Returns:
            The newline-terminated line.
        """
        line = self._encode(list(self.paths), truncated=False)
        if len(line) <= MAX_LINE_BYTES:
            return line
        if (smaller := self._shrunk()) is not None:
            return smaller.to_line()
        low, high = 0, len(self.paths)
        while low < high:
            mid = (low + high + 1) // 2
            if len(self._encode(list(self.paths[:mid]), truncated=True)) <= MAX_LINE_BYTES:
                low = mid
            else:
                high = mid - 1
        return self._encode(list(self.paths[:low]), truncated=bool(self.paths))

    def _shrunk(self) -> Event | None:
        """Return a copy with the next field dropped or cut, or None when only paths remain."""
        if self.host is not None:
            return replace(self, host=None)
        if self.command is not None:
            return replace(self, command=None, command_truncated=True)
        # A cut name is the last resort, so a second pass stops instead of recursing.
        if self._fits_without_paths() or self.name_truncated:
            return None
        dropped = {field: None for field in _DROPPABLE if getattr(self, field) is not None}
        if dropped:
            return replace(self, **dropped)
        if self.repo is not None and not self._fits_without_paths(name=""):
            return replace(self, repo=None)
        # The JSON is ASCII-escaped, so slicing by code point never splits a UTF-8 sequence.
        low, high = 0, len(self.name)
        while low < high:
            mid = (low + high + 1) // 2
            if self._fits_without_paths(name=self.name[:mid]):
                low = mid
            else:
                high = mid - 1
        return replace(self, name=self.name[:low], name_truncated=True)

    def _fits_without_paths(self, name: str | None = None) -> bool:
        """Return whether the line fits once every path is cut, with name cut to name if given."""
        line = self._encode([], truncated=bool(self.paths), name=name)
        return len(line) <= MAX_LINE_BYTES


def inbox_path(environ: Mapping[str, str] | None = None) -> Path:
    """Return the path of the events inbox.

    Args:
        environ: Environment to read the data directory from; defaults to the process
            environment.

    Returns:
        The path of `events.jsonl` in the stats data directory.
    """
    return config.state_dir(environ) / INBOX_NAME


def record_event(
    event: Event,
    environ: Mapping[str, str] | None = None,
    *,
    setting: config.StatsSetting | None = None,
) -> None:
    """Append an event to the inbox when stats are on; never raise.

    Args:
        event: The event to store.
        environ: Environment to read the setting and the data directory from; defaults to
            the process environment.
        setting: A setting the caller already read, which skips reading it again.
    """
    # Stats are optional telemetry: no failure here may touch a gate's exit code or output.
    try:
        if setting is None:
            setting = config.stats_setting(environ)
        if not setting.enabled:
            return
        path = inbox_path(environ)
        path.parent.mkdir(mode=config.STATE_DIR_MODE, parents=True, exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, _INBOX_MODE)
        try:
            # One write keeps concurrent appends from interleaving.
            os.write(fd, event.to_line())
        finally:
            os.close(fd)
    except Exception:  # noqa: BLE001
        return
