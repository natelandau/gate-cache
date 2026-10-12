"""Tests for user-facing messages."""

import io

import pytest

from gate_cache.console import kv, say


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
