"""Tests for the wait settings."""

from pathlib import Path

import pytest

from gate_cache.config import MAX_WHOLE_NUMBER, parse_whole_number
from gate_cache.wait_settings import (
    WaitSettings,
    parse_failed,
    wait_settings,
)

Dirs = tuple[Path, Path]
CONFIG = 'wait_timeout = 60\nwait_on_failure = "report"\n'


def _write(dirs: Dirs, text: str) -> None:
    dirs[0].parent.mkdir(parents=True, exist_ok=True)
    dirs[0].write_text(text, encoding="utf-8")


def test_defaults_without_config(stats_dirs: Dirs) -> None:
    """Without a config file the defaults apply."""
    assert wait_settings() == WaitSettings(900, "rerun")


def test_config_values_used(stats_dirs: Dirs) -> None:
    """The flat wait keys set both values."""
    _write(stats_dirs, CONFIG)
    assert wait_settings() == WaitSettings(60, "report")


def test_flags_override_config(stats_dirs: Dirs) -> None:
    """Flag values win over the config file."""
    _write(stats_dirs, CONFIG)
    assert wait_settings(timeout=0, failed="rerun") == WaitSettings(0, "rerun")


@pytest.mark.parametrize(
    ("line", "key"),
    [
        ("wait_timeout = -1", "wait_timeout"),
        ('wait_timeout = "x"', "wait_timeout"),
        ("wait_timeout = 1.5", "wait_timeout"),
        ("wait_timeout = true", "wait_timeout"),
        ('wait_on_failure = "skip"', "wait_on_failure"),
    ],
)
def test_invalid_config_warns_and_defaults(
    stats_dirs: Dirs, capsys: pytest.CaptureFixture[str], line: str, key: str
) -> None:
    """An invalid value warns and falls back to the default."""
    _write(stats_dirs, f"{line}\n")
    assert wait_settings() == WaitSettings(900, "rerun")
    err = capsys.readouterr().err
    assert "warning:" in err
    assert key in err


def test_invalid_config_ignored_when_flag_given(
    stats_dirs: Dirs, capsys: pytest.CaptureFixture[str]
) -> None:
    """A flag skips reading the config value, so no warning appears."""
    _write(stats_dirs, "wait_timeout = -1\n")
    assert wait_settings(timeout=5).timeout == 5
    assert capsys.readouterr().err == ""


def test_invalid_toml_uses_defaults_silently(
    stats_dirs: Dirs, capsys: pytest.CaptureFixture[str]
) -> None:
    """A file that is not valid TOML never warns or fails."""
    _write(stats_dirs, "not = [valid")
    assert wait_settings() == WaitSettings(900, "rerun")
    assert capsys.readouterr().err == ""


def test_old_tables_are_ignored(stats_dirs: Dirs, capsys: pytest.CaptureFixture[str]) -> None:
    """The old `[wait]` table sets nothing and warns of nothing."""
    _write(stats_dirs, "[wait]\ntimeout = 5\n")
    assert wait_settings() == WaitSettings()
    assert capsys.readouterr().err == ""


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("0", 0),
        ("50", 50),
        ("900", 900),
        (" 7 ", 7),
        ("0" * 50 + "7", 7),
        (str(10**12), 10**12),
        ("-1", None),
        ("1.5", None),
        ("1/50", None),
        ("abc", None),
        ("", None),
        ("9" * 40, MAX_WHOLE_NUMBER),
        ("9" * 400, MAX_WHOLE_NUMBER),
        ("9" * 5000, MAX_WHOLE_NUMBER),
        (str(MAX_WHOLE_NUMBER + 1), MAX_WHOLE_NUMBER),
    ],
)
def test_parse_whole_number(text: str, expected: int | None) -> None:
    """Only a non-negative whole number parses, ignoring padding, and a huge one is capped."""
    assert parse_whole_number(text) == expected


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
    _write(stats_dirs, "extra = 1\nwait_timeout = 7\n")
    assert wait_settings() == WaitSettings(7, "rerun")
    assert capsys.readouterr().err == ""


def test_huge_timeout_accepted(stats_dirs: Dirs) -> None:
    """A very large integer is kept as written."""
    _write(stats_dirs, f"wait_timeout = {10**12}\n")
    assert wait_settings().timeout == 10**12
