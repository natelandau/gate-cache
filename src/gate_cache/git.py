"""Run git subcommands and capture their output."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping


class GitError(Exception):
    """Base class for every error raised while running git."""


class GitNotFoundError(GitError):
    """Raised when the git executable is not on PATH."""


class GitFailedError(GitError):
    """Raised when git cannot start in the requested directory or exits with an error."""


@dataclass(frozen=True, slots=True)
class GitResult:
    """The exit code and decoded output of a finished git command.

    Attributes:
        returncode: The exit code of the git process.
        stdout: Standard output with trailing newlines removed.
        stderr: Standard error with trailing newlines removed.
    """

    returncode: int
    stdout: str
    stderr: str


def run_git(
    *args: str,
    cwd: Path | str | None = None,
    env: Mapping[str, str] | None = None,
    check: bool = True,
) -> GitResult:
    """Run `git` with the given arguments and return its decoded output.

    Output is decoded as strict UTF-8 from raw bytes. Text mode would use the locale
    encoding and translate carriage returns in NUL-delimited path listings.

    Args:
        *args: The git subcommand and its arguments.
        cwd: Directory to run git in. None inherits the process working directory.
        env: Environment that replaces the inherited one, or None to inherit it.
        check: Raise GitFailedError when git exits with a non-zero code.

    Returns:
        The exit code and output of the command.

    Raises:
        GitNotFoundError: git is not on PATH.
        GitFailedError: cwd is not a directory, git cannot start, or git fails under check.
        UnicodeDecodeError: git printed output that is not valid UTF-8.
    """
    argv = ["git", *args]
    resolved: Path | None = None
    if cwd is not None:
        resolved = Path(cwd).expanduser().resolve()
        # Popen reports a missing cwd as FileNotFoundError, the same as a missing git.
        if not resolved.is_dir():
            msg = f"Cannot enter directory {resolved}: not a directory"
            raise GitFailedError(msg)
    try:
        proc = subprocess.run(  # noqa: S603
            argv,
            cwd=resolved,
            env=dict(env) if env is not None else None,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            check=False,
        )
    except FileNotFoundError as e:
        msg = "git not found on PATH"
        raise GitNotFoundError(msg) from e
    except OSError as e:
        msg = f"Failed to start git: {e}"
        raise GitFailedError(msg) from e

    result = GitResult(
        returncode=proc.returncode,
        stdout=proc.stdout.decode("utf-8").rstrip("\n"),
        stderr=proc.stderr.decode("utf-8").rstrip("\n"),
    )
    if check and result.returncode != 0:
        msg = f"git {' '.join(args)} failed with exit code {result.returncode}: {result.stderr}"
        raise GitFailedError(msg)
    return result
