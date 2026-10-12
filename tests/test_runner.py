"""Tests for the child process runner."""

import os
import signal
import sys
import time
from collections.abc import Callable
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from gate_cache.runner import ChildResult, run_child


def test_exit_zero() -> None:
    """Exit zero."""
    assert run_child([sys.executable, "-c", "pass"]) == ChildResult(0, interrupted=False)


def test_exit_code_passes_through() -> None:
    """Exit code passes through."""
    assert run_child([sys.executable, "-c", "import sys; sys.exit(3)"]).exit_code == 3


def test_signal_maps_to_128_plus_signal() -> None:
    """Signal maps to 128 plus signal."""
    code = "import os, signal; os.kill(os.getpid(), signal.SIGTERM)"
    assert run_child([sys.executable, "-c", code]).exit_code == 143


def test_missing_executable_returns_127(capfd: pytest.CaptureFixture[str]) -> None:
    """Missing executable returns 127."""
    result = run_child(["definitely-not-a-command-xyz"])
    assert result.exit_code == 127
    assert "command not found" in capfd.readouterr().err


def test_not_executable_returns_126(tmp_path: Path, capfd: pytest.CaptureFixture[str]) -> None:
    """Non-executable file returns 126."""
    script = tmp_path / "script.sh"
    script.write_text("#!/bin/sh\n")
    result = run_child([str(script)])
    assert result.exit_code == 126
    assert "permission denied" in capfd.readouterr().err


def test_output_is_inherited(capfd: pytest.CaptureFixture[str]) -> None:
    """Output is inherited."""
    run_child([sys.executable, "-c", "print('hello')"])
    assert "hello" in capfd.readouterr().out


def test_other_spawn_error_returns_126(capfd: pytest.CaptureFixture[str]) -> None:
    """Any other OSError from spawning returns 126 and names the command."""
    with patch("gate_cache.runner.subprocess.Popen", side_effect=OSError(8, "Exec format error")):
        result = run_child(["weird-binary"])
    assert result == ChildResult(126, interrupted=False)
    assert "gate-cache: could not run weird-binary: " in capfd.readouterr().err


_SIGNAL_PARENT = """\
import os, signal, sys, time
os.kill(os.getppid(), getattr(signal, sys.argv[1]))
time.sleep(float(sys.argv[2]))
"""


def test_sigint_keeps_waiting_and_flags() -> None:
    """SIGINT to gate-cache alone does not abandon the child; its status is reported."""
    result = run_child([sys.executable, "-c", _SIGNAL_PARENT, "SIGINT", "0.3"])
    assert result == ChildResult(0, interrupted=True)


@pytest.mark.parametrize(("name", "code"), [("SIGTERM", 143), ("SIGHUP", 129)])
def test_terminating_signal_is_forwarded_to_child(name: str, code: int) -> None:
    """SIGTERM and SIGHUP sent to gate-cache reach the child, whose status is reported."""
    started = time.monotonic()
    result = run_child([sys.executable, "-c", _SIGNAL_PARENT, name, "30"])
    assert result == ChildResult(code, interrupted=True)
    assert time.monotonic() - started < 15


def test_signal_handlers_are_restored() -> None:
    """The previous handlers are back in place after the child exits."""
    before = {s: signal.getsignal(s) for s in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)}
    run_child([sys.executable, "-c", _SIGNAL_PARENT, "SIGTERM", "30"])
    assert {s: signal.getsignal(s) for s in before} == before


@pytest.mark.parametrize("signum", [signal.SIGTERM, signal.SIGHUP])
def test_signal_during_spawn_is_forwarded(signum: int) -> None:
    """A signal that arrives before Popen returns is forwarded once the child exists."""
    proc = MagicMock()
    proc.wait.return_value = -signum

    def spawn(_argv: list[str]) -> MagicMock:
        os.kill(os.getpid(), signum)
        return proc

    with patch("gate_cache.runner.subprocess.Popen", side_effect=spawn):
        result = run_child(["anything"])
    proc.send_signal.assert_called_once_with(signum)
    assert result == ChildResult(128 + signum, interrupted=True)


def test_sigint_during_spawn_is_forwarded() -> None:
    """Ctrl-C during spawn is forwarded once the child exists, and gate-cache still waits."""
    proc = MagicMock()
    proc.wait.return_value = 130

    def spawn(_argv: list[str]) -> MagicMock:
        os.kill(os.getpid(), signal.SIGINT)
        return proc

    with patch("gate_cache.runner.subprocess.Popen", side_effect=spawn):
        result = run_child(["anything"])
    proc.wait.assert_called_once_with()
    proc.send_signal.assert_called_once_with(signal.SIGINT)
    assert result == ChildResult(130, interrupted=True)


def test_spawn_failure_with_queued_signal_returns_spawn_code() -> None:
    """A signal queued during a failed spawn still yields the spawn error code."""

    def spawn(_argv: list[str]) -> None:
        os.kill(os.getpid(), signal.SIGTERM)
        raise FileNotFoundError

    with patch("gate_cache.runner.subprocess.Popen", side_effect=spawn):
        result = run_child(["missing"])
    assert result == ChildResult(127, interrupted=True)


_REPORT_IGNORED = """\
import signal
print(",".join(str(signal.getsignal(s) is signal.SIG_IGN) for s in (signal.SIGINT, signal.SIGHUP)))
"""


def test_ignored_signals_stay_ignored_in_child(capfd: pytest.CaptureFixture[str]) -> None:
    """Verify signals ignored by gate-cache's caller, as under nohup, stay ignored in the child."""
    previous = {s: signal.signal(s, signal.SIG_IGN) for s in (signal.SIGINT, signal.SIGHUP)}
    try:
        assert run_child([sys.executable, "-c", _REPORT_IGNORED]).exit_code == 0
        assert {s: signal.getsignal(s) for s in previous} == dict.fromkeys(previous, signal.SIG_IGN)
    finally:
        for signum, handler in previous.items():
            signal.signal(signum, handler)
    assert "True,True" in capfd.readouterr().out


def test_restore_skips_handlers_set_outside_python(monkeypatch: pytest.MonkeyPatch) -> None:
    """A previous handler Python cannot reinstate does not break the restore."""
    real_signal = signal.signal
    original = signal.getsignal(signal.SIGHUP)

    def fake_signal(signum: int, handler: signal.Handlers | Callable[..., object] | None) -> object:
        if handler is None:
            msg = "cannot install None"
            raise TypeError(msg)
        previous = real_signal(signum, handler)
        return None if signum == signal.SIGHUP else previous

    monkeypatch.setattr("gate_cache.runner.signal.signal", fake_signal)
    try:
        assert run_child([sys.executable, "-c", "pass"]) == ChildResult(0, interrupted=False)
    finally:
        real_signal(signal.SIGHUP, original)
