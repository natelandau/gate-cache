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
    from rich.console import RenderableType

SCHEMA = 1
JSON_NEEDS_YES = "--json needs --yes, because {command} cannot ask for confirmation"
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


@dataclass
class DeletionOutcome:
    """How many files a deletion removed and where they lived."""

    deleted: int
    noun: str
    location_key: str
    location: str
    exit_code: int = 0

    def to_json(self) -> dict[str, Any]:
        """Return the count and the folder under its JSON key."""
        return {"deleted": self.deleted, self.location_key: self.location}

    def render(self) -> RenderableType:
        """Return the human line."""
        return Text(f"removed {plural(self.deleted, self.noun)}", style="success")


def require_yes_for_json(command: str, *, yes: bool, as_json: bool) -> None:
    """Refuse --json without --yes for a command that would otherwise ask for confirmation.

    Args:
        command: The command as typed after `gate-cache`, such as `stats clear`.
        yes: Whether --yes was given.
        as_json: Whether --json was given.

    Raises:
        UsageError: When --json is given without --yes.
    """
    if as_json and not yes:
        raise UsageError(
            JSON_NEEDS_YES.format(command=command), hint=f"gate-cache {command} --yes --json"
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
