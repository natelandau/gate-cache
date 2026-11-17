"""Tests for environment flag parsing."""

import pytest

from gate_cache.env import flag_on


@pytest.mark.parametrize(("value", "expected"), [
    ("", False), ("0", False), ("false", False), ("FALSE", False), (" 0 ", False),
    ("1", True), ("yes", True), ("true", True),
])  # fmt: skip
def test_flag_on(value: str, expected: bool) -> None:
    """Empty, 0, and false in any case are off; anything else is on."""
    assert flag_on(value) is expected
