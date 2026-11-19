"""Interactive confirmation for commands that delete data."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.prompt import Prompt
from rich.text import Text

from gate_cache import console
from gate_cache.commands.theme import err

if TYPE_CHECKING:
    from collections.abc import Sequence

NOTHING_DELETED = "aborted; nothing was deleted"


def confirm_deletion(action: str, warning: Sequence[str]) -> bool:
    """Warn that a deletion is permanent and return True only when the user types `yes`.

    Without a terminal on stdin nobody can answer, so refuse rather than block or guess; the
    caller's `--yes` flag skips this call.

    Args:
        action: The command's verb phrase, such as `clear stats`, used in the prompt.
        warning: What is deleted and what is lost; the first line is the headline.

    Returns:
        bool: True when the user typed `yes`, False when they refused or could not answer.
    """
    console_err = err()
    if not console.stdin_isatty():
        console_err.print(
            f"error: refusing to {action} without confirmation; pass --yes to {action} "
            "non-interactively",
            style="error",
            markup=False,
        )
        return False
    headline, *details = warning
    block = Text(f"WARNING: {headline}", style="warning")
    for line in [*details, "This cannot be undone."]:
        block.append(f"\n  {line}")
    console_err.print(block)
    try:
        answer = Prompt.ask(Text(f"type 'yes' to {action}"), console=console_err)
    except (EOFError, KeyboardInterrupt) as interrupt:
        console_err.print()
        console_err.print(NOTHING_DELETED, style="muted")
        if isinstance(interrupt, KeyboardInterrupt):
            raise
        return False
    if answer.strip() != "yes":
        console_err.print(NOTHING_DELETED, style="muted")
        return False
    return True
