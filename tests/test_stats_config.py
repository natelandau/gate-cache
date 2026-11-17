"""Tests for the stats setting."""

import tomllib
from pathlib import Path

import pytest

from gate_cache.stats.config import ConfigError, StatsSetting, stats_setting, write_enabled

Dirs = tuple[Path, Path]


def _write(dirs: Dirs, text: str) -> None:
    dirs[0].parent.mkdir(parents=True, exist_ok=True)
    dirs[0].write_text(text, encoding="utf-8")


def test_default_is_off(stats_dirs: Dirs) -> None:
    """Without any setting, recording is off."""
    assert stats_setting({}) == StatsSetting(enabled=False, source="default")


def test_config_turns_on(stats_dirs: Dirs) -> None:
    """The config file can turn recording on."""
    _write(stats_dirs, "[stats]\nenabled = true\n")
    assert stats_setting({}) == StatsSetting(enabled=True, source="config")


def test_env_overrides_config(stats_dirs: Dirs) -> None:
    """GATE_CACHE_STATS beats the config file in both directions."""
    _write(stats_dirs, "[stats]\nenabled = true\n")
    assert stats_setting({"GATE_CACHE_STATS": "0"}) == StatsSetting(enabled=False, source="env")
    _write(stats_dirs, "[stats]\nenabled = false\n")
    assert stats_setting({"GATE_CACHE_STATS": "1"}) == StatsSetting(enabled=True, source="env")


def test_ci_forces_off_unless_env(stats_dirs: Dirs) -> None:
    """CI turns recording off unless GATE_CACHE_STATS is set."""
    _write(stats_dirs, "[stats]\nenabled = true\n")
    assert stats_setting({"CI": "true"}) == StatsSetting(enabled=False, source="ci")
    assert stats_setting({"CI": "true", "GATE_CACHE_STATS": "1"}) == StatsSetting(
        enabled=True, source="env"
    )


def test_invalid_toml_is_off(stats_dirs: Dirs) -> None:
    """A config file that is not valid TOML leaves recording off."""
    _write(stats_dirs, "[stats\n")
    assert stats_setting({}) == StatsSetting(enabled=False, source="default")


def test_non_bool_is_off(stats_dirs: Dirs) -> None:
    """A non-boolean value leaves recording off."""
    _write(stats_dirs, '[stats]\nenabled = "yes"\n')
    assert stats_setting({}) == StatsSetting(enabled=False, source="default")


def test_write_enabled_creates_file(stats_dirs: Dirs) -> None:
    """Writing creates the config file and its directory."""
    write_enabled(enabled=True)
    assert tomllib.loads(stats_dirs[0].read_text())["stats"]["enabled"] is True


def test_write_enabled_creates_and_preserves(stats_dirs: Dirs) -> None:
    """Writing keeps comments and other tables."""
    _write(stats_dirs, "# mine\n[other]\nx = 1\n")
    write_enabled(enabled=True)
    text = stats_dirs[0].read_text()
    assert "# mine" in text
    assert "x = 1" in text
    assert tomllib.loads(text)["stats"]["enabled"] is True
    write_enabled(enabled=False)
    assert tomllib.loads(stats_dirs[0].read_text())["stats"]["enabled"] is False


def test_write_enabled_edits_inside_existing_table(stats_dirs: Dirs) -> None:
    """Writing edits the stats table, not a same-named key elsewhere."""
    _write(stats_dirs, "[stats]\nother = 2\n[x]\nenabled = 5\n")
    write_enabled(enabled=True)
    data = tomllib.loads(stats_dirs[0].read_text())
    assert data == {"stats": {"enabled": True, "other": 2}, "x": {"enabled": 5}}


@pytest.mark.parametrize("header", ["[stats]  # note", "[ stats ]", "  [stats]"])
def test_write_enabled_accepts_header_variants(stats_dirs: Dirs, header: str) -> None:
    """Whitespace and a trailing comment on the table header still match."""
    _write(stats_dirs, f"{header}\nenabled = false\n")
    write_enabled(enabled=True)
    assert tomllib.loads(stats_dirs[0].read_text())["stats"]["enabled"] is True


@pytest.mark.parametrize(
    "content",
    [
        "stats.enabled = false\n",
        "stats = {enabled = false}\n",
        '[stats]\n"enabled" = false\n',
        "[stats\n",
    ],
)
def test_write_enabled_refuses_what_it_cannot_edit(stats_dirs: Dirs, content: str) -> None:
    """A file the line editor cannot handle is refused and left untouched."""
    _write(stats_dirs, content)
    with pytest.raises(ConfigError):
        write_enabled(enabled=True)
    assert stats_dirs[0].read_text() == content


def test_write_enabled_refuses_non_utf8(stats_dirs: Dirs) -> None:
    """A file that is not UTF-8 is refused and left untouched."""
    stats_dirs[0].parent.mkdir(parents=True)
    stats_dirs[0].write_bytes(b"\xff\xfe")
    with pytest.raises(ConfigError):
        write_enabled(enabled=True)
    assert stats_dirs[0].read_bytes() == b"\xff\xfe"


def test_whitespace_env_counts_as_unset(stats_dirs: Dirs) -> None:
    """A blank GATE_CACHE_STATS does not override the config file."""
    _write(stats_dirs, "[stats]\nenabled = true\n")
    assert stats_setting({"GATE_CACHE_STATS": "  "}) == StatsSetting(enabled=True, source="config")


def test_write_enabled_follows_a_symlink(stats_dirs: Dirs, tmp_path: Path) -> None:
    """A symlinked config stays a link and its target is updated."""
    target = tmp_path / "dotfiles" / "real.toml"
    target.parent.mkdir()
    target.write_text("[other]\nx = 1\n")
    stats_dirs[0].parent.mkdir(parents=True)
    stats_dirs[0].symlink_to(target)
    write_enabled(enabled=True)
    assert stats_dirs[0].is_symlink()
    assert tomllib.loads(target.read_text())["stats"]["enabled"] is True


def test_write_enabled_keeps_the_file_mode(stats_dirs: Dirs) -> None:
    """An existing file keeps its permissions."""
    _write(stats_dirs, "[other]\nx = 1\n")
    stats_dirs[0].chmod(0o640)
    write_enabled(enabled=True)
    assert stats_dirs[0].stat().st_mode & 0o777 == 0o640
