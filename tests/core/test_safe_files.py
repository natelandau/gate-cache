"""Tests for opening and creating files that others cannot redirect."""

import os
from pathlib import Path

import pytest

from gate_cache.safe_files import ensure_private_dir


@pytest.mark.parametrize("unsafe", ["group_writable", "other_writable", "other_owner"])
def test_refuses_a_folder_others_control(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, unsafe: str
) -> None:
    """A folder another user owns or can write to is refused, not used."""
    folder = tmp_path / "state"
    folder.mkdir(mode=0o700)
    if unsafe == "group_writable":
        folder.chmod(0o770)
    elif unsafe == "other_writable":
        folder.chmod(0o703)
    else:
        uid = os.getuid()
        monkeypatch.setattr(os, "getuid", lambda: uid + 1)
    with pytest.raises(PermissionError, match="this directory"):
        ensure_private_dir(folder)


def test_creates_a_missing_folder_readable_only_by_the_user(tmp_path: Path) -> None:
    """A missing folder and its parents are created, and the folder is private."""
    folder = tmp_path / "a" / "state"
    ensure_private_dir(folder)
    assert folder.stat().st_mode & 0o777 == 0o700
