"""The `status` subcommand: report which gates would skip on the current content."""

from __future__ import annotations

import shlex
from dataclasses import dataclass
from typing import TYPE_CHECKING, Annotated, Any

import cyclopts
from rich.console import Group
from rich.text import Text

from gate_cache.cli import NO_COMMAND
from gate_cache.commands.app import JsonFlag, command_after_separator
from gate_cache.commands.output import UsageError, emit, warn
from gate_cache.commands.theme import kv, spinner, table
from gate_cache.console import format_duration
from gate_cache.gate import gate_status

if TYPE_CHECKING:
    from rich.console import RenderableType

NEEDS_SEPARATOR = "put -- before the command"
SEPARATOR_EXAMPLE = "e.g. gate-cache status -- uv run pytest"
PATH_NEEDS_NAME = "--path needs --name or a command after --"
PATH_NEEDS_VALUE = "--path needs a value, e.g. gate-cache status --name pytest --path src/"
NO_GATES = "No gates match the current tree"
NAME_OR_COMMAND = "give --name or a command after --, not both"


@dataclass
class StatusOutcome:
    """A status report: the JSON object, without its schema key, and the exit code."""

    data: dict[str, Any]
    exit_code: int

    def to_json(self) -> dict[str, Any]:
        """Return the report as the JSON body."""
        return self.data

    def render(self) -> RenderableType:
        """Return the human view of an enabled report."""
        if "name" in self.data:
            return self._named()
        return self._listing()

    def _unknown(self, value: str | None) -> str:
        return value if value is not None else f"unknown: {self.data['reason']}"

    def _named(self) -> RenderableType:
        data = self.data
        scoped = "paths" in data
        marker = data["marker"]
        if marker is None:
            marker = f"none: {data['reason']}" if data["tree"] is not None else "none"
        rows = {"name": data["name"]}
        if scoped:
            rows["paths"] = " ".join(data["paths"])
            rows["scope"] = self._unknown(data["tree"])
        rows["tree"] = self._unknown(data["full_tree"] if scoped else data["tree"])
        rows |= {"marker": marker, "result": data["result"]}
        if data["duration"] is not None:
            rows["duration"] = format_duration(data["duration"])
        if data["last_run"] is not None:
            rows["last run"] = str(data["last_run"]["reason"])
        return kv(rows)

    def _listing(self) -> RenderableType:
        data = self.data
        if data["tree"] is None:
            return kv({"tree": self._unknown(None)})
        if data["reason"] is not None:
            return kv({"tree": data["tree"], "passed": self._unknown(None)})
        if not data["passed"] and not data["missed"]:
            return Group(kv({"tree": data["tree"]}), Text(NO_GATES))
        rows = [[name, "passed", "", ""] for name in data["passed"]]
        rows += [
            [
                miss["name"],
                "missed",
                "" if miss["exit_code"] is None else str(miss["exit_code"]),
                miss["reason"] or "",
            ]
            for miss in data["missed"]
        ]
        return Group(
            kv({"tree": data["tree"]}),
            table(["gate", "result", "exit code", "reason"], rows, right=["exit code"]),
        )


def resolve_gate(
    command: tuple[str, ...], name: str | None, *, example: str
) -> tuple[str | None, bool]:
    """Return the gate a command names by --name or by the command after --.

    A gate that ran without --name has its quoted command line as its name, so a lookup by
    command must quote it the same way.

    Args:
        command: The positional values cyclopts bound.
        name: The --name value, if any.
        example: The hint shown when the command lacks its `--`.

    Returns:
        tuple[str | None, bool]: The gate name, or None for neither, and whether -- gave it.

    Raises:
        UsageError: When positionals come without --, -- has no command, or both are given.
    """
    wrapped = command_after_separator()
    if wrapped is None:
        if command:
            raise UsageError(NEEDS_SEPARATOR, hint=example)
        return name, False
    if not wrapped:
        raise UsageError(NO_COMMAND)
    if tuple(command) != tuple(wrapped):
        raise UsageError(NEEDS_SEPARATOR, hint=example)
    if name is not None:
        raise UsageError(NAME_OR_COMMAND)
    return shlex.join(wrapped), True


def gate_name(command: tuple[str, ...], name: str | None, *, example: str) -> str | None:
    """Return the gate a command names by --name or by the command after --.

    Args:
        command: The positional values cyclopts bound.
        name: The --name value, if any.
        example: The hint shown when the command lacks its `--`.

    Returns:
        str | None: The gate name, or None when neither names one.
    """
    return resolve_gate(command, name, example=example)[0]


def status(
    *command: str,
    name: Annotated[str | None, cyclopts.Parameter(metavar="NAME")] = None,
    path: Annotated[
        list[str] | None, cyclopts.Parameter(metavar="PATHSPEC", negative_iterable="")
    ] = None,
    as_json: JsonFlag = False,
) -> int:
    """Report which gates would skip on the current content, running nothing.

    With no gate given, list each gate that passed or failed on the current tree. With
    --name, or with a command after --, show one gate: whether it would skip, the marker
    that records its pass, how long the passing run took, and how its last run failed.

    A gate that ran without --name has its command line as its name, so give the same
    command after --. For a gate scoped with --path, give the same --path values. The
    exit code is 0 when the gate, or at least one listed gate, would skip, and 1
    otherwise.

    Args:
        command: The command of a gate that ran without --name, after --.
        name: Gate to look up. Default: list every gate on this tree.
        path: Pathspec of a gate scoped with --path. Repeat for each path.
        as_json: Print one JSON object instead of text.

    Returns:
        int: The exit code.

    Raises:
        UsageError: When the options conflict or --path has no gate to apply to.
    """
    name = gate_name(command, name, example=SEPARATOR_EXAMPLE)
    paths = path or []
    if paths and name is None:
        raise UsageError(PATH_NEEDS_NAME)
    if "" in paths:
        raise UsageError(PATH_NEEDS_VALUE)

    with spinner("reading the working tree", enabled=not as_json):
        data, code = gate_status(name, paths=paths)
    if not as_json and not data["enabled"]:
        warn(data["reason"])
        return code
    return emit(StatusOutcome(data=data, exit_code=code), as_json=as_json)
