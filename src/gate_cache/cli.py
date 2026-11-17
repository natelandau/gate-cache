"""Command line interface for gate-cache."""

from __future__ import annotations

import argparse
import shlex
import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING

from gate_cache import __version__
from gate_cache.console import kv, say
from gate_cache.gate import (
    DEFAULT_MAX_AGE_DAYS,
    FILES_CHANGED_NOTICE,
    clear_cache,
    gate_status,
    run_gate,
)
from gate_cache.markers import MARKER_DIRNAME
from gate_cache.stats import config as stats_config

if TYPE_CHECKING:
    from collections.abc import Sequence

_USAGE_ERROR = 2
_INTERRUPTED = 130
_INFO_FLAGS = {"-h", "--help", "--version", "--skill", "--prompt"}
_NAME_NEEDS_VALUE = "--name needs a value, e.g. gate-cache --name pytest -- uv run pytest"
_NEEDS_SEPARATOR = "put -- before the command, e.g. gate-cache -- uv run pytest"
_NEEDS_VALUE = {
    "--name": _NAME_NEEDS_VALUE,
    "--path": "--path needs a value, e.g. gate-cache --path src/ -- uv run pytest",
}
_NAME_REPEATED = "--name given more than once"
_NO_COMMAND = "no command given after --"

_USAGE = """\
gate-cache [--name NAME] [--path PATHSPEC]... -- COMMAND [ARGS...]
       gate-cache status [--name NAME [--path PATHSPEC]...] [--json]
       gate-cache clear [--yes]
       gate-cache stats [on|off|clear [--yes]]
       gate-cache dashboard [--port N] [--no-browser]
       gate-cache --skill | --prompt"""

_HELP = f"""\
Skip a lint or test command that already passed on the same content. gate-cache
runs the command, records a pass keyed on the git tree of the working copy
(tracked and untracked, non-ignored files), and skips the command next time the
tree is identical. A pass on uncommitted work therefore skips when the same
content is committed. A skip prints one line to stderr, such as "pytest already
passed on tree aaff74984ccc, skipping", and exits 0.

AI agents: run `gate-cache --skill` and read the guide before you run, add, or
change a gate.

-- is required, and only --name and --path can come before it. Everything after
-- is the command, verbatim. gate-cache does not use a shell. Without --name,
the gate name is the command itself, so each set of arguments has its own
records. Give --name to share records between commands that check the same
thing, or to key on inputs that the tree does not cover.

Only the name and the file content are keyed. The working directory is not, so
a command whose meaning depends on it needs a distinct --name. To also key on an
ignored file, an environment variable, or a tool version, put its value in
--name. A changed value gives a new name, so the command runs again. Never put a
secret in a name, because markers and status store it as plain text. Give --name
to a command that takes a secret argument.

--path scopes a gate to the files it reads, so a change elsewhere in the
repository does not run it again. Each --path is a git pathspec, read from the
top of the work tree. The working directory has no effect. Repeat --path for
each path. The gate skips when nothing under its paths changed, so a path that
is missing from the list hides a change that must run the command. A path that
matches no file runs the command without the cache.

A pass is recorded only when the command exits 0 and leaves the files
unchanged. A command that changes files prints:
  {FILES_CHANGED_NOTICE}

Hook (prek, pre-commit 3.2+): repo https://github.com/natelandau/gate-cache,
rev v{__version__}, id gate-cache. Its args are the same as the command line.

Exit codes:
  run        the command's own exit code, or 0 when a recorded pass makes it
             skip. 127 when the command is not found, 126 when it cannot
             run, 128+N when signal N stops it. Usage errors exit 2 and run
             nothing.
  status     0 when the named gate, or any gate without --name, passed on the
             current tree. 1 otherwise.
  clear      0 on success, 1 on failure or when not confirmed.
  stats      0 on success, 1 on failure or when clear is not confirmed.
  dashboard  0 after a clean stop or when one already runs, 1 when it cannot
             start.

Environment:
  GATE_CACHE_DISABLE and CI are on when the value is not empty, 0, or false (any
  case). If GATE_CACHE_DISABLE is on, the command always runs without the cache.
  If it is 0 or false, caching stays on. If it is empty or not set, CI decides
  the same way.
  GATE_CACHE_MAX_AGE_DAYS: a positive whole number of days that a recorded pass
  lasts (default {DEFAULT_MAX_AGE_DAYS}).
  GATE_CACHE_STATS: if on, record run stats even in CI. If 0 or false, do not
  record. If empty or not set, CI and then the config file decide.

Typical use:
  gate-cache -- uv run pytest -x
  gate-cache --name pytest -- uv run pytest -x
  gate-cache --name "test-$(git hash-object .env)" -- uv run pytest
  gate-cache --name api-test --path api/ --path uv.lock -- uv run pytest api
"""

_RUN_HELP = """\
subcommands:
  status       Report which gates skip on the current content. Nothing runs.
  clear        Delete every recorded pass for this repository.
  stats        Show, turn on or off, or clear the opt-in recording of run stats.
  dashboard    Serve a local dashboard of the recorded stats.

run:
  The command runs without caching, and nothing is recorded, when
  GATE_CACHE_DISABLE or CI turns caching off, when this is not a git repository,
  or when the tree is unknown, such as during a merge conflict. The printed
  reason names the cause. A failed run is recorded as a miss that status
  reports.

Run gate-cache SUBCOMMAND --help for the options of a subcommand.
"""

_STATUS_HELP = """\
Report which gates skip on the current content. Nothing runs.

With --name, print the name, the tree hash (or why it is unknown), the marker
path, hit or miss, how long the passing run took, and how the last run on this
tree failed when it did. Exit 0 on a hit, 1 otherwise. A gate that ran without
--name has the command line as its name, with shell quoting, such as
--name "uv run ruff check .". A name built with $(...) must be given expanded.
For a gate scoped with --path, give the same --path values with --name. The
report adds "paths" and "scope" lines.

Without --name, list the gates that passed on the current tree and the gates
that ran on it without passing, with the exit code. Scoped gates are listed
when they passed or missed on the current content of their paths. Exit 0 when
at least one gate passed, 1 otherwise.

--json prints one object with "enabled", "tree", "reason" (why the tree is
unknown, or null), and either "passed" and "missed" (without --name) or "name",
"marker", "result", "last_run", and "duration" (with --name). With --path,
"tree" holds the scope and the object adds "paths" and "full_tree".
"""

_CLEAR_HELP = """\
Permanently delete every recorded pass for this repository.

Use after something outside git changes, such as a tool upgrade. Every gate then
runs again in full. It also deletes the records of missed runs. It does not
delete recorded stats. Use `gate-cache stats clear` for those. It asks you to
type `yes` first, and refuses when stdin is not a terminal unless you give
--yes. Exits 1 outside a git repository.
"""

_STATS_HELP = """\
Show or change whether gate-cache records run stats.

Recording is off until you turn it on. Without an action, print whether
recording is on, what decided it, the config file, and the data directory.
`on` and `off` write [stats] enabled to the config file and keep its other
lines. The setting comes from the first of: GATE_CACHE_STATS when not empty
(0 or false is off, any other value is on), CI (on means off), the config file,
and then off.

Recording never changes whether a command skips, its exit code, or its output,
and a failure to record is silent. Each run adds one event: the gate name, the
--path values, the tree key, the outcome, timings, the exit code, the CPU time
and peak memory of the command, the gate-cache version, the platform, what
started the run (CI, a git hook, a coding agent, or a terminal), the repository
and working tree paths, the directory where the gate ran, the branch and
commit, the URL of origin (or the first remote) without credentials, the host
name, a random machine ID, and the command line when --name differs from it.
An event holds no command output and no file content. The data stays on this
machine.

`clear` permanently deletes all recorded stats. It asks you to type `yes`
first, and refuses when stdin is not a terminal unless you give --yes. It
refuses while the dashboard is running. It does not delete markers. Use
`gate-cache clear` for those.
"""

_DASHBOARD_HELP = f"""\
Serve a local dashboard of the recorded stats on 127.0.0.1 and open it in the
browser. Press Ctrl-C to stop it.

Without --port, it listens on {stats_config.DASHBOARD_PORT}, or on a free port when {stats_config.DASHBOARD_PORT} is taken. With
--port, it listens on that port only and fails when the port is in use. Only
one dashboard runs at a time. A second one prints the address of the running
one and opens it, unless you give --no-browser. It also exits 0 without serving
while `gate-cache stats clear` waits at its prompt.

The dashboard reads the stats that `gate-cache stats on` records. The copy of
gate-cache that a prek or pre-commit hook installs has no dashboard UI. Run the
dashboard from a `uv tool install gate-cache` install.
"""
_MAX_PORT = 65535


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
    """Build the top-level parser, which serves only --help, --version, --skill, and --prompt.

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
        "--skill",
        action="store_const",
        dest="guide",
        const="skill.md",
        help="Print the guide for coding agents that use gate-cache, as a SKILL.md file.",
    )
    parser.add_argument(
        "--prompt",
        action="store_const",
        dest="guide",
        const="prompt.md",
        help="Print a prompt that has a coding agent add gate-cache to a repository.",
    )
    parser.add_argument(
        "--name",
        metavar="NAME",
        help="Gate name. Records match only when the name and the tree both match. "
        "Defaults to the command and its arguments, quoted as a shell would.",
    )
    parser.add_argument(
        "--path",
        metavar="PATHSPEC",
        help="Key on only the files under this git pathspec, read from the top of the work "
        "tree. Repeat for each path.",
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
        "--path",
        action="append",
        default=[],
        metavar="PATHSPEC",
        help="Look up the gate scoped to these paths. Repeat for each path. Needs --name.",
    )
    parser.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        help="Print one JSON object to stdout instead of text. Exit codes are unchanged.",
    )
    return parser


def _add_yes(parser: argparse.ArgumentParser, help_text: str) -> None:
    """Add the -y/--yes flag that skips a deletion's confirmation prompt."""
    parser.add_argument("-y", "--yes", action="store_true", help=help_text)


def _clear_parser() -> argparse.ArgumentParser:
    """Build the parser for the clear subcommand."""
    parser = argparse.ArgumentParser(
        prog="gate-cache clear",
        description=_CLEAR_HELP,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        allow_abbrev=False,
    )
    _add_yes(parser, "Delete without asking for confirmation.")
    return parser


def _stats_parser() -> argparse.ArgumentParser:
    """Build the parser for the stats subcommand."""
    parser = argparse.ArgumentParser(
        prog="gate-cache stats",
        description=_STATS_HELP,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        allow_abbrev=False,
    )
    parser.add_argument(
        "action",
        nargs="?",
        choices=["on", "off", "clear"],
        help="Turn recording on or off, or delete all recorded stats.",
    )
    _add_yes(parser, "With clear, delete without asking for confirmation.")
    return parser


def _port(text: str) -> int:
    """Parse a TCP port argument."""
    try:
        value = int(text)
    except ValueError:
        value = -1
    if not 1 <= value <= _MAX_PORT:
        msg = f"invalid port: {text!r}"
        raise argparse.ArgumentTypeError(msg)
    return value


def _dashboard_parser() -> argparse.ArgumentParser:
    """Build the parser for the dashboard subcommand."""
    parser = argparse.ArgumentParser(
        prog="gate-cache dashboard",
        description=_DASHBOARD_HELP,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        allow_abbrev=False,
    )
    parser.add_argument("--port", type=_port, metavar="N", help="Port to listen on.")
    parser.add_argument(
        "--no-browser", action="store_true", help="Do not open the dashboard in a browser."
    )
    return parser


def _stats_command(tokens: list[str]) -> int:
    """Parse the stats subcommand and run its action."""
    parser = _stats_parser()
    args = parser.parse_args(tokens)
    if args.yes and args.action != "clear":
        parser.error("--yes only applies to clear")
    if args.action == "clear":
        from gate_cache.stats.clear import stats_clear

        return stats_clear(confirmed=args.yes)
    return _stats(args.action)


def _stats(action: str | None) -> int:
    """Show the stats setting, or change it when an action is given."""
    if action is not None:
        try:
            stats_config.write_enabled(enabled=action == "on")
        except (OSError, stats_config.ConfigError) as error:
            reason = error.strerror if isinstance(error, OSError) else error
            say(f"could not write {stats_config.config_path()}: {reason or error}")
            return 1
    setting = stats_config.stats_setting()
    kv(
        {
            "recording": "on" if setting.enabled else "off",
            "decided by": setting.source,
            "config": str(stats_config.config_path()),
            "data": str(stats_config.state_dir()),
        }
    )
    return 0


@dataclass(frozen=True)
class _RunArgs:
    """The options before -- and the command after it."""

    name: str | None
    paths: list[str]
    command: list[str]


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


def _split_run(tokens: list[str]) -> _RunArgs:
    """Split a run invocation into its options and the command after the first --.

    Only `--name` and `--path`, each as `--opt X` or `--opt=X`, may precede `--`, so a stray
    option such as `--version` or the first word of the command can never be mistaken for
    one of ours.

    Raises:
        _UsageError: When anything else precedes `--`, `--` is missing, an option is
            missing its value, or `--name` is given twice.
    """
    name: str | None = None
    paths: list[str] = []
    index = 0
    while index < len(tokens):
        if tokens[index] == "--":
            return _RunArgs(name=name, paths=paths, command=tokens[index + 1 :])
        if (found := _option_value(tokens=tokens, index=index, option="--name")) is not None:
            if name is not None:
                raise _UsageError(_NAME_REPEATED)
            name, index = found
        elif (found := _option_value(tokens=tokens, index=index, option="--path")) is not None:
            value, index = found
            paths.append(value)
        else:
            break
    raise _UsageError(_NEEDS_SEPARATOR)


def _dispatch(tokens: list[str]) -> int:
    """Run the invocation in tokens and return its exit code.

    Raises:
        _UsageError: When a run invocation is malformed.
    """
    if tokens and tokens[0] in _INFO_FLAGS:
        # --help and --version print and exit inside parse_args
        args = _main_parser().parse_args(tokens)
        sys.stdout.write(agent_text(args.guide))
        return 0
    if tokens and tokens[0] == "status":
        parser = _status_parser()
        args = parser.parse_args(tokens[1:])
        if args.path and args.name is None:
            parser.error("--path needs --name")
        if "" in args.path:
            parser.error(_NEEDS_VALUE["--path"])
        return gate_status(args.name, as_json=args.as_json, paths=args.path)
    if tokens and tokens[0] == "clear":
        return clear_cache(confirmed=_clear_parser().parse_args(tokens[1:]).yes)
    if tokens and tokens[0] == "stats":
        return _stats_command(tokens[1:])
    if tokens and tokens[0] == "dashboard":
        args = _dashboard_parser().parse_args(tokens[1:])
        from gate_cache.dashboard.app import run_dashboard

        return run_dashboard(port=args.port, open_browser=not args.no_browser)

    run = _split_run(tokens)
    if not run.command:
        raise _UsageError(_NO_COMMAND)
    name = shlex.join(run.command) if run.name is None else run.name
    return run_gate(name, run.command, paths=run.paths)


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
