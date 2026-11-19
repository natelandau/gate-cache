"""The `clear` subcommand: delete every recorded pass for this repository."""

from __future__ import annotations

from gate_cache.commands.app import JsonFlag, YesFlag  # noqa: TC001  # cyclopts reads it at runtime
from gate_cache.commands.output import CliError, DeletionOutcome, emit, require_yes_for_json
from gate_cache.commands.prompt import confirm_deletion
from gate_cache.durations import durations_dir
from gate_cache.gate import clear_cache
from gate_cache.git import git_common_dir
from gate_cache.markers import marker_dir

NOT_A_REPO = "not a git repository"


def clear(*, yes: YesFlag = False, as_json: JsonFlag = False) -> int:
    """Permanently delete every recorded pass for this repository.

    Every gate then runs again in full, even on content that already passed. Use it after a
    change that the tree does not show, such as a tool upgrade. It also deletes the records
    of failed runs. Recorded run stats stay: `gate-cache stats clear` deletes those.

    gate-cache shows what it will delete and asks you to type yes. Give --yes to skip the
    question, as a script or an agent must.

    Args:
        yes: Delete without asking for confirmation.
        as_json: Print one JSON object instead of text. Needs --yes.

    Returns:
        int: The exit code.

    Raises:
        UsageError: When --json is given without --yes.
        CliError: When outside a git repository or the markers cannot be removed.
    """
    require_yes_for_json("clear", yes=yes, as_json=as_json)
    common_dir = git_common_dir()
    if common_dir is None:
        raise CliError(NOT_A_REPO)
    markers = marker_dir(common_dir)
    if not yes:
        warning = [
            "this permanently deletes every recorded pass for this repository.",
            f"markers: {markers}",
            f"usual run times: {durations_dir(common_dir)}",
            "Every gate runs again in full, even on code that already passed.",
            "Recorded run stats are not affected.",
        ]
        if not confirm_deletion("clear markers", warning):
            return 1
    try:
        deleted = clear_cache(common_dir)
    except OSError as error:
        message = f"could not clear markers: {error}"
        raise CliError(message) from error
    outcome = DeletionOutcome(
        deleted=deleted, noun="marker", location_key="marker_dir", location=str(markers)
    )
    return emit(outcome, as_json=as_json)
