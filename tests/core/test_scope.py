"""Tests for path-scoped snapshots."""

import hashlib
import re
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from gate_cache.gate import gate_status, run_gate
from gate_cache.snapshot import take_snapshot, take_snapshots
from tests.conftest import (
    ROOT,
    Counter,
    expected_tree,
    git,
    intercept_run_git,
    markers,
    misses,
    read_records,
)


@pytest.fixture
def scoped_repo(git_repo: Path) -> Path:
    """Add a committed src/ directory beside a.txt."""
    (git_repo / "src").mkdir()
    (git_repo / "src" / "app.py").write_text("print('app')\n")
    (git_repo / "src" / "app.just").write_text("x:\n")
    git("add", "src", cwd=git_repo)
    git("commit", "-q", "-m", "src", cwd=git_repo)
    return git_repo


def test_unscoped_key_is_the_tree(scoped_repo: Path) -> None:
    """Verify a snapshot without paths keys on the whole tree."""
    snap = take_snapshot()
    assert snap.scope is None
    assert snap.key == git("rev-parse", "HEAD^{tree}", cwd=scoped_repo)


def test_scope_matches_documented_formula(scoped_repo: Path) -> None:
    """Verify the scope value is the public formula over the ls-files listing."""
    listing = subprocess.run(
        ["git", "ls-files", "--stage", "-z", "--", "src"],  # noqa: S607
        cwd=scoped_repo,
        check=True,
        capture_output=True,
    ).stdout
    digest = hashlib.sha256(b"gate-cache-paths-v1\0src\0\0" + listing).hexdigest()

    snap = take_snapshot(paths=["src"])

    assert snap.key == f"paths:{digest}"
    assert snap.tree == git("rev-parse", "HEAD^{tree}", cwd=scoped_repo)


def test_change_outside_paths_keeps_scope(scoped_repo: Path) -> None:
    """Verify edits and new files outside the paths leave the scope unchanged."""
    before = take_snapshot(paths=["src"]).key
    (scoped_repo / "a.txt").write_text("changed\n")
    (scoped_repo / "notes.md").write_text("new\n")
    assert take_snapshot(paths=["src"]).key == before


@pytest.mark.parametrize(
    "change",
    [
        lambda repo: (repo / "src" / "app.py").write_text("print('changed')\n"),
        lambda repo: (repo / "src" / "new.py").write_text("untracked\n"),
        lambda repo: (repo / "src" / "app.py").chmod(0o755),
    ],
    ids=["edit", "untracked", "mode"],
)
def test_change_inside_paths_changes_scope(
    scoped_repo: Path, change: Callable[[Path], object]
) -> None:
    """Verify an edit, an untracked file, or a mode change inside the paths changes the scope."""
    before = take_snapshot(paths=["src"]).key
    change(scoped_repo)
    assert take_snapshot(paths=["src"]).key != before


def test_path_order_and_duplicates_do_not_matter(scoped_repo: Path) -> None:
    """Verify the same set of paths in any order gives one scope."""
    assert (
        take_snapshot(paths=["src", "a.txt"]).key
        == take_snapshot(paths=["a.txt", "src", "a.txt"]).key
    )


def test_different_paths_with_same_files_differ(scoped_repo: Path) -> None:
    """Verify two path lists that match the same files never share a scope."""
    assert take_snapshot(paths=["src"]).key != take_snapshot(paths=["src/"]).key


def test_paths_resolve_from_the_top(scoped_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify a gate run from a subdirectory gets the same scope as one run from the top."""
    top = take_snapshot(paths=["src"]).key
    monkeypatch.chdir(scoped_repo / "src")
    assert take_snapshot(paths=["src"]).key == top


def test_exclude_pathspec_drops_files(scoped_repo: Path) -> None:
    """Verify a change to an excluded file leaves the scope unchanged."""
    paths = ["src", ":(exclude)src/app.just"]
    before = take_snapshot(paths=paths).key
    (scoped_repo / "src" / "app.just").write_text("changed:\n")
    assert take_snapshot(paths=paths).key == before


def test_glob_pathspec_selects_files(scoped_repo: Path) -> None:
    """Verify a wildcard path scopes to the files it matches."""
    before = take_snapshot(paths=["*.just"]).key
    (scoped_repo / "src" / "app.py").write_text("print('changed')\n")
    assert take_snapshot(paths=["*.just"]).key == before
    (scoped_repo / "src" / "app.just").write_text("changed:\n")
    assert take_snapshot(paths=["*.just"]).key != before


def test_literal_pathspec_env_does_not_change_scope(
    scoped_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify pathspec environment variables cannot change what a path matches."""
    expected = take_snapshot(paths=["*.just"])
    monkeypatch.setenv("GIT_LITERAL_PATHSPECS", "1")
    assert take_snapshot(paths=["*.just"]) == expected


@pytest.mark.parametrize(
    ("paths", "unmatched"),
    [
        (["src", "nope/"], "nope/"),
        (["src/app.py", ":(exclude)src/app.py"], "src/app.py"),
    ],
    ids=["typo", "fully-excluded"],
)
def test_path_matching_nothing_is_unknown(
    scoped_repo: Path, paths: list[str], unmatched: str
) -> None:
    """Verify a path that selects no file makes the key unknown instead of constant."""
    snap = take_snapshot(paths=paths)
    assert snap.key is None
    assert snap.reason is not None
    assert unmatched in snap.reason
    assert "matches no files" in snap.reason


def test_exclude_matching_nothing_is_fine(scoped_repo: Path) -> None:
    """Verify an exclude path that matches nothing does not make the key unknown."""
    assert take_snapshot(paths=["src", ":(exclude)nope/"]).key is not None


def test_path_outside_repository_is_unknown(scoped_repo: Path, tmp_path: Path) -> None:
    """Verify a path git rejects makes the key unknown."""
    snap = take_snapshot(paths=[str(tmp_path / "elsewhere")])
    assert snap.key is None
    assert snap.reason is not None


def test_scoped_gate_skips_after_change_outside_paths(scoped_repo: Path, counter: Counter) -> None:
    """Verify a docs-style change outside the paths lets a scoped gate skip."""
    assert run_gate("t", counter.argv(), paths=["src"]) == 0
    (scoped_repo / "a.txt").write_text("docs\n")
    assert run_gate("t", counter.argv(), paths=["src"]) == 0
    assert counter.count == 1


def test_scoped_gate_reruns_after_change_inside_paths(scoped_repo: Path, counter: Counter) -> None:
    """Verify a change inside the paths runs a scoped gate again."""
    run_gate("t", counter.argv(), paths=["src"])
    (scoped_repo / "src" / "app.py").write_text("print('changed')\n")
    run_gate("t", counter.argv(), paths=["src"])
    assert counter.count == 2


def test_scoped_and_unscoped_markers_never_match(scoped_repo: Path, counter: Counter) -> None:
    """Verify a scoped pass never skips the unscoped gate of the same name, or the reverse."""
    run_gate("t", counter.argv(), paths=["src"])
    run_gate("t", counter.argv())
    assert counter.count == 2
    (scoped_repo / "a.txt").write_text("other\n")
    run_gate("t", counter.argv())
    run_gate("t", counter.argv(), paths=["a.txt"])
    assert counter.count == 4


def test_unmatched_path_runs_uncached(
    scoped_repo: Path, counter: Counter, capfd: pytest.CaptureFixture[str]
) -> None:
    """Verify a path that matches nothing runs every time and records nothing."""
    assert run_gate("t", counter.argv(), paths=["nope/"]) == 0
    assert run_gate("t", counter.argv(), paths=["nope/"]) == 0
    assert counter.count == 2
    assert read_records(markers(scoped_repo)) == []
    assert "--path nope/ matches no files, running without cache" in capfd.readouterr().err


def test_edit_outside_paths_during_run_records_pass(scoped_repo: Path, counter: Counter) -> None:
    """Verify an edit outside the paths while the gate runs does not block its marker."""
    run_gate("t", counter.argv(touch=scoped_repo / "a.txt"), paths=["src"])
    run_gate("t", counter.argv(), paths=["src"])
    assert counter.count == 1


def test_edit_inside_paths_during_run_records_miss(scoped_repo: Path, counter: Counter) -> None:
    """Verify an edit inside the paths while the gate runs records a miss, not a pass."""
    run_gate("t", counter.argv(touch=scoped_repo / "src" / "app.py"), paths=["src"])
    assert read_records(markers(scoped_repo)) == []
    assert [r["reason"] for r in read_records(misses(scoped_repo))] == [
        "files changed during the run"
    ]


def test_scoped_marker_records_paths_and_full_tree(scoped_repo: Path, counter: Counter) -> None:
    """Verify a scoped marker keeps the scope as its tree and adds the paths and full tree."""
    run_gate("t", counter.argv(), paths=["src", "a.txt"])
    (record,) = read_records(markers(scoped_repo))
    assert str(record["tree"]).startswith("paths:")
    assert record["paths"] == ["a.txt", "src"]
    assert record["full_tree"] == git("rev-parse", "HEAD^{tree}", cwd=scoped_repo)


def test_unscoped_marker_is_unchanged(scoped_repo: Path, counter: Counter) -> None:
    """Verify an unscoped marker writes only the keys it always has."""
    run_gate("t", counter.argv())
    (record,) = read_records(markers(scoped_repo))
    assert set(record) == {"tree", "name", "command", "timestamp", "duration"}


def test_status_finds_scoped_pass_after_outside_change(scoped_repo: Path, counter: Counter) -> None:
    """Verify status --path reports a scoped hit after a change outside the paths."""
    run_gate("t", counter.argv(), paths=["src"])
    (scoped_repo / "a.txt").write_text("docs\n")
    report, code = gate_status("t", paths=["src"])
    assert code == 0
    assert report["result"] == "hit"
    assert report["tree"].startswith("paths:")
    assert report["paths"] == ["src"]
    assert report["full_tree"] == expected_tree(scoped_repo)


def test_status_reports_paths_and_scope(scoped_repo: Path, counter: Counter) -> None:
    """Verify the report names the paths and the scope it looked up."""
    run_gate("t", counter.argv(), paths=["src", "a.txt"])
    report, code = gate_status("t", paths=["src", "a.txt"])
    assert code == 0
    assert report["paths"] == ["a.txt", "src"]
    assert re.fullmatch(r"paths:[0-9a-f]{64}", report["tree"])


def test_status_without_paths_ignores_scoped_pass(scoped_repo: Path, counter: Counter) -> None:
    """Verify status --name alone looks up only the unscoped gate."""
    run_gate("t", counter.argv(), paths=["src"])
    assert gate_status("t")[1] == 1


def test_status_unmatched_path_is_a_miss(scoped_repo: Path) -> None:
    """Verify status explains a path that matches nothing."""
    report, code = gate_status("t", paths=["nope/"])
    assert code == 1
    assert report["result"] == "miss"
    assert report["reason"] == "--path nope/ matches no files"


def test_status_listing_includes_scoped_gates(scoped_repo: Path, counter: Counter) -> None:
    """Verify the plain listing reports scoped passes and misses on the current content."""
    run_gate("scoped-pass", counter.argv(), paths=["src"])
    run_gate("scoped-fail", counter.argv(exit_code=1), paths=["a.txt"])
    run_gate("plain", counter.argv())
    (scoped_repo / "a.txt").write_text("docs\n")

    report, code = gate_status()

    assert code == 0
    assert report["passed"] == ["scoped-pass"]
    assert report["missed"] == []


def test_status_listing_includes_scoped_misses(scoped_repo: Path, counter: Counter) -> None:
    """Verify the plain listing reports a scoped miss whose paths did not change."""
    run_gate("scoped-fail", counter.argv(exit_code=1), paths=["src"])
    (scoped_repo / "a.txt").write_text("docs\n")

    report, code = gate_status()

    assert code == 1
    assert [m["name"] for m in report["missed"]] == ["scoped-fail"]


def _doc_snippet(marker_text: str) -> str:
    """Return the bash block in the marker format page that contains marker_text."""
    doc = (ROOT / "docs" / "reference" / "marker-format.md").read_text()
    blocks = re.findall(r"```bash\n(.*?)```", doc, flags=re.DOTALL)
    (block,) = [b for b in blocks if marker_text in b]
    return block


def test_documented_shell_snippet_finds_the_scoped_marker(
    scoped_repo: Path, counter: Counter
) -> None:
    """Verify the marker format snippet computes the marker path of a scoped gate."""
    (scoped_repo / "tests").mkdir()
    (scoped_repo / "tests" / "test_app.py").write_text("def test_app(): pass\n")
    run_gate("pytest", counter.argv(), paths=["tests", "src"])
    (scoped_repo / "notes.md").write_text("outside the paths\n")

    script = _doc_snippet("gate-cache-paths-v1") + '\nprintf "%s" "$marker"\n'
    marker = subprocess.run(  # noqa: S603
        ["bash", "-c", script],  # noqa: S607
        cwd=scoped_repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout

    assert [Path(marker).resolve()] == [path.resolve() for path in markers(scoped_repo)]


def test_status_names_paths_when_they_match_nothing(scoped_repo: Path) -> None:
    """Verify the report shows the paths and why the lookup failed."""
    report, code = gate_status("t", paths=["nope/"])
    assert code == 1
    assert report["paths"] == ["nope/"]
    assert report["tree"] is None
    assert report["reason"] == "--path nope/ matches no files"
    assert report["full_tree"] == expected_tree(scoped_repo)


def test_status_listing_skips_paths_that_no_longer_match(
    scoped_repo: Path, counter: Counter
) -> None:
    """Verify a recorded path list that matches nothing now drops out of the listing."""
    run_gate("gone", counter.argv(), paths=["src/app.just"])
    run_gate("kept", counter.argv(), paths=["src/app.py"])
    (scoped_repo / "src" / "app.just").unlink()

    report, code = gate_status()

    assert code == 0
    assert report["passed"] == ["kept"]


def test_undecodable_listing_leaves_other_path_sets_known(
    scoped_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify a path set whose listing cannot decode leaves the whole-tree key known."""

    def undecodable_listing(args: tuple[str, ...], _kwargs: dict[str, Any]) -> None:
        if "--error-unmatch" in args:
            b"\xff".decode()

    intercept_run_git(monkeypatch, undecodable_listing)
    whole, scoped = take_snapshots([(), ("src",)])
    assert whole.key == expected_tree(scoped_repo)
    assert scoped.key is None
    assert scoped.tree == whole.tree
    assert scoped.reason == "could not match --path: output is not UTF-8"


def test_status_listing_reads_each_record_once(
    scoped_repo: Path, counter: Counter, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify the listing parses each marker and miss file once, however many keys it checks."""
    from gate_cache import markers as markers_module

    run_gate("scoped", counter.argv(), paths=["src"])
    run_gate("failing", counter.argv(exit_code=1), paths=["a.txt"])
    run_gate("plain", counter.argv())
    files = len(markers(scoped_repo)) + len(misses(scoped_repo))
    real = markers_module.read_record
    reads: list[Path] = []

    def counting(path: Path) -> dict[str, object] | None:
        reads.append(path)
        return real(path)

    monkeypatch.setattr(markers_module, "read_record", counting)
    gate_status()
    assert len(reads) == files
