"""Tests for the command line interface."""

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import gate_cache
from gate_cache import cli
from gate_cache import gate as gate_module
from gate_cache.commands.app import DOCS_URL
from gate_cache.wait_settings import WaitSettings
from tests.conftest import Counter, invoke


def test_run_requires_double_dash(
    git_repo: Path,
    counter: Counter,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """Without -- nothing runs and the error names the separator."""
    assert invoke(monkeypatch, "--name", "x", *counter.argv()) == 2
    assert counter.count == 0
    assert "--" in capfd.readouterr().err


def test_run_without_name_keys_on_the_command(
    git_repo: Path, counter: Counter, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Without --name, a rerun of the same command skips and other arguments run again."""
    assert invoke(monkeypatch, "--", *counter.argv()) == 0
    assert invoke(monkeypatch, "--", *counter.argv()) == 0
    assert counter.count == 1

    assert invoke(monkeypatch, "--", *counter.argv(touch=tmp_path / "elsewhere.txt")) == 0
    assert counter.count == 2


def test_run_rejects_empty_name(
    git_repo: Path,
    counter: Counter,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """An empty --name, such as an unset shell variable, is a usage error and nothing runs."""
    assert invoke(monkeypatch, "--name", "", "--", *counter.argv()) == 2
    assert counter.count == 0
    assert "--name needs a value" in capfd.readouterr().err


@pytest.mark.parametrize(
    ("command", "name"),
    [
        (["pytest", "a b"], "pytest 'a b'"),
        (["pytest", "a", "b"], "pytest a b"),
        (["status"], "status"),
    ],
)
def test_run_without_name_uses_quoted_command(
    monkeypatch: pytest.MonkeyPatch, command: list[str], name: str
) -> None:
    """The default name quotes arguments, so differently split commands never share a name."""
    run_gate = MagicMock(return_value=0)
    monkeypatch.setattr(cli, "run_gate", run_gate)
    assert invoke(monkeypatch, "--", *command) == 0
    run_gate.assert_called_once_with(name, command, paths=[], wait=None, junit=[], spot_check=False)


def test_empty_command_is_usage_error(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    """Nothing after -- exits 2 without running anything."""
    run_gate = MagicMock(return_value=0)
    monkeypatch.setattr(cli, "run_gate", run_gate)
    assert invoke(monkeypatch, "--name", "x", "--") == 2
    run_gate.assert_not_called()
    assert capfd.readouterr().err


def test_run_passes_through_exit_code(
    git_repo: Path, counter: Counter, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The wrapped command's exit code becomes gate-cache's."""
    assert invoke(monkeypatch, "--name", "x", "--", *counter.argv(exit_code=5)) == 5
    assert counter.count == 1


def test_run_passes_options_through_verbatim(monkeypatch: pytest.MonkeyPatch) -> None:
    """Options after -- belong to the wrapped command, even ours."""
    run_gate = MagicMock(return_value=0)
    monkeypatch.setattr(cli, "run_gate", run_gate)
    assert invoke(monkeypatch, "--name", "x", "--", "uv", "run", "pytest", "-x", "--name", "y") == 0
    run_gate.assert_called_once_with(
        "x",
        ["uv", "run", "pytest", "-x", "--name", "y"],
        paths=[],
        wait=None,
        junit=[],
        spot_check=False,
    )


def test_double_dash_protects_subcommand_names(monkeypatch: pytest.MonkeyPatch) -> None:
    """A wrapped program named like a subcommand is run, not dispatched."""
    run_gate = MagicMock(return_value=0)
    monkeypatch.setattr(cli, "run_gate", run_gate)
    assert invoke(monkeypatch, "--name", "s", "--", "status") == 0
    run_gate.assert_called_once_with(
        "s", ["status"], paths=[], wait=None, junit=[], spot_check=False
    )


@pytest.mark.parametrize(
    "text",
    [
        "--name",
        "--path",
        "--junit",
        "--wait-timeout",
        "--on-wait-failure",
        "--spot-check",
        "--skill",
        "--prompt",
        "status",
        "clear",
        "stats",
        "dashboard",
        DOCS_URL,
    ],
)
def test_help_names_the_run_options_and_subcommands(
    monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str], text: str
) -> None:
    """Top-level help names every gate run option, the agent flags, and the docs link."""
    monkeypatch.setenv("COLUMNS", "200")
    assert invoke(monkeypatch, "--help") == 0
    assert text in capfd.readouterr().out


@pytest.mark.parametrize("args", [["--help"], ["-h"], ["--help", "--", "true"], ["-h", "--foo"]])
def test_top_help_is_one_screen_and_lists_commands_from_the_app(
    monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str], args: list[str]
) -> None:
    """Any invocation that starts with a help flag prints the full top-level help."""
    monkeypatch.setenv("COLUMNS", "200")
    assert invoke(monkeypatch, *args) == 0
    out = capfd.readouterr().out
    assert DOCS_URL in out
    # Only the Commands panel prints a command's own help text.
    assert "Print the installed version" not in out
    assert "Print the guide for coding agents that use gate-cache" in out


def _frontmatter(text: str) -> dict[str, str]:
    """Parse the simple `key: value` frontmatter that opens a SKILL.md file."""
    lines = text.splitlines()
    assert lines[0] == "---"
    end = lines.index("---", 1)
    return dict(line.split(": ", 1) for line in lines[1:end])


def test_skill_flag_prints_skill_file(
    monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    """Verify --skill prints a SKILL.md with frontmatter and every token filled in."""
    assert invoke(monkeypatch, "--skill") == 0
    out = capfd.readouterr().out
    meta = _frontmatter(out)
    assert meta["name"] == "gate-cache"
    assert "already passed on" in meta["description"]
    assert f"rev: v{gate_cache.__version__}" in out
    assert "{{" not in out


@pytest.mark.parametrize(
    ("quoted", "source_fragments"),
    [
        ("already passed on tree", ["already passed on {snapshot.label}", 'f"tree {']),
        ("already passed on paths", ["already passed on {snapshot.label}", 'f"paths {']),
        (gate_module.FILES_CHANGED_NOTICE, []),
        (", running without cache", [", running without cache"]),
        (", waiting", [', waiting"']),
        (
            "after 15m 0s, running anyway",
            ["after ", "format_duration(settings.timeout)", ", running anyway"],
        ),
        ("not running again", [", not running again"]),
        ("caching disabled in CI", ["caching disabled in CI"]),
        ("matches no files", ["matches no files"]),
        ("warning: could not record pass: ", ["warning: could not record pass: "]),
    ],
)
def test_skill_quotes_messages_the_code_prints(quoted: str, source_fragments: list[str]) -> None:
    """Verify each message the skill tells agents to look for still comes from the code."""
    source = "".join(
        path.read_text(encoding="utf-8") for path in Path(cli.__file__).parent.rglob("*.py")
    )
    assert quoted in cli.agent_text("skill.md")
    for fragment in source_fragments:
        assert fragment in source


def test_prompt_flag_points_agent_to_skill(
    monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    """Verify --prompt prints the setup and review tasks and sends the agent to --skill."""
    assert invoke(monkeypatch, "--prompt") == 0
    out = capfd.readouterr().out
    assert out.startswith("# Set up gate-cache in this repository")
    assert "gate-cache --skill" in out
    assert "## Review an existing setup" in out
    assert "{{" not in out


def test_skill_sections_named_in_prompt_exist() -> None:
    """Verify every guide section the prompt names is a heading in the skill."""
    skill = cli.agent_text("skill.md")
    prompt = cli.agent_text("prompt.md")
    headings = {line.lstrip("#").strip() for line in skill.splitlines() if line.startswith("#")}
    named = re.findall(r'the "([^"]+)" section of the guide', prompt)
    assert named
    assert set(named) <= headings


@pytest.mark.parametrize(
    ("tokens", "expected"),
    [
        (["status", "--json"], True),
        (["status", "--", "tool", "--json"], False),
        (["stats", "report", "--json", "--", "x"], True),
        ([], False),
    ],
)
def test_json_requested(tokens: list[str], expected: bool) -> None:
    """Only a --json before the first -- belongs to gate-cache."""
    from gate_cache.commands.app import json_requested

    assert json_requested(tokens) is expected


@pytest.mark.parametrize(
    "args",
    [["--", "CMD", "--help"], ["--name", "x", "--", "CMD", "--version"]],
)
def test_info_words_inside_the_run_reach_the_command(
    monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str], args: list[str]
) -> None:
    """--help and --version after -- belong to the wrapped command."""
    run_gate = MagicMock(return_value=7)
    monkeypatch.setattr(cli, "run_gate", run_gate)
    assert invoke(monkeypatch, *args) == 7
    assert run_gate.call_args.args[1] == ["CMD", args[-1]]
    assert DOCS_URL not in capfd.readouterr().out


def test_version_flag(monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]) -> None:
    """--version prints the package version."""
    assert invoke(monkeypatch, "--version") == 0
    assert gate_cache.__version__ in capfd.readouterr().out


@pytest.mark.parametrize(
    "args",
    [
        ["--name", "a", "--version", "--", "x"],
        ["--name", "a", "--skill", "--", "x"],
        ["--name", "a", "--help", "--", "x"],
        ["--name", "a", "false", "--version", "--", "x"],
        ["--name", "a", "false", "--help", "--", "x"],
        ["--name", "a", "echo", "hi", "--", "there"],
        ["--name=a", "echo", "hi", "--", "there"],
        ["--name", "a", "status", "--", "x"],
        ["--name", "a"],
    ],
)
def test_tokens_before_double_dash_are_usage_error(
    monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str], args: list[str]
) -> None:
    """Only --name may come before --; anything else is a usage error and nothing runs."""
    run_gate = MagicMock(return_value=0)
    monkeypatch.setattr(cli, "run_gate", run_gate)
    assert invoke(monkeypatch, *args) == 2
    run_gate.assert_not_called()
    captured = capfd.readouterr()
    assert gate_cache.__version__ not in captured.out
    assert "put -- before the command" in captured.err


@pytest.mark.parametrize("args", [["--name"], ["--name", "--", "echo", "hi"]])
def test_run_name_without_value_is_usage_error(
    monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str], args: list[str]
) -> None:
    """Verify a bare --name reports the missing value instead of asking for --."""
    run_gate = MagicMock(return_value=0)
    monkeypatch.setattr(cli, "run_gate", run_gate)
    assert invoke(monkeypatch, *args) == 2
    run_gate.assert_not_called()
    assert "--name needs a value" in capfd.readouterr().err


def test_name_equals_form_is_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    """--name=X before -- is a valid run invocation."""
    run_gate = MagicMock(return_value=0)
    monkeypatch.setattr(cli, "run_gate", run_gate)
    assert invoke(monkeypatch, "--name=a", "--", "echo", "hi") == 0
    run_gate.assert_called_once_with(
        "a", ["echo", "hi"], paths=[], wait=None, junit=[], spot_check=False
    )


@pytest.mark.parametrize(
    "flags",
    [
        ["--wait-timeout", "30", "--on-wait-failure", "report"],
        ["--wait-timeout=30", "--on-wait-failure=report"],
    ],
)
def test_wait_flags_reach_run_gate(monkeypatch: pytest.MonkeyPatch, flags: list[str]) -> None:
    """Both wait flags, in either form, reach run_gate as resolved settings."""
    run_gate = MagicMock(return_value=0)
    monkeypatch.setattr(cli, "run_gate", run_gate)
    assert invoke(monkeypatch, *flags, "--", "true") == 0
    run_gate.assert_called_once_with(
        "true", ["true"], paths=[], wait=WaitSettings(30, "report"), junit=[], spot_check=False
    )


@pytest.mark.parametrize("value", ["-1", "x", ""])
def test_wait_timeout_invalid_is_usage_error(
    monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str], value: str
) -> None:
    """A bad --wait-timeout exits 2 with one line naming the flag."""
    run_gate = MagicMock(return_value=0)
    monkeypatch.setattr(cli, "run_gate", run_gate)
    assert invoke(monkeypatch, "--wait-timeout", value, "--", "true") == 2
    run_gate.assert_not_called()
    err = capfd.readouterr().err
    assert "--wait-timeout" in err
    assert len(err.strip().splitlines()) == 1


def test_on_wait_failure_invalid_is_usage_error(
    monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    """--on-wait-failure accepts only rerun or report."""
    run_gate = MagicMock(return_value=0)
    monkeypatch.setattr(cli, "run_gate", run_gate)
    assert invoke(monkeypatch, "--on-wait-failure", "skip", "--", "true") == 2
    run_gate.assert_not_called()
    assert "--on-wait-failure" in capfd.readouterr().err


@pytest.mark.parametrize("flag", ["--wait-timeout", "--on-wait-failure"])
def test_wait_flag_repeated_is_usage_error(
    monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str], flag: str
) -> None:
    """A wait flag given twice is a usage error."""
    run_gate = MagicMock(return_value=0)
    monkeypatch.setattr(cli, "run_gate", run_gate)
    value = "5" if flag == "--wait-timeout" else "rerun"
    assert invoke(monkeypatch, flag, value, flag, value, "--", "true") == 2
    run_gate.assert_not_called()
    assert f"{flag} given more than once" in capfd.readouterr().err


def test_wait_flag_after_separator_is_part_of_command(monkeypatch: pytest.MonkeyPatch) -> None:
    """A wait flag after -- belongs to the command and sets no wait settings."""
    run_gate = MagicMock(return_value=0)
    monkeypatch.setattr(cli, "run_gate", run_gate)
    assert invoke(monkeypatch, "--", "--wait-timeout", "5") == 0
    run_gate.assert_called_once_with(
        "--wait-timeout 5", ["--wait-timeout", "5"], paths=[], wait=None, junit=[], spot_check=False
    )


@pytest.mark.parametrize("args", [["--wait-timeout="], ["--wait-timeout", "--", "true"]])
def test_wait_timeout_without_value_is_usage_error(
    monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str], args: list[str]
) -> None:
    """An empty or missing --wait-timeout value is a usage error."""
    run_gate = MagicMock(return_value=0)
    monkeypatch.setattr(cli, "run_gate", run_gate)
    assert invoke(monkeypatch, *args) == 2
    run_gate.assert_not_called()
    assert "--wait-timeout needs a value" in capfd.readouterr().err


def test_ctrl_c_exits_130_quietly(
    monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    """Ctrl-C outside the child, such as during git probes, exits 130 with no traceback."""

    def interrupt(_name: str, _command: list[str], **_kwargs: object) -> int:
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "run_gate", interrupt)
    assert invoke(monkeypatch, "--name", "x", "--", "true") == 130
    assert "Traceback" not in capfd.readouterr().err


def test_ctrl_c_while_parsing_exits_130_quietly(
    monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    """Ctrl-C before a command body starts also exits 130 with no traceback."""

    def interrupt(_tokens: list[str]) -> int:
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "_dispatch", interrupt)
    assert invoke(monkeypatch, "--name", "x", "--", "true") == 130
    assert "Traceback" not in capfd.readouterr().err


@pytest.mark.parametrize(
    "args",
    [
        ["--name", "a", "--name", "b", "--", "true"],
        ["--name=a", "--name", "b", "--", "true"],
    ],
)
def test_repeated_name_is_usage_error(
    monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str], args: list[str]
) -> None:
    """Verify a second --name is rejected instead of silently replacing the first."""
    run_gate = MagicMock(return_value=0)
    monkeypatch.setattr(cli, "run_gate", run_gate)
    assert invoke(monkeypatch, *args) == 2
    run_gate.assert_not_called()
    assert "--name given more than once" in capfd.readouterr().err


@pytest.mark.parametrize(
    ("args", "options"),
    [
        (["status", "--help"], ["--name", "--path", "--json"]),
        (["clear", "-h"], ["--yes", "--json"]),
        (["stats", "--help"], ["report", "--yes", "--json"]),
        (
            ["stats", "report", "-h"],
            ["--name", "--repo", "--all-repos", "--since", "--until", "--limit", "--json"],
        ),
        (["dashboard", "--help"], ["--port", "--no-browser", "--json"]),
    ],
)
def test_subcommand_help_lists_its_options(
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
    args: list[str],
    options: list[str],
) -> None:
    """-h and --help on a subcommand print its usage and every option, then exit 0."""
    monkeypatch.setenv("COLUMNS", "200")
    assert invoke(monkeypatch, *args) == 0
    out = capfd.readouterr().out
    assert f"gate-cache {' '.join(args[:-1])}" in out
    for option in options:
        assert option in out


def test_no_arguments_is_usage_error(
    monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    """Verify a bare gate-cache asks for -- and exits 2."""
    assert invoke(monkeypatch) == 2
    assert "put -- before the command" in capfd.readouterr().err


def test_name_starting_with_dash_is_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify a --name value that looks like an option is still taken as the name."""
    run_gate = MagicMock(return_value=0)
    monkeypatch.setattr(cli, "run_gate", run_gate)
    assert invoke(monkeypatch, "--name", "-x", "--", "echo", "hi") == 0
    run_gate.assert_called_once_with(
        "-x", ["echo", "hi"], paths=[], wait=None, junit=[], spot_check=False
    )


def test_later_double_dash_reaches_the_command(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify only the first -- separates, so the command keeps its own --."""
    run_gate = MagicMock(return_value=0)
    monkeypatch.setattr(cli, "run_gate", run_gate)
    assert invoke(monkeypatch, "--name", "x", "--", "uv", "run", "--", "pytest") == 0
    run_gate.assert_called_once_with(
        "x", ["uv", "run", "--", "pytest"], paths=[], wait=None, junit=[], spot_check=False
    )


@pytest.mark.parametrize(
    "args",
    [
        ["--path", "a", "--path=b", "--name", "x", "--", "echo", "hi"],
        ["--name=x", "--path=a", "--path", "b", "--", "echo", "hi"],
    ],
)
def test_path_options_reach_the_gate(monkeypatch: pytest.MonkeyPatch, args: list[str]) -> None:
    """Verify repeated --path values in either form and order reach the gate."""
    run_gate = MagicMock(return_value=0)
    monkeypatch.setattr(cli, "run_gate", run_gate)
    assert invoke(monkeypatch, *args) == 0
    run_gate.assert_called_once_with(
        "x", ["echo", "hi"], paths=["a", "b"], wait=None, junit=[], spot_check=False
    )


@pytest.mark.parametrize(
    "args",
    [
        ["--path"],
        ["--path", "--", "echo"],
        ["--path=", "--", "echo"],
        ["--junit", "--", "echo"],
        ["--junit=", "--", "echo"],
    ],
)
def test_option_without_value_is_usage_error(
    monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str], args: list[str]
) -> None:
    """Verify --path or --junit with no value exits 2, runs nothing, and shows an example."""
    run_gate = MagicMock(return_value=0)
    monkeypatch.setattr(cli, "run_gate", run_gate)
    assert invoke(monkeypatch, *args) == 2
    run_gate.assert_not_called()
    option = args[0].removesuffix("=")
    assert capfd.readouterr().err.strip() == f"gate-cache: {cli._NEEDS_VALUE[option]}"


def test_junit_options_reach_the_gate(git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify repeated --junit values, in either form, reach the gate in order."""
    run_gate = MagicMock(return_value=0)
    monkeypatch.setattr(cli, "run_gate", run_gate)
    args = ["--junit", "a.xml", "--junit=b/", "--junit", "/abs/c.xml", "--", "echo"]

    assert invoke(monkeypatch, *args) == 0

    run_gate.assert_called_once_with(
        "echo",
        ["echo"],
        paths=[],
        wait=None,
        junit=["a.xml", "b/", "/abs/c.xml"],
        spot_check=False,
    )


@pytest.mark.parametrize("stats", [False, True])
def test_junit_in_deleted_cwd_runs_the_command(
    stats_dirs: tuple[Path, Path],
    counter: Counter,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
    tmp_path: Path,
    stats: bool,
) -> None:
    """Verify --junit in a deleted cwd runs the command and keeps its exit code and stderr."""
    if stats:
        config_file = stats_dirs[0]
        config_file.parent.mkdir(parents=True, exist_ok=True)
        config_file.write_text("[stats]\nenabled = true\n", encoding="utf-8")
    gone = tmp_path / "gone"
    gone.mkdir()
    monkeypatch.chdir(gone)
    gone.rmdir()
    assert invoke(monkeypatch, "--", *counter.argv(exit_code=3)) == 3
    without_junit = capfd.readouterr().err

    assert invoke(monkeypatch, "--junit", "report.xml", "--", *counter.argv(exit_code=3)) == 3

    assert counter.count == 2
    assert capfd.readouterr().err == without_junit


def test_scoped_skip_names_the_paths(
    git_repo: Path,
    counter: Counter,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """Verify a scoped skip says it matched on paths rather than the tree."""
    assert invoke(monkeypatch, "--name", "t", "--path", "a.txt", "--", *counter.argv()) == 0
    capfd.readouterr()
    assert invoke(monkeypatch, "--name", "t", "--path", "a.txt", "--", *counter.argv()) == 0
    assert counter.count == 1
    assert re.search(
        r"t already passed on paths [0-9a-f]{12}, skipping \(saved <1s\)$", capfd.readouterr().err
    )


def test_skill_timeout_line_matches_default_timeout_format() -> None:
    """Verify the timeout line in the skill shows the default limit as the code formats it."""
    from gate_cache.console import format_duration
    from gate_cache.wait_settings import DEFAULT_WAIT_TIMEOUT

    assert f"after {format_duration(DEFAULT_WAIT_TIMEOUT)}, running anyway" in cli.agent_text(
        "skill.md"
    )


def test_spot_check_flag_reaches_run_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    """--spot-check before -- reaches run_gate as spot_check=True."""
    run_gate = MagicMock(return_value=0)
    monkeypatch.setattr(cli, "run_gate", run_gate)
    assert invoke(monkeypatch, "--spot-check", "--", "true") == 0
    run_gate.assert_called_once_with(
        "true", ["true"], paths=[], wait=None, junit=[], spot_check=True
    )


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (["--spot-check", "--spot-check"], "--spot-check given more than once"),
        (["--spot-check=1"], "put -- before the command"),
    ],
)
def test_spot_check_flag_misuse_is_usage_error(
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
    args: list[str],
    message: str,
) -> None:
    """A repeated or valued --spot-check is a usage error."""
    run_gate = MagicMock(return_value=0)
    monkeypatch.setattr(cli, "run_gate", run_gate)
    assert invoke(monkeypatch, *args, "--", "true") == 2
    run_gate.assert_not_called()
    assert message in capfd.readouterr().err


def test_hook_flag_puts_the_users_path_first(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Run as the prek or pre-commit hook, the command sees the user's PATH before the hook's."""
    hook_env = tmp_path / "hook-env"
    monkeypatch.setattr(sys, "prefix", str(hook_env))
    monkeypatch.setenv("PATH", f"{hook_env / 'bin'}{os.pathsep}/usr/bin")
    monkeypatch.setenv("VIRTUAL_ENV", str(hook_env))
    seen: dict[str, str | None] = {}

    def run_gate(name: str, command: list[str], paths: list[str], **_: object) -> int:
        seen.update(PATH=os.environ.get("PATH"), VIRTUAL_ENV=os.environ.get("VIRTUAL_ENV"))
        return 0

    monkeypatch.setattr(cli, "run_gate", run_gate)
    assert invoke(monkeypatch, "--hook", "--name", "x", "--", "pytest") == 0
    assert seen == {"PATH": f"/usr/bin{os.pathsep}{hook_env / 'bin'}", "VIRTUAL_ENV": None}


def test_hook_flag_leaves_a_shared_python_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Outside a virtual environment, --hook never moves a shared bin/ such as /usr/bin."""
    shared = tmp_path / "usr"
    monkeypatch.setattr(sys, "prefix", str(shared))
    monkeypatch.setattr(sys, "base_prefix", str(shared))
    path = f"{shared / 'bin'}{os.pathsep}/opt/bin"
    monkeypatch.setenv("PATH", path)
    seen: dict[str, str | None] = {}

    def run_gate(name: str, command: list[str], paths: list[str], **_: object) -> int:
        seen["PATH"] = os.environ.get("PATH")
        return 0

    monkeypatch.setattr(cli, "run_gate", run_gate)
    assert invoke(monkeypatch, "--hook", "--name", "x", "--", "pytest") == 0
    assert seen == {"PATH": path}


_IMPORT_GUARD_SCRIPT = """
import json, sys
sys.argv = ["gate-cache", "--name", "guard", "--", sys.executable, "-c", "pass"]
import gate_cache.cli
code = None
try:
    gate_cache.cli.main()
except SystemExit as e:
    code = e.code
heavy = {"cyclopts", "rich"}
loaded = sorted(
    m for m in sys.modules if m.split(".")[0] in heavy or m.startswith("gate_cache.commands")
)
print(json.dumps({"code": code, "loaded": loaded}))
"""


def test_gate_run_never_imports_the_rich_cli(git_repo: Path) -> None:
    """A gate run and a skip load neither cyclopts, rich, nor the command modules."""
    # Subprocess: pytest plugins import rich into the test process.
    env = {k: v for k, v in os.environ.items() if k not in {"GATE_CACHE_DISABLE", "CI"}} | {
        "GATE_CACHE_STATS": "1"
    }
    for attempt in range(2):  # a run, then a skip
        result = subprocess.run(  # noqa: S603
            [sys.executable, "-c", _IMPORT_GUARD_SCRIPT],
            cwd=git_repo,
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
        report = json.loads(result.stdout.strip().splitlines()[-1])
        assert report == {"code": 0, "loaded": []}
        if attempt == 1:
            assert "already passed on" in result.stderr
