"""Delete every recorded stat on this machine."""

from __future__ import annotations

from typing import TYPE_CHECKING

from gate_cache.stats import config
from gate_cache.stats.archive import ARCHIVE_NAME
from gate_cache.stats.context import MACHINE_ID_TEMP_GLOB
from gate_cache.stats.junit import TESTS_DIR_NAME
from gate_cache.stats.lock import InstanceLock
from gate_cache.stats.recorder import INBOX_NAME

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence


class StatsInUseError(Exception):
    """The dashboard or a stats report holds the stats, so they cannot be cleared."""


def clear_stats(*, confirm: Callable[[Sequence[str]], bool]) -> int | None:
    """Delete every recorded event and the archive, unless the dashboard or a report holds them.

    Keep `machine-id` so the machine keeps its ID, but remove temp files a killed run left
    while it created that file. Ask `confirm` first, since the deletion cannot be undone.

    Args:
        confirm: Called with the warning lines; returns True to go ahead. It never runs while
            the lock is held elsewhere.

    Returns:
        int | None: The number of files deleted, or None when not confirmed.

    Raises:
        StatsInUseError: When the dashboard or a report holds the stats.
        OSError: When the lock or a file cannot be handled.
    """
    state = config.state_dir()
    lock = InstanceLock.acquire(state)
    if lock is None:
        message = "stats are in use by the dashboard or a stats report"
        raise StatsInUseError(message)
    try:
        warning = [
            "this permanently deletes every recorded run stat on this machine.",
            f"data: {state}",
            "The history, time saved, and skip rates of every repository are lost.",
            "Recorded passes (markers) are not affected.",
        ]
        if not confirm(warning):
            return None
        targets = [
            state / INBOX_NAME,
            *state.glob("events.*.processing"),
            *state.glob(MACHINE_ID_TEMP_GLOB),
            *(state / f"{ARCHIVE_NAME}{suffix}" for suffix in ("", "-wal", "-shm")),
            # The folder stays, since a gate run can write into it meanwhile.
            *(state / TESTS_DIR_NAME).glob("*"),
        ]
        deleted = 0
        for target in targets:
            existed = target.exists()
            target.unlink(missing_ok=True)
            deleted += existed
        return deleted
    finally:
        lock.release()
