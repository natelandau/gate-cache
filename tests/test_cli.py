"""Tests for the command line interface."""

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


def test_run_requires_name(
    git_repo: Path, counter: Counter, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A run without --name is a usage error."""
    assert invoke(monkeypatch, "--", *counter.argv()) != 0
    assert counter.count == 0


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
    status.assert_called_once_with("x")
    assert invoke(monkeypatch, "clear") == 0
    clear.assert_called_once_with()


def test_status_without_name_lists_gates(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify status with no --name asks for the list of passed gates."""
    status = MagicMock(return_value=0)
    monkeypatch.setattr(cli, "gate_status", status)
    assert invoke(monkeypatch, "status") == 0
    status.assert_called_once_with(None)


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
    ):
        assert text in out
    flat = " ".join(out.split())
    assert "records a pass keyed on the git tree of the tracked files" in flat
    assert "untracked files the command runs without caching" in flat
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

    monkeypatch.setattr(cli, "app", interrupt)
    assert invoke(monkeypatch, "--name", "x", "--", "true") == 130
    assert "Traceback" not in capfd.readouterr().err
