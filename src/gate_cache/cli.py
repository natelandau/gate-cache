"""Command line interface for gate-cache."""

from __future__ import annotations

import argparse
import shlex
import sys
from typing import TYPE_CHECKING

from gate_cache import __version__
from gate_cache.console import say
from gate_cache.gate import clear_cache, gate_status, run_gate

if TYPE_CHECKING:
    from collections.abc import Sequence

_USAGE_ERROR = 2
_INTERRUPTED = 130
_INFO_FLAGS = {"-h", "--help", "--version"}
_NAME_NEEDS_VALUE = "--name needs a value, e.g. gate-cache --name pytest -- uv run pytest"
_NEEDS_SEPARATOR = "put -- before the command, e.g. gate-cache -- uv run pytest"
_NAME_REPEATED = "--name given more than once"
_NO_COMMAND = "no command given after --"

_USAGE = """\
gate-cache [--name NAME] -- COMMAND [ARGS...]
       gate-cache status [--name NAME] [--json]
       gate-cache clear"""

_HELP = """\
Skip a lint or test command that already passed on the same git tree. gate-cache
runs the command, records a pass keyed on the git tree of the working copy
(tracked and untracked, non-ignored files), and skips the command next time the
tree is identical. A pass on uncommitted work therefore skips when the same
content is committed.

-- is required, and only --name may come before it. Everything after -- is the
command, verbatim. Without --name, the gate name is the command itself, so each
set of arguments has its own records. Give --name to share records between
commands that check the same thing, or to key on inputs that the tree does not
cover.

Exit codes:
  run     the command's own exit code, or 0 when a recorded pass lets it skip.
          Usage errors exit 2.
  status  0 when the named gate, or any gate without --name, passed on the
          current tree. 1 otherwise. --json prints one JSON object instead.
  clear   0 on success, 1 on failure.

GATE_CACHE_DISABLE and CI are on when the value is not empty, 0, or false (any
case). If GATE_CACHE_DISABLE is on, the command always runs without the cache.
If it is 0 or false, caching stays on. If it is empty or not set, CI decides the
same way.
Set GATE_CACHE_MAX_AGE_DAYS to a positive whole number to change how many days a
recorded pass lasts (default 30).

Only the name and the file content are keyed. The working directory is not, so
a command whose meaning depends on it needs a distinct --name. To also key on an
ignored file, an environment variable, or a tool version, put its value in
--name. A changed value gives a new name, so the command runs again. Never put a
secret in a name, because markers and status store it as plain text. Without
--name the command line is the name, so give --name to a command that takes a
secret argument. Never wrap checks that depend on the commit message or the
branch name.

Typical use:
  gate-cache -- uv run pytest -x
  gate-cache --name pytest -- uv run pytest -x
  gate-cache --name "test-$(git hash-object .env)" -- uv run pytest
"""

_RUN_HELP = """\
subcommands:
  status       Report whether gates would skip, without running anything.
  clear        Delete every recorded pass for this repository.

run:
  gate-cache [--name NAME] -- COMMAND [ARGS...] runs COMMAND unless it already
  passed on the current git tree. On a skip, it prints one line to stderr and
  exits 0 without running anything. Otherwise it runs the command and exits with
  its exit code. The command runs without caching (and nothing is recorded) when
  GATE_CACHE_DISABLE or CI turns caching off, the tree is unknown (for example an
  unmerged index), or this is not a git repository. A pass is recorded only when
  the command exits 0 and the run leaves the tree unchanged.

Run gate-cache SUBCOMMAND --help for the options of a subcommand.
"""

_STATUS_HELP = """\
Report whether gates would skip, without running anything.

With --name, print the tree hash (or why it is unknown), the marker path,
hit or miss, and how the last run on this tree failed when it did. Exit 0 on a
hit, 1 otherwise.

Without --name, list the gates that passed on the current tree and the gates
that ran on it without passing. Exit 0 when at least one gate passed, 1 otherwise.
"""

_CLEAR_HELP = """\
Delete every recorded pass for this repository.

Use after something outside git changes, such as a tool upgrade. Exits 1 outside a
git repository.
"""


class _UsageError(Exception):
    """A malformed run invocation, reported as one line on stderr with exit code 2."""


class _StoreOnce(argparse.Action):
    """Store an option's value, rejecting a second occurrence instead of overwriting the first."""

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: str | Sequence[object] | None,
        option_string: str | None = None,
    ) -> None:
        if getattr(namespace, self.dest) is not None:
            parser.error(f"{option_string} given more than once")
        setattr(namespace, self.dest, values)


def _main_parser() -> argparse.ArgumentParser:
    """Build the top-level parser, which serves only --help and --version.

    The run form is not parsed here because everything after -- must reach the wrapped
    command verbatim. The parser still declares --name so that --help documents it.
    """
    parser = argparse.ArgumentParser(
        prog="gate-cache",
        usage=_USAGE,
        description=_HELP,
        epilog=_RUN_HELP,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        allow_abbrev=False,
    )
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument(
        "--name",
        metavar="NAME",
        help="Gate name. Records match only when the name and the tree both match. "
        "Defaults to the command and its arguments, quoted as a shell would.",
    )
    return parser


def _status_parser() -> argparse.ArgumentParser:
    """Build the parser for the status subcommand."""
    parser = argparse.ArgumentParser(
        prog="gate-cache status",
        description=_STATUS_HELP,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        allow_abbrev=False,
    )
    parser.add_argument(
        "--name",
        action=_StoreOnce,
        help="Gate name to look up. Omit it to list every gate that ran on this tree.",
    )
    parser.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        help="Print one JSON object to stdout instead of text. Exit codes are unchanged.",
    )
    return parser


def _clear_parser() -> argparse.ArgumentParser:
    """Build the parser for the clear subcommand."""
    return argparse.ArgumentParser(
        prog="gate-cache clear",
        description=_CLEAR_HELP,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        allow_abbrev=False,
    )


def _split_run(tokens: list[str]) -> tuple[str | None, list[str]]:
    """Split a run invocation into its --name value and the command after the first --.

    Only `--name X` or `--name=X` may precede `--`, so a stray option such as `--version`
    or the first word of the command can never be mistaken for one of ours.

    Raises:
        _UsageError: When anything else precedes `--`, `--` is missing, or `--name` is
            missing its value or given twice.
    """
    name: str | None = None
    index = 0
    while index < len(tokens):
        arg = tokens[index]
        if arg == "--":
            return name, tokens[index + 1 :]
        if arg == "--name":
            if index + 1 == len(tokens) or tokens[index + 1] == "--":
                raise _UsageError(_NAME_NEEDS_VALUE)
            value = tokens[index + 1]
            index += 2
        elif arg.startswith("--name="):
            value = arg.removeprefix("--name=")
            index += 1
        else:
            break
        if name is not None:
            raise _UsageError(_NAME_REPEATED)
        name = value
    raise _UsageError(_NEEDS_SEPARATOR)


def _dispatch(tokens: list[str]) -> int:
    """Run the invocation in tokens and return its exit code.

    Raises:
        _UsageError: When a run invocation is malformed.
    """
    if tokens and tokens[0] in _INFO_FLAGS:
        _main_parser().parse_args(tokens)  # prints help or the version, then exits
    if tokens and tokens[0] == "status":
        args = _status_parser().parse_args(tokens[1:])
        return gate_status(args.name, as_json=args.as_json)
    if tokens and tokens[0] == "clear":
        _clear_parser().parse_args(tokens[1:])
        return clear_cache()

    name, command = _split_run(tokens)
    if not command:
        raise _UsageError(_NO_COMMAND)
    if name == "":
        raise _UsageError(_NAME_NEEDS_VALUE)
    return run_gate(shlex.join(command) if name is None else name, command)


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
