"""Tests for environment flag parsing."""

from pathlib import Path

import pytest

from gate_cache.env import flag_on, hook_environment


@pytest.mark.parametrize(("value", "expected"), [
    ("", False), ("0", False), ("false", False), ("FALSE", False), (" 0 ", False),
    ("1", True), ("yes", True), ("true", True),
])  # fmt: skip
def test_flag_on(value: str, expected: bool) -> None:
    """Empty, 0, and false in any case are off; anything else is on."""
    assert flag_on(value) is expected


_HOOK = "/cache/hooks/py-env"
_BIN = f"{_HOOK}/bin"


@pytest.mark.parametrize(("environ", "expected"), [
    ({"PATH": f"{_BIN}:/usr/bin:/bin"}, {"PATH": f"/usr/bin:/bin:{_BIN}"}),
    ({"PATH": "/usr/bin:/bin"}, {"PATH": "/usr/bin:/bin"}),
    ({"PATH": f"{_BIN}:/usr/bin:{_BIN}/"}, {"PATH": f"/usr/bin:{_BIN}:{_BIN}/"}),
    ({"PATH": f"{_BIN}::/usr/bin"}, {"PATH": f":/usr/bin:{_BIN}"}),
    ({"PATH": "/usr/bin", "VIRTUAL_ENV": _HOOK}, {"PATH": "/usr/bin"}),
    ({"PATH": "/usr/bin", "VIRTUAL_ENV": f"{_HOOK}/"}, {"PATH": "/usr/bin"}),
    ({"PATH": "/usr/bin", "VIRTUAL_ENV": "/proj/.venv"}, {"PATH": "/usr/bin", "VIRTUAL_ENV": "/proj/.venv"}),
    ({"HOME": "/home/u"}, {"HOME": "/home/u"}),
])  # fmt: skip
def test_hook_environment(environ: dict[str, str], expected: dict[str, str]) -> None:
    """The hook's own bin/ moves behind the user's PATH and its VIRTUAL_ENV is cleared."""
    assert hook_environment(environ=environ, prefix=_HOOK) == expected


def test_hook_environment_tolerates_a_symlink_loop_on_path(tmp_path: Path) -> None:
    """A PATH entry that is a symlink loop stays in place instead of crashing the hook."""
    loop = tmp_path / "loop"
    loop.symlink_to(loop)
    environ = {"PATH": f"{_BIN}:{loop}:/usr/bin"}
    assert hook_environment(environ=environ, prefix=_HOOK) == {"PATH": f"{loop}:/usr/bin:{_BIN}"}
