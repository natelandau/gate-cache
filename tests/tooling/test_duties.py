"""Tests for the helpers the duties use."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pytest

from tests.tooling import load_duties

if TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.parametrize(
    ("installed_age", "stale"),
    [
        pytest.param(None, True, id="never installed"),
        pytest.param(-100, True, id="lockfile changed after install"),
        pytest.param(100, False, id="installed after lockfile"),
    ],
)
def test_frontend_deps_stale(tmp_path: Path, installed_age: int | None, *, stale: bool) -> None:
    """Verify the frontend dependencies reinstall when missing or older than the lockfile."""
    lockfile = tmp_path / "package-lock.json"
    lockfile.write_text("{}")
    os.utime(lockfile, (1_000, 1_000))
    (tmp_path / "node_modules").mkdir()
    if installed_age is not None:
        installed = tmp_path / "node_modules" / ".package-lock.json"
        installed.write_text("{}")
        os.utime(installed, (1_000 + installed_age, 1_000 + installed_age))

    assert load_duties()._frontend_deps_stale(tmp_path) is stale
