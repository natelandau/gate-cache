"""The cyclopts application that serves every subcommand and the info flags."""

from __future__ import annotations

import sys
from contextvars import ContextVar
from typing import TYPE_CHECKING, Annotated

import cyclopts
from rich import box
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from gate_cache import __version__
from gate_cache.commands.output import CliError, UsageError, emit_error
from gate_cache.commands.theme import out
from gate_cache.wait_settings import DEFAULT_WAIT_TIMEOUT

if TYPE_CHECKING:
    from collections.abc import Sequence

DOCS_URL = "https://natelandau.github.io/gate-cache/"
_HELP_FLAGS = ("-h", "--help")
_BUILTIN_FLAGS = {*_HELP_FLAGS, "--version"}
_STATS_FLAGS = {"--json", "--yes", "-y"}
_PIPED_HELP_WIDTH = 80
_ABOUT = (
    "Skip a lint or test command that already passed on the same git tree. "
    "Wrap the command after --."
)
_AGENT_NOTE = (
    "AI agents that set up, configure, or troubleshoot gate-cache: run "
    "`gate-cache --skill` or `gate-cache --prompt`."
)
_RUN_USAGE = "gate-cache [OPTIONS] -- COMMAND [ARGS...]"
_RUN_OPTIONS = (
    ("--name NAME", "Gate name. Default: the command itself."),
    ("--path PATHSPEC", "Key on only the files under this git pathspec. Repeat for each path."),
    ("--junit PATH", "Record the tests in this JUnit XML report. Repeat for each path."),
    (
        "--wait-timeout SECONDS",
        f"Longest wait for another run of the same gate. Default: {DEFAULT_WAIT_TIMEOUT}.",
    ),
    ("--on-wait-failure rerun|report", "What to do when the awaited run failed. Default: rerun."),
    ("--spot-check", "Run the command even when it already passed on this tree."),
)
_NAME_WARNING = "Never put a secret in --name: markers and `status` store the name as plain text."

JsonFlag = Annotated[bool, cyclopts.Parameter(name="--json", negative="", show_default=False)]
YesFlag = Annotated[bool, cyclopts.Parameter(name=["--yes", "-y"], negative="", show_default=False)]


def examples(*commands: str) -> str:
    """Return an Examples section for a command's help, printed after its options.

    Args:
        commands: Command lines to show, one per row.

    Returns:
        str: Markdown that cyclopts renders as a bulleted list of commands.
    """
    return "**Examples**\n\n" + "\n".join(f"- `{command}`" for command in commands)


app = cyclopts.App(
    name="gate-cache",
    version_flags=[],
    result_action="return_value",
    group_parameters=cyclopts.Group("Options"),
)
# Commands are registered by import path, so a command's module loads only when it runs or
# the top-level help lists it. Their examples live here for the same reason.
app.command(
    "gate_cache.commands.status:status",
    name="status",
    help_epilogue=examples(
        "gate-cache status",
        "gate-cache status --name pytest",
        "gate-cache status -- uv run pytest -x",
        "gate-cache status --name api-test --path api/ --path uv.lock",
        "gate-cache status --json",
    ),
)
app.command(
    "gate_cache.commands.clear:clear",
    name="clear",
    help_epilogue=examples("gate-cache clear", "gate-cache clear --yes --json"),
)
app.command("gate_cache.commands.stats:stats", name="stats")
app.command(
    "gate_cache.commands.dashboard:dashboard",
    name="dashboard",
    help_epilogue=examples(
        "gate-cache dashboard",
        "gate-cache dashboard --port 8080 --no-browser",
    ),
)

# Cyclopts drops the `--` separator, so run() keeps the wrapped command for the command to read.
_wrapped: ContextVar[list[str] | None] = ContextVar("wrapped", default=None)


def split_separator(tokens: Sequence[str]) -> tuple[list[str], list[str] | None]:
    """Split a command line at its first `--`.

    Args:
        tokens: The command line after the program name.

    Returns:
        tuple[list[str], list[str] | None]: The tokens before `--`, and the tokens after it,
            empty when `--` ends the line, or None when the line has no `--`.
    """
    if "--" not in tokens:
        return list(tokens), None
    index = tokens.index("--")
    return list(tokens[:index]), list(tokens[index + 1 :])


def json_requested(tokens: Sequence[str]) -> bool:
    """Report whether --json appears before the first `--`.

    Args:
        tokens: The command line after the program name.

    Returns:
        bool: True when a --json flag belongs to gate-cache, not to a wrapped command.
    """
    own, _ = split_separator(tokens)
    return "--json" in own


def command_after_separator() -> list[str] | None:
    """Return the tokens after the first `--` of the running command line.

    Returns:
        list[str] | None: The wrapped command, empty when `--` ends the line, or None when
            the line has no `--`.
    """
    return _wrapped.get()


def _panel(title: str, rows: Sequence[tuple[str, str]]) -> Panel:
    grid = Table.grid(padding=(0, 2))
    grid.add_column(style="accent", no_wrap=True)
    grid.add_column()
    for label, text in rows:
        grid.add_row(Text(label), Text(text))
    return Panel(grid, title=title, title_align="left", box=box.ROUNDED, border_style="muted")


def _summary(help_text: str | None) -> str:
    """Return a command's first paragraph, the part the Commands panel shows."""
    return " ".join((help_text or "").strip().split("\n\n")[0].split())


def print_top_help() -> None:
    """Print the top-level help: what gate-cache does, the gate run, and the subcommands."""
    console = out()
    # Off a terminal the console does not wrap, so cap the help at the width cyclopts uses.
    width = None if console.is_terminal else _PIPED_HELP_WIDTH
    commands = [(name, _summary(app[name].help)) for name in app if name not in _BUILTIN_FLAGS]
    for part in (
        Text(_ABOUT),
        Text(""),
        Text(_AGENT_NOTE, style="muted"),
        Text(""),
        Text("Usage: ", style="bold") + Text(_RUN_USAGE),
        _panel("Gate run options", _RUN_OPTIONS),
        _panel("Commands", commands),
        Text(_NAME_WARNING, style="warning"),
        Text(f"Docs: {DOCS_URL}", style="muted"),
    ):
        console.print(part, width=width)


@app.command(name="--version")
def version() -> int:
    """Print the installed version."""
    sys.stdout.write(f"{__version__}\n")
    return 0


@app.command(name="--skill")
def skill() -> int:
    """Print the guide for coding agents that use gate-cache."""
    from gate_cache.cli import agent_text

    sys.stdout.write(agent_text("skill.md"))
    return 0


@app.command(name="--prompt")
def prompt() -> int:
    """Print a prompt that has a coding agent add gate-cache or review its setup."""
    from gate_cache.cli import agent_text

    sys.stdout.write(agent_text("prompt.md"))
    return 0


def _report_first(tokens: list[str]) -> list[str]:
    """Move `report` straight after `stats`, so `stats --json report` reaches the report.

    Cyclopts finds a subcommand only before the first option. Only the value-less flags of
    `stats` may come before `report`; anything else stays as typed.
    """
    if not tokens or tokens[0] != "stats":
        return tokens
    for index, word in enumerate(tokens[1:], start=1):
        if word == "report":
            return ["stats", "report", *tokens[1:index], *tokens[index + 1 :]]
        if word not in _STATS_FLAGS:
            return tokens
    return tokens


def run(tokens: list[str]) -> int:
    """Run the command line in tokens and return its exit code.

    Args:
        tokens: The command line after the program name.

    Returns:
        int: The exit code. A usage or command error prints through the shared error output.
    """
    if tokens and tokens[0] in _HELP_FLAGS:
        print_top_help()
        return 0
    tokens = _report_first(tokens)
    reset = _wrapped.set(split_separator(tokens)[1])
    try:
        result = app(tokens, exit_on_error=False, print_error=False)
    except cyclopts.CycloptsError as error:
        return emit_error(UsageError(str(error).strip()), as_json=json_requested(tokens))
    except CliError as error:
        return emit_error(error, as_json=json_requested(tokens))
    finally:
        _wrapped.reset(reset)
    return 0 if result is None else int(result)
