"""Tests for recording one stats event per gate run."""

import json
import os
import stat
import subprocess
import sys
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import NoReturn

import pytest

from gate_cache import __version__
from gate_cache.gate import run_gate
from gate_cache.runner import ChildResult
from gate_cache.snapshot import Snapshot, git_common_dir
from gate_cache.stats import context
from gate_cache.stats.config import DATA_DIR_ENV, STATS_ENV
from gate_cache.stats.recorder import MAX_LINE_BYTES, Event, inbox_path, record_event
from tests.conftest import Counter, git, hide_common_dir

SECRET = "tok3nS3cretValue"  # noqa: S105


def read_events(state: Path) -> list[dict[str, object]]:
    """Parse every line of the inbox."""
    return [json.loads(line) for line in (state / "events.jsonl").read_text().splitlines()]


def test_pass_then_skip(git_repo: Path, stats_dirs: tuple[Path, Path], stats_on: None) -> None:
    """A pass then a skip record one event each, with the skip's saved time."""
    assert run_gate("t", ["true"]) == 0
    assert run_gate("t", ["true"]) == 0
    first, second = read_events(stats_dirs[1])
    assert first["v"] == 1
    assert first["outcome"] == "pass"
    assert first["exit_code"] == 0
    assert first["repo"] == str(git_common_dir())
    assert first["tree"]
    assert second["outcome"] == "skip"
    assert second["duration"] is None
    assert second["exit_code"] is None
    assert second["saved"] == pytest.approx(first["duration"], abs=0.001)


def test_fail(git_repo: Path, stats_dirs: tuple[Path, Path], stats_on: None) -> None:
    """A failing command records a fail with its exit code."""
    assert run_gate("t", ["false"]) == 1
    (event,) = read_events(stats_dirs[1])
    assert event["outcome"] == "fail"
    assert event["exit_code"] == 1
    assert event["duration"] is not None


def test_pass_unrecorded(
    git_repo: Path, stats_dirs: tuple[Path, Path], stats_on: None, counter: Counter
) -> None:
    """A pass that rewrites keyed files records pass_unrecorded."""
    touch = git_repo / "a.txt"
    assert run_gate("t", counter.argv(touch=touch)) == 0
    (event,) = read_events(stats_dirs[1])
    assert event["outcome"] == "pass_unrecorded"
    assert event["exit_code"] == 0


def test_uncached_disabled(
    git_repo: Path,
    stats_dirs: tuple[Path, Path],
    stats_on: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A disabled-cache run records uncached with the repo and reason."""
    monkeypatch.setenv("GATE_CACHE_DISABLE", "1")
    assert run_gate("t", ["true"], paths=["a.txt"]) == 0
    (event,) = read_events(stats_dirs[1])
    assert event["outcome"] == "uncached"
    assert event["repo"] == str(git_common_dir())
    assert event["tree"] is None
    assert event["paths"] == ["a.txt"]
    assert "GATE_CACHE_DISABLE" in str(event["reason"])
    assert event["exit_code"] == 0


def test_unknown_tree_records_repo_without_another_lookup(
    git_repo: Path,
    stats_dirs: tuple[Path, Path],
    stats_on: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify an unknown tree records the repo the snapshot found, without asking git again."""
    git("update-index", "--assume-unchanged", "a.txt", cwd=git_repo)
    repo = git_common_dir()

    def no_lookup() -> None:
        msg = "the snapshot already found the common dir"
        raise AssertionError(msg)

    monkeypatch.setattr("gate_cache.gate.git_common_dir", no_lookup)
    assert run_gate("t", ["true"]) == 0
    (event,) = read_events(stats_dirs[1])
    assert event["outcome"] == "uncached"
    assert str(event["reason"]).startswith("skip-worktree or assume-unchanged entry")
    assert event["repo"] == str(repo)


def test_off_writes_nothing(git_repo: Path, stats_dirs: tuple[Path, Path]) -> None:
    """Nothing is written while stats are off."""
    run_gate("t", ["true"])
    assert not (stats_dirs[1] / "events.jsonl").exists()


def test_ci_writes_nothing(
    git_repo: Path,
    stats_dirs: tuple[Path, Path],
    stats_on: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Nothing is written in CI, even with stats on in the config."""
    monkeypatch.setenv("CI", "true")
    monkeypatch.setenv("GATE_CACHE_DISABLE", "0")
    run_gate("t", ["true"])
    assert not (stats_dirs[1] / "events.jsonl").exists()


def test_line_limit_truncates_paths() -> None:
    """An oversized line keeps a prefix of paths and flags truncation."""
    event = Event(
        ts=1.0,
        repo="/r",
        name="n",
        tree="abc",
        paths=tuple(f"p{i}" * 50 for i in range(200)),
        outcome="pass",
        duration=1.0,
        saved=None,
        exit_code=0,
        reason=None,
    )
    line = event.to_line()
    assert len(line) <= MAX_LINE_BYTES
    assert line.endswith(b"\n")
    data = json.loads(line)
    assert data["paths_truncated"] is True
    assert 0 < len(data["paths"]) < 200
    assert next(iter(data)) == "v"


def test_short_line_is_not_truncated() -> None:
    """A short line keeps every path and omits the truncation flag."""
    event = Event(
        ts=1.0, repo=None, name="n", tree=None, paths=("a",), outcome="skip",
        duration=None, saved=0.5, exit_code=None, reason=None,
    )  # fmt: skip
    data = json.loads(event.to_line())
    assert "paths_truncated" not in data
    assert data["paths"] == ["a"]


def test_passed_environ_moves_the_inbox(tmp_path: Path, isolate_user_dirs: Path) -> None:
    """record_event writes to the data directory of the environment it is given."""
    event = Event(
        ts=1.0, repo=None, name="n", tree=None, paths=(), outcome="skip",
        duration=None, saved=0.5, exit_code=None, reason=None,
    )  # fmt: skip
    environ = {STATS_ENV: "1", DATA_DIR_ENV: str(tmp_path / "passed")}
    record_event(event, environ)
    assert (tmp_path / "passed" / "events.jsonl").read_text(encoding="utf-8").strip()
    assert not (isolate_user_dirs / "events.jsonl").exists()


def test_inbox_mode_0600(git_repo: Path, stats_dirs: tuple[Path, Path], stats_on: None) -> None:
    """The inbox is private to the user."""
    run_gate("t", ["true"])
    assert stat.S_IMODE(inbox_path().stat().st_mode) == 0o600


@pytest.mark.parametrize(
    "breakage", ["readonly_state", "file_in_the_way", "garbage_config", "inbox_unwritable"]
)
def test_stats_failure_is_invisible(
    git_repo: Path,
    stats_dirs: tuple[Path, Path],
    stats_on: None,
    capfd: pytest.CaptureFixture[str],
    breakage: str,
) -> None:
    """A broken state dir or config changes no exit code, stdout, or stderr."""
    config_file, state = stats_dirs
    if breakage == "readonly_state" and os.geteuid() == 0:
        pytest.skip("root ignores directory permissions")

    def run_all(prefix: str) -> tuple[list[int], str, str]:
        codes = [
            run_gate(f"{prefix}-pass", ["true"]),
            run_gate(f"{prefix}-pass", ["true"]),
            run_gate(f"{prefix}-fail", ["false"]),
        ]
        out, err = capfd.readouterr()
        return codes, out.replace(prefix, "NAME"), err.replace(prefix, "NAME")

    config_file.write_text("stats_enabled = false\n", encoding="utf-8")
    baseline = run_all("base")

    config_file.write_text("stats_enabled = true\n", encoding="utf-8")
    state.parent.mkdir(parents=True, exist_ok=True)
    if breakage == "readonly_state":
        state.mkdir(mode=0o500)
    elif breakage == "file_in_the_way":
        state.write_text("not a directory", encoding="utf-8")
    elif breakage == "inbox_unwritable":
        state.mkdir()
        (state / "events.jsonl").mkdir()
    else:
        config_file.write_text("[stats\nenabled = = =\x00", encoding="utf-8")
    try:
        broken = run_all("broken")
    finally:
        if state.is_dir():
            state.chmod(0o700)

    assert broken == baseline


def test_uncached_paths_are_normalized(
    git_repo: Path,
    stats_dirs: tuple[Path, Path],
    stats_on: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Uncached events carry sorted, distinct paths like cached ones."""
    monkeypatch.setenv("GATE_CACHE_DISABLE", "1")
    run_gate("t", ["true"], paths=["b", "a", "a"])
    (event,) = read_events(stats_dirs[1])
    assert event["paths"] == ["a", "b"]


def test_tree_unknown_is_uncached(
    git_repo: Path,
    stats_dirs: tuple[Path, Path],
    stats_on: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A run outside a git work tree records uncached with no tree."""
    outside = git_repo.parent / "outside"
    outside.mkdir()
    monkeypatch.chdir(outside)
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(git_repo.parent))
    assert run_gate("t", ["true"]) == 0
    (event,) = read_events(stats_dirs[1])
    assert event["outcome"] == "uncached"
    assert event["tree"] is None
    assert event["repo"] is None


def test_tree_unknown_in_repo_records_repo(
    git_repo: Path,
    stats_dirs: tuple[Path, Path],
    stats_on: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A tree-unknown run inside a repo still records the repo."""
    monkeypatch.setattr(
        "gate_cache.gate.take_snapshot", lambda paths=(): Snapshot(tree=None, reason="no tree")
    )
    assert run_gate("t", ["true"]) == 0
    (event,) = read_events(stats_dirs[1])
    assert event["outcome"] == "uncached"
    assert event["tree"] is None
    assert event["repo"] == str(git_common_dir())
    assert event["reason"] == "no tree"


def test_no_common_dir_is_uncached(
    git_repo: Path,
    stats_dirs: tuple[Path, Path],
    stats_on: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A missing common directory records uncached with the tree and no repo."""
    hide_common_dir(monkeypatch)
    assert run_gate("t", ["true"]) == 0
    (event,) = read_events(stats_dirs[1])
    assert event["outcome"] == "uncached"
    assert event["tree"]
    assert event["repo"] is None


def test_interrupted_run_records_nothing(
    git_repo: Path,
    stats_dirs: tuple[Path, Path],
    stats_on: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An interrupted run writes no event, cached or not."""
    monkeypatch.setattr(
        "gate_cache.gate.run_child", lambda _argv: ChildResult(130, interrupted=True)
    )
    assert run_gate("t", ["true"]) == 130
    monkeypatch.setenv("GATE_CACHE_DISABLE", "1")
    assert run_gate("t", ["true"]) == 130
    assert not (stats_dirs[1] / "events.jsonl").exists()


def test_skip_without_marker_duration_saves_null(
    git_repo: Path, stats_dirs: tuple[Path, Path], stats_on: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A skip whose marker has no duration records saved as null."""
    run_gate("t", ["true"])
    monkeypatch.setattr("gate_cache.gate.marker_duration", lambda _path: None)
    run_gate("t", ["true"])
    _, second = read_events(stats_dirs[1])
    assert second["outcome"] == "skip"
    assert second["saved"] is None


def test_pass_stays_pass_when_marker_write_fails(
    git_repo: Path, stats_dirs: tuple[Path, Path], stats_on: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failed marker write still records the command's pass."""

    def boom(*_args: object, **_kwargs: object) -> None:
        msg = "boom"
        raise ValueError(msg)

    monkeypatch.setattr("gate_cache.gate.write_marker", boom)
    assert run_gate("t", ["true"]) == 0
    (event,) = read_events(stats_dirs[1])
    assert event["outcome"] == "pass"


@pytest.mark.parametrize("enabled", [True, False], ids=["stats-on", "stats-off"])
def test_gate_path_does_not_load_dashboard(
    git_repo: Path, stats_dirs: tuple[Path, Path], *, enabled: bool
) -> None:
    """Running a gate never imports the archive, queries, or dashboard modules."""
    config_file, state = stats_dirs
    config_file.parent.mkdir(parents=True, exist_ok=True)
    config_file.write_text(f"stats_enabled = {str(enabled).lower()}\n", encoding="utf-8")
    script = (
        "import sys\n"
        "from pathlib import Path\n"
        "from gate_cache import config as core_config\n"
        "core_config.config_path = lambda: Path(sys.argv[1])\n"
        "from gate_cache.gate import run_gate\n"
        "assert run_gate('t', ['true']) == 0\n"
        "assert run_gate('t', ['true']) == 0\n"
        "print('\\n'.join(sorted(sys.modules)))\n"
    )
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-c", script, str(config_file)],
        cwd=git_repo,
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        check=True,
    )
    mods = set(result.stdout.splitlines())
    forbidden = {"sqlite3", "http.server", "gate_cache.stats.archive", "gate_cache.stats.queries"}
    assert not forbidden & mods
    assert not any(m.startswith("gate_cache.dashboard") for m in mods)
    assert "socket" not in mods
    if not enabled:
        assert not {"uuid", "resource"} & mods
    inbox = state / "events.jsonl"
    assert (len(inbox.read_text().splitlines()) if inbox.exists() else 0) == (2 if enabled else 0)


CONTEXT_FIELDS = (
    "version",
    "trigger",
    "worktree",
    "branch",
    "remote",
    "machine",
    "host",
    "overhead",
    "command",
    "id",
    "head",
    "marker_age",
    "cpu",
    "max_rss",
    "subdir",
    "hook_stage",
    "agent",
    "platform",
)


def long_event(**changes: object) -> Event:
    """Build an event whose context fields push the line past the limit."""
    fields: dict[str, object] = {
        "ts": 1.0,
        "repo": "/r/.git",
        "name": "n",
        "tree": "abc",
        "paths": tuple(f"p{i}" * 10 for i in range(20)),
        "outcome": "pass",
        "duration": 1.0,
        "saved": None,
        "exit_code": 0,
        "reason": None,
        "host": "h" * 100,
        "command": "c" * 3500,
    }
    fields.update(changes)
    return Event(**fields)  # ty: ignore[invalid-argument-type]


def test_new_fields_default_to_null() -> None:
    """An event built without context still writes every field as null."""
    data = json.loads(long_event(host=None, command=None).to_line())
    assert data["v"] == 1
    assert all(data[field] is None for field in CONTEXT_FIELDS)
    assert "command_truncated" not in data


def test_waited_is_encoded() -> None:
    """A wait is written as `waited`, with no timeout flag."""
    data = json.loads(long_event(host=None, command=None, waited=12.5).to_line())
    assert data["waited"] == 12.5
    assert "wait_timed_out" not in data


def test_waited_defaults_to_null() -> None:
    """An event with no wait writes `waited` as null."""
    data = json.loads(long_event(host=None, command=None).to_line())
    assert data["waited"] is None


def test_wait_timed_out_is_encoded_only_when_set() -> None:
    """The timeout flag appears only for a wait that timed out."""
    data = json.loads(
        long_event(host=None, command=None, waited=900.0, wait_timed_out=True).to_line()
    )
    assert data["wait_timed_out"] is True
    assert "wait_timed_out" not in json.loads(long_event(host=None, command=None).to_line())


def test_line_limit_drops_host_first() -> None:
    """A line just over the limit loses the host and keeps the command and paths."""
    command = "c" * 3000
    fits = long_event(host=None, command=command)
    room = MAX_LINE_BYTES - len(fits.to_line())
    assert room > 0
    data = json.loads(long_event(host="h" * (room + 4), command=command).to_line())
    assert data["host"] is None
    assert data["command"] == command
    assert "command_truncated" not in data
    assert "paths_truncated" not in data


def test_line_limit_drops_command_before_paths() -> None:
    """A long command is dropped and flagged before any path is cut."""
    line = long_event().to_line()
    assert len(line) <= MAX_LINE_BYTES
    data = json.loads(line)
    assert data["host"] is None
    assert data["command"] is None
    assert data["command_truncated"] is True
    assert "paths_truncated" not in data
    assert len(data["paths"]) == 20


def test_line_limit_then_truncates_paths() -> None:
    """With the command gone and the line still too long, paths are cut as before."""
    event = long_event(paths=tuple(f"p{i}" * 50 for i in range(200)))
    data = json.loads(event.to_line())
    assert data["command_truncated"] is True
    assert data["paths_truncated"] is True
    assert 0 < len(data["paths"]) < 200


def test_line_limit_drops_location_when_paths_cannot_fit() -> None:
    """Location fields too long for any line are dropped so the line stays in the limit."""
    event = long_event(worktree="/w" * 1500, subdir="s/" * 600, branch="b", remote="r/x")
    line = event.to_line()
    assert len(line) <= MAX_LINE_BYTES
    data = json.loads(line)
    assert all(data[field] is None for field in ("worktree", "subdir", "branch", "remote"))
    assert len(data["paths"]) == 20
    assert "paths_truncated" not in data


@pytest.mark.parametrize("unit", ["n", "\u00e9", "\U0001f600", "\x00", "\udcff"])
def test_line_limit_truncates_a_long_name_last(unit: str) -> None:
    """A name too long for any line keeps a prefix, is flagged, and the line fits."""
    name = unit * 5000
    event = long_event(name=name, worktree="/w", subdir=".", branch="b", remote="h/o/r")
    line = event.to_line()
    assert len(line) <= MAX_LINE_BYTES
    data = json.loads(line)
    assert data["name_truncated"] is True
    assert data["name"]
    assert name.startswith(data["name"])
    assert all(data[field] is None for field in ("worktree", "subdir", "branch", "remote"))
    assert data["paths"] == []
    assert data["paths_truncated"] is True


def test_line_limit_drops_long_env_fields_and_repo() -> None:
    """Unbounded hook stage, reason, and repo values never push a line past the limit."""
    event = long_event(
        name="gate", repo="/r" * 3000, reason="x" * 5000, hook_stage="s" * 5000, paths=()
    )
    line = event.to_line()
    assert len(line) <= MAX_LINE_BYTES
    data = json.loads(line)
    assert data["name"] == "gate"
    assert "name_truncated" not in data
    assert data["hook_stage"] is None
    assert data["reason"] is None
    assert data["repo"] is None
    assert "paths_truncated" not in data


def test_line_limit_stops_after_cutting_the_name() -> None:
    """A line no cut can fit still encodes once the name is gone, without recursing."""
    data = json.loads(long_event(name="n" * 100, tree="t" * 5000).to_line())
    assert data["name"] == ""
    assert data["name_truncated"] is True


def test_short_name_is_not_flagged() -> None:
    """A line that fits after the usual drops never sets name_truncated."""
    assert "name_truncated" not in json.loads(long_event().to_line())


SOURCE_ENVS = ("PRE_COMMIT", "PREK_HOOK_STAGE", "CLAUDECODE", "GEMINI_CLI", "CODEX_THREAD_ID")


@pytest.fixture
def agent_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Run as a Claude Code agent with no hook or other agent variables set."""
    for var in SOURCE_ENVS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("CLAUDECODE", "1")


def is_hex(value: object, length: int) -> bool:
    """Return whether value is a lowercase hex string of the given length."""
    return isinstance(value, str) and len(value) == length and set(value) <= set("0123456789abcdef")


def test_events_carry_run_context(
    git_repo: Path,
    stats_dirs: tuple[Path, Path],
    stats_on: None,
    agent_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A pass and a skip record where, how, and on what commit the gate ran."""
    git(
        "remote", "add", "origin", f"https://user:{SECRET}@Example.com/Owner/Repo.git", cwd=git_repo
    )
    sub = git_repo / "sub"
    sub.mkdir()
    monkeypatch.chdir(sub)
    assert run_gate("t", ["true"]) == 0
    assert run_gate("t", ["true"]) == 0
    first, second = read_events(stats_dirs[1])
    machine = (stats_dirs[1] / "machine-id").read_text().strip()
    for event in (first, second):
        assert event["version"] == __version__
        assert event["trigger"] == "agent"
        assert event["agent"] == "claude-code"
        assert event["hook_stage"] is None
        assert event["worktree"] == str(git_repo.resolve())
        assert event["subdir"] == "sub"
        assert event["branch"] == "main"
        assert event["head"] == git("rev-parse", "HEAD", cwd=git_repo)
        assert event["remote"] == "example.com/Owner/Repo"
        assert event["machine"] == machine
        assert event["host"]
        assert event["platform"] == sys.platform
        assert event["command"] == "true"
        assert isinstance(event["overhead"], float)
        assert event["overhead"] >= 0
    assert is_hex(machine, 32)
    assert is_hex(first["id"], 32)
    assert is_hex(second["id"], 32)
    assert first["id"] != second["id"]
    assert first["marker_age"] is None
    assert isinstance(first["cpu"], float)
    assert isinstance(first["max_rss"], int)
    assert first["max_rss"] > 0
    assert isinstance(second["marker_age"], float)
    assert second["marker_age"] >= 0
    assert second["cpu"] is None
    assert second["max_rss"] is None
    assert SECRET not in (stats_dirs[1] / "events.jsonl").read_text()


@pytest.mark.parametrize(
    "url",
    [
        f"git::https://u:{SECRET}@host.example/o/r",
        f"https://tok:12/{SECRET}@github.com/o/r.git",
        f"https:/u:{SECRET}@host.example/o/r",
        f"user:to/{SECRET}@host.example:o/r",
    ],
)
def test_remote_credentials_never_reach_the_inbox(
    git_repo: Path, stats_dirs: tuple[Path, Path], stats_on: None, url: str
) -> None:
    """No remote URL form writes its credentials into an event line."""
    git("remote", "add", "origin", url, cwd=git_repo)
    assert run_gate("t", ["true"]) == 0
    text = (stats_dirs[1] / "events.jsonl").read_text()
    assert SECRET not in text
    (event,) = read_events(stats_dirs[1])
    assert event["remote"] in {None, "host.example/o/r"}


def test_command_is_null_when_name_is_the_command(
    git_repo: Path, stats_dirs: tuple[Path, Path], stats_on: None
) -> None:
    """A gate named by its own command line does not store the command twice."""
    assert run_gate("echo 'a b'", ["echo", "a b"]) == 0
    (event,) = read_events(stats_dirs[1])
    assert event["command"] is None


def test_uncached_event_carries_known_context(
    git_repo: Path,
    stats_dirs: tuple[Path, Path],
    stats_on: None,
    agent_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A run with caching off still records the work tree, branch, commit, and usage."""
    monkeypatch.setenv("GATE_CACHE_DISABLE", "1")
    assert run_gate("t", ["true"]) == 0
    (event,) = read_events(stats_dirs[1])
    assert event["worktree"] == str(git_repo.resolve())
    assert event["subdir"] == "."
    assert event["branch"] == "main"
    assert event["head"] == git("rev-parse", "HEAD", cwd=git_repo)
    assert event["remote"] is None
    assert event["overhead"] is None
    assert event["marker_age"] is None
    assert isinstance(event["cpu"], float)
    assert is_hex(event["machine"], 32)


def test_stats_off_does_no_context_work(
    git_repo: Path, stats_dirs: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """With stats off, no context helper, rusage read, or ID generation runs."""
    called: list[str] = []

    def tripwire(label: str) -> Callable[..., NoReturn]:
        def fail(*_args: object, **_kwargs: object) -> NoReturn:
            called.append(label)
            raise AssertionError(label)

        return fail

    for helper in (
        "detect_source",
        "find_worktree",
        "relative_subdir",
        "worktree_git_dir",
        "read_head",
        "branch_from_head",
        "head_commit",
        "config_remote_url",
        "normalize_remote",
        "machine_id",
        "host_name",
        "child_usage",
    ):
        monkeypatch.setattr(context, helper, tripwire(helper))
    monkeypatch.setattr("gate_cache.gate.stdin_isatty", tripwire("stdin_isatty"))
    monkeypatch.setattr(uuid, "uuid4", tripwire("uuid4"))
    if sys.platform != "win32":
        import resource

        monkeypatch.setattr(resource, "getrusage", tripwire("getrusage"))
    assert run_gate("t", ["true"]) == 0
    assert run_gate("t", ["true"]) == 0
    assert run_gate("f", ["false"]) == 1
    monkeypatch.setenv("GATE_CACHE_DISABLE", "1")
    assert run_gate("t", ["true"]) == 0
    assert called == []
    assert not (stats_dirs[1] / "events.jsonl").exists()
    assert not (stats_dirs[1] / "machine-id").exists()


def test_clear_keeps_machine_id(
    git_repo: Path, stats_dirs: tuple[Path, Path], stats_on: None
) -> None:
    """Clearing stats deletes the events but keeps the machine's identity."""
    from gate_cache.stats.clear import stats_clear

    run_gate("t", ["true"])
    machine = stats_dirs[1] / "machine-id"
    identity = machine.read_text()
    assert stats_clear(confirmed=True) == 0
    assert not (stats_dirs[1] / "events.jsonl").exists()
    assert machine.read_text() == identity


def test_reported_is_encoded_only_when_set() -> None:
    """Verify a reported failure carries `reported`, and other events leave it out."""
    data = json.loads(long_event(host=None, command=None, reported=True).to_line())
    assert data["reported"] is True
    assert "reported" not in json.loads(long_event(host=None, command=None).to_line())
