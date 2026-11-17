"""End-to-end tests that run concurrent gate-cache processes on one repository."""

import os
import select
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from gate_cache.gate_lock import GateLock, lock_path
from gate_cache.snapshot import take_snapshot
from gate_cache.stats import config as stats_config

pytestmark = pytest.mark.e2e

_GATE_CACHE = [sys.executable, "-c", "from gate_cache.cli import main; main()"]
_SLOW_COUNTER = """\
import sys, time

with open(sys.argv[1], "a", encoding="utf-8") as counter:
    counter.write("run\\n")
time.sleep(1)
"""


def _wait_for_output(proc: subprocess.Popen[bytes], text: bytes, *, timeout: float) -> bytes:
    """Read the process's stderr until it contains the text or the timeout passes."""
    assert proc.stderr is not None
    seen = b""
    deadline = time.monotonic() + timeout
    while text not in seen:
        remaining = deadline - time.monotonic()
        assert remaining > 0, f"never printed {text!r}: {seen!r}"
        ready, _, _ = select.select([proc.stderr], [], [], remaining)
        if ready:
            chunk = os.read(proc.stderr.fileno(), 4096)
            assert chunk, f"exited before printing {text!r}: {seen!r}"
            seen += chunk
    return seen


def test_two_processes_run_once(git_repo: Path, tmp_path: Path) -> None:
    """Verify two runs of the same gate started at once run the command once."""
    script = tmp_path / "slow.py"
    script.write_text(_SLOW_COUNTER, encoding="utf-8")
    count = tmp_path / "count.txt"
    argv = [*_GATE_CACHE, "--name", "slow", "--", sys.executable, str(script), str(count)]

    procs = [
        subprocess.Popen(argv, cwd=git_repo, stderr=subprocess.PIPE)  # noqa: S603
        for _ in range(2)
    ]
    try:
        results = [proc.communicate(timeout=30) for proc in procs]
    finally:
        for proc in procs:
            proc.kill()
            proc.wait()

    assert [proc.returncode for proc in procs] == [0, 0], results
    assert count.read_text(encoding="utf-8").splitlines() == ["run"]


def test_interrupt_while_waiting_exits_130(
    git_repo: Path, tmp_path: Path, isolate_user_dirs: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify Ctrl-C during a wait exits 130 and records no stats event."""
    monkeypatch.setenv(stats_config.STATS_ENV, "1")
    snap = take_snapshot()
    assert snap.key is not None
    assert snap.common_dir is not None
    lock = GateLock.try_acquire(lock_path(snap.common_dir, snap.key, "slow"))
    assert lock is not None
    argv = [*_GATE_CACHE, "--name", "slow", "--", sys.executable, "-c", "pass"]

    try:
        proc = subprocess.Popen(argv, cwd=git_repo, stderr=subprocess.PIPE)  # noqa: S603
        try:
            _wait_for_output(proc, b"is running in", timeout=15)
            proc.send_signal(signal.SIGINT)
            code = proc.wait(timeout=15)
        finally:
            proc.kill()
            proc.communicate()
    finally:
        lock.release()

    assert code == 130
    assert not (isolate_user_dirs / "events.jsonl").exists()


def test_terminate_while_waiting_exits_143(
    git_repo: Path, tmp_path: Path, isolate_user_dirs: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify SIGTERM during a wait exits 143, as a terminated run does, and records nothing."""
    monkeypatch.setenv(stats_config.STATS_ENV, "1")
    snap = take_snapshot()
    assert snap.key is not None
    assert snap.common_dir is not None
    lock = GateLock.try_acquire(lock_path(snap.common_dir, snap.key, "slow"))
    assert lock is not None
    argv = [*_GATE_CACHE, "--name", "slow", "--", sys.executable, "-c", "pass"]

    try:
        proc = subprocess.Popen(argv, cwd=git_repo, stderr=subprocess.PIPE)  # noqa: S603
        try:
            _wait_for_output(proc, b"is running in", timeout=15)
            proc.send_signal(signal.SIGTERM)
            code = proc.wait(timeout=15)
        finally:
            proc.kill()
            proc.communicate()
    finally:
        lock.release()

    assert code == 143
    assert not (isolate_user_dirs / "events.jsonl").exists()
