"""Tests for the package version."""

import tomllib

import gate_cache
from tests.conftest import ROOT


def test_version_matches_pyproject():
    """Verify the package version matches the version in pyproject.toml."""
    pyproject = ROOT / "pyproject.toml"
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))

    assert gate_cache.__version__ == data["project"]["version"]
