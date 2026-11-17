"""Tests for user-facing messages."""

import io
from collections.abc import Callable

import pytest

from gate_cache import console
from gate_cache.console import confirm_deletion, format_duration, kv, say

WARNING = ["this deletes everything.", "data: /tmp/x"]


def test_say_prints_prefixed_verbatim_to_stderr(capfd: pytest.CaptureFixture[str]) -> None:
    """Brackets print verbatim with the prefix, on stderr only."""
    say("unit [fast] [bold]x[/bold]")
    out, err = capfd.readouterr()
    assert out == ""
    assert err.strip() == "gate-cache: unit [fast] [bold]x[/bold]"


def test_kv_aligns_values(capfd: pytest.CaptureFixture[str]) -> None:
    """Values line up after the widest key, and continuation lines indent under them."""
    kv({"name": "unit", "last run": "first\nsecond"})
    out, _ = capfd.readouterr()
    assert out == "  name:     unit\n  last run: first\n            second\n"


def test_kv_prints_nothing_for_no_rows(capfd: pytest.CaptureFixture[str]) -> None:
    """An empty mapping prints nothing."""
    kv({})
    assert capfd.readouterr().out == ""


class _Terminal(io.StringIO):
    def __init__(self, *, tty: bool) -> None:
        super().__init__()
        self._tty = tty

    def isatty(self) -> bool:
        return self._tty


@pytest.mark.parametrize(
    ("tty", "env", "dimmed"),
    [
        (True, {}, True),
        (False, {}, False),
        (True, {"NO_COLOR": "1"}, False),
        (True, {"TERM": "dumb"}, False),
    ],
)
def test_kv_dims_keys_only_on_a_color_terminal(
    monkeypatch: pytest.MonkeyPatch, *, tty: bool, env: dict[str, str], dimmed: bool
) -> None:
    """Keys are dimmed on a terminal unless NO_COLOR or a dumb TERM opts out."""
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("TERM", "xterm-256color")
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    stdout = _Terminal(tty=tty)
    monkeypatch.setattr("sys.stdout", stdout)
    kv({"tree": "abc"})
    out = stdout.getvalue()
    assert ("\033[2mtree\033[0m" in out) is dimmed
    assert out.replace("\033[2m", "").replace("\033[0m", "") == "  tree: abc\n"


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (0, "<1s"),
        (0.4, "<1s"),
        (0.999, "<1s"),
        (1, "1s"),
        (59.4, "59s"),
        (59.6, "1m 0s"),
        (60, "1m 0s"),
        (94, "1m 34s"),
        (3599, "59m 59s"),
        (3600, "1h 0m"),
        (3725, "1h 2m"),
        (3750, "1h 3m"),
        (7199, "2h 0m"),
    ],
)
def test_format_duration_boundaries(seconds: float, expected: str) -> None:
    """Verify durations render as <1s, seconds, minutes and seconds, or hours and minutes."""
    assert format_duration(seconds) == expected


def test_confirm_refuses_without_terminal(
    monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    """With no terminal to answer, refuse and name the --yes escape hatch."""
    monkeypatch.setattr(console, "stdin_isatty", lambda: False)
    assert confirm_deletion("clear things", WARNING) is False
    err = capfd.readouterr().err
    assert "refusing to clear things without confirmation; pass --yes" in err
    assert "WARNING" not in err


@pytest.mark.parametrize("typed", ["no", "y", "YES", "", None])
def test_confirm_rejects_anything_but_yes(
    answer: Callable[[str | None], None], typed: str | None, capfd: pytest.CaptureFixture[str]
) -> None:
    """Only the exact word yes confirms; anything else, or end of input, aborts."""
    answer(typed)
    assert confirm_deletion("clear things", WARNING) is False
    err = capfd.readouterr().err
    assert "gate-cache: WARNING: this deletes everything.\n" in err
    assert "gate-cache:   data: /tmp/x\n" in err
    assert "gate-cache:   This cannot be undone.\n" in err
    assert "gate-cache: type 'yes' to clear things: " in err
    assert "aborted; nothing was deleted" in err


def test_confirm_ctrl_c_ends_line_and_reraises(
    answer: Callable[[str | None], None], capfd: pytest.CaptureFixture[str]
) -> None:
    """Ctrl-C at the prompt ends the prompt line, says nothing was deleted, and propagates."""
    answer("^C")
    with pytest.raises(KeyboardInterrupt):
        confirm_deletion("clear things", WARNING)
    assert capfd.readouterr().err.endswith(
        "type 'yes' to clear things: \ngate-cache: aborted; nothing was deleted\n"
    )


def test_confirm_accepts_yes(
    answer: Callable[[str | None], None], capfd: pytest.CaptureFixture[str]
) -> None:
    """Typing yes, with surrounding whitespace, confirms."""
    answer(" yes ")
    assert confirm_deletion("clear things", WARNING) is True
    assert "aborted" not in capfd.readouterr().err
