"""Tests for the spot-check rate setting and roll."""

from pathlib import Path

import pytest

from gate_cache.config import MAX_WHOLE_NUMBER
from gate_cache.spot_check import (
    CONFIG_KEY,
    DEFAULT_ONE_RUN_IN,
    SPOT_CHECK_ENV,
    decide,
    one_run_in,
)
from tests.conftest import write_config

Dirs = tuple[Path, Path]


def test_one_run_in_precedence(stats_dirs: Dirs, monkeypatch: pytest.MonkeyPatch) -> None:
    """The environment beats the config file, which beats the default."""
    monkeypatch.delenv(SPOT_CHECK_ENV, raising=False)
    assert one_run_in() == DEFAULT_ONE_RUN_IN
    write_config(stats_dirs[0], f"{CONFIG_KEY} = 20\n")
    assert one_run_in() == 20
    assert one_run_in({SPOT_CHECK_ENV: "10"}) == 10
    assert one_run_in({SPOT_CHECK_ENV: "  "}) == 20


def test_huge_config_value_is_capped_silently(
    stats_dirs: Dirs, capsys: pytest.CaptureFixture[str]
) -> None:
    """A config integer past the cap is capped without a warning."""
    write_config(stats_dirs[0], f"{CONFIG_KEY} = 99999999999999999999999\n")
    assert one_run_in({}) == MAX_WHOLE_NUMBER
    assert capsys.readouterr().err == ""


@pytest.mark.parametrize(
    ("env", "config", "expected", "named"),
    [
        ("abc", "", DEFAULT_ONE_RUN_IN, SPOT_CHECK_ENV),
        ("1/50", "", DEFAULT_ONE_RUN_IN, SPOT_CHECK_ENV),
        ("abc", f"{CONFIG_KEY} = 20", 20, SPOT_CHECK_ENV),
        ("", f"{CONFIG_KEY} = true", DEFAULT_ONE_RUN_IN, CONFIG_KEY),
        ("", f"{CONFIG_KEY} = 2.5", DEFAULT_ONE_RUN_IN, CONFIG_KEY),
        ("", f"{CONFIG_KEY} = -3", DEFAULT_ONE_RUN_IN, CONFIG_KEY),
        ("", f'{CONFIG_KEY} = "50"', DEFAULT_ONE_RUN_IN, CONFIG_KEY),
    ],
)
def test_invalid_values_warn_and_fall_back(
    stats_dirs: Dirs,
    capsys: pytest.CaptureFixture[str],
    env: str,
    config: str,
    expected: int,
    named: str,
) -> None:
    """An invalid value warns, naming its key, and the next source applies."""
    write_config(stats_dirs[0], f"{config}\n")
    assert one_run_in({SPOT_CHECK_ENV: env}) == expected
    err = capsys.readouterr().err
    assert "warning:" in err
    assert named in err


@pytest.mark.parametrize(
    ("n", "roll", "due"),
    [(50, 0.019, True), (50, 0.02, False), (0, 0.0, False), (1, 0.999, True)],
)
def test_decide_rolls_against_rate(n: int, roll: float, due: bool) -> None:
    """A run is due when the roll falls below 1/N, and never when N is 0."""
    result = decide(forced=False, environ={SPOT_CHECK_ENV: str(n)}, chance=lambda: roll)
    assert result.due is due
    assert result.forced is False
    assert result.one_run_in == n


def test_decide_forced_ignores_rate(capsys: pytest.CaptureFixture[str]) -> None:
    """The flag makes a run due without reading the setting, so a bad value never warns."""
    result = decide(forced=True, environ={SPOT_CHECK_ENV: "abc"}, chance=lambda: 0.999)
    assert result.due is True
    assert result.forced is True
    assert capsys.readouterr().err == ""
