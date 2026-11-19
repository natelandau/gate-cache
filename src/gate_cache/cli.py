"""Command line interface for gate-cache."""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import shlex
import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING

from gate_cache import __version__
from gate_cache import config as core_config
from gate_cache.console import kv, say
from gate_cache.env import hook_environment
from gate_cache.gate import (
    DEFAULT_MAX_AGE_DAYS,
    FILES_CHANGED_NOTICE,
    clear_cache,
    gate_status,
    run_gate,
)
from gate_cache.markers import MARKER_DIRNAME
from gate_cache.stats import config as stats_config
from gate_cache.wait_settings import FailedBehavior, parse_failed, wait_settings

if TYPE_CHECKING:
    import sqlite3
    from collections.abc import Callable, Sequence
    from typing import Any

    from gate_cache.stats.report import Window

_USAGE_ERROR = 2
_INTERRUPTED = 130
_INFO_FLAGS = {"-h", "--help", "--version", "--skill", "--prompt"}
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
_NO_COMMAND = "no command given after --"
NAME_OR_COMMAND = "give --name or a command after --, not both"
STATS_JSON_ACTION = "--json only applies to stats with no action"
ALL_REPOS_CONFLICT = "--all-repos cannot be combined with --repo or --name"
NAME_NEEDS_REPO = "one gate needs a repository: run inside one, or give --repo"
LIMIT_ERROR = "--limit takes a whole number, e.g. --limit 50"
_STATS_SCHEMA = 1
_LIMIT_DEFAULT = 20
_LIMIT_MAX = 500

_USAGE = """\
gate-cache [--name NAME] [--path PATHSPEC]... [--junit PATH]...
                  [--wait-timeout SECONDS] [--on-wait-failure rerun|report]
                  [--spot-check]
                  -- COMMAND [ARGS...]
       gate-cache status [--name NAME] [--path PATHSPEC]... [--json] [-- COMMAND...]
       gate-cache clear [--yes]
       gate-cache stats [--json | on | off | clear [--yes]]
       gate-cache stats report [--json] [--since DURATION] [--until WHEN] [--limit N]
                  [--all-repos | --repo NAME|PATH] [--name NAME | -- COMMAND...]
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

-- is required, and only --name, --path, --junit, --wait-timeout,
--on-wait-failure, and --spot-check can come before it. Everything after -- is
the command, verbatim. gate-cache does not use a shell. Without --name, the gate
name is the command itself, so each set of arguments has its own records. Give
--name to share records between commands that check the same thing, or to key on
inputs that the tree does not cover.

Only the name and the file content are keyed. The working directory is not, so
a command whose meaning depends on it needs a distinct --name. To also key on an
ignored file, an environment variable, or a tool version, put its value in
--name after an @, as in test@v22. A changed value gives a new name, so the
command runs again, and stats count every value toward the gate before the @.
Never put a secret in a name, because markers and status store it as plain
text. Give --name to a command that takes a secret argument.

--path scopes a gate to the files it reads, so a change elsewhere in the
repository does not run it again. Each --path is a git pathspec, read from the
top of the work tree. The working directory has no effect. Repeat --path for
each path. The gate skips when nothing under its paths changed, so a path that
is missing from the list hides a change that must run the command. A path that
matches no file runs the command without the cache.

A run waits for another run of the same gate that is still in progress, then
skips when that run passed. --wait-timeout SECONDS sets the longest wait (default
900, 0 never waits). --on-wait-failure sets what happens when the awaited run
failed: rerun (default) runs the command, report exits with the failure without
a rerun. Both flags override the `wait_timeout` and `wait_on_failure` keys of
the config file.

--spot-check runs the command even when it already passed on this tree, and
records the run as a spot check. Without the flag, a run that would skip runs
anyway about 1 time in 50; spot_check_one_run_in in the config file or
GATE_CACHE_SPOT_CHECK_ONE_RUN_IN changes the rate, and 0 turns it off.

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
             stats report: 1 for an unknown gate or repository, 2 for a usage
             error.
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
  GATE_CACHE_DATA_DIR: the directory for recorded stats. If empty or not set,
  `stats_data_dir` in the config file and then the platform default decide.

Typical use:
  gate-cache -- uv run pytest -x
  gate-cache --name pytest -- uv run pytest -x
  gate-cache --name "test@$(git hash-object .env)" -- uv run pytest
  gate-cache --name api-test --path api/ --path uv.lock -- uv run pytest api
"""

_RUN_HELP = """\
subcommands:
  status       Report which gates skip on the current content. Nothing runs.
  clear        Delete every recorded pass for this repository.
  stats        Show, turn on or off, or clear the opt-in recording of run stats,
               or print a report of them.
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

With --name or a command, print the name, the tree hash (or why it is
unknown), the marker path, hit or miss, how long the passing run took, and how
the last run on this tree failed when it did. Exit 0 on a hit, 1 otherwise. A
gate that ran without --name has the command line as its name. To look it up,
give the same command after --, such as `gate-cache status -- uv run ruff
check .`. A name built with $(...) must be given expanded. For a gate scoped
with --path, give the same --path values. The report adds "paths" and "scope"
lines.

Without either, list the gates that passed on the current tree and the gates
that ran on it without passing, with the exit code. Scoped gates are listed
when they passed or missed on the current content of their paths. Exit 0 when
at least one gate passed, 1 otherwise.

--json prints one object with "enabled", "tree", "reason" (why the tree is
unknown, or null), and either "passed" and "missed" (without either) or "name",
"marker", "result", "last_run", and "duration" (with either). With --path,
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
--json prints the same as one object with "schema", "enabled", "decided_by",
"config_file", and "data_dir".
`on` and `off` write `stats_enabled` to the config file and keep its other
lines. The setting comes from the first of: GATE_CACHE_STATS when not empty
(0 or false is off, any other value is on), CI (on means off), the config file,
and then off. GATE_CACHE_DATA_DIR, or `stats_data_dir` in the
config file, moves the data directory.

Recording never changes whether a command skips, its exit code, or its output,
and a failure to record is silent. Each run adds one event: the gate name, the
--path values, the tree key, the outcome, timings, the exit code, the CPU time
and peak memory of the command, the gate-cache version, the platform, what
started the run (CI, a git hook, a coding agent, or a terminal), the repository
and working tree paths, the directory where the gate ran, the branch and
commit, the URL of origin (or the first remote) without credentials, the host
name, a random machine ID, and the command line when --name differs from it.
A run that runs the command and finds a fresh --junit report also stores the
test names, outcomes, and durations from it in a separate file.
An event holds no command output and no file content. The data stays on this
machine.

`clear` permanently deletes all recorded stats. It asks you to type `yes`
first, and refuses when stdin is not a terminal unless you give --yes. It
refuses while the dashboard is running. It does not delete markers. Use
`gate-cache clear` for those.

`report` prints what the recorded runs cost and how they fail. Run
`gate-cache stats report --help` for its options.
"""

_STATS_REPORT_HELP = """\
Print a report of the recorded stats: for each gate, its runs, skip rate,
failures, run times, and the time it spent and saved. With --name, or a command
after --, print one gate in detail: its status on the current content, trend,
exit codes, flaky trees, where its runs came from, and its recent runs.

The report covers the repository given with --repo, else every repository with
--all-repos, else the current repository, else every repository when run
outside one. A gate that ran without --name has the command line as its name.
To look it up, give the same command after --. The report groups
test@v22 under test, so give --name test.

--json prints one object instead of text.

Exits 0 on success, also when nothing was recorded, 1 for an unknown gate or
repository, and 2 for a usage error.
"""

_DASHBOARD_HELP = f"""\
Serve a local dashboard of the recorded stats on 127.0.0.1 and open it in the
browser. Press Ctrl-C to stop it.

Without --port, it listens on {stats_config.DASHBOARD_PORT}, or on a free port when {stats_config.DASHBOARD_PORT} is taken. With
--port, it listens on that port only and fails when the port is in use. Only
one dashboard runs at a time. A second one prints the address of the running
one and opens it, unless you give --no-browser. It also exits 0 without serving
while `gate-cache stats clear` waits at its prompt.

The dashboard reads the stats that `gate-cache stats on` records. Only a
release wheel contains the dashboard UI. A copy installed from source, such as
the copy that a prek or pre-commit hook installs, or a git or path dependency,
has no UI. Run the dashboard from a `uv tool install gate-cache` install. In a
source checkout of gate-cache, run `uv run duty frontend_build` first.
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
        help="Print a prompt that has a coding agent add gate-cache to a repository or review its setup.",
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
    parser.add_argument(
        "--junit",
        metavar="PATH",
        help="With stats on, record the tests in this JUnit XML report, or folder of reports, "
        "that the command writes. Repeat for each path.",
    )
    return parser


def _status_parser() -> argparse.ArgumentParser:
    """Build the parser for the status subcommand."""
    parser = argparse.ArgumentParser(
        prog="gate-cache status",
        usage="%(prog)s [--name NAME] [--path PATHSPEC]... [--json] [-- COMMAND...]",
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
    _add_json(parser)
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


def _add_json(parser: argparse.ArgumentParser) -> None:
    """Add the --json flag that prints one JSON object instead of text."""
    parser.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        help="Print one JSON object to stdout instead of text. Exit codes are unchanged.",
    )


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
        # `report` never reaches this parser: _stats_command routes it to its own parser.
        choices=["on", "off", "clear"],
        help="Turn recording on or off, delete all recorded stats, or print a report.",
    )
    _add_yes(parser, "With clear, delete without asking for confirmation.")
    _add_json(parser)
    return parser


def _limit(text: str) -> int:
    """Parse --limit, pulling a value out of range into 1 to 500."""
    try:
        value = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(LIMIT_ERROR) from None
    return min(max(value, 1), _LIMIT_MAX)


def _stats_report_parser() -> argparse.ArgumentParser:
    """Build the parser for `stats report`."""
    parser = argparse.ArgumentParser(
        prog="gate-cache stats report",
        usage="%(prog)s [--json] [--since DURATION] [--until WHEN] [--limit N]\n"
        "       [--all-repos | --repo NAME|PATH] [--name NAME | -- COMMAND...]",
        description=_STATS_REPORT_HELP,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        allow_abbrev=False,
    )
    _add_json(parser)
    parser.add_argument(
        "--since",
        default="30d",
        metavar="DURATION",
        help="Window length: a whole number and h, d, w, or y. Default 30d.",
    )
    parser.add_argument(
        "--until",
        metavar="WHEN",
        help="Window end: a date, an ISO 8601 timestamp, or a duration ago. Default now.",
    )
    parser.add_argument(
        "--limit",
        type=_limit,
        default=_LIMIT_DEFAULT,
        metavar="N",
        help="Most items in each list, 1 to 500. Default 20.",
    )
    parser.add_argument("--all-repos", action="store_true", help="Cover every repository.")
    parser.add_argument(
        "--repo",
        action=_StoreOnce,
        metavar="NAME|PATH",
        help="Cover one repository, by the name the report prints or a path inside it.",
    )
    parser.add_argument(
        "--name", action=_StoreOnce, help="Report one gate, by its name without any @key."
    )
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
    """Parse the stats subcommand and run its action.

    `report` has flags of its own, which one parser with a positional action cannot give
    it, so its tokens go to a parser of their own.
    """
    action = next((token for token in tokens if not token.startswith("-")), None)
    if action == "report":
        # Only flags can come before `report`; its own parser accepts --json and rejects the rest.
        split = tokens.index("report")
        return _stats_report_command(tokens[:split] + tokens[split + 1 :])
    parser = _stats_parser()
    args = parser.parse_args(tokens)
    if args.yes and args.action != "clear":
        parser.error("--yes only applies to clear")
    if args.as_json and args.action is not None:
        parser.error(STATS_JSON_ACTION)
    if args.action == "clear":
        from gate_cache.stats.clear import stats_clear

        return stats_clear(confirmed=args.yes)
    return _stats(args.action, as_json=args.as_json)


def _stats_report_command(tokens: list[str]) -> int:
    """Parse `stats report`, check its flag combinations, and print the report."""
    import time

    from gate_cache.snapshot import git_common_dir
    from gate_cache.stats.archive import gate_of
    from gate_cache.stats.report import Window
    from gate_cache.stats.report_text import KEYED_NAME_ERROR
    from gate_cache.stats.window import local_zone, parse_window

    parser = _stats_report_parser()
    args, from_command = _parse_named(parser, tokens)
    if not from_command and args.name is not None and (gate := gate_of(args.name)) != args.name:
        parser.error(KEYED_NAME_ERROR.format(gate=gate))
    if args.all_repos and (args.repo is not None or args.name is not None):
        parser.error(ALL_REPOS_CONFLICT)
    now, tz = time.time(), local_zone()
    try:
        start, end = parse_window(args.since, args.until, now=now, tz=tz)
    except ValueError as error:
        parser.error(str(error))
    common = git_common_dir()
    here = None if common is None else str(common)
    if args.name is not None and args.repo is None and here is None:
        parser.error(NAME_NEEDS_REPO)
    scope = _ReportScope(
        repo=args.repo, all_repos=args.all_repos, name=args.name, here=here, limit=args.limit
    )
    window = Window(start=start, end=end, tz=tz, ends_now=end >= now)
    return _stats_report(scope, window=window, as_json=args.as_json)


@dataclass(frozen=True)
class _ReportScope:
    """What a `stats report` covers: the flags that pick repos and a gate, and the current repo."""

    repo: str | None
    all_repos: bool
    name: str | None
    here: str | None
    limit: int


class _UnknownGateError(LookupError):
    """The repo has no recorded run of the gate."""

    def __init__(self, name: str, repo: str | None) -> None:
        super().__init__(name)
        self.name = name
        self.repo = repo


def _build_report(
    conn: sqlite3.Connection | None, scope: _ReportScope, *, window: Window, recording: bool
) -> dict[str, Any]:
    """Return the report a scope asks for, from the open record.

    Raises:
        RepoNotFoundError: When --repo matches no recorded repo.
        _UnknownGateError: When the repo never recorded the gate.
    """
    from functools import partial

    from gate_cache.gate import current_status
    from gate_cache.stats.report import RepoNotFoundError, gate_report, resolve_repo, suite_report

    repo = scope.here
    if scope.repo is not None:
        if conn is None:
            raise RepoNotFoundError(scope.repo)
        repo = resolve_repo(conn, scope.repo)
    if scope.name is None:
        repos = None if scope.all_repos or repo is None else (repo,)
        return suite_report(conn, repos=repos, window=window, recording=recording)
    report = None
    if conn is not None:
        report = gate_report(
            conn,
            repo=repo,
            name=scope.name,
            window=window,
            limit=scope.limit,
            # The status on the current content says nothing about a gate of another repo.
            current=partial(current_status, snapshots={}) if repo == scope.here else None,
            recording=recording,
        )
    if report is None:
        raise _UnknownGateError(scope.name, repo)
    return report


def _stats_report(scope: _ReportScope, *, window: Window, as_json: bool) -> int:
    """Print the report for a scope and return the exit code."""
    import sqlite3

    from gate_cache.stats import report_text
    from gate_cache.stats.archive import ArchiveVersionError
    from gate_cache.stats.report import AmbiguousRepoError, RepoNotFoundError, open_record

    recording = stats_config.stats_setting().enabled
    try:
        with open_record() as conn:
            report = _build_report(conn, scope, window=window, recording=recording)
    except RepoNotFoundError as error:
        say(report_text.UNKNOWN_REPO.format(text=error.text))
        return 1
    except AmbiguousRepoError as error:
        say(report_text.AMBIGUOUS_REPO.format(text=error.text))
        for label, folder in error.matches:
            say(f"  {label}: {folder}")
        return _USAGE_ERROR
    except _UnknownGateError as error:
        say(report_text.UNKNOWN_GATE.format(name=error.name, repo=error.repo))
        if not recording:
            say(report_text.RECORDING_OFF_HINT)
        return 1
    except (ArchiveVersionError, sqlite3.Error, OSError) as error:
        say(str(error))
        return 1
    if as_json:
        text = json.dumps(report, indent=2) + "\n"
    elif scope.name is None:
        text = report_text.render_suite(report, window=window)
    else:
        text = report_text.render_gate(report, window=window, limit=scope.limit)
    sys.stdout.write(text)
    return 0


def _stats(action: str | None, *, as_json: bool = False) -> int:
    """Show the stats setting, or change it when an action is given."""
    if action is not None:
        try:
            stats_config.write_enabled(enabled=action == "on")
        except (OSError, stats_config.ConfigError) as error:
            reason = error.strerror if isinstance(error, OSError) else error
            say(f"could not write {core_config.config_path()}: {reason or error}")
            return 1
    setting = stats_config.stats_setting()
    if as_json:
        data = {
            "schema": _STATS_SCHEMA,
            "enabled": setting.enabled,
            "decided_by": setting.source,
            "config_file": str(core_config.config_path()),
            "data_dir": str(stats_config.state_dir()),
        }
        print(json.dumps(data, indent=2))  # noqa: T201
        return 0
    kv(
        {
            "recording": "on" if setting.enabled else "off",
            "decided by": setting.source,
            "config": str(core_config.config_path()),
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


def _parse_named(
    parser: argparse.ArgumentParser, tokens: list[str]
) -> tuple[argparse.Namespace, bool]:
    """Parse tokens that name a gate by --name, or by the command after -- as a run names it.

    Returns:
        The parsed flags, with `name` set from the command when one is given, and whether
        it was.

    Raises:
        _UsageError: When -- is given with no command after it.
    """
    command: list[str] | None = None
    if "--" in tokens:
        split = tokens.index("--")
        tokens, command = tokens[:split], tokens[split + 1 :]
    args = parser.parse_args(tokens)
    if command is not None:
        if not command:
            raise _UsageError(_NO_COMMAND)
        if args.name is not None:
            parser.error(NAME_OR_COMMAND)
        args.name = _command_name(command)
    return args, command is not None


def _status_command(tokens: list[str]) -> int:
    """Look up a gate by --name, or by the command after -- as a run without --name names it."""
    parser = _status_parser()
    args, _ = _parse_named(parser, tokens)
    if args.path and args.name is None:
        parser.error("--path needs --name or a command after --")
    if "" in args.path:
        parser.error(_NEEDS_VALUE["--path"])
    return gate_status(args.name, as_json=args.as_json, paths=args.path)


def _run_command(tokens: list[str]) -> int:
    """Run the gate for a run invocation and return its exit code.

    Raises:
        _UsageError: When the invocation is malformed.
    """
    run = _split_run(tokens)
    if not run.command:
        raise _UsageError(_NO_COMMAND)
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
    if tokens and tokens[0] in _INFO_FLAGS:
        # --help and --version print and exit inside parse_args
        args = _main_parser().parse_args(tokens)
        sys.stdout.write(agent_text(args.guide))
        return 0
    if tokens and tokens[0] == "status":
        return _status_command(tokens[1:])
    if tokens and tokens[0] == "clear":
        return clear_cache(confirmed=_clear_parser().parse_args(tokens[1:]).yes)
    if tokens and tokens[0] == "stats":
        return _stats_command(tokens[1:])
    if tokens and tokens[0] == "dashboard":
        args = _dashboard_parser().parse_args(tokens[1:])
        from gate_cache.dashboard.app import run_dashboard

        return run_dashboard(port=args.port, open_browser=not args.no_browser)

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
