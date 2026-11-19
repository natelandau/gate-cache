"""Entry point for the `stats clear` command."""

from __future__ import annotations

from gate_cache.console import confirm_deletion, say
from gate_cache.stats import config
from gate_cache.stats.archive import ARCHIVE_NAME
from gate_cache.stats.context import MACHINE_ID_TEMP_GLOB
from gate_cache.stats.junit import TESTS_DIR_NAME
from gate_cache.stats.lock import InstanceLock
from gate_cache.stats.recorder import INBOX_NAME


def stats_clear(*, confirmed: bool = False) -> int:
    """Delete every recorded event and the archive, unless the dashboard is running.

    Keep `machine-id` so the machine keeps its ID, but remove temp files a killed run left
    while it created that file. Ask the user to confirm first, since the deletion cannot be
    undone.

    Args:
        confirmed: Skip the confirmation prompt, as `--yes` does for scripts.

    Returns:
        The process exit code.
    """
    state = config.state_dir()
    try:
        lock = InstanceLock.acquire(state)
    except OSError as error:
        say(f"could not clear stats: {error.strerror or error}")
        return 1
    if lock is None:
        say("stop the dashboard before clearing stats")
        return 1
    try:
        warning = [
            "this permanently deletes every recorded run stat on this machine.",
            f"data: {state}",
            "The history, time saved, and skip rates of every repository are lost.",
            "Recorded passes (markers) are not affected.",
        ]
        if not confirmed and not confirm_deletion("clear stats", warning):
            return 1
        targets = [
            state / INBOX_NAME,
            *state.glob("events.*.processing"),
            *state.glob(MACHINE_ID_TEMP_GLOB),
            *(state / f"{ARCHIVE_NAME}{suffix}" for suffix in ("", "-wal", "-shm")),
            # The folder stays, since a gate run can write into it meanwhile.
            *(state / TESTS_DIR_NAME).glob("*"),
        ]
        for target in targets:
            target.unlink(missing_ok=True)
    except OSError as error:
        say(f"could not clear stats: {error.strerror or error}")
        return 1
    finally:
        lock.release()
    say("cleared stats")
    return 0
