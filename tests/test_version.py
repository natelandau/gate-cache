"""Tests for the package version."""

import tomllib
from pathlib import Path

import gate_cache


def test_version_matches_pyproject():
    """Verify the package version matches the version in pyproject.toml."""
    pyproject = Path(__file__).parent.parent / "pyproject.toml"
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))

    assert gate_cache.__version__ == data["project"]["version"]
