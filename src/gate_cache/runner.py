"""Run the wrapped gate command."""

from __future__ import annotations

import contextlib
import signal
import subprocess
import threading
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from gate_cache.console import say

if TYPE_CHECKING:
    from collections.abc import Generator, Sequence
    from types import FrameType

_EXIT_NOT_EXECUTABLE = 126
_EXIT_NOT_FOUND = 127
_SIGNAL_EXIT_BASE = 128
_FORWARDED_SIGNALS = (signal.SIGTERM, signal.SIGHUP)


@dataclass(frozen=True)
class ChildResult:
    """Outcome of the wrapped command.

    Attributes:
        exit_code: Exit code to propagate, with signal deaths mapped to 128 + signal.
        interrupted: True when gate-cache received SIGINT, SIGTERM, or SIGHUP while the
            child ran.
    """

    exit_code: int
    interrupted: bool


@dataclass
class _SignalState:
    """Signals received while the child runs, and the child to forward them to."""

    proc: subprocess.Popen[bytes] | None = None
    interrupted: bool = False
    pending: list[int] = field(default_factory=list)

    def handle(self, signum: int, _frame: FrameType | None) -> None:
        """Record a signal and forward SIGTERM or SIGHUP to the child."""
        self.interrupted = True
        if self.proc is None:
            # A signal during spawn may predate the fork, so the child never saw it.
            self.pending.append(signum)
        elif signum != signal.SIGINT:
            # SIGINT already reaches a running child through the shared process group. A
            # group-wide TERM or HUP reaches it twice; that beats orphaning it on a direct one.
            _forward(self.proc, signum)

    def attach(self, proc: subprocess.Popen[bytes]) -> None:
        """Set the child and forward any signal that arrived while it was starting."""
        self.proc = proc
        while self.pending:
            _forward(proc, self.pending.pop(0))


def _forward(proc: subprocess.Popen[bytes], signum: int) -> None:
    with contextlib.suppress(OSError):
        proc.send_signal(signum)


@contextlib.contextmanager
def _trap_signals(state: _SignalState) -> Generator[None]:
    """Route SIGINT, SIGTERM, and SIGHUP to state, restoring the previous handlers after.

    Python handlers reset to the default on exec, so the child keeps normal signal
    behavior. Ignored signals stay ignored so the child inherits that disposition, as
    under `nohup` or a background job. Handlers can only be set from the main thread;
    elsewhere signals keep their current disposition.
    """
    if threading.current_thread() is not threading.main_thread():
        yield
        return
    previous = {
        signum: signal.signal(signum, state.handle)
        for signum in (signal.SIGINT, *_FORWARDED_SIGNALS)
        if signal.getsignal(signum) is not signal.SIG_IGN
    }
    try:
        yield
    finally:
        for signum, handler in previous.items():
            # None means a handler installed outside Python, which cannot be reinstated.
            if handler is not None:
                signal.signal(signum, handler)


def run_child(argv: Sequence[str]) -> ChildResult:
    """Run a command with inherited streams and environment, and wait for it.

    The child shares our process group, so Ctrl-C reaches it directly; SIGTERM and SIGHUP
    sent to gate-cache are forwarded to it. Either way gate-cache keeps waiting and
    reports the child's status instead of abandoning it.

    Args:
        argv: Command and arguments to execute.

    Returns:
        The exit code (127 if not found, 126 if it cannot be executed) and whether a
        signal arrived while the child ran.
    """
    state = _SignalState()
    with _trap_signals(state):
        try:
            proc = subprocess.Popen(list(argv))  # noqa: S603
        except FileNotFoundError:
            say(f"command not found: {argv[0]}")
            return ChildResult(_EXIT_NOT_FOUND, interrupted=state.interrupted)
        except PermissionError:
            say(f"permission denied: {argv[0]}")
            return ChildResult(_EXIT_NOT_EXECUTABLE, interrupted=state.interrupted)
        except OSError as error:
            say(f"could not run {argv[0]}: {error}")
            return ChildResult(_EXIT_NOT_EXECUTABLE, interrupted=state.interrupted)
        state.attach(proc)
        code = proc.wait()

    if code < 0:
        code = _SIGNAL_EXIT_BASE - code
    return ChildResult(code, interrupted=state.interrupted)
