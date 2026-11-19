"""Tests for the subcommands served by the cyclopts app."""

import json
import re
import shlex
import sqlite3
import sys
import time
from collections.abc import Callable, Generator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from gate_cache import gate as gate_module
from gate_cache.cli import NO_COMMAND
from gate_cache.commands import status as status_module
from gate_cache.commands.app import _report_first
from gate_cache.commands.clear import NOT_A_REPO
from gate_cache.commands.dashboard import RECORDING_OFF
from gate_cache.commands.output import UsageError, require_yes_for_json
from gate_cache.commands.stats import ALL_REPOS_CONFLICT, NAME_NEEDS_REPO
from gate_cache.commands.status import (
    NAME_OR_COMMAND,
    NEEDS_SEPARATOR,
    NO_GATES,
    PATH_NEEDS_NAME,
    PATH_NEEDS_VALUE,
    StatusOutcome,
)
from gate_cache.git import git_common_dir
from gate_cache.markers import marker_dir
from gate_cache.stats import report as report_module
from gate_cache.stats.archive import ARCHIVE_NAME, Archive, ArchiveVersionError, archive_path
from gate_cache.stats.lock import InstanceLock
from gate_cache.stats.report_text import (
    AMBIGUOUS_REPO,
    KEYED_NAME_ERROR,
    RECORDING_OFF_HINT,
    REPORT_HINT,
    UNKNOWN_GATE,
    UNKNOWN_REPO,
)
from gate_cache.stats.window import DURATION_ERROR, UNTIL_ERROR
from tests.conftest import REPO_A, REPO_B, Counter, insert, invoke, markers, rendered_text

DISABLED_REASON = "caching disabled by GATE_CACHE_DISABLE"


def _mock_status(monkeypatch: pytest.MonkeyPatch, *, code: int = 0) -> MagicMock:
    """Replace the gate lookup with a mock that reports an empty listing."""
    status = MagicMock(
        return_value=(
            {"enabled": True, "tree": "t", "reason": None, "passed": [], "missed": []},
            code,
        )
    )
    monkeypatch.setattr(status_module, "gate_status", status)
    return status


def test_status_finds_a_pass_recorded_under_the_default_name(
    git_repo: Path, counter: Counter, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify status --name with the quoted command reports a pass recorded without --name."""
    assert invoke(monkeypatch, "--", *counter.argv()) == 0
    assert invoke(monkeypatch, "status", "--name", shlex.join(counter.argv())) == 0


def test_status_command_finds_a_pass_recorded_under_the_default_name(
    git_repo: Path, counter: Counter, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify status -- COMMAND looks up the gate that the same command ran without --name."""
    assert invoke(monkeypatch, "status", "--", *counter.argv()) == 1
    assert invoke(monkeypatch, "--", *counter.argv()) == 0
    assert invoke(monkeypatch, "status", "--", *counter.argv()) == 0
    assert counter.count == 1


def test_status_command_passes_options(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify status -- COMMAND joins the command as the name and keeps --path and --json."""
    status = _mock_status(monkeypatch)
    args = ["status", "--json", "--path", "a", "--", "uv", "run", "ruff", "check", "."]
    assert invoke(monkeypatch, *args) == 0
    status.assert_called_once_with("uv run ruff check .", paths=["a"])


def test_status_json_after_separator_is_part_of_the_command(
    monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    """Verify a --json after -- names the gate and leaves the output human."""
    status = _mock_status(monkeypatch)
    assert invoke(monkeypatch, "status", "--", "tool", "--json") == 0
    status.assert_called_once_with("tool --json", paths=[])
    with pytest.raises(json.JSONDecodeError):
        json.loads(capfd.readouterr().out)


def test_status_without_name_lists_gates(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify status with no --name asks for the list of passed gates."""
    status = _mock_status(monkeypatch)
    assert invoke(monkeypatch, "status") == 0
    status.assert_called_once_with(None, paths=[])


def test_status_passes_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify status forwards repeated --path values with --name."""
    status = _mock_status(monkeypatch)
    assert invoke(monkeypatch, "status", "--name", "x", "--path", "a", "--path", "b") == 0
    status.assert_called_once_with("x", paths=["a", "b"])


@pytest.mark.parametrize(
    ("disabled", "args"),
    [(False, []), (False, ["--name", "x"]), (True, []), (True, ["--name", "x"])],
)
def test_status_json_carries_the_schema_first(
    git_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
    *,
    disabled: bool,
    args: list[str],
) -> None:
    """Verify every status --json shape starts with the schema version and prints nothing else."""
    if disabled:
        monkeypatch.setenv("GATE_CACHE_DISABLE", "1")
    assert invoke(monkeypatch, "status", *args, "--json") == 1
    captured = capfd.readouterr()
    data = json.loads(captured.out)
    assert next(iter(data)) == "schema"
    assert data["schema"] == 1
    assert captured.err == ""


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (["status", "--name", "x", "--", "pytest"], NAME_OR_COMMAND),
        (["status", "--"], NO_COMMAND),
        (["status", "--name", "a", "--name", "b"], "--name"),
        (["status", "--path", "a"], PATH_NEEDS_NAME),
        (["status", "--name", "x", "--path", ""], PATH_NEEDS_VALUE),
        (["status", "--bogus"], "--bogus"),
        (["status", "--name"], "--name"),
        (["status", "true"], NEEDS_SEPARATOR),
        (["status", "--name", "x", "--path", "a", "b"], NEEDS_SEPARATOR),
    ],
)
def test_status_usage_errors(
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
    args: list[str],
    message: str,
) -> None:
    """Verify a malformed status line exits 2, names the problem, and looks nothing up."""
    status = _mock_status(monkeypatch)
    assert invoke(monkeypatch, *args) == 2
    status.assert_not_called()
    assert message in capfd.readouterr().err


def test_status_usage_error_json(
    monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    """Verify --json turns a usage error into an error object on stdout."""
    assert invoke(monkeypatch, "status", "--name", "a", "--name", "b", "--json") == 2
    data = json.loads(capfd.readouterr().out)
    assert "--name" in data["error"]["message"]


def test_status_shows_markup_literally(
    git_repo: Path,
    counter: Counter,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """Verify a gate name that looks like rich markup prints as written."""
    assert invoke(monkeypatch, "--name", "pytest[unit]", "--", *counter.argv()) == 0
    capfd.readouterr()
    assert invoke(monkeypatch, "status", "--name", "pytest[unit]") == 0
    assert "pytest[unit]" in capfd.readouterr().out


def test_status_when_disabled_warns_on_stderr(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    """Verify disabled caching prints its reason as a warning and nothing on stdout."""
    monkeypatch.setenv("GATE_CACHE_DISABLE", "1")
    assert invoke(monkeypatch, "status") == 1
    captured = capfd.readouterr()
    assert DISABLED_REASON in captured.err
    assert captured.out == ""


def test_status_json_when_disabled_prints_only_json(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    """Verify --json reports disabled caching on stdout only."""
    monkeypatch.setenv("GATE_CACHE_DISABLE", "1")
    assert invoke(monkeypatch, "status", "--name", "x", "--json") == 1
    captured = capfd.readouterr()
    assert captured.err == ""
    data = json.loads(captured.out)
    assert data["enabled"] is False
    assert data["reason"] == DISABLED_REASON


def _named(**overrides: Any) -> dict[str, Any]:
    data = {
        "enabled": True,
        "name": "pytest",
        "tree": "abc123",
        "reason": None,
        "marker": "/repo/.git/markers/abc",
        "result": "hit",
        "last_run": None,
        "duration": 94.0,
    }
    return data | overrides


def test_named_report_shows_the_lookup() -> None:
    """Verify a hit shows its tree, marker, result, and how long the pass took."""
    text = rendered_text(StatusOutcome(_named(), 0).render(), width=100)
    for part in ("pytest", "abc123", "/repo/.git/markers/abc", "hit", "1m 34s"):
        assert part in text
    assert "last run" not in text
    assert "scope" not in text


def test_named_miss_shows_the_last_run_and_no_duration() -> None:
    """Verify a miss shows how the last run failed."""
    data = _named(
        result="miss",
        marker="/repo/.git/markers/abc",
        duration=None,
        last_run={"exit_code": 2, "reason": "exit code 2", "timestamp": "t"},
    )
    text = rendered_text(StatusOutcome(data, 1).render(), width=100)
    assert "exit code 2" in text
    assert "duration" not in text


def test_scoped_report_shows_paths_and_scope() -> None:
    """Verify a scoped lookup shows its paths, its scope, and the whole tree."""
    data = _named(tree="paths:feed", paths=["a.txt", "src"], full_tree="whole")
    text = rendered_text(StatusOutcome(data, 0).render(), width=100)
    assert "a.txt src" in text
    assert "paths:feed" in text
    assert "whole" in text


def test_unknown_tree_shows_the_reason() -> None:
    """Verify an unknown tree and marker show why they are unknown."""
    data = _named(
        tree=None, marker=None, result="miss", duration=None, reason="a hidden entry: a.txt"
    )
    text = rendered_text(StatusOutcome(data, 1).render(), width=100)
    assert "unknown: a hidden entry: a.txt" in text
    assert "none" in text


def _listing(**overrides: Any) -> dict[str, Any]:
    return {
        "enabled": True,
        "tree": "abc123",
        "reason": None,
        "passed": [],
        "missed": [],
    } | overrides


def test_listing_shows_passed_and_missed_gates() -> None:
    """Verify the listing names each passed gate and each missed gate with its exit code."""
    data = _listing(
        passed=["api-lint"],
        missed=[
            {"name": "ruff", "exit_code": 3, "reason": "boom", "timestamp": "t"},
            {"name": "bare", "exit_code": None, "reason": None, "timestamp": None},
        ],
    )
    text = rendered_text(StatusOutcome(data, 0).render(), width=100)
    assert "abc123" in text
    assert "api-lint" in text
    assert "ruff" in text
    assert "boom" in text
    assert re.search(r"ruff\s+missed\s+3\s+boom", text)
    assert "None" not in text


def test_empty_listing_says_no_gates_match() -> None:
    """Verify a tree with no records says so."""
    assert NO_GATES in rendered_text(StatusOutcome(_listing(), 1).render(), width=100)


@pytest.mark.parametrize(
    "data",
    [
        _listing(tree=None, reason="a hidden entry"),
        _listing(reason="could not locate git directory"),
    ],
)
def test_unreadable_listing_shows_the_reason_not_an_empty_list(data: dict[str, Any]) -> None:
    """Verify a listing that could not be read shows why, never the empty message."""
    text = rendered_text(StatusOutcome(data, 1).render(), width=100)
    assert data["reason"] in text
    assert NO_GATES not in text


@pytest.mark.parametrize("args", [["--yes"], ["-y"], ["--yes", "--json"]])
def test_clear_deletes_markers(
    git_repo: Path,
    counter: Counter,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
    args: list[str],
) -> None:
    """Verify clear --yes removes the markers and reports the count."""
    assert invoke(monkeypatch, "--", *counter.argv()) == 0
    capfd.readouterr()
    assert invoke(monkeypatch, "clear", *args) == 0
    assert markers(git_repo) == []
    out = capfd.readouterr().out
    if "--json" in args:
        data = json.loads(out)
        assert data["deleted"] == 1
        assert data["schema"] == 1
        assert Path(data["marker_dir"]).parts[-1] == "gate-cache"
    else:
        assert re.search(r"\b1 marker\b", out)


def test_clear_json_without_yes_is_refused(
    git_repo: Path,
    counter: Counter,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """Verify clear --json cannot ask for confirmation, so it exits 2 and deletes nothing."""
    assert invoke(monkeypatch, "--", *counter.argv()) == 0
    capfd.readouterr()
    assert invoke(monkeypatch, "clear", "--json") == 2
    error = json.loads(capfd.readouterr().out)["error"]
    with pytest.raises(UsageError) as expected:
        require_yes_for_json("clear", yes=False, as_json=True)
    assert error["message"] == expected.value.message
    assert error["hint"] == expected.value.hint
    assert len(markers(git_repo)) == 1


@pytest.mark.parametrize("json_flag", [[], ["--json"]])
def test_clear_outside_a_repo_exits_1(
    git_env: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
    json_flag: list[str],
) -> None:
    """Verify clear outside a git repository exits 1 and says so."""
    outside = tmp_path / "outside"
    outside.mkdir()
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    monkeypatch.chdir(outside)
    assert invoke(monkeypatch, "clear", "--yes", *json_flag) == 1
    captured = capfd.readouterr()
    if json_flag:
        assert NOT_A_REPO in json.loads(captured.out)["error"]["message"]
    else:
        assert NOT_A_REPO in captured.err


@pytest.mark.parametrize(("reply", "deleted"), [("yes", True), ("no", False), (None, False)])
def test_clear_asks_before_deleting(
    git_repo: Path,
    counter: Counter,
    answer: Callable[[str | None], None],
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
    reply: str | None,
    *,
    deleted: bool,
) -> None:
    """Verify only a typed yes deletes, and a refusal exits 1 with the warning on stderr."""
    assert invoke(monkeypatch, "--", *counter.argv()) == 0
    capfd.readouterr()
    answer(reply)
    assert invoke(monkeypatch, "clear") == (0 if deleted else 1)
    assert (markers(git_repo) == []) is deleted
    captured = capfd.readouterr()
    assert "permanently deletes every recorded pass" in captured.err
    # A long path folds onto several lines at the test terminal width.
    assert "".join(str(marker_dir(git_repo / ".git")).split()) in "".join(captured.err.split())


def test_clear_without_a_terminal_refuses(
    git_repo: Path,
    counter: Counter,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """Verify clear without --yes and without a terminal on stdin deletes nothing."""
    assert invoke(monkeypatch, "--", *counter.argv()) == 0
    monkeypatch.setattr("gate_cache.console.stdin_isatty", lambda: False)
    assert invoke(monkeypatch, "clear") == 1
    assert "--yes" in capfd.readouterr().err
    assert len(markers(git_repo)) == 1


def test_clear_ctrl_c_at_prompt_keeps_markers(
    git_repo: Path,
    counter: Counter,
    answer: Callable[[str | None], None],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify Ctrl-C at the prompt exits 130 and deletes nothing."""
    assert invoke(monkeypatch, "--", *counter.argv()) == 0
    answer("^C")
    assert invoke(monkeypatch, "clear") == 130
    assert len(markers(git_repo)) == 1


def test_clear_reports_os_error(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    """Verify a filesystem error while clearing exits 1 and names the error."""

    def fail(_common_dir: Path) -> int:
        raise OSError(16, "Resource busy")

    monkeypatch.setattr("gate_cache.commands.clear.clear_cache", fail)
    assert invoke(monkeypatch, "clear", "--yes") == 1
    assert "Resource busy" in capfd.readouterr().err


@pytest.mark.parametrize("args", [["extra"], ["--bogus"], ["--yes", "--json", "extra"]])
def test_clear_bad_arguments_are_usage_errors(
    git_repo: Path,
    counter: Counter,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
    args: list[str],
) -> None:
    """Verify malformed clear arguments exit 2 and delete nothing."""
    assert invoke(monkeypatch, "--", *counter.argv()) == 0
    assert invoke(monkeypatch, "clear", *args) == 2
    assert len(markers(git_repo)) == 1


def test_stats_reports_the_setting(
    stats_dirs: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """Stats prints the setting rows and exits 0."""
    assert invoke(monkeypatch, "stats") == 0
    out = capfd.readouterr().out
    for label in ("recording", "decided by", "config", "data"):
        assert label in out
    flat = "".join(out.split())
    assert "".join(str(stats_dirs[0]).split()) in flat
    assert "".join(str(stats_dirs[1]).split()) in flat


def test_stats_on_then_off(
    stats_dirs: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """Stats on turns recording on and stats off turns it back off."""
    assert invoke(monkeypatch, "stats", "on") == 0
    assert re.search(r"recording +on", capfd.readouterr().out)
    assert invoke(monkeypatch, "stats") == 0
    assert re.search(r"recording +on", capfd.readouterr().out)
    assert invoke(monkeypatch, "stats", "off") == 0
    assert re.search(r"recording +off", capfd.readouterr().out)


@pytest.mark.parametrize("action", ["on", "off"])
def test_stats_on_off_json(
    stats_dirs: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
    action: str,
) -> None:
    """Stats on and off print the new setting as JSON."""
    assert invoke(monkeypatch, "stats", action, "--json") == 0
    data = json.loads(capfd.readouterr().out)
    assert data["enabled"] is (action == "on")
    assert data["schema"] == 1


def test_stats_on_reports_an_unwritable_config(
    stats_dirs: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """A config file that cannot be written exits 1 and names the file."""

    def refuse(*, enabled: bool) -> None:
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr("gate_cache.stats.config.write_enabled", refuse)
    assert invoke(monkeypatch, "stats", "on") == 1
    err = capfd.readouterr().err
    assert "could not write" in err
    assert "".join(str(stats_dirs[0]).split()) in "".join(err.split())


@pytest.mark.parametrize(
    ("content", "reason"),
    [
        (b"[stats\n", "not valid TOML"),
        (b"\xff\xfe\x00", "not valid UTF-8"),
        (b"stats_enabled.x = 1\n", "safely"),
    ],
)
def test_stats_on_leaves_an_uneditable_config_untouched(
    stats_dirs: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
    content: bytes,
    reason: str,
) -> None:
    """A config that cannot be edited safely exits 1, says why, and stays as it was."""
    config_file = stats_dirs[0]
    config_file.parent.mkdir(parents=True)
    config_file.write_bytes(content)
    assert invoke(monkeypatch, "stats", "on") == 1
    err = capfd.readouterr().err
    assert "could not write" in err
    assert reason in err
    assert config_file.read_bytes() == content


def test_stats_shows_the_decider_when_env_overrides_config(
    stats_on: None,
    stats_dirs: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """The environment and CI beat the config file, and the output names the decider."""
    monkeypatch.setenv("GATE_CACHE_STATS", "0")
    assert invoke(monkeypatch, "stats") == 0
    out = capfd.readouterr().out
    assert re.search(r"recording +off", out)
    assert re.search(r"decided by +env", out)

    monkeypatch.delenv("GATE_CACHE_STATS")
    monkeypatch.setenv("CI", "true")
    assert invoke(monkeypatch, "stats") == 0
    assert re.search(r"decided by +ci", capfd.readouterr().out)


@pytest.mark.parametrize(
    "args", [["bogus"], ["--action", "on"], ["--yes"], ["on", "--yes"], ["off", "-y"]]
)
def test_stats_bad_arguments_are_usage_errors(
    stats_dirs: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch, args: list[str]
) -> None:
    """An unknown action, or --yes without clear, is a usage error."""
    assert invoke(monkeypatch, "stats", *args) == 2


def test_stats_json(
    stats_dirs: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """Stats --json prints the setting as one versioned object."""
    assert invoke(monkeypatch, "stats", "--json") == 0
    data = json.loads(capfd.readouterr().out)
    assert data == {
        "schema": 1,
        "enabled": False,
        "decided_by": "default",
        "project": None,
        "config_file": str(stats_dirs[0]),
        "data_dir": str(stats_dirs[1]),
    }


@pytest.fixture
def seeded_stats(stats_dirs: tuple[Path, Path]) -> Path:
    """Create an archive so a test can see whether clearing deleted it."""
    stats_dirs[1].mkdir(parents=True)
    Archive.open(archive_path()).close()
    return archive_path()


def test_stats_clear_json(
    seeded_stats: Path, monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    """Stats clear --json needs --yes, and with it reports the number deleted."""
    assert invoke(monkeypatch, "stats", "clear", "--json") == 2
    error = json.loads(capfd.readouterr().out)["error"]
    with pytest.raises(UsageError) as expected:
        require_yes_for_json("stats clear", yes=False, as_json=True)
    assert error["message"] == expected.value.message
    assert seeded_stats.exists()
    assert invoke(monkeypatch, "stats", "clear", "--yes", "--json") == 0
    data = json.loads(capfd.readouterr().out)
    assert data["schema"] == 1
    assert data["deleted"] >= 1
    assert data["data_dir"] == str(seeded_stats.parent)
    assert not seeded_stats.exists()


@pytest.mark.parametrize(("reply", "deleted"), [("yes", True), ("no", False), (None, False)])
def test_stats_clear_asks_before_deleting(
    seeded_stats: Path,
    answer: Callable[[str | None], None],
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
    reply: str | None,
    *,
    deleted: bool,
) -> None:
    """Only a typed yes clears stats, and the warning names the data directory."""
    answer(reply)
    assert invoke(monkeypatch, "stats", "clear") == (0 if deleted else 1)
    assert seeded_stats.exists() is not deleted
    err = capfd.readouterr().err
    assert "".join(str(seeded_stats.parent).split()) in "".join(err.split())


def test_stats_clear_ctrl_c_keeps_stats(
    seeded_stats: Path, answer: Callable[[str | None], None], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ctrl-C at the prompt exits 130 and deletes nothing."""
    answer("^C")
    assert invoke(monkeypatch, "stats", "clear") == 130
    assert seeded_stats.exists()


@pytest.mark.parametrize("json_flag", [[], ["--json"]])
def test_stats_clear_refuses_while_the_dashboard_runs(
    seeded_stats: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
    json_flag: list[str],
) -> None:
    """A held lock exits 1 with a hint, and nothing is deleted."""
    held = InstanceLock.acquire(seeded_stats.parent)
    assert held is not None
    try:
        assert invoke(monkeypatch, "stats", "clear", "--yes", *json_flag) == 1
    finally:
        held.release()
    captured = capfd.readouterr()
    if json_flag:
        assert json.loads(captured.out)["error"]["hint"]
    else:
        assert "hint:" in captured.err
    assert seeded_stats.exists()


def test_stats_clear_reports_os_error(
    seeded_stats: Path, monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    """A filesystem error while clearing exits 1 and names the error."""

    def fail(**_kwargs: object) -> int:
        raise OSError(16, "Resource busy")

    monkeypatch.setattr("gate_cache.stats.clear.clear_stats", fail)
    assert invoke(monkeypatch, "stats", "clear", "--yes") == 1
    assert "Resource busy" in capfd.readouterr().err


def _record(state: Path, *events: tuple[str, str]) -> None:
    """Archive one recent passing run for each (repo, gate name) pair."""
    with Archive.open(state / ARCHIVE_NAME) as archive:
        for offset, (repo, name) in enumerate(events):
            insert(archive.connection, time.time() - 600 + offset, "pass", repo=repo, name=name)


def _report_json(
    monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str], *args: str
) -> dict[str, Any]:
    """Run `stats report --json` with args, require exit 0, and return the parsed report."""
    capfd.readouterr()
    assert invoke(monkeypatch, "stats", "report", "--json", *args) == 0
    return json.loads(capfd.readouterr().out)


@pytest.fixture
def outside_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, git_env: Path) -> Path:
    """Chdir into a directory outside any git repository and return it."""
    outside = tmp_path / "outside"
    outside.mkdir()
    monkeypatch.chdir(outside)
    return outside


COMMAND = ["npx", "eslint@9", "."]


@pytest.fixture
def recorded_here(
    git_repo: Path,
    stats_on: None,
    stats_dirs: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> list[str]:
    """Record `lint` and a gate named by COMMAND here and `other` elsewhere; fake the status.

    Returns:
        The gate names whose status on the current content was looked up.
    """
    common = str(git_common_dir(git_repo))
    _record(stats_dirs[1], (common, "lint"), (common, shlex.join(COMMAND)), (REPO_B, "other"))
    looked_up: list[str] = []

    def current_status(name: str, paths: list[str], **_: object) -> dict[str, Any]:
        looked_up.append(name)
        return {"tree": "here", "result": "hit", "last_run": None}

    monkeypatch.setattr(gate_module, "current_status", current_status)
    return looked_up


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (["report", "--all-repos", "--repo", "x"], ALL_REPOS_CONFLICT),
        (["report", "--all-repos", "--name", "x"], ALL_REPOS_CONFLICT),
        (["report", "--name", "test@v22"], KEYED_NAME_ERROR.format(gate="test")),
        (["report", "--name", "x", "--", "pytest"], NAME_OR_COMMAND),
        (["report", "--name", "x"], NAME_NEEDS_REPO),
        (["report", "--", "echo", "hi"], NAME_NEEDS_REPO),
        (["report", "--"], NO_COMMAND),
        (["report", "pytest"], NEEDS_SEPARATOR),
        (["report", "--name", "a", "--name", "b"], "--name"),
        (["report", "--repo", "a", "--repo", "b"], "--repo"),
        (["report", "--since", "0d"], DURATION_ERROR),
        (["report", "--since", "7"], DURATION_ERROR),
        (["report", "--since", "9" * 400 + "d"], DURATION_ERROR),
        (["report", "--until", "soon"], UNTIL_ERROR),
        (["report", "--until", "0001-01-01"], UNTIL_ERROR),
        (["report", "--until", "10000y"], UNTIL_ERROR),
        (["report", "--limit", "many"], "--limit"),
    ],
)
def test_stats_report_usage_errors(
    stats_dirs: tuple[Path, Path],
    outside_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
    args: list[str],
    message: str,
) -> None:
    """Each invalid flag combination or value exits 2 and says what is wrong."""
    assert invoke(monkeypatch, "stats", *args) == 2
    assert message in " ".join(capfd.readouterr().err.split())


@pytest.mark.parametrize(
    ("args", "repo", "gates"),
    [
        pytest.param([], "here", {"lint", shlex.join(COMMAND)}, id="current repo"),
        pytest.param(["--all-repos"], None, {"lint", shlex.join(COMMAND), "other"}, id="all repos"),
        pytest.param(["--repo", "other"], REPO_B, {"other"}, id="named repo"),
    ],
)
def test_stats_report_scope(
    recorded_here: list[str],
    git_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
    args: list[str],
    repo: str | None,
    gates: set[str],
) -> None:
    """--repo picks one repo, else --all-repos every repo, else the current repo."""
    expected = str(git_common_dir(git_repo)) if repo == "here" else repo

    report = _report_json(monkeypatch, capfd, *args)

    assert report["repo"] == expected
    assert "recording" not in report
    assert {g["name"] for g in report["gates"]} == gates


@pytest.mark.parametrize(
    ("args", "name", "tree"),
    [
        pytest.param(["--name", "lint"], "lint", "here", id="name"),
        pytest.param(["--", *COMMAND], shlex.join(COMMAND), "here", id="command"),
        pytest.param(["--name", shlex.join(COMMAND)], shlex.join(COMMAND), "here", id="name @"),
        pytest.param(["--repo", "other", "--name", "other"], "other", None, id="other repo"),
    ],
)
def test_stats_report_one_gate(
    recorded_here: list[str],
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
    args: list[str],
    name: str,
    tree: str | None,
) -> None:
    """One gate is named by --name or its command, with a status only in the current repo."""
    report = _report_json(monkeypatch, capfd, *args)

    assert report["name"] == name
    assert (report["current"] or {}).get("tree") == tree
    assert recorded_here == ([name] if tree else [])


@pytest.mark.parametrize(
    ("args", "hint"),
    [pytest.param([], True, id="suite"), pytest.param(["--name", "lint"], False, id="gate")],
)
def test_stats_report_text(
    recorded_here: list[str],
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
    args: list[str],
    hint: bool,
) -> None:
    """Without --json, each view prints text that names the gate."""
    assert invoke(monkeypatch, "stats", "report", *args) == 0
    out = capfd.readouterr().out
    assert "lint" in out
    assert (REPORT_HINT in out) is hint


@pytest.mark.parametrize(
    "args", [["report", "--json"], ["--json", "report"], ["--json", "report", "--since", "7d"]]
)
def test_stats_report_json_outside_repo(
    stats_dirs: tuple[Path, Path],
    outside_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
    args: list[str],
) -> None:
    """Outside a repo with nothing recorded, the machine-wide report is empty and creates nothing."""
    assert invoke(monkeypatch, "stats", *args) == 0
    report = json.loads(capfd.readouterr().out)
    assert report["repo"] is None
    assert report["recording"] is False
    assert report["gates"] == []
    state = stats_dirs[1]
    assert not state.exists() or not any(state.iterdir())


@pytest.mark.parametrize(("limit", "shown"), [("0", 1), ("2", 2), ("9999", 3)])
def test_stats_report_limit_is_clamped(
    stats_dirs: tuple[Path, Path],
    outside_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
    limit: str,
    shown: int,
) -> None:
    """--limit caps each list, and a value out of range is pulled into 1 to 500."""
    _record(stats_dirs[1], *[(REPO_A, "lint")] * 3)

    report = _report_json(monkeypatch, capfd, "--repo", "proj", "--name", "lint", "--limit", limit)
    assert report["recent"]["shown"] == shown


@pytest.mark.parametrize("recording", [True, False])
def test_stats_report_name_unknown(
    git_repo: Path,
    stats_dirs: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
    recording: bool,
) -> None:
    """A gate the repo never recorded exits 1 and names it, with a hint when recording is off."""
    monkeypatch.setenv("GATE_CACHE_STATS", "1" if recording else "0")
    common = str(git_common_dir(git_repo))
    _record(stats_dirs[1], (common, "lint"))

    assert invoke(monkeypatch, "stats", "report", "--name", "nope") == 1
    err = capfd.readouterr().err
    # The repo path is long enough to fold, so check the words and the path apart.
    gate_part = UNKNOWN_GATE.format(name="nope", repo="").strip()
    assert gate_part in " ".join(err.split())
    assert common in "".join(err.split())
    assert (RECORDING_OFF_HINT in " ".join(err.split())) is not recording


@pytest.mark.parametrize("record", [True, False])
def test_stats_report_repo_unknown(
    stats_dirs: tuple[Path, Path],
    outside_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
    record: bool,
) -> None:
    """A --repo that matches no recorded repo exits 1, with or without a record."""
    if record:
        _record(stats_dirs[1], (REPO_A, "lint"))

    assert invoke(monkeypatch, "stats", "report", "--repo", "nowhere") == 1
    assert UNKNOWN_REPO.format(text="nowhere") in capfd.readouterr().err


def test_stats_report_repo_ambiguous(
    stats_dirs: tuple[Path, Path],
    outside_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """A --repo name shared by two repos exits 2 and lists both paths."""
    _record(stats_dirs[1], ("/a/shop/.git", "lint"), ("/b/shop/.git", "lint"))

    assert invoke(monkeypatch, "stats", "report", "--repo", "shop") == 2
    err = capfd.readouterr().err
    assert "/a/shop" in err
    assert "/b/shop" in err


def test_stats_report_ambiguous_repo_json(
    stats_dirs: tuple[Path, Path],
    outside_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """With --json, an ambiguous --repo exits 2 and lists each matching folder in the details."""
    _record(stats_dirs[1], ("/a/shop/.git", "lint"), ("/b/shop/.git", "lint"))

    assert invoke(monkeypatch, "stats", "report", "--repo", "shop", "--json") == 2
    error = json.loads(capfd.readouterr().out)["error"]
    assert error["message"] == AMBIGUOUS_REPO.format(text="shop")
    assert {m["folder"] for m in error["details"]["matches"]} == {"/a/shop", "/b/shop"}


def test_stats_report_json_after_separator_is_part_of_the_command(
    recorded_here: list[str],
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """A --json after -- names the gate and leaves the output as text."""
    assert invoke(monkeypatch, "stats", "report", "--", *COMMAND, "--json") == 1
    captured = capfd.readouterr()
    assert captured.out == ""
    name = shlex.join([*COMMAND, "--json"])
    assert name in " ".join(captured.err.split())


def test_stats_report_shows_markup_literally(
    stats_dirs: tuple[Path, Path],
    outside_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """Gate names and repo labels with brackets print as given."""
    _record(stats_dirs[1], ("/x/[red]shop/.git", "pytest[unit]"))

    assert invoke(monkeypatch, "stats", "report", "--all-repos") == 0
    out = capfd.readouterr().out
    assert "pytest[unit]" in out
    assert "[red]shop" in out


@pytest.mark.parametrize(
    "error",
    [
        ArchiveVersionError("archive schema 9 is newer than this gate-cache supports"),
        sqlite3.DatabaseError("file is not a database"),
        PermissionError(13, "Permission denied"),
    ],
)
def test_stats_report_unreadable_record(
    stats_dirs: tuple[Path, Path],
    outside_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
    error: Exception,
) -> None:
    """A record that cannot be read exits 1 with one line that says why."""

    @contextmanager
    def broken() -> Generator[None]:
        raise error
        yield

    monkeypatch.setattr(report_module, "open_record", broken)
    assert invoke(monkeypatch, "stats", "report") == 1
    err = capfd.readouterr().err
    assert str(error) in err
    assert "Traceback" not in err


@pytest.mark.parametrize(
    ("tokens", "expected"),
    [
        (["stats", "--json", "report"], ["stats", "report", "--json"]),
        (["stats", "-y", "--json", "report"], ["stats", "report", "-y", "--json"]),
        (
            ["stats", "--json", "report", "--name", "report"],
            ["stats", "report", "--json", "--name", "report"],
        ),
        (["stats", "report", "--", "tool", "report"], ["stats", "report", "--", "tool", "report"]),
        (["stats", "--json", "--", "report"], ["stats", "--json", "--", "report"]),
        (["stats", "--name", "report"], ["stats", "--name", "report"]),
        (["stats", "on"], ["stats", "on"]),
        (["status", "--json", "report"], ["status", "--json", "report"]),
    ],
)
def test_report_moves_ahead_of_stats_flags_only(tokens: list[str], expected: list[str]) -> None:
    """Only value-less stats flags before `report` move behind it; anything else stays as typed."""
    assert _report_first(tokens) == expected


class _FakeDashboardError(Exception):
    """Stand-in for the dashboard's start failure."""


@dataclass(frozen=True)
class _FakeStart:
    """Stand-in for the dashboard's start report."""

    url: str | None
    port: int | None
    already_running: bool
    busy: bool
    recording: bool


@pytest.fixture
def fake_dashboard(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """Replace the dashboard package, so core never runs dashboard code."""
    fake = SimpleNamespace(
        run_dashboard=MagicMock(),
        DashboardError=_FakeDashboardError,
        DashboardStart=_FakeStart,
        DASHBOARD_BUSY="busy message",
        DASHBOARD_RUNNING="running at {url}",
    )
    monkeypatch.setitem(sys.modules, "gate_cache.dashboard.app", fake)
    return fake


def _start_with(fake: SimpleNamespace, start: _FakeStart) -> None:
    fake.run_dashboard.side_effect = lambda *, on_start, **_: on_start(start)


STARTS = [
    _FakeStart(
        url="http://127.0.0.1:7878", port=7878, already_running=True, busy=False, recording=True
    ),
    _FakeStart(url=None, port=None, already_running=False, busy=True, recording=True),
    _FakeStart(
        url="http://127.0.0.1:9000", port=9000, already_running=False, busy=False, recording=False
    ),
    _FakeStart(
        url="http://127.0.0.1:9000", port=9000, already_running=False, busy=False, recording=True
    ),
]


@pytest.mark.parametrize("start", STARTS)
def test_dashboard_json_line(
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
    fake_dashboard: SimpleNamespace,
    start: _FakeStart,
) -> None:
    """`dashboard --json` prints one compact JSON line with the address and the state."""
    _start_with(fake_dashboard, start)
    assert invoke(monkeypatch, "dashboard", "--json") == 0
    lines = capfd.readouterr().out.splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0]) == {
        "schema": 1,
        "url": start.url,
        "port": start.port,
        "already_running": start.already_running,
        "busy": start.busy,
    }


@pytest.mark.parametrize("start", STARTS)
def test_dashboard_human_output(
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
    fake_dashboard: SimpleNamespace,
    start: _FakeStart,
) -> None:
    """The address prints when there is one; the recording-off warning only when serving."""
    _start_with(fake_dashboard, start)
    assert invoke(monkeypatch, "dashboard") == 0
    captured = capfd.readouterr()
    if start.url:
        assert start.url in captured.out
    if start.busy:
        assert "busy message" in captured.err
    serving = not (start.busy or start.already_running)
    assert (RECORDING_OFF in captured.err) == (serving and not start.recording)


def test_dashboard_passes_its_options_through(
    monkeypatch: pytest.MonkeyPatch, fake_dashboard: SimpleNamespace
) -> None:
    """The dashboard command hands the port and the browser choice to the server."""
    assert invoke(monkeypatch, "dashboard", "--port", "9000", "--no-browser") == 0
    kwargs = fake_dashboard.run_dashboard.call_args.kwargs
    assert kwargs["port"] == 9000
    assert kwargs["open_browser"] is False


@pytest.mark.parametrize("bad", ["0x", "0", "70000"])
def test_dashboard_rejects_bad_port(
    monkeypatch: pytest.MonkeyPatch, fake_dashboard: SimpleNamespace, bad: str
) -> None:
    """A non-numeric or out-of-range port is a usage error."""
    assert invoke(monkeypatch, "dashboard", "--port", bad) == 2


@pytest.mark.parametrize("json_flag", [[], ["--json"]])
def test_dashboard_start_failure_is_exit_1(
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
    fake_dashboard: SimpleNamespace,
    json_flag: list[str],
) -> None:
    """A dashboard that cannot start reports the reason and exits 1."""
    fake_dashboard.run_dashboard.side_effect = _FakeDashboardError("no UI here")
    assert invoke(monkeypatch, "dashboard", *json_flag) == 1
    captured = capfd.readouterr()
    if json_flag:
        assert json.loads(captured.out)["error"]["message"] == "no UI here"
    else:
        assert "no UI here" in captured.err
