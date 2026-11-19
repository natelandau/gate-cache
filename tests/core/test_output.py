"""Tests for the styled output layer."""

import json
import sys
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from rich.console import RenderableType

from gate_cache import console
from gate_cache.commands import theme
from gate_cache.commands.output import CliError, UsageError, emit, emit_error
from gate_cache.commands.prompt import NOTHING_DELETED, confirm_deletion
from gate_cache.commands.theme import kv, table
from tests.conftest import rendered_text

WARNING = ["this deletes everything.", "data: /tmp/x"]


@pytest.fixture(autouse=True)
def _fresh_consoles() -> Iterator[None]:
    """Rebuild the cached consoles around each test so environment changes apply."""
    theme.out.cache_clear()
    theme.err.cache_clear()
    yield
    theme.out.cache_clear()
    theme.err.cache_clear()


class _Stub:
    exit_code = 3

    def to_json(self) -> dict[str, Any]:
        return {"a": 1}

    def render(self) -> RenderableType:
        return kv({"tree": "abc"})


def test_emit_json_adds_schema(capfd: pytest.CaptureFixture[str]) -> None:
    """JSON output carries the schema version and the outcome's exit code is returned."""
    assert emit(_Stub(), as_json=True) == 3
    assert json.loads(capfd.readouterr().out) == {"schema": 1, "a": 1}


@pytest.mark.parametrize(
    ("hint", "details"),
    [(None, None), ("try this", None), (None, {"k": ["a", "b"]}), ("try this", {"k": "v"})],
)
def test_emit_error_json_shape(
    capfd: pytest.CaptureFixture[str], hint: str | None, details: dict[str, Any] | None
) -> None:
    """The JSON error goes to stdout with null for what is absent, and returns the code."""
    error = CliError("boom", hint=hint, details=details, code=4)
    assert emit_error(error, as_json=True) == 4
    assert json.loads(capfd.readouterr().out) == {
        "schema": 1,
        "error": {"message": "boom", "hint": hint, "details": details},
    }


def test_usage_error_defaults_to_code_2() -> None:
    """A usage error exits 2 unless told otherwise."""
    assert UsageError("x").code == 2


def test_emit_error_human_goes_to_stderr(capfd: pytest.CaptureFixture[str]) -> None:
    """The human error prints the message, hint, and details on stderr only."""
    error = CliError("boom [x]", hint="try this", details={"files": ["item-one", "item-two"]})
    assert emit_error(error, as_json=False) == 1
    captured = capfd.readouterr()
    assert captured.out == ""
    assert "boom [x]" in captured.err
    assert "try this" in captured.err
    lines = captured.err.splitlines()
    assert any("item-one" in line and "item-two" not in line for line in lines)
    assert any("item-two" in line and "item-one" not in line for line in lines)


def test_no_escape_codes_when_piped(
    monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    """Output to a pipe carries no ANSI escape codes."""
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("FORCE_COLOR", raising=False)
    emit(_Stub(), as_json=False)
    emit_error(CliError("boom", hint="try this"), as_json=False)
    captured = capfd.readouterr()
    assert "tree" in captured.out
    assert "\x1b[" not in captured.out
    assert "\x1b[" not in captured.err


def test_piped_lines_never_wrap(
    monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    """A long error and a long value stay on one line each when output goes to a pipe."""
    monkeypatch.delenv("COLUMNS", raising=False)
    long = "/x/" + "a" * 200
    emit_error(CliError(f"no repository matches {long}"), as_json=False)
    theme.out().print(kv({"marker": long}))
    captured = capfd.readouterr()
    assert captured.err.splitlines() == [f"error: no repository matches {long}"]
    assert [line.rstrip() for line in captured.out.splitlines()] == [f"marker  {long}"]


def test_force_color_adds_escape_codes(
    monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    """FORCE_COLOR turns styling on even when piped."""
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("FORCE_COLOR", "1")
    emit(_Stub(), as_json=False)
    assert "\x1b[" in capfd.readouterr().out


def test_kv_keeps_markup_literal() -> None:
    """Brackets in a value print as typed, not as rich markup."""
    text = rendered_text(kv({"name": "pytest[unit] [bold]x[/bold]"}), width=80)
    assert "pytest[unit] [bold]x[/bold]" in text


@pytest.mark.parametrize(
    "build",
    [
        pytest.param(lambda value: kv({"marker": value}), id="kv"),
        pytest.param(lambda value: table(["folder"], [[value]]), id="table"),
    ],
)
def test_long_values_fold(build: Callable[[str], RenderableType]) -> None:
    """A value wider than the terminal wraps whole, with no ellipsis."""
    value = "/" + "a" * 150
    text = rendered_text(build(value), width=40)
    assert value in "".join(text.split())
    assert "…" not in text


def test_confirm_refuses_without_terminal(
    monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    """With no terminal to answer, refuse and name the --yes escape hatch."""
    monkeypatch.setattr(console, "stdin_isatty", lambda: False)
    assert confirm_deletion("clear things", WARNING) is False
    err = capfd.readouterr().err
    assert "--yes" in err
    assert "WARNING" not in err


@pytest.mark.parametrize("typed", ["no", "y", "YES", "", None])
def test_confirm_rejects_anything_but_yes(
    answer: Callable[[str | None], None], typed: str | None, capfd: pytest.CaptureFixture[str]
) -> None:
    """Only the exact word yes confirms; anything else, or end of input, aborts."""
    answer(typed)
    assert confirm_deletion("clear things", WARNING) is False
    err = capfd.readouterr().err
    assert "this deletes everything." in err


def test_confirm_ctrl_c_ends_line_and_reraises(
    answer: Callable[[str | None], None], capfd: pytest.CaptureFixture[str]
) -> None:
    """Ctrl-C at the prompt says nothing was deleted and propagates."""
    answer("^C")
    with pytest.raises(KeyboardInterrupt):
        confirm_deletion("clear things", WARNING)
    assert capfd.readouterr().err.rstrip().endswith(NOTHING_DELETED)


def test_confirm_accepts_yes(
    answer: Callable[[str | None], None], capfd: pytest.CaptureFixture[str]
) -> None:
    """Typing yes, with surrounding whitespace, confirms."""
    answer(" yes ")
    assert confirm_deletion("clear things", WARNING) is True
    assert NOTHING_DELETED not in capfd.readouterr().err


def test_spinner_keeps_stdout_results_on_stdout(
    monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    """Text written to stdout while a spinner shows is not redirected to stderr."""
    monkeypatch.setenv("FORCE_COLOR", "1")
    monkeypatch.delenv("NO_COLOR", raising=False)
    assert theme.err().is_terminal
    with theme.spinner("working"):
        sys.stdout.write("result\n")
    captured = capfd.readouterr()
    assert "result" in captured.out
    assert "result" not in captured.err


def test_error_details_that_are_not_json_types_still_serialize(
    capfd: pytest.CaptureFixture[str],
) -> None:
    """A path in the details prints as its string instead of raising."""
    emit_error(CliError("boom", details={"where": Path("data/x")}), as_json=True)
    assert json.loads(capfd.readouterr().out)["error"]["details"] == {"where": str(Path("data/x"))}
