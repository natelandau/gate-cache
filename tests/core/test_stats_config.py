"""Tests for the stats setting."""

import os
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest
from platformdirs import user_state_path

from gate_cache.config import config_path
from gate_cache.spot_check import CONFIG_KEY
from gate_cache.stats.config import (
    DATA_DIR_ENV,
    ConfigError,
    StatsSetting,
    state_dir,
    stats_setting,
    write_enabled,
)

Dirs = tuple[Path, Path]


def _write(dirs: Dirs, text: str) -> None:
    dirs[0].parent.mkdir(parents=True, exist_ok=True)
    dirs[0].write_text(text, encoding="utf-8")


def test_default_is_off(stats_dirs: Dirs) -> None:
    """Without any setting, recording is off."""
    assert stats_setting({}) == StatsSetting(enabled=False, source="default")


def test_config_turns_on(stats_dirs: Dirs) -> None:
    """The config file can turn recording on."""
    _write(stats_dirs, "stats_enabled = true\n")
    assert stats_setting({}) == StatsSetting(enabled=True, source="config")


def test_env_overrides_config(stats_dirs: Dirs) -> None:
    """GATE_CACHE_STATS beats the config file in both directions."""
    _write(stats_dirs, "stats_enabled = true\n")
    assert stats_setting({"GATE_CACHE_STATS": "0"}) == StatsSetting(enabled=False, source="env")
    _write(stats_dirs, "stats_enabled = false\n")
    assert stats_setting({"GATE_CACHE_STATS": "1"}) == StatsSetting(enabled=True, source="env")


def test_ci_forces_off_unless_env(stats_dirs: Dirs) -> None:
    """CI turns recording off unless GATE_CACHE_STATS is set."""
    _write(stats_dirs, "stats_enabled = true\n")
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
    _write(stats_dirs, 'stats_enabled = "yes"\n')
    assert stats_setting({}) == StatsSetting(enabled=False, source="default")


@pytest.mark.parametrize("enabled", [True, False])
def test_write_enabled_creates_file(stats_dirs: Dirs, enabled: bool) -> None:
    """A created file activates only `stats_enabled`; every other setting is commented out."""
    write_enabled(enabled=enabled)
    assert tomllib.loads(stats_dirs[0].read_text()) == {"stats_enabled": enabled}


def test_created_file_lists_every_setting(stats_dirs: Dirs) -> None:
    """The created file names every top-level key that gate-cache reads."""
    write_enabled(enabled=True)
    text = stats_dirs[0].read_text()
    keys = ["stats_enabled", "stats_data_dir", "wait_timeout", "wait_on_failure", CONFIG_KEY]
    assert [key for key in keys if key not in text] == []


def test_write_enabled_keeps_comments_and_tables(stats_dirs: Dirs) -> None:
    """Writing keeps comments and tables as they were."""
    _write(stats_dirs, "# mine\n[other]\nx = 1\n")
    write_enabled(enabled=True)
    assert stats_dirs[0].read_text() == "stats_enabled = true\n# mine\n[other]\nx = 1\n"


def test_write_enabled_replaces_the_line_in_place(stats_dirs: Dirs) -> None:
    """An existing top-level key is replaced where it stands."""
    _write(stats_dirs, "a = 1\nstats_enabled = false\nb = 2\n")
    write_enabled(enabled=True)
    assert stats_dirs[0].read_text() == "a = 1\nstats_enabled = true\nb = 2\n"


@pytest.mark.parametrize(
    "content",
    [
        "wait_timeout = 5\n[tool]\nx = 1\n",
        "[other]\nstats_enabled = false\n",
        "rows = [\n  [1, 2],\n  [3, 4],\n]\nstats_enabled = false\n",
    ],
)
def test_write_enabled_sets_the_top_level_key(stats_dirs: Dirs, content: str) -> None:
    """The key lands at the top level, never inside a table or in place of a table's key."""
    _write(stats_dirs, content)
    write_enabled(enabled=True)
    assert tomllib.loads(stats_dirs[0].read_text())["stats_enabled"] is True


def test_write_enabled_refuses_invalid_toml(stats_dirs: Dirs) -> None:
    """A file that is not valid TOML is refused and left untouched."""
    _write(stats_dirs, "[stats\n")
    with pytest.raises(ConfigError):
        write_enabled(enabled=True)
    assert stats_dirs[0].read_text() == "[stats\n"


def test_write_enabled_refuses_non_utf8(stats_dirs: Dirs) -> None:
    """A file that is not UTF-8 is refused and left untouched."""
    stats_dirs[0].parent.mkdir(parents=True)
    stats_dirs[0].write_bytes(b"\xff\xfe")
    with pytest.raises(ConfigError):
        write_enabled(enabled=True)
    assert stats_dirs[0].read_bytes() == b"\xff\xfe"


def test_whitespace_env_counts_as_unset(stats_dirs: Dirs) -> None:
    """A blank GATE_CACHE_STATS does not override the config file."""
    _write(stats_dirs, "stats_enabled = true\n")
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
    assert tomllib.loads(target.read_text())["stats_enabled"] is True


def test_write_enabled_keeps_the_file_mode(stats_dirs: Dirs) -> None:
    """An existing file keeps its permissions."""
    _write(stats_dirs, "[other]\nx = 1\n")
    stats_dirs[0].chmod(0o640)
    write_enabled(enabled=True)
    assert stats_dirs[0].stat().st_mode & 0o777 == 0o640


def _write_config(text: str) -> Path:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_data_dir_env_beats_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """GATE_CACHE_DATA_DIR wins over `stats_data_dir` and the default."""
    _write_config(f'stats_data_dir = "{tmp_path / "from-config"}"\n')
    monkeypatch.setenv(DATA_DIR_ENV, str(tmp_path / "from-env"))
    assert state_dir() == tmp_path / "from-env"


def test_data_dir_env_expands_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A leading ~ in GATE_CACHE_DATA_DIR expands to HOME."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv(DATA_DIR_ENV, "~/stats")
    assert state_dir() == tmp_path / "home" / "stats"


def test_data_dir_env_relative_uses_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A relative GATE_CACHE_DATA_DIR resolves against the current directory."""
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    monkeypatch.setenv(DATA_DIR_ENV, "stats")
    assert state_dir() == work.resolve() / "stats"


def test_data_dir_from_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`stats_data_dir` moves the data when GATE_CACHE_DATA_DIR is unset."""
    monkeypatch.delenv(DATA_DIR_ENV)
    _write_config(f'stats_data_dir = "{tmp_path / "from-config"}"\n')
    assert state_dir() == tmp_path / "from-config"


def test_data_dir_config_relative_uses_config_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A relative `stats_data_dir` resolves against the config file's directory, not the cwd."""
    monkeypatch.delenv(DATA_DIR_ENV)
    monkeypatch.chdir(tmp_path)
    path = _write_config('stats_data_dir = "stats"\n')
    assert state_dir() == path.parent / "stats"


def test_data_dir_config_expands_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A leading ~ in `stats_data_dir` expands to HOME."""
    monkeypatch.delenv(DATA_DIR_ENV)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    _write_config('stats_data_dir = "~/stats"\n')
    assert state_dir() == tmp_path / "home" / "stats"


@pytest.mark.parametrize("blank", ["", "  "])
def test_blank_data_dir_env_falls_through_to_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, blank: str
) -> None:
    """A blank GATE_CACHE_DATA_DIR counts as unset."""
    monkeypatch.setenv(DATA_DIR_ENV, blank)
    _write_config(f'stats_data_dir = "{tmp_path / "from-config"}"\n')
    assert state_dir() == tmp_path / "from-config"


@pytest.mark.parametrize(
    "content",
    [
        'stats_data_dir = ""\n',
        "stats_data_dir = 5\n",
        'stats_data_dir = ["a"]\n',
        "[stats\n",
    ],
    ids=["empty", "integer", "array", "invalid-toml"],
)
def test_unusable_data_dir_falls_through_to_default(
    monkeypatch: pytest.MonkeyPatch, content: str
) -> None:
    """An empty or non-string `stats_data_dir`, or an unreadable file, uses the default."""
    monkeypatch.delenv(DATA_DIR_ENV)
    _write_config(content)
    assert state_dir() == user_state_path("gate-cache", appauthor=False)


def test_default_data_dir_without_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """With no variable and no config file, the data lives in the platform state dir."""
    monkeypatch.delenv(DATA_DIR_ENV)
    assert not config_path().exists()
    assert state_dir() == user_state_path("gate-cache", appauthor=False)
    assert state_dir().is_relative_to(tmp_path)


def test_recorded_event_lands_in_data_dir(git_repo: Path, isolate_user_dirs: Path) -> None:
    """A gate run with recording on writes its event under GATE_CACHE_DATA_DIR."""
    script = "import sys\nfrom gate_cache.cli import main\nmain()\n"
    env = {**os.environ, "GATE_CACHE_STATS": "1"}
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-c", script, "--name", "t", "--", sys.executable, "-c", "pass"],
        cwd=git_repo,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert (isolate_user_dirs / "events.jsonl").read_text(encoding="utf-8").strip()
    assert not user_state_path("gate-cache", appauthor=False).exists()


def test_passed_environ_sets_data_dir(tmp_path: Path, isolate_user_dirs: Path) -> None:
    """A passed environment decides the data directory instead of the process one."""
    environ = {DATA_DIR_ENV: str(tmp_path / "passed")}
    assert state_dir(environ) == tmp_path / "passed"
    assert os.environ[DATA_DIR_ENV] == str(isolate_user_dirs)


def test_absolute_data_dir_env_works_from_deleted_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An absolute GATE_CACHE_DATA_DIR does not need the current directory to exist."""
    gone = tmp_path / "gone"
    gone.mkdir()
    monkeypatch.chdir(gone)
    gone.rmdir()
    monkeypatch.setenv(DATA_DIR_ENV, str(tmp_path / "data"))
    assert state_dir() == tmp_path / "data"


def test_unknown_user_tilde_is_kept_as_written(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A `~user` with no home stays literal, as a shell leaves it, instead of raising."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(DATA_DIR_ENV, "~no-such-user-gate-cache/stats")
    assert state_dir() == tmp_path.resolve() / "~no-such-user-gate-cache" / "stats"


def test_config_parsed_once_until_it_changes(
    stats_dirs: Dirs, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Repeated lookups reuse the parsed file, and an edit is picked up."""
    monkeypatch.delenv(DATA_DIR_ENV)
    _write(stats_dirs, "stats_enabled = true\nstats_data_dir = 'one'\n")
    calls: list[str] = []
    real_loads = tomllib.loads
    monkeypatch.setattr(tomllib, "loads", lambda text: calls.append(text) or real_loads(text))
    assert stats_setting({}).enabled
    assert state_dir({}) == stats_dirs[0].parent / "one"
    assert state_dir({}) == stats_dirs[0].parent / "one"
    assert len(calls) == 1
    _write(stats_dirs, "stats_enabled = false\nstats_data_dir = 'two-longer'\n")
    assert state_dir({}) == stats_dirs[0].parent / "two-longer"
    assert not stats_setting({}).enabled
    assert len(calls) == 2
