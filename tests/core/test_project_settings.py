"""Tests for per-project settings tables in the user config file."""

import json
import tomllib
from pathlib import Path

import pytest

from gate_cache.git import GitNotFoundError
from gate_cache.spot_check import SPOT_CHECK_ENV, one_run_in
from gate_cache.stats.config import DATA_DIR_ENV, StatsSetting, state_dir, stats_setting
from gate_cache.wait_settings import wait_settings
from tests.conftest import add_submodule, git, invoke, write_config

Dirs = tuple[Path, Path]
REMOTE = "github.com/acme/app"


@pytest.fixture
def repo(git_repo: Path) -> Path:
    """A repository whose origin normalizes to REMOTE."""
    git("remote", "add", "origin", "git@github.com:acme/app.git", cwd=git_repo)
    return git_repo


def test_table_overrides_top_level(stats_dirs: Dirs, repo: Path) -> None:
    """A matching table wins over the top-level key."""
    write_config(stats_dirs[0], f'wait_timeout = 5\n[projects."{REMOTE}"]\nwait_timeout = 9\n')
    assert wait_settings().timeout == 9


def test_unset_key_falls_through(stats_dirs: Dirs, repo: Path) -> None:
    """A key the table does not set comes from the top level."""
    write_config(
        stats_dirs[0], f'wait_timeout = 5\n[projects."{REMOTE}"]\nspot_check_one_run_in = 3\n'
    )
    assert wait_settings().timeout == 5


def test_env_beats_table(stats_dirs: Dirs, repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The environment variable still wins over a matching table."""
    monkeypatch.delenv(SPOT_CHECK_ENV, raising=False)
    write_config(stats_dirs[0], f'[projects."{REMOTE}"]\nspot_check_one_run_in = 3\n')
    assert one_run_in({}) == 3
    assert one_run_in({SPOT_CHECK_ENV: "7"}) == 7


@pytest.mark.parametrize(
    ("winner", "loser"),
    [
        (REMOTE, "github.com/acme/*"),
        ("github.com/acme/*", "github.com/*"),
        ("github.com/acme/*", "*"),
    ],
)
@pytest.mark.parametrize("winner_first", [True, False])
def test_most_specific_wins(
    stats_dirs: Dirs, repo: Path, winner: str, loser: str, *, winner_first: bool
) -> None:
    """The most specific matching pattern wins, whatever the order in the file."""
    tables = [
        f'[projects."{winner}"]\nwait_timeout = 1\n',
        f'[projects."{loser}"]\nwait_timeout = 2\n',
    ]
    if not winner_first:
        tables.reverse()
    write_config(stats_dirs[0], "".join(tables))
    assert wait_settings().timeout == 1


@pytest.mark.parametrize("pattern", ["{repo}", "{parent}/*"])
def test_path_pattern_matches_worktree(
    stats_dirs: Dirs, repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, pattern: str
) -> None:
    """A path pattern names the main checkout and also covers its linked worktrees."""
    text = pattern.format(repo=repo, parent=repo.parent)
    write_config(stats_dirs[0], f'[projects."{text}"]\nwait_timeout = 9\n')
    linked = tmp_path / "elsewhere" / "linked"
    git("worktree", "add", "-q", str(linked), "-b", "side", cwd=repo)
    monkeypatch.chdir(linked)
    assert wait_settings().timeout == 9


def test_tilde_pattern_matches(
    stats_dirs: Dirs, repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A leading ~ expands to the home directory."""
    monkeypatch.setenv("HOME", str(repo.parent))
    write_config(stats_dirs[0], '[projects."~/repo"]\nwait_timeout = 9\n')
    assert wait_settings().timeout == 9


def test_symlinked_pattern_matches(stats_dirs: Dirs, repo: Path, tmp_path: Path) -> None:
    """A path pattern written through a symlink matches the real checkout."""
    link = tmp_path / "link"
    link.symlink_to(repo.parent, target_is_directory=True)
    write_config(stats_dirs[0], f'[projects."{link}/*"]\nwait_timeout = 9\n')
    assert wait_settings().timeout == 9


@pytest.mark.parametrize(
    ("folder", "pattern", "matches"),
    [
        ("work [old]", "{parent}/work [old]/*", True),
        ("a?b", "{parent}/a?b/repo", True),
        ("axb", "{parent}/a?b/repo", False),
    ],
)
def test_only_star_is_a_wildcard(
    stats_dirs: Dirs,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    folder: str,
    pattern: str,
    *,
    matches: bool,
) -> None:
    """`?` and `[` in a path pattern match as written, so a folder with them in its name matches."""
    checkout = tmp_path / folder / "repo"
    checkout.mkdir(parents=True)
    git("init", "-q", cwd=checkout)
    monkeypatch.chdir(checkout)
    write_config(
        stats_dirs[0], f'[projects."{pattern.format(parent=tmp_path)}"]\nwait_timeout = 9\n'
    )
    assert (wait_settings().timeout == 9) is matches


def test_no_remote_matches_only_paths(stats_dirs: Dirs, git_repo: Path) -> None:
    """Without a remote, remote patterns never match but path patterns still do."""
    write_config(stats_dirs[0], '[projects."*"]\nwait_timeout = 1\n')
    assert wait_settings().timeout == 900
    write_config(stats_dirs[0], f'[projects."{git_repo}"]\nwait_timeout = 2\n')
    assert wait_settings().timeout == 2


def test_outside_repo_uses_top_level(
    stats_dirs: Dirs, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, git_env: Path
) -> None:
    """Outside a repository no table matches."""
    plain = tmp_path / "plain"
    plain.mkdir()
    monkeypatch.chdir(plain)
    write_config(
        stats_dirs[0], f'wait_timeout = 5\n[projects."{plain.parent}/*"]\nwait_timeout = 9\n'
    )
    assert wait_settings().timeout == 5


def test_invalid_table_value_warns_and_falls_through(
    stats_dirs: Dirs, repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """An invalid value in a table warns, naming the table, and the top level applies."""
    write_config(stats_dirs[0], f'wait_timeout = 5\n[projects."{REMOTE}"]\nwait_timeout = "soon"\n')
    assert wait_settings().timeout == 5
    err = capsys.readouterr().err
    assert f'[projects."{REMOTE}"]' in err
    assert "wait_timeout" in err


def test_unknown_key_in_matching_table_warns(
    stats_dirs: Dirs, repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A typo in a matching table warns; the same typo in a table for another repo does not."""
    write_config(stats_dirs[0], f'[projects."{REMOTE}"]\nwait_seconds = 5\n')
    wait_settings()
    assert "wait_seconds" in capsys.readouterr().err
    write_config(stats_dirs[0], '[projects."github.com/other/*"]\nwait_seconds = 5\n')
    wait_settings()
    assert capsys.readouterr().err == ""


@pytest.mark.parametrize(
    "text", ["projects = 5\n", '[projects]\n"x" = 3\n'], ids=["not-a-table", "entry-not-a-table"]
)
def test_malformed_projects_warns(
    stats_dirs: Dirs, repo: Path, capsys: pytest.CaptureFixture[str], text: str
) -> None:
    """A malformed projects entry warns, and the top-level settings still apply."""
    write_config(stats_dirs[0], "wait_timeout = 5\n" + text)
    assert wait_settings().timeout == 5
    assert "projects" in capsys.readouterr().err


def test_table_turns_stats_off(stats_dirs: Dirs, repo: Path) -> None:
    """A matching table decides the stats setting and is named as the decider."""
    write_config(
        stats_dirs[0], f'stats_enabled = true\n[projects."{REMOTE}"]\nstats_enabled = false\n'
    )
    assert stats_setting({}) == StatsSetting(enabled=False, source="config", project=REMOTE)


def test_non_bool_in_table_falls_through(stats_dirs: Dirs, repo: Path) -> None:
    """A non-boolean stats_enabled in a table falls through to the top level."""
    write_config(
        stats_dirs[0], f'stats_enabled = true\n[projects."{REMOTE}"]\nstats_enabled = "yes"\n'
    )
    assert stats_setting({}) == StatsSetting(enabled=True, source="config", project=None)


def test_table_sets_data_dir(
    stats_dirs: Dirs, repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A table's relative stats_data_dir resolves against the config file's directory."""
    monkeypatch.delenv(DATA_DIR_ENV)
    write_config(
        stats_dirs[0], f'stats_data_dir = "all"\n[projects."{REMOTE}"]\nstats_data_dir = "app"\n'
    )
    assert state_dir({}) == stats_dirs[0].parent / "app"
    assert state_dir({DATA_DIR_ENV: str(tmp_path / "env")}) == tmp_path / "env"


def test_stats_on_reports_table_override(
    stats_dirs: Dirs,
    repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """`stats on` sets the top-level key and says when a table overrides it here."""
    write_config(stats_dirs[0], f'[projects."{REMOTE}"]\nstats_enabled = false\n')
    assert invoke(monkeypatch, "stats", "on") == 0
    assert tomllib.loads(stats_dirs[0].read_text())["stats_enabled"] is True
    assert f'[projects."{REMOTE}"]' in capfd.readouterr().err
    assert invoke(monkeypatch, "stats", "--json") == 0
    data = json.loads(capfd.readouterr().out)
    assert (data["enabled"], data["decided_by"], data["project"]) == (False, "config", REMOTE)


def test_nul_in_pattern_warns_without_crashing(
    stats_dirs: Dirs, repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A pattern that no path can hold warns, and the run still gets its settings."""
    write_config(stats_dirs[0], 'wait_timeout = 5\n[projects."/x\\u0000y"]\nwait_timeout = 9\n')
    assert wait_settings().timeout == 5
    assert "projects" in capsys.readouterr().err


@pytest.mark.parametrize(
    "pattern",
    [
        "github.com/ACME/App",
        "https://github.com/acme/app.git",
        "git@github.com:acme/*",
        "github.com:acme/app",
        "github.com/acme/app.git",
    ],
)
def test_remote_pattern_forms_match(stats_dirs: Dirs, repo: Path, pattern: str) -> None:
    """A remote pattern ignores case and may be written as a clone URL."""
    write_config(stats_dirs[0], f'[projects."{pattern}"]\nwait_timeout = 9\n')
    assert wait_settings().timeout == 9


def test_submodule_matches_its_folder(
    stats_dirs: Dirs, repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A path pattern matches a submodule's own folder."""
    sub = add_submodule(repo, tmp_path)
    monkeypatch.chdir(sub)
    write_config(stats_dirs[0], f'[projects."{sub}"]\nwait_timeout = 9\n')
    assert wait_settings().timeout == 9


def test_separate_git_dir_matches_its_folder(
    stats_dirs: Dirs, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, git_env: Path
) -> None:
    """A path pattern matches a checkout whose git directory lives elsewhere."""
    checkout = tmp_path / "checkout"
    git("init", "-q", "--separate-git-dir", str(tmp_path / "gitdir"), str(checkout), cwd=tmp_path)
    monkeypatch.chdir(checkout)
    write_config(stats_dirs[0], f'[projects."{checkout}"]\nwait_timeout = 9\n')
    assert wait_settings().timeout == 9


@pytest.mark.parametrize(("key", "value"), [("stats_enabled", '"no"'), ("stats_data_dir", "5")])
def test_invalid_stats_value_in_table_warns(
    stats_dirs: Dirs, repo: Path, capsys: pytest.CaptureFixture[str], key: str, value: str
) -> None:
    """A wrong-type stats key in a table warns, naming the table."""
    write_config(stats_dirs[0], f'[projects."{REMOTE}"]\n{key} = {value}\n')
    stats_setting({})
    state_dir({DATA_DIR_ENV: ""})
    err = capsys.readouterr().err
    assert key in err
    assert f'[projects."{REMOTE}"]' in err


def test_invalid_value_warns_once(
    stats_dirs: Dirs, repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Reading a setting again does not repeat its warning."""
    write_config(stats_dirs[0], f'[projects."{REMOTE}"]\nstats_enabled = "no"\n')
    stats_setting({})
    stats_setting({})
    assert capsys.readouterr().err.count("stats_enabled") == 1


def test_tilde_pattern_ranks_as_its_full_path(
    stats_dirs: Dirs, repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A ~ pattern ranks the same as the full path it names."""
    monkeypatch.setenv("HOME", str(repo.parent))
    long_remote = "github.com/acme/a*"
    assert len(long_remote) - 1 < len(f"{repo.parent}/r*") - 1
    write_config(
        stats_dirs[0],
        f'[projects."~/r*"]\nwait_timeout = 1\n[projects."{long_remote}"]\nwait_timeout = 2\n',
    )
    assert wait_settings().timeout == 1


def test_identity_follows_a_new_remote(stats_dirs: Dirs, git_repo: Path) -> None:
    """A process that keeps running sees a remote added after its first lookup."""
    write_config(stats_dirs[0], f'[projects."{REMOTE}"]\nwait_timeout = 9\n')
    assert wait_settings().timeout == 900
    git("remote", "add", "origin", "git@github.com:acme/app.git", cwd=git_repo)
    assert wait_settings().timeout == 9


def test_unknown_user_pattern_warns(
    stats_dirs: Dirs, repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A ~user pattern for a user that does not exist warns."""
    write_config(stats_dirs[0], '[projects."~no-such-user-xyz/x"]\nwait_timeout = 9\n')
    assert wait_settings().timeout == 900
    assert "~no-such-user-xyz" in capsys.readouterr().err


def test_bare_repo_pattern_matches_its_worktrees(
    stats_dirs: Dirs, repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A folder pattern naming a bare repository covers every worktree made from it."""
    bare = tmp_path / "app.git"
    git("clone", "-q", "--bare", str(repo), str(bare), cwd=tmp_path)
    linked = tmp_path / "app" / "feature"
    git("worktree", "add", "-q", str(linked), "-b", "feature", cwd=bare)
    monkeypatch.chdir(linked)
    write_config(stats_dirs[0], f'[projects."{bare}"]\nwait_timeout = 9\n')
    assert wait_settings().timeout == 9


@pytest.mark.parametrize(
    "error", [UnicodeDecodeError("utf-8", b"\xff", 0, 1, "bad"), GitNotFoundError("git")]
)
def test_checkout_lookup_failure_falls_back(
    stats_dirs: Dirs,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    git_env: Path,
    error: Exception,
) -> None:
    """When git cannot name the checkout, the git folder still matches and nothing crashes."""
    checkout = tmp_path / "checkout"
    gitdir = tmp_path / "gitdir"
    git("init", "-q", "--separate-git-dir", str(gitdir), str(checkout), cwd=tmp_path)
    monkeypatch.chdir(checkout)

    def fail(*_args: object, **_kwargs: object) -> object:
        raise error

    monkeypatch.setattr("gate_cache.config.run_git", fail)
    write_config(stats_dirs[0], f'wait_timeout = 5\n[projects."{gitdir}"]\nwait_timeout = 9\n')
    assert wait_settings().timeout == 9
