"""Tests for the command line interface."""

import shlex
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import gate_cache
from gate_cache import cli
from tests.conftest import Counter


def invoke(monkeypatch: pytest.MonkeyPatch, *args: str) -> int:
    """Run main() with the given arguments and return the exit code."""
    monkeypatch.setattr(sys, "argv", ["gate-cache", *args])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    code = exc.value.code
    assert isinstance(code, int)
    return code


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


def test_status_finds_a_pass_recorded_under_the_default_name(
    git_repo: Path, counter: Counter, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify status --name with the quoted command reports a pass recorded without --name."""
    assert invoke(monkeypatch, "--", *counter.argv()) == 0
    assert invoke(monkeypatch, "status", "--name", shlex.join(counter.argv())) == 0


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
    run_gate.assert_called_once_with(name, command)


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
    run_gate.assert_called_once_with("x", ["uv", "run", "pytest", "-x", "--name", "y"])


def test_double_dash_protects_subcommand_names(monkeypatch: pytest.MonkeyPatch) -> None:
    """A wrapped program named like a subcommand is run, not dispatched."""
    run_gate = MagicMock(return_value=0)
    status = MagicMock(return_value=1)
    monkeypatch.setattr(cli, "run_gate", run_gate)
    monkeypatch.setattr(cli, "gate_status", status)
    assert invoke(monkeypatch, "--name", "s", "--", "status") == 0
    run_gate.assert_called_once_with("s", ["status"])
    status.assert_not_called()


def test_status_and_clear_dispatch(monkeypatch: pytest.MonkeyPatch) -> None:
    """Subcommands call their gate functions and propagate the codes."""
    status = MagicMock(return_value=1)
    clear = MagicMock(return_value=0)
    monkeypatch.setattr(cli, "gate_status", status)
    monkeypatch.setattr(cli, "clear_cache", clear)
    assert invoke(monkeypatch, "status", "--name", "x") == 1
    status.assert_called_once_with("x", as_json=False)
    assert invoke(monkeypatch, "clear") == 0
    clear.assert_called_once_with()


def test_status_without_name_lists_gates(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify status with no --name asks for the list of passed gates."""
    status = MagicMock(return_value=0)
    monkeypatch.setattr(cli, "gate_status", status)
    assert invoke(monkeypatch, "status") == 0
    status.assert_called_once_with(None, as_json=False)


def test_status_json_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify --json is passed through to the status report."""
    status = MagicMock(return_value=0)
    monkeypatch.setattr(cli, "gate_status", status)
    assert invoke(monkeypatch, "status", "--json") == 0
    status.assert_called_once_with(None, as_json=True)


def test_help_is_self_describing(
    monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    """Help explains the tool to a reader with no other context."""
    assert invoke(monkeypatch, "--help") == 0
    out = capfd.readouterr().out
    for text in (
        "--name",
        "GATE_CACHE_DISABLE",
        "GATE_CACHE_MAX_AGE_DAYS",
        "status",
        "clear",
        "gate-cache --name pytest -- ",
        "gate-cache -- uv run pytest",
    ):
        assert text in out
    flat = " ".join(out.split())
    assert "records a pass keyed on the git tree of the working copy" in flat
    assert "A pass on uncommitted work therefore skips when the same content is committed" in flat
    assert "If it is empty or not set, CI decides the same way" in flat
    assert "put its value in --name" in flat
    assert 'gate-cache --name "test-$(git hash-object .env)" -- ' in out
    assert "empty-command" not in out


def test_version_flag(monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]) -> None:
    """--version prints the package version."""
    assert invoke(monkeypatch, "--version") == 0
    assert gate_cache.__version__ in capfd.readouterr().out


@pytest.mark.parametrize(
    "args",
    [
        ["--name", "a", "--version", "--", "x"],
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
    run_gate.assert_called_once_with("a", ["echo", "hi"])


def test_ctrl_c_exits_130_quietly(
    monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    """Ctrl-C outside the child, such as during git probes, exits 130 with no traceback."""

    def interrupt(_name: str, _command: list[str]) -> int:
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
        ["status", "--name", "a", "--name", "b"],
    ],
)
def test_repeated_name_is_usage_error(
    monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str], args: list[str]
) -> None:
    """Verify a second --name is rejected instead of silently replacing the first."""
    run_gate = MagicMock(return_value=0)
    status = MagicMock(return_value=0)
    monkeypatch.setattr(cli, "run_gate", run_gate)
    monkeypatch.setattr(cli, "gate_status", status)
    assert invoke(monkeypatch, *args) == 2
    run_gate.assert_not_called()
    status.assert_not_called()
    assert "--name given more than once" in capfd.readouterr().err


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        (["status", "--help"], ["gate-cache status", "--name", "--json", "list the gates"]),
        (["status", "-h"], ["gate-cache status", "--json"]),
        (["clear", "--help"], ["gate-cache clear", "Delete every recorded pass"]),
        (["-h"], ["status", "clear", "GATE_CACHE_DISABLE"]),
    ],
)
def test_help_flags(
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
    args: list[str],
    expected: list[str],
) -> None:
    """Verify -h and --help describe the top level and each subcommand, then exit 0."""
    assert invoke(monkeypatch, *args) == 0
    out = capfd.readouterr().out
    for text in expected:
        assert text in out


@pytest.mark.parametrize("args", [["status", "--bogus"], ["clear", "extra"], ["status", "--name"]])
def test_subcommand_bad_arguments_are_usage_errors(
    monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str], args: list[str]
) -> None:
    """Verify malformed subcommand arguments exit 2 with the subcommand's usage."""
    status = MagicMock(return_value=0)
    clear = MagicMock(return_value=0)
    monkeypatch.setattr(cli, "gate_status", status)
    monkeypatch.setattr(cli, "clear_cache", clear)
    assert invoke(monkeypatch, *args) == 2
    status.assert_not_called()
    clear.assert_not_called()
    assert f"gate-cache {args[0]}" in capfd.readouterr().err


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
    run_gate.assert_called_once_with("-x", ["echo", "hi"])


def test_later_double_dash_reaches_the_command(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify only the first -- separates, so the command keeps its own --."""
    run_gate = MagicMock(return_value=0)
    monkeypatch.setattr(cli, "run_gate", run_gate)
    assert invoke(monkeypatch, "--name", "x", "--", "uv", "run", "--", "pytest") == 0
    run_gate.assert_called_once_with("x", ["uv", "run", "--", "pytest"])
