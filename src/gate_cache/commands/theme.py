"""Shared rich theme, consoles, and renderables for subcommand output."""

from __future__ import annotations

import contextlib
import os
from functools import cache
from typing import TYPE_CHECKING

from rich import box
from rich.console import Console
from rich.live import Live
from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text
from rich.theme import Theme

if TYPE_CHECKING:
    from collections.abc import Collection, Mapping, Sequence

    from rich.console import RenderableType

THEME = Theme(
    {
        "error": "bold red",
        "hint": "dim",
        "success": "green",
        "warning": "yellow",
        "muted": "dim",
        "accent": "cyan",
    }
)
# Wide enough that no result or error line wraps when output goes to a pipe or a file.
_UNWRAPPED_WIDTH = 10_000


def _console(*, stderr: bool) -> Console:
    console = Console(theme=THEME, highlight=False, stderr=stderr)
    # Rich wraps at 80 columns off a terminal, which splits paths and error lines that
    # scripts and agents read line by line. COLUMNS still sets the width when given.
    if not console.is_terminal and "COLUMNS" not in os.environ:
        console.width = _UNWRAPPED_WIDTH
    return console


@cache
def out() -> Console:
    """Return the shared stdout console, created on first use.

    Creation is deferred so color settings in the environment are read when output starts.
    """
    return _console(stderr=False)


@cache
def err() -> Console:
    """Return the shared stderr console, created on first use."""
    return _console(stderr=True)


def kv(rows: Mapping[str, str]) -> RenderableType:
    """Build a two-column grid of labels and values.

    Values are plain text, so brackets in a gate name or path print literally. Long values
    fold onto more lines because people copy them.

    Args:
        rows: Labels mapped to their values, in display order.
    """
    grid = Table.grid(padding=(0, 2))
    grid.add_column(style="muted")
    grid.add_column(overflow="fold")
    for label, value in rows.items():
        grid.add_row(label, Text(value))
    return grid


def table(
    headings: Sequence[str], rows: Sequence[Sequence[str]], *, right: Collection[str] = ()
) -> Table:
    """Build a lightly ruled table whose cells print as plain text.

    Args:
        headings: Column headings, in order.
        rows: One sequence of cell values per row.
        right: Headings whose columns are right-aligned, such as numbers.
    """
    result = Table(box=box.SIMPLE_HEAD)
    for heading in headings:
        result.add_column(heading, justify="right" if heading in right else "left", overflow="fold")
    for row in rows:
        result.add_row(*(Text(cell) for cell in row))
    return result


def spinner(message: str, *, enabled: bool = True) -> contextlib.AbstractContextManager[None]:
    """Show a spinner on stderr while a block runs, only on a terminal.

    Args:
        message: Text shown beside the spinner.
        enabled: Pass False to suppress the spinner, such as for `--json`.
    """
    console = err()
    if enabled and console.is_terminal:
        # Live without stdout redirection, so results printed inside the block stay on stdout.
        return Live(  # ty: ignore[invalid-explicit-return]
            Spinner("dots", text=message),
            console=console,
            transient=True,
            redirect_stdout=False,
            redirect_stderr=False,
        )
    return contextlib.nullcontext()
