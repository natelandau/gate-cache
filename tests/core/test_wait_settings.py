"""Tests for the wait settings."""

from pathlib import Path

import pytest

from gate_cache.wait_settings import (
    MAX_WAIT_TIMEOUT,
    WaitSettings,
    parse_failed,
    parse_timeout,
    wait_settings,
)

Dirs = tuple[Path, Path]
CONFIG = '[wait]\ntimeout = 60\nfailed = "report"\n'


def _write(dirs: Dirs, text: str) -> None:
    dirs[0].parent.mkdir(parents=True, exist_ok=True)
    dirs[0].write_text(text, encoding="utf-8")


def test_defaults_without_config(stats_dirs: Dirs) -> None:
    """Without a config file the defaults apply."""
    assert wait_settings() == WaitSettings(900, "rerun")


def test_config_values_used(stats_dirs: Dirs) -> None:
    """The `[wait]` table sets both values."""
    _write(stats_dirs, CONFIG)
    assert wait_settings() == WaitSettings(60, "report")


def test_flags_override_config(stats_dirs: Dirs) -> None:
    """Flag values win over the config file."""
    _write(stats_dirs, CONFIG)
    assert wait_settings(timeout=0, failed="rerun") == WaitSettings(0, "rerun")


@pytest.mark.parametrize(
    ("line", "key"),
    [
        ("timeout = -1", "timeout"),
        ('timeout = "x"', "timeout"),
        ("timeout = 1.5", "timeout"),
        ("timeout = true", "timeout"),
        ('failed = "skip"', "failed"),
    ],
)
def test_invalid_config_warns_and_defaults(
    stats_dirs: Dirs, capsys: pytest.CaptureFixture[str], line: str, key: str
) -> None:
    """An invalid value warns and falls back to the default."""
    _write(stats_dirs, f"[wait]\n{line}\n")
    assert wait_settings() == WaitSettings(900, "rerun")
    err = capsys.readouterr().err
    assert "warning:" in err
    assert key in err


def test_invalid_config_ignored_when_flag_given(
    stats_dirs: Dirs, capsys: pytest.CaptureFixture[str]
) -> None:
    """A flag skips reading the config value, so no warning appears."""
    _write(stats_dirs, "[wait]\ntimeout = -1\n")
    assert wait_settings(timeout=5).timeout == 5
    assert capsys.readouterr().err == ""


@pytest.mark.parametrize("text", ["not = [valid", "wait = 3\n"])
def test_unreadable_or_invalid_toml_uses_defaults_silently(
    stats_dirs: Dirs, capsys: pytest.CaptureFixture[str], text: str
) -> None:
    """A broken file or table never warns or fails."""
    _write(stats_dirs, text)
    assert wait_settings() == WaitSettings(900, "rerun")
    assert capsys.readouterr().err == ""


@pytest.mark.parametrize(
    ("text", "expected"),
    [("0", 0), ("900", 900), ("-1", None), ("1.5", None), ("x", None), ("", None)],
)
def test_parse_timeout(text: str, expected: int | None) -> None:
    """Only non-negative whole numbers parse."""
    assert parse_timeout(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("rerun", "rerun"),
        (" report\n", "report"),
        ("report", "report"),
        ("skip", None),
        ("", None),
        ("Rerun", None),
    ],
)
def test_parse_failed(text: str, expected: str | None) -> None:
    """Only `rerun` and `report` parse."""
    assert parse_failed(text) == expected


def test_flag_and_config_combine(stats_dirs: Dirs) -> None:
    """A flag for one key leaves the other key to the config file."""
    _write(stats_dirs, CONFIG)
    assert wait_settings(timeout=5) == WaitSettings(5, "report")
    assert wait_settings(failed="rerun") == WaitSettings(60, "rerun")


def test_unknown_keys_ignored_silently(
    stats_dirs: Dirs, capsys: pytest.CaptureFixture[str]
) -> None:
    """Keys the settings do not know never warn."""
    _write(stats_dirs, "[wait]\nextra = 1\ntimeout = 7\n")
    assert wait_settings() == WaitSettings(7, "rerun")
    assert capsys.readouterr().err == ""


def test_huge_timeout_accepted(stats_dirs: Dirs) -> None:
    """A very large integer is kept as written."""
    _write(stats_dirs, f"[wait]\ntimeout = {10**12}\n")
    assert wait_settings().timeout == 10**12
    assert parse_timeout(str(10**12)) == 10**12


@pytest.mark.parametrize("text", ["9" * 400, "9" * 5000, str(MAX_WAIT_TIMEOUT + 1)])
def test_oversized_timeout_capped(text: str) -> None:
    """Verify a timeout too large for the clock is capped instead of crashing."""
    assert parse_timeout(text) == MAX_WAIT_TIMEOUT


def test_padded_timeout_parsed() -> None:
    """Verify leading zeros do not count toward the size cap."""
    assert parse_timeout("0" * 50 + "7") == 7
