"""The `stats` command: show or change run-stats recording, delete the stats, or report on them."""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from functools import partial
from typing import TYPE_CHECKING, Annotated, Any, Literal

import cyclopts

from gate_cache import config as core_config
from gate_cache.commands.app import (  # cyclopts reads the flags at runtime
    JsonFlag,
    YesFlag,
    examples,
)
from gate_cache.commands.output import (
    CliError,
    DeletionOutcome,
    UsageError,
    emit,
    require_yes_for_json,
    warn,
)
from gate_cache.commands.prompt import confirm_deletion
from gate_cache.commands.status import resolve_gate
from gate_cache.commands.theme import kv, spinner
from gate_cache.stats import clear as stats_clear
from gate_cache.stats import config as stats_config

if TYPE_CHECKING:
    from collections.abc import Sequence

    from rich.console import RenderableType

    from gate_cache.stats.report import Window

STATS_IN_USE_HINT = "stop the dashboard, or try again in a moment"
YES_NEEDS_CLEAR = "--yes only applies to clear"
PROJECT_OVERRIDES = "{location} overrides this for the current repository"
ALL_REPOS_CONFLICT = "--all-repos cannot be combined with --repo or --name"
NAME_NEEDS_REPO = "one gate needs a repository: run inside one, or give --repo"
REPORT_SEPARATOR_EXAMPLE = "e.g. gate-cache stats report -- uv run pytest"
_LIMIT_MAX = 500

stats = cyclopts.App(
    name="stats",
    result_action="return_value",
    help_epilogue=examples(
        "gate-cache stats",
        "gate-cache stats on",
        "gate-cache stats report --since 7d",
        "gate-cache stats clear --yes",
    ),
)


@dataclass
class SettingOutcome:
    """Whether recording is on, what decided it, and where the config and data live."""

    setting: stats_config.StatsSetting
    exit_code: int = 0

    def to_json(self) -> dict[str, Any]:
        """Return the setting as the JSON body."""
        return {
            "enabled": self.setting.enabled,
            "decided_by": self.setting.source,
            "project": self.setting.project,
            "config_file": str(core_config.config_path()),
            "data_dir": str(stats_config.state_dir()),
        }

    def render(self) -> RenderableType:
        """Return the setting as label and value rows."""
        return kv(
            {
                "recording": "on" if self.setting.enabled else "off",
                "decided by": self.setting.source,
                **({"project": self.setting.project} if self.setting.project is not None else {}),
                "config": str(core_config.config_path()),
                "data": str(stats_config.state_dir()),
            }
        )


def _write_setting(*, enabled: bool) -> None:
    try:
        stats_config.write_enabled(enabled=enabled)
    except (OSError, stats_config.ConfigError) as error:
        reason = error.strerror if isinstance(error, OSError) else error
        message = f"could not write {core_config.config_path()}: {reason or error}"
        raise CliError(message) from error


def _clear(*, yes: bool, as_json: bool) -> int:
    require_yes_for_json("stats clear", yes=yes, as_json=as_json)

    def confirm(warning: Sequence[str]) -> bool:
        return yes or confirm_deletion("clear stats", warning)

    try:
        deleted = stats_clear.clear_stats(confirm=confirm)
    except stats_clear.StatsInUseError as error:
        raise CliError(str(error), hint=STATS_IN_USE_HINT) from error
    except OSError as error:
        message = f"could not clear stats: {error.strerror or error}"
        raise CliError(message) from error
    if deleted is None:
        return 1
    outcome = DeletionOutcome(
        deleted=deleted,
        noun="stats file",
        location_key="data_dir",
        location=str(stats_config.state_dir()),
    )
    return emit(outcome, as_json=as_json)


@stats.default
def stats_command(
    action: Literal["on", "off", "clear"] | None = None,
    /,
    *,
    yes: YesFlag = False,
    as_json: JsonFlag = False,
) -> int:
    """Show or change whether gate-cache records run stats, or delete the recorded stats.

    Recording is off until you turn it on. With no action, show whether recording is on,
    what decided it, and where the config file and the data are. `on` and `off` write the
    setting to the config file. The GATE_CACHE_STATS environment variable overrides it.

    Each run records its timings, outcome, and where it ran, but no command output and no
    file content. The data stays on this machine. `clear` permanently deletes it after you
    type yes, and keeps the recorded passes. Use `report` to read the stats here, or
    `gate-cache dashboard` to see them in a browser.

    Args:
        action: Turn recording on or off, or clear the recorded stats. Default: show the setting.
        yes: Clear without asking for confirmation.
        as_json: Print one JSON object instead of text. With clear, needs --yes.

    Returns:
        int: The exit code.

    Raises:
        UsageError: When --yes is given without clear, or --json with clear but no --yes.
        CliError: When the setting cannot be written or the stats cannot be cleared.
    """
    if yes and action != "clear":
        raise UsageError(YES_NEEDS_CLEAR)
    if action == "clear":
        return _clear(yes=yes, as_json=as_json)
    if action is not None:
        _write_setting(enabled=action == "on")
    setting = stats_config.stats_setting()
    if action is not None and setting.project is not None and setting.enabled != (action == "on"):
        warn(PROJECT_OVERRIDES.format(location=core_config.table_location(setting.project)))
    return emit(SettingOutcome(setting), as_json=as_json)


@dataclass
class ReportOutcome:
    """A stats report: the contract object, the window it covers, and how to show it."""

    report: dict[str, Any]
    window: Window
    name: str | None
    limit: int
    exit_code: int = 0

    def to_json(self) -> dict[str, Any]:
        """Return the report as the JSON body; it already holds its schema key."""
        return self.report

    def render(self) -> RenderableType:
        """Return the suite view, or the one-gate view when a gate was named."""
        from gate_cache.stats import report_text

        if self.name is None:
            return report_text.render_suite(self.report, window=self.window)
        return report_text.render_gate(self.report, window=self.window, limit=self.limit)


@dataclass(frozen=True)
class _ReportQuery:
    """What a report covers, from the flags and the current repository."""

    repo: str | None
    all_repos: bool
    name: str | None
    here: str | None
    window: Window
    limit: int
    recording: bool


def _build_report(conn: sqlite3.Connection | None, query: _ReportQuery) -> dict[str, Any]:
    """Return the report the query asks for, from the open record."""
    from gate_cache.gate import current_status
    from gate_cache.stats import report_text
    from gate_cache.stats.report import RepoNotFoundError, gate_report, resolve_repo, suite_report

    target = query.here
    if query.repo is not None:
        if conn is None:
            raise RepoNotFoundError(query.repo)
        target = resolve_repo(conn, query.repo)
    if query.name is None:
        repos = None if query.all_repos or target is None else (target,)
        return suite_report(conn, repos=repos, window=query.window, recording=query.recording)
    report = None
    if conn is not None:
        report = gate_report(
            conn,
            repo=target,
            name=query.name,
            window=query.window,
            limit=query.limit,
            # The status on the current content says nothing about a gate of another repo.
            current=partial(current_status, snapshots={}) if target == query.here else None,
            recording=query.recording,
        )
    if report is None:
        raise CliError(
            report_text.UNKNOWN_GATE.format(name=query.name, repo=target),
            hint=None if query.recording else report_text.RECORDING_OFF_HINT,
        )
    return report


_GATE = cyclopts.Group("Gate", sort_key=1)
_SCOPE = cyclopts.Group("Scope", sort_key=2)
_WINDOW = cyclopts.Group("Window", sort_key=3)
_OUTPUT = cyclopts.Group("Output", sort_key=4)


@stats.command(
    help_epilogue=examples(
        "gate-cache stats report",
        "gate-cache stats report --since 7d --limit 50",
        "gate-cache stats report --name pytest",
        "gate-cache stats report -- uv run pytest -x",
        "gate-cache stats report --all-repos --json",
    )
)
def report(
    *command: Annotated[str, cyclopts.Parameter(group=_GATE)],
    name: Annotated[str | None, cyclopts.Parameter(metavar="NAME", group=_GATE)] = None,
    repo: Annotated[str | None, cyclopts.Parameter(metavar="NAME|PATH", group=_SCOPE)] = None,
    all_repos: Annotated[
        bool, cyclopts.Parameter(negative="", show_default=False, group=_SCOPE)
    ] = False,
    since: Annotated[
        str, cyclopts.Parameter(metavar="DURATION", show_default=False, group=_WINDOW)
    ] = "30d",
    until: Annotated[str | None, cyclopts.Parameter(metavar="WHEN", group=_WINDOW)] = None,
    limit: Annotated[int, cyclopts.Parameter(metavar="N", show_default=False, group=_OUTPUT)] = 20,
    as_json: Annotated[JsonFlag, cyclopts.Parameter(group=_OUTPUT)] = False,
) -> int:
    """Print a report of the recorded stats for each gate, or for one gate in detail.

    The suite view lists each gate with its runs, skip rate, failures, run times, and the
    time it spent and saved. With --name, or a command after --, the report shows one gate
    in detail: its status on the current content, its trend, exit codes, flaky trees,
    where its runs came from, and its recent runs.

    The report covers the current repository, or every repository when you run it outside
    one. Names with an @ key, such as test@v22, are grouped under the gate before the @.

    Args:
        command: The command of a gate that ran without --name, after --.
        name: Gate to report in detail, without any @key.
        repo: Repository: its report name or a path inside it. Default: this one.
        all_repos: Cover every repository.
        since: Window length: a whole number and h, d, w, or y. Default: 30d.
        until: Window end: a date, an ISO 8601 timestamp, or a duration ago. Default: now.
        limit: Most items in each list, 1 to 500. Default: 20.
        as_json: Print one JSON object instead of text.

    Returns:
        int: The exit code.

    Raises:
        UsageError: When the options conflict, the window is invalid, or a --repo name
            matches more than one repository.
        CliError: When the repository or gate is unknown or the stats cannot be read.
    """
    from gate_cache.git import git_common_dir
    from gate_cache.stats import report_text
    from gate_cache.stats.archive import ArchiveVersionError, gate_of
    from gate_cache.stats.report import (
        AmbiguousRepoError,
        RepoNotFoundError,
        Window,
        open_record,
    )
    from gate_cache.stats.window import local_zone, parse_window

    name, from_command = resolve_gate(command, name, example=REPORT_SEPARATOR_EXAMPLE)
    if not from_command and name is not None and (gate := gate_of(name)) != name:
        raise UsageError(report_text.KEYED_NAME_ERROR.format(gate=gate))
    if all_repos and (repo is not None or name is not None):
        raise UsageError(ALL_REPOS_CONFLICT)
    now, tz = time.time(), local_zone()
    try:
        start, end = parse_window(since, until, now=now, tz=tz)
    except ValueError as error:
        raise UsageError(str(error)) from error
    common = git_common_dir()
    here = None if common is None else str(common)
    if name is not None and repo is None and here is None:
        raise UsageError(NAME_NEEDS_REPO)
    limit = min(max(limit, 1), _LIMIT_MAX)
    window = Window(start=start, end=end, tz=tz, ends_now=end >= now)
    query = _ReportQuery(
        repo=repo,
        all_repos=all_repos,
        name=name,
        here=here,
        window=window,
        limit=limit,
        recording=stats_config.stats_setting().enabled,
    )

    try:
        with spinner("reading the stats", enabled=not as_json), open_record() as conn:
            data = _build_report(conn, query)
    except RepoNotFoundError as error:
        raise CliError(report_text.UNKNOWN_REPO.format(text=error.text)) from error
    except AmbiguousRepoError as error:
        matches = [{"label": label, "folder": folder} for label, folder in error.matches]
        raise UsageError(
            report_text.AMBIGUOUS_REPO.format(text=error.text), details={"matches": matches}
        ) from error
    except (ArchiveVersionError, sqlite3.Error, OSError) as error:
        raise CliError(str(error)) from error
    outcome = ReportOutcome(report=data, window=window, name=name, limit=limit)
    return emit(outcome, as_json=as_json)
