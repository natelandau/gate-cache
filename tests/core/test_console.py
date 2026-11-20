"""Tests for user-facing messages."""

from collections.abc import Callable

import pytest
from rich.text import Text

from gate_cache.commands.theme import err, kv, out, table
from gate_cache.console import CONTROL_STAND_IN, format_duration, say


def test_say_prints_prefixed_verbatim_to_stderr(capfd: pytest.CaptureFixture[str]) -> None:
    """Brackets print verbatim with the prefix, on stderr only."""
    say("unit [fast] [bold]x[/bold]")
    out, err = capfd.readouterr()
    assert out == ""
    assert err.strip() == "gate-cache: unit [fast] [bold]x[/bold]"


_HOSTILE = "a\x1b]0;title\x07b\x9b2Jc\x00\r"


@pytest.mark.parametrize(
    "write",
    [
        lambda text: say(text),
        lambda text: out().print(Text(text)),
        lambda text: err().print(table(["name"], [[text]])),
        lambda text: out().print(kv({"branch": text})),
    ],
    ids=["say", "text", "table", "kv"],
)
def test_control_characters_never_reach_the_terminal(
    capfd: pytest.CaptureFixture[str], write: Callable[[str], None]
) -> None:
    """Escape sequences in stored names print as stand-ins, and the rest of the text prints."""
    write(_HOSTILE + "\tend")
    printed = "".join(capfd.readouterr())
    assert not any(ch in printed for ch in "\x1b\x07\x9b\x00\r")
    assert CONTROL_STAND_IN in printed
    assert "end" in printed


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
