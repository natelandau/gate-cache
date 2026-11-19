"""Tests for user-facing messages."""

import pytest

from gate_cache.console import format_duration, say


def test_say_prints_prefixed_verbatim_to_stderr(capfd: pytest.CaptureFixture[str]) -> None:
    """Brackets print verbatim with the prefix, on stderr only."""
    say("unit [fast] [bold]x[/bold]")
    out, err = capfd.readouterr()
    assert out == ""
    assert err.strip() == "gate-cache: unit [fast] [bold]x[/bold]"


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
