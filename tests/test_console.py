"""Tests for user-facing messages."""

import pytest

from gate_cache.console import say


def test_say_prints_prefixed_verbatim_to_stderr(capfd: pytest.CaptureFixture[str]) -> None:
    """Brackets print verbatim with the prefix, on stderr only."""
    say("unit [fast] [bold]x[/bold]")
    out, err = capfd.readouterr()
    assert out == ""
    assert err.strip() == "gate-cache: unit [fast] [bold]x[/bold]"
