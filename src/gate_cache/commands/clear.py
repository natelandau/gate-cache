"""The `clear` subcommand: delete the recorded passes of this repository, or of one gate."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

import cyclopts

from gate_cache.commands.app import (  # noqa: TC001  # cyclopts reads them at runtime
    DryRunFlag,
    JsonFlag,
    YesFlag,
)
from gate_cache.commands.output import (
    CliError,
    DeletionOutcome,
    emit,
    gate_list,
    require_yes_for_json,
)
from gate_cache.commands.prompt import confirm_deletion
from gate_cache.console import plural
from gate_cache.durations import durations_dir, durations_path
from gate_cache.gate import clear_cache
from gate_cache.git import git_common_dir
from gate_cache.markers import marker_dir, select_markers

if TYPE_CHECKING:
    from pathlib import Path

    from gate_cache.markers import MarkerSelection

NOT_A_REPO = "not a git repository"
NO_RECORDS_OF_GATE = "no records of the gate {name}"
NO_RECORDS_HINT = "check the name; `gate-cache clear --dry-run` lists the gates with records"


def _summary(selection: MarkerSelection, *, markers: Path, durations: Path) -> tuple[str, ...]:
    """Return the lines that say what a clear deletes, shared by the warning and a dry run."""
    lines = [f"{plural(len(selection.passes), 'marker')} of recorded passes"]
    if selection.misses:
        lines.append(f"{plural(len(selection.misses), 'record')} of failed runs")
    if selection.names:
        lines.append(f"gates: {gate_list(selection.names)}")
    lines += [f"markers: {markers}", f"usual run times: {durations}"]
    return tuple(lines)


def clear(
    *,
    name: Annotated[str | None, cyclopts.Parameter(metavar="NAME")] = None,
    dry_run: DryRunFlag = False,
    yes: YesFlag = False,
    as_json: JsonFlag = False,
) -> int:
    """Permanently delete the recorded passes of this repository, or of one gate.

    Every gate you clear then runs again in full, even on content that already passed. Use
    it after a change that the tree does not show, such as a tool upgrade. It also deletes
    the records of failed runs. Recorded run stats stay: `gate-cache stats clear` deletes
    those.

    gate-cache shows what it will delete and asks you to type yes. Give --yes to skip the
    question, as a script or an agent must. Give --dry-run to see what would go.

    Args:
        name: Clear only this gate, and its keyed names such as NAME@key.
        dry_run: Show what would be deleted, and delete nothing.
        yes: Delete without asking for confirmation.
        as_json: Print one JSON object instead of text. Needs --yes or --dry-run.

    Returns:
        int: The exit code.

    Raises:
        UsageError: When --json is given without --yes or --dry-run.
        CliError: When outside a git repository or the markers cannot be removed.
    """
    require_yes_for_json("clear", asks=not (yes or dry_run), as_json=as_json)
    common_dir = git_common_dir()
    if common_dir is None:
        raise CliError(NOT_A_REPO)
    markers = marker_dir(common_dir)
    selection = select_markers(common_dir, gate=name)
    summary = _summary(selection, markers=markers, durations=durations_dir(common_dir))
    details = {
        "failed_runs": len(selection.misses),
        "gates": list(selection.names),
        "marker_dir": str(markers),
    }
    empty = not (selection.passes or selection.misses)
    if empty and name is not None and not durations_path(common_dir, name).exists():
        # A mistyped name would otherwise report success and leave the real gate skipping.
        raise CliError(NO_RECORDS_OF_GATE.format(name=name), hint=NO_RECORDS_HINT)
    if dry_run:
        outcome = DeletionOutcome(
            deleted=len(selection.passes),
            noun="marker",
            details=details,
            summary=summary,
            dry_run=True,
            empty=empty,
        )
        return emit(outcome, as_json=as_json)
    # With no records the question is skipped, but stale usual run times still go.
    if not (yes or empty):
        whose = "this repository" if name is None else f"the gate {name}"
        warning = [
            f"this permanently deletes the recorded passes of {whose}.",
            *summary,
            "Each of these gates runs again in full, even on code that already passed.",
            "Recorded run stats are not affected.",
        ]
        if not confirm_deletion("clear markers", warning):
            return 1
    try:
        deleted = clear_cache(common_dir, selection)
    except OSError as error:
        message = f"could not clear markers: {error}"
        raise CliError(message) from error
    also = (
        (f"{plural(len(selection.misses), 'record')} of failed runs",) if selection.misses else ()
    )
    outcome = DeletionOutcome(
        deleted=deleted, noun="marker", details=details, empty=empty, also=also
    )
    return emit(outcome, as_json=as_json)
