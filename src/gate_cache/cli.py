"""Command line interface for gate-cache."""

from __future__ import annotations

import sys
from typing import Annotated

from cyclopts import App, Parameter

from gate_cache import __version__
from gate_cache.console import say
from gate_cache.gate import clear_cache, gate_status, run_gate

_USAGE_ERROR = 2
_INTERRUPTED = 130
_SUBCOMMANDS = {"status", "clear"}
_INFO_FLAGS = {"-h", "--help", "--version"}

_HELP = """\
Skip a lint or test command that already passed on the same git tree. gate-cache runs
the command, records a pass keyed on the git tree of the tracked files (the index, when
the working copy matches it), and skips the command next time the tree is identical.
With unstaged changes or untracked files the command runs without caching and nothing
is recorded.

Both --name and -- are required, and only --name may come before --. Everything after
-- is the command, verbatim.

Exit codes:
  run     the command's own exit code, or 0 when a recorded pass lets it skip.
          Usage errors exit 2.
  status  0 when the named gate, or any gate without --name, passed on the
          current tree. 1 otherwise.
  clear   0 on success, 1 on failure.

Set GATE_CACHE_DISABLE to any non-empty value other than 0 to always run the command.
Set GATE_CACHE_MAX_AGE_DAYS to a positive whole number to change how many days a
recorded pass lasts (default 30).

Only file content is keyed. Never wrap checks that depend on anything else,
such as commit-message or branch-name checks.

Typical use:
  gate-cache --name pytest -- uv run pytest -x
"""

app = App(
    name="gate-cache",
    version=__version__,
    help=_HELP,
    help_format="plaintext",
    usage=(
        "Usage: gate-cache --name NAME -- COMMAND [ARGS...]\n"
        "       gate-cache status [--name NAME]\n"
        "       gate-cache clear"
    ),
    result_action="return_int_as_exit_code_else_zero",
)


@app.default
def run(
    command: Annotated[
        list[str], Parameter(allow_leading_hyphen=True, negative_iterable="", show_default=False)
    ],
    /,
    *,
    name: str,
) -> int:
    """Run COMMAND unless it already passed on the current git tree.

    On a skip, prints one line to stderr and exits 0 without running anything. Otherwise
    runs the command and exits with its exit code. The command runs without caching
    (and nothing is recorded) when GATE_CACHE_DISABLE is set, the tree has unstaged
    changes or untracked files, or this is not a git repository. A pass is recorded only
    when the command exits 0 and the run leaves the tree unchanged.

    Parameters
    ----------
    command
        The command and its arguments, given after `--`. Example: -- uv run pytest -x
    name
        Gate name. Records match only when the name and the tree both match.
    """
    if not command:
        say("no command given after --")
        return _USAGE_ERROR
    return run_gate(name, command)


@app.command
def status(*, name: str | None = None) -> int:
    """Report whether gates would skip, without running anything.

    With --name, print the tree hash (or why it is unknown), the marker path,
    and hit or miss. Exit 0 on a hit, 1 otherwise.

    Without --name, list every gate that passed on the current tree.
    Exit 0 when at least one gate matches, 1 otherwise.

    Parameters
    ----------
    name
        Gate name to look up. Omit it to list every gate that passed on this tree.
    """
    return gate_status(name)


@app.command
def clear() -> int:
    """Delete every recorded pass for this repository.

    Use after something outside git changes, such as a tool upgrade. Exits 1 outside a
    git repository.
    """
    return clear_cache()


def _usage_error(tokens: list[str]) -> str | None:
    """Return the usage problem with a run invocation, or None when it is well formed.

    Only `--name X` or `--name=X` may precede `--`, so a stray option such as `--version`
    or the first word of the command can never be mistaken for one of ours.
    """
    if not tokens or tokens[0] in _SUBCOMMANDS | _INFO_FLAGS:
        return None
    index = 0
    while index < len(tokens):
        arg = tokens[index]
        if arg == "--":
            return None
        if arg == "--name":
            if index + 1 == len(tokens) or tokens[index + 1] == "--":
                return "--name needs a value, e.g. gate-cache --name pytest -- uv run pytest"
            index += 2
        elif arg.startswith("--name="):
            index += 1
        else:
            break
    return "put -- before the command, e.g. gate-cache --name pytest -- uv run pytest"


def main() -> None:
    """Run the gate-cache command line interface and exit with its code."""
    tokens = sys.argv[1:]
    if problem := _usage_error(tokens):
        say(problem)
        sys.exit(_USAGE_ERROR)
    try:
        code = app(tokens)
    except KeyboardInterrupt:
        sys.exit(_INTERRUPTED)
    sys.exit(code)
