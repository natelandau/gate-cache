"""Result and error output shared by every subcommand."""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

from rich.text import Text

from gate_cache.commands.theme import err, kv, out
from gate_cache.console import plural

if TYPE_CHECKING:
    from collections.abc import Sequence

    from rich.console import RenderableType

SCHEMA = 1
JSON_NEEDS_YES = "--json needs --yes or --dry-run, because {command} cannot ask for confirmation"
_USAGE_CODE = 2


class CliError(Exception):
    """A failure a subcommand reports to the user and turns into an exit code."""

    default_code = 1

    def __init__(
        self,
        message: str,
        *,
        hint: str | None = None,
        details: Mapping[str, Any] | None = None,
        code: int | None = None,
    ) -> None:
        """Store the message and the optional hint, details, and exit code.

        Args:
            message: What went wrong.
            hint: What the user can do about it.
            details: Extra facts, shown as rows under the hint and in JSON.
            code: Process exit code; defaults to the class's `default_code`.
        """
        super().__init__(message)
        self.message = message
        self.hint = hint
        self.details = details
        self.code = self.default_code if code is None else code


class UsageError(CliError):
    """A command line the user got wrong; exits with code 2."""

    default_code = _USAGE_CODE


class Outcome(Protocol):
    """A subcommand result that prints as JSON or as a rendered view."""

    exit_code: int

    def to_json(self) -> dict[str, Any]:
        """Return the JSON body, without the schema key."""
        ...

    def render(self) -> RenderableType:
        """Return the human view."""
        ...


NOTHING_TO_DELETE = "nothing to delete"
WOULD_DELETE = "would delete {what}"
_LISTED_GATES = 8


def gate_list(names: Sequence[str]) -> str:
    """Return gate names for one warning line, cut short so a large suite stays readable.

    Args:
        names: The gate names, in the order to show them.

    Returns:
        str: The names joined by commas, ending with how many more when some are left out.
    """
    shown = ", ".join(names[:_LISTED_GATES])
    rest = len(names) - _LISTED_GATES
    return f"{shown}, and {rest} more" if rest > 0 else shown


@dataclass
class DeletionOutcome:
    """What a deletion removed, or in a dry run what it would remove.

    Attributes:
        deleted: How many items were deleted, or would be in a dry run. None when the
            count is unknown, such as for stats this version cannot read.
        noun: The singular name of one item, such as `recorded pass`.
        details: Extra JSON keys, such as the gates and the folder.
        summary: Lines that say what the items are, shown in a dry run.
        dry_run: Whether nothing was deleted on purpose.
        empty: Whether there was nothing to delete at all.
        also: Other things deleted beside the counted items, such as `1 record of failed
            runs`, named after the count.
    """

    deleted: int | None
    noun: str
    details: dict[str, Any]
    summary: tuple[str, ...] = ()
    dry_run: bool = False
    empty: bool = False
    also: tuple[str, ...] = ()
    exit_code: int = 0

    def to_json(self) -> dict[str, Any]:
        """Return the count, the dry-run flag, and the details."""
        return {"dry_run": self.dry_run, "deleted": self.deleted, **self.details}

    def render(self) -> RenderableType:
        """Return the human lines."""
        if self.empty:
            return Text(NOTHING_TO_DELETE, style="muted")
        what = f"every {self.noun}" if self.deleted is None else plural(self.deleted, self.noun)
        if not self.dry_run:
            parts = [what] if self.deleted != 0 else []
            return Text("deleted " + " and ".join([*parts, *self.also]), style="success")
        text = Text(WOULD_DELETE.format(what=what))
        for line in self.summary:
            text.append(f"\n  {line}")
        text.append("\nNothing was deleted.", style="muted")
        return text


def require_yes_for_json(command: str, *, asks: bool, as_json: bool) -> None:
    """Refuse --json for a run that would ask for confirmation, since JSON output cannot.

    Args:
        command: The command as typed after `gate-cache`, such as `stats clear`.
        asks: Whether the run would ask, that is, it has neither --yes nor --dry-run.
        as_json: Whether --json was given.

    Raises:
        UsageError: When --json is given to a run that would ask.
    """
    if as_json and asks:
        raise UsageError(
            JSON_NEEDS_YES.format(command=command), hint=f"gate-cache {command} --dry-run --json"
        )


def write_json(payload: Mapping[str, Any], *, indent: int | None = 2, flush: bool = False) -> None:
    """Write a payload with the schema key to stdout as JSON.

    Args:
        payload: The JSON body, without the schema key.
        indent: Spaces per nesting level, or None for one compact line.
        flush: Flush stdout after writing, for a process that keeps running.
    """
    text = json.dumps({"schema": SCHEMA, **payload}, indent=indent, default=str)
    sys.stdout.write(text + "\n")
    if flush:
        sys.stdout.flush()


def emit(outcome: Outcome, *, as_json: bool) -> int:
    """Print an outcome to stdout as JSON or as its human view.

    Args:
        outcome: The result to print.
        as_json: Print JSON instead of the human view.

    Returns:
        int: The outcome's exit code.
    """
    if as_json:
        write_json(outcome.to_json())
    else:
        out().print(outcome.render())
    return outcome.exit_code


def _detail_item(item: object) -> str:
    """Show a mapping in a details list as `key: value` pairs, such as `label: shop, folder: /a`."""
    if isinstance(item, Mapping):
        return ", ".join(f"{key}: {value}" for key, value in item.items())
    return str(item)


def _detail_rows(details: Mapping[str, Any]) -> dict[str, str]:
    rows: dict[str, str] = {}
    for key, value in details.items():
        if isinstance(value, (list, tuple)):
            rows[key] = "\n".join(_detail_item(item) for item in value)
        else:
            rows[key] = str(value)
    return rows


def emit_error(error: CliError, *, as_json: bool) -> int:
    """Print an error as a JSON object on stdout or as lines on stderr.

    Args:
        error: The failure to report.
        as_json: Print JSON instead of the human form.

    Returns:
        int: The error's exit code.
    """
    if as_json:
        write_json(
            {
                "error": {
                    "message": error.message,
                    "hint": error.hint,
                    "details": dict(error.details) if error.details is not None else None,
                }
            }
        )
        return error.code
    console = err()
    console.print(_labeled("error:", "error", error.message))
    if error.hint:
        console.print(_labeled("  hint:", "hint", error.hint, style="hint"))
    if error.details:
        console.print(kv(_detail_rows(error.details)))
    return error.code


def _labeled(label: str, label_style: str, message: str, *, style: str = "") -> Text:
    """Join a styled label and a literal message so wrapped lines stay one block."""
    return Text.assemble((label, label_style), " ", (message, style))


def warn(message: str) -> None:
    """Print one warning line on stderr."""
    err().print(_labeled("warning:", "warning", message))
