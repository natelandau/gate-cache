"""Tests for the distribution check used by the release workflow."""

from __future__ import annotations

import io
import tarfile
import zipfile
from typing import TYPE_CHECKING

import pytest

from tests.tooling import load_script

if TYPE_CHECKING:
    from pathlib import Path

dist_check = load_script("scripts/dist_check.py")


def make_wheel(path: Path, *, missing: tuple[str, ...] = (), padding: int = 0) -> Path:
    """Write a synthetic wheel that ships every required file except those in missing."""
    with zipfile.ZipFile(path, "w", zipfile.ZIP_STORED) as archive:
        archive.writestr("gate_cache/__init__.py", "")
        for required in dist_check.REQUIRED_FILES:
            if required not in missing:
                archive.writestr(required, "x")
        if padding:
            archive.writestr("pad.bin", b"x" * padding)
    return path


def make_sdist(path: Path, *, missing: tuple[str, ...] = ()) -> Path:
    """Write a synthetic sdist that ships every required file except those in missing."""
    names = ["gate_cache-1.0/pyproject.toml"]
    names += [
        f"gate_cache-1.0/src/{required}"
        for required in dist_check.REQUIRED_FILES
        if required not in missing
    ]
    with tarfile.open(path, "w:gz") as archive:
        for name in names:
            data = b"x"
            info = tarfile.TarInfo(name)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
    return path


def test_wheel_with_index_passes(tmp_path: Path) -> None:
    """Verify wheel with index passes."""
    wheel = make_wheel(tmp_path / "a-1.0-py3-none-any.whl")
    lines, problems = dist_check.check_dists((str(tmp_path / "*.whl"),))
    assert problems == []
    assert lines[0].startswith(f"ok: {wheel}")


@pytest.mark.parametrize("missing", list(dist_check.REQUIRED_FILES))
def test_wheel_missing_required_file_fails(tmp_path: Path, missing: str) -> None:
    """Verify a wheel without the dashboard UI or an agent guide fails."""
    make_wheel(tmp_path / "a.whl", missing=(missing,))
    _, problems = dist_check.check_dists((str(tmp_path / "a.whl"),))
    assert problems == [f"{tmp_path / 'a.whl'} is missing {missing}"]


def test_wheel_over_budget_fails(tmp_path: Path) -> None:
    """Verify wheel over budget fails."""
    make_wheel(tmp_path / "a.whl", padding=dist_check.WHEEL_MAX_BYTES + 1)
    _, problems = dist_check.check_dists((str(tmp_path / "a.whl"),))
    assert any("over the" in problem for problem in problems)


def test_sdist_with_index_passes(tmp_path: Path) -> None:
    """Verify sdist with index passes."""
    make_sdist(tmp_path / "a-1.0.tar.gz")
    _, problems = dist_check.check_dists((str(tmp_path / "*.tar.gz"),))
    assert problems == []


@pytest.mark.parametrize("missing", list(dist_check.REQUIRED_FILES))
def test_sdist_missing_required_file_fails(tmp_path: Path, missing: str) -> None:
    """Verify an sdist without the dashboard UI or an agent guide fails."""
    make_sdist(tmp_path / "a.tar.gz", missing=(missing,))
    _, problems = dist_check.check_dists((str(tmp_path / "a.tar.gz"),))
    assert problems == [f"{tmp_path / 'a.tar.gz'} is missing {missing}"]


def test_sdist_size_is_not_budgeted(tmp_path: Path) -> None:
    """Verify sdist size is not budgeted."""
    sdist = make_sdist(tmp_path / "a.tar.gz")
    assert sdist.stat().st_size < dist_check.WHEEL_MAX_BYTES
    _, problems = dist_check.check_dists((str(sdist),))
    assert problems == []


def test_no_match_fails(tmp_path: Path) -> None:
    """Verify no match fails."""
    lines, problems = dist_check.check_dists((str(tmp_path / "*.whl"),))
    assert lines == []
    assert "no distribution matched" in problems[0]


def test_unknown_file_type_fails(tmp_path: Path) -> None:
    """Verify unknown file type fails."""
    other = tmp_path / "a.zip"
    other.write_bytes(b"")
    _, problems = dist_check.check_dists((str(other),))
    assert "neither a wheel nor an sdist" in problems[0]


def test_multiple_paths_are_all_checked(tmp_path: Path) -> None:
    """Verify multiple paths are all checked."""
    make_wheel(tmp_path / "a.whl")
    make_sdist(tmp_path / "a.tar.gz", missing=("gate_cache/agent/skill.md",))
    lines, problems = dist_check.check_dists((str(tmp_path / "*.whl"), str(tmp_path / "*.tar.gz")))
    assert len(lines) + len(problems) == 2


def test_any_unmatched_pattern_fails(tmp_path: Path) -> None:
    """Verify one pattern matching nothing fails even when others match."""
    make_wheel(tmp_path / "a.whl")
    lines, problems = dist_check.check_dists((str(tmp_path / "*.whl"), str(tmp_path / "*.tar.gz")))
    assert len(lines) == 1
    assert problems == [f"no distribution matched: {tmp_path / '*.tar.gz'}"]
