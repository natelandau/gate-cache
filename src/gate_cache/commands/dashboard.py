"""The `dashboard` subcommand: serve a local dashboard of the recorded stats."""

from __future__ import annotations

from contextlib import ExitStack
from typing import TYPE_CHECKING, Annotated

import cyclopts
from cyclopts import validators
from rich.text import Text

from gate_cache.commands.app import JsonFlag  # noqa: TC001  # cyclopts reads it at runtime
from gate_cache.commands.output import CliError, warn, write_json
from gate_cache.commands.theme import err, out, spinner
from gate_cache.stats import config as stats_config

if TYPE_CHECKING:
    from gate_cache.dashboard.app import DashboardStart

RECORDING_OFF = "recording is off; turn it on with: gate-cache stats on"


def _print_json(start: DashboardStart) -> None:
    """Write the start as one compact line; the process keeps serving after it."""
    payload = {
        "url": start.url,
        "port": start.port,
        "already_running": start.already_running,
        "busy": start.busy,
    }
    write_json(payload, indent=None, flush=True)


def _print_human(start: DashboardStart) -> None:
    from gate_cache.dashboard.app import DASHBOARD_BUSY, DASHBOARD_RUNNING

    if start.busy:
        err().print(Text(DASHBOARD_BUSY))
    elif start.already_running:
        out().print(Text(DASHBOARD_RUNNING.format(url=start.url)))
    else:
        out().print(Text.assemble("dashboard at ", (str(start.url), "accent")))
        err().print(Text("press Ctrl-C to stop", style="muted"))
    if not (start.busy or start.already_running or start.recording):
        warn(RECORDING_OFF)


def dashboard(
    *,
    port: Annotated[
        int | None,
        cyclopts.Parameter(
            metavar="PORT",
            validator=validators.Number(gte=1, lte=65535),
            help=(
                "Port to listen on, 1 to 65535. "
                f"Default: {stats_config.DASHBOARD_PORT}, or a free port when it is taken."
            ),
        ),
    ] = None,
    no_browser: Annotated[bool, cyclopts.Parameter(negative="", show_default=False)] = False,
    as_json: JsonFlag = False,
) -> int:
    """Serve a local dashboard of the recorded stats on 127.0.0.1.

    The dashboard opens in your browser and runs until you press Ctrl-C. It shows the
    stats that `gate-cache stats on` records. Only one dashboard runs at a time: a second
    one prints the address of the running one and opens it.

    The dashboard UI ships only in the release package. A copy installed from source, such
    as the copy that a git hook manager installs, has no UI.

    Args:
        port: Port to listen on.
        no_browser: Do not open the dashboard in a browser.
        as_json: Print one JSON line with the address instead of text.

    Returns:
        int: The exit code.

    Raises:
        CliError: When the dashboard cannot start.
    """
    # Imported here so the core suite never loads the dashboard package.
    from gate_cache.dashboard.app import DashboardError, run_dashboard

    with ExitStack() as spin:
        spin.enter_context(spinner("starting the dashboard", enabled=not as_json))

        def on_start(start: DashboardStart) -> None:
            # Stop the spinner first so it never overdraws what prints next.
            spin.close()
            (_print_json if as_json else _print_human)(start)

        try:
            run_dashboard(port=port, open_browser=not no_browser, on_start=on_start)
        except DashboardError as error:
            raise CliError(str(error)) from error
    return 0
