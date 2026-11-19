"""Command line interface for gate-cache."""

from __future__ import annotations

import dataclasses
import os
import shlex
import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING

from gate_cache import __version__
from gate_cache import config as core_config
from gate_cache.console import say
from gate_cache.env import hook_environment
from gate_cache.gate import (
    DEFAULT_MAX_AGE_DAYS,
    run_gate,
)
from gate_cache.markers import MARKER_DIRNAME
from gate_cache.wait_settings import FailedBehavior, parse_failed, wait_settings

if TYPE_CHECKING:
    from collections.abc import Callable

_USAGE_ERROR = 2
_INTERRUPTED = 130
_APP_TOKENS = {
    "status",
    "clear",
    "stats",
    "dashboard",
    "-h",
    "--help",
    "--version",
    "--skill",
    "--prompt",
}
# Hidden: the prek and pre-commit hook manifest passes it in `entry`.
_HOOK_FLAG = "--hook"
_NAME_NEEDS_VALUE = "--name needs a value, e.g. gate-cache --name pytest -- uv run pytest"
_NEEDS_SEPARATOR = "put -- before the command, e.g. gate-cache -- uv run pytest"
_NEEDS_VALUE = {
    "--name": _NAME_NEEDS_VALUE,
    "--path": "--path needs a value, e.g. gate-cache --path src/ -- uv run pytest",
    "--junit": (
        "--junit needs a value, e.g. gate-cache --junit report.xml -- pytest --junitxml=report.xml"
    ),
    "--wait-timeout": (
        "--wait-timeout needs a value, e.g. gate-cache --wait-timeout 300 -- uv run pytest"
    ),
    "--on-wait-failure": (
        "--on-wait-failure needs a value, e.g. gate-cache --on-wait-failure report -- uv run pytest"
    ),
}
_NAME_REPEATED = "--name given more than once"
_SPOT_CHECK_REPEATED = "--spot-check given more than once"
# Each wait flag: the _WaitFlags field it sets, its parser, and the invalid-value message.
_WAIT_FLAGS: dict[str, tuple[str, Callable[[str], object | None], str]] = {
    "--wait-timeout": (
        "timeout",
        core_config.parse_whole_number,
        (
            "--wait-timeout takes whole seconds, 0 or more, "
            "e.g. gate-cache --wait-timeout 300 -- uv run pytest"
        ),
    ),
    "--on-wait-failure": (
        "failed",
        parse_failed,
        (
            "--on-wait-failure takes rerun or report, e.g. "
            "gate-cache --on-wait-failure report -- uv run pytest"
        ),
    ),
}
NO_COMMAND = "no command given after --"


def agent_text(filename: str) -> str:
    """Read a guide for coding agents that ships inside the package.

    The guides ship with the code so that an agent always reads the text that matches the
    installed version.

    Args:
        filename: File name in the package's agent directory, such as `skill.md`.

    Returns:
        str: The guide, with each `{{token}}` replaced by the installed value.
    """
    from importlib import resources  # lazy: keeps the import cost off every gate run

    text = resources.files("gate_cache").joinpath(f"agent/{filename}").read_text(encoding="utf-8")
    values = {
        "version": __version__,
        "max_age_days": str(DEFAULT_MAX_AGE_DAYS),
        "marker_dir": f".git/{MARKER_DIRNAME}/",
    }
    for token, value in values.items():
        text = text.replace(f"{{{{{token}}}}}", value)
    return text


class _UsageError(Exception):
    """A malformed run invocation, reported as one line on stderr with exit code 2."""


@dataclass(frozen=True)
class _RunArgs:
    """The options before -- and the command after it."""

    name: str | None
    paths: list[str]
    command: list[str]
    wait_timeout: int | None = None
    on_wait_failure: FailedBehavior | None = None
    junit: list[str] = dataclasses.field(default_factory=list)
    spot_check: bool = False


def _option_value(tokens: list[str], index: int, option: str) -> tuple[str, int] | None:
    """Read `option X` or `option=X` at index, returning the value and the next index.

    Raises:
        _UsageError: When the option has no value or an empty one, such as an unset shell
            variable.
    """
    arg = tokens[index]
    if arg == option:
        if index + 1 == len(tokens) or tokens[index + 1] == "--":
            raise _UsageError(_NEEDS_VALUE[option])
        value, after = tokens[index + 1], index + 2
    elif arg.startswith(f"{option}="):
        value, after = arg.removeprefix(f"{option}="), index + 1
    else:
        return None
    if not value:
        raise _UsageError(_NEEDS_VALUE[option])
    return value, after


@dataclass
class _WaitFlags:
    """The wait flags seen so far while splitting a run invocation."""

    timeout: int | None = None
    failed: FailedBehavior | None = None


def _wait_flag(tokens: list[str], index: int, wait: _WaitFlags) -> int | None:
    """Read a wait flag at index into wait, returning the next index, or None if it is not one.

    Raises:
        _UsageError: When the flag is repeated or its value is invalid.
    """
    for flag, (field, parse, invalid) in _WAIT_FLAGS.items():
        if (found := _option_value(tokens=tokens, index=index, option=flag)) is None:
            continue
        if getattr(wait, field) is not None:
            repeated = f"{flag} given more than once"
            raise _UsageError(repeated)
        value, after = found
        if (parsed := parse(value)) is None:
            raise _UsageError(invalid)
        setattr(wait, field, parsed)
        return after
    return None


def _split_run(tokens: list[str]) -> _RunArgs:
    """Split a run invocation into its options and the command after the first --.

    Only `--name`, `--path`, `--junit`, `--wait-timeout`, and `--on-wait-failure`, each as
    `--opt X` or `--opt=X`, and the bare `--spot-check` may precede `--`, so a stray option
    such as `--version` or the first word of the command can never be mistaken for one of ours.

    Raises:
        _UsageError: When anything else precedes `--`, `--` is missing, an option is
            missing its value or invalid, or a flag other than `--path` is given twice.
    """
    name: str | None = None
    paths: list[str] = []
    junit: list[str] = []
    wait = _WaitFlags()
    spot_check = False
    index = 0
    while index < len(tokens):
        if tokens[index] == "--":
            return _RunArgs(
                name=name,
                paths=paths,
                command=tokens[index + 1 :],
                wait_timeout=wait.timeout,
                on_wait_failure=wait.failed,
                junit=junit,
                spot_check=spot_check,
            )
        if (found := _option_value(tokens=tokens, index=index, option="--name")) is not None:
            if name is not None:
                raise _UsageError(_NAME_REPEATED)
            name, index = found
        elif (found := _option_value(tokens=tokens, index=index, option="--path")) is not None:
            value, index = found
            paths.append(value)
        elif (found := _option_value(tokens=tokens, index=index, option="--junit")) is not None:
            value, index = found
            junit.append(value)
        elif (found := _wait_flag(tokens, index, wait)) is not None:
            index = found
        elif tokens[index] == "--spot-check":
            if spot_check:
                raise _UsageError(_SPOT_CHECK_REPEATED)
            spot_check = True
            index += 1
        else:
            break
    raise _UsageError(_NEEDS_SEPARATOR)


def _command_name(command: list[str]) -> str:
    """Return the gate name of a run without --name: the command, quoted as a shell would."""
    return shlex.join(command)


def _run_command(tokens: list[str]) -> int:
    """Run the gate for a run invocation and return its exit code.

    Raises:
        _UsageError: When the invocation is malformed.
    """
    run = _split_run(tokens)
    if not run.command:
        raise _UsageError(NO_COMMAND)
    name = _command_name(run.command) if run.name is None else run.name
    wait = (
        wait_settings(timeout=run.wait_timeout, failed=run.on_wait_failure)
        if run.wait_timeout is not None or run.on_wait_failure is not None
        else None
    )
    return run_gate(
        name,
        run.command,
        paths=run.paths,
        wait=wait,
        junit=run.junit,
        spot_check=run.spot_check,
    )


def _enter_hook_environment() -> None:
    """Give the wrapped command the user's PATH when gate-cache runs as a prek or pre-commit hook."""
    if sys.prefix == sys.base_prefix:
        # Not a virtual environment, so sys.prefix/bin is a shared directory such as /usr/bin.
        return
    adjusted = hook_environment(environ=os.environ, prefix=sys.prefix)
    for removed in os.environ.keys() - adjusted.keys():
        del os.environ[removed]
    os.environ.update(adjusted)


def _dispatch(tokens: list[str]) -> int:
    """Run the invocation in tokens and return its exit code.

    Raises:
        _UsageError: When a run invocation is malformed.
    """
    if tokens and tokens[0] == _HOOK_FLAG:
        _enter_hook_environment()
        tokens = tokens[1:]
    if tokens and tokens[0] in _APP_TOKENS:
        from gate_cache.commands.app import run

        return run(tokens)
    return _run_command(tokens)


def main() -> None:
    """Run the gate-cache command line interface and exit with its code."""
    try:
        code = _dispatch(sys.argv[1:])
    except _UsageError as error:
        say(str(error))
        sys.exit(_USAGE_ERROR)
    except KeyboardInterrupt:
        sys.exit(_INTERRUPTED)
    sys.exit(code)
