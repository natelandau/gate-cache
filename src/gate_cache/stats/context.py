"""Describe where and how a gate ran, for the stats event.

Everything here runs only while stats are on, on every gate run including skips, so it
reads files directly and never starts a subprocess.
"""

from __future__ import annotations

import errno
import os
import re
import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from gate_cache.env import CI_ENV, flag_on
from gate_cache.safe_files import ensure_private_dir

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

Trigger = Literal["hook", "agent", "ci", "terminal", "other"]

# pre-commit and prek both export PRE_COMMIT=1 to every hook they run.
_HOOK_ENV = "PRE_COMMIT"
# prek names the stage; pre-commit exports no stage variable.
_HOOK_STAGE_ENV = "PREK_HOOK_STAGE"
# Claude Code and Gemini CLI set their variable to 1 in the shells they start. Codex CLI
# sets its variable to the thread ID, so any value counts.
_AGENT_ENVS = (("CLAUDECODE", "claude-code"), ("GEMINI_CLI", "gemini-cli"))
_AGENT_ID_ENVS = (("CODEX_THREAD_ID", "codex"),)

MACHINE_ID_FILE = "machine-id"
# Temp files that _create_machine_id leaves behind when a run is killed mid-create.
MACHINE_ID_TEMP_GLOB = f".{MACHINE_ID_FILE}.*"
_MACHINE_ID_RE = re.compile(r"[0-9a-f]{32}")
_MACHINE_ID_MODE = 0o600
# Errors that mean the file system has no hard links, as opposed to a failing disk.
_NO_HARD_LINK_ERRNOS = frozenset({errno.EPERM, errno.ENOTSUP, errno.EOPNOTSUPP, errno.EXDEV})

_REF_PREFIX = "ref: "
_BRANCH_PREFIX = "refs/heads/"
# What `git check-ref-format --branch` rejects anywhere in a name: control characters, space,
# `~^:?*[\`, `..`, `@{`, and `//`.
_BAD_IN_BRANCH = re.compile(r"[\x00-\x20\x7f~^:?*\[\\]|\.\.|@\{|//")
_GITDIR_PREFIX = "gitdir:"
# SHA-1 and SHA-256 object names.
_COMMIT_RE = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")


@dataclass(frozen=True)
class Source:
    """What started a gate run.

    Attributes:
        trigger: hook, agent, ci, terminal, or other.
        agent: The coding agent's name, when the trigger is an agent.
        hook_stage: The git hook stage, when a hook manager names it.
    """

    trigger: Trigger
    agent: str | None = None
    hook_stage: str | None = None


def detect_source(environ: Mapping[str, str], *, isatty: bool) -> Source:
    """Name what started a gate run, so stats can tell hooks, agents, and people apart.

    The first match wins: CI, then a pre-commit or prek hook, then a coding agent, then
    an interactive terminal.

    Args:
        environ: Environment of the run.
        isatty: Whether standard input is a terminal.

    Returns:
        The trigger, with the agent or hook stage when one applies.
    """
    if flag_on(environ.get(CI_ENV, "")):
        return Source(trigger="ci")
    if flag_on(environ.get(_HOOK_ENV, "")):
        return Source(trigger="hook", hook_stage=environ.get(_HOOK_STAGE_ENV, "").strip() or None)
    for variable, agent in _AGENT_ENVS:
        if flag_on(environ.get(variable, "")):
            return Source(trigger="agent", agent=agent)
    for variable, agent in _AGENT_ID_ENVS:
        if environ.get(variable, "").strip():
            return Source(trigger="agent", agent=agent)
    return Source(trigger="terminal" if isatty else "other")


def find_worktree(start: Path) -> Path | None:
    """Return the nearest directory at or above start that holds a `.git` entry.

    Args:
        start: Directory to search from.

    Returns:
        The top of the working tree, or None when no `.git` entry exists above start.
    """
    try:
        resolved = start.resolve()
        return next(
            (path for path in (resolved, *resolved.parents) if (path / ".git").exists()), None
        )
    except (OSError, RuntimeError):
        return None


def relative_subdir(cwd: Path, *, worktree: Path | None) -> str | None:
    """Return cwd relative to the top of the working tree, in POSIX form.

    Args:
        cwd: The working directory of the run.
        worktree: Top of the working tree.

    Returns:
        `.` at the top, the relative path below it, or None outside it or when unknown.
    """
    if worktree is None or not cwd.is_relative_to(worktree):
        return None
    return cwd.relative_to(worktree).as_posix()


def worktree_git_dir(worktree: Path | None) -> Path | None:
    """Return the git directory of a working tree from its `.git` directory or file.

    Args:
        worktree: Top of the working tree.

    Returns:
        The git directory, or None when it cannot be found.
    """
    if worktree is None:
        return None
    dot_git = worktree / ".git"
    try:
        if dot_git.is_dir():
            return dot_git
        text = dot_git.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError):
        return None
    if not text.startswith(_GITDIR_PREFIX):
        return None
    # A linked worktree's `.git` file holds `gitdir: <path>`, relative to the working tree.
    return worktree / text.removeprefix(_GITDIR_PREFIX).strip()


def read_head(git_dir: Path | None) -> str | None:
    """Return the stripped content of a git directory's HEAD file, or None when unreadable."""
    if git_dir is None:
        return None
    try:
        return (git_dir / "HEAD").read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError):
        return None


def branch_from_head(head: str | None) -> str | None:
    """Return the branch a HEAD value points at, or None when detached or not a branch.

    The HEAD file is read without git, so its value is checked against git's own branch
    name rules before it is stored or shown.
    """
    if head is None or not head.startswith(_REF_PREFIX + _BRANCH_PREFIX):
        return None
    branch = head.removeprefix(_REF_PREFIX + _BRANCH_PREFIX)
    return branch if _valid_branch(branch) else None


def _valid_branch(branch: str) -> bool:
    """Return whether git accepts a name as a branch, per `git check-ref-format --branch`."""
    if not branch or branch == "@" or branch.startswith(("-", "/")):
        return False
    if branch.endswith(("/", ".")) or _BAD_IN_BRANCH.search(branch):
        return False
    # A reftable repository's HEAD file holds the placeholder `refs/heads/.invalid`, which the
    # leading-dot rule rejects.
    return not any(part.startswith(".") or part.endswith(".lock") for part in branch.split("/"))


def _commit(value: str) -> str | None:
    """Return value when it is a full lowercase object name, else None."""
    return value if _COMMIT_RE.fullmatch(value) else None


def _packed_ref(common_dir: Path, ref: str) -> str | None:
    """Look a ref up in packed-refs, or None when it is not there."""
    for line in (common_dir / "packed-refs").read_text(encoding="utf-8").splitlines():
        value, _, name = line.partition(" ")
        if name == ref:
            return value
    return None


def head_commit(head: str | None, *, common_dir: Path | None) -> str | None:
    """Resolve a HEAD value to its commit by reading ref files, without running git.

    Branch refs live in the common directory, which linked worktrees share.

    Args:
        head: Content of the HEAD file.
        common_dir: Git common directory that holds the refs.

    Returns:
        The commit hash, or None when it cannot be resolved or is not a valid hash.
    """
    if head is None:
        return None
    if not head.startswith(_REF_PREFIX):
        return _commit(head)
    ref = head.removeprefix(_REF_PREFIX)
    if common_dir is None or not ref.startswith(_BRANCH_PREFIX) or ".." in ref.split("/"):
        return None
    try:
        try:
            value = (common_dir / ref).read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            value = _packed_ref(common_dir, ref)
    except (OSError, UnicodeDecodeError):
        return None
    return _commit(value) if value is not None else None


def max_rss_bytes(value: int, *, platform: str) -> int:
    """Convert a `ru_maxrss` value to bytes: macOS reports bytes, other systems KiB.

    Args:
        value: The `ru_maxrss` field.
        platform: `sys.platform` of the system that reported it.

    Returns:
        The peak resident set size in bytes.
    """
    return value if platform == "darwin" else value * 1024


@dataclass(frozen=True)
class ChildUsage:
    """Resource use of every finished child process so far.

    Attributes:
        cpu: User plus system CPU seconds.
        max_rss: Peak resident set size of the largest child, in bytes.
    """

    cpu: float
    max_rss: int


def child_usage() -> ChildUsage | None:
    """Read the resource use of finished children, or None where the platform has no rusage."""
    try:
        import resource

        usage = resource.getrusage(resource.RUSAGE_CHILDREN)
    except (ImportError, OSError, ValueError):
        return None
    return ChildUsage(
        cpu=usage.ru_utime + usage.ru_stime,
        max_rss=max_rss_bytes(usage.ru_maxrss, platform=sys.platform),
    )


def _read_machine_id(path: Path) -> str | None:
    """Return the ID stored in path, or None when it does not hold a valid ID."""
    value = path.read_text(encoding="utf-8").strip()
    return value if _MACHINE_ID_RE.fullmatch(value) else None


def _create_machine_id(path: Path) -> str | None:
    """Create the ID file atomically, or read the ID that a concurrent run created first."""
    import uuid

    value = uuid.uuid4().hex
    temp = path.with_name(f".{path.name}.{os.getpid()}.{value}")
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, _MACHINE_ID_MODE)
    try:
        try:
            _write_all(fd, data=f"{value}\n".encode())
        finally:
            os.close(fd)
        try:
            # A hard link never replaces an existing file, so the first run to land wins.
            path.hardlink_to(temp)
        except FileExistsError:
            return _read_machine_id(path)
        except OSError as error:
            if error.errno not in _NO_HARD_LINK_ERRNOS:
                raise
            return _create_machine_id_exclusive(path, value=value)
    finally:
        temp.unlink(missing_ok=True)
    return value


def _write_all(fd: int, *, data: bytes) -> None:
    """Write data in one call, treating a short write as a failure.

    Raises:
        OSError: If the write fails or stores only part of data.
    """
    written = os.write(fd, data)
    if written != len(data):
        msg = f"wrote {written} of {len(data)} bytes"
        raise OSError(msg)


def _create_machine_id_exclusive(path: Path, *, value: str) -> str | None:
    """Create the ID file in place for file systems without hard links.

    A concurrent reader can see the file before its single write lands; that run records no
    ID, and the file is whole for every later run. A failed write removes the file, since an
    invalid ID file is never replaced.
    """
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, _MACHINE_ID_MODE)
    except FileExistsError:
        return _read_machine_id(path)
    try:
        try:
            _write_all(fd, data=f"{value}\n".encode())
        finally:
            os.close(fd)
    except OSError:
        path.unlink(missing_ok=True)
        raise
    return value


def machine_id(state_dir: Path) -> str | None:
    """Return the random ID that ties events to this machine, creating it on first use.

    A file that does not hold a valid ID is left as it is, so no run replaces an identity
    another run may have recorded.

    Args:
        state_dir: The stats data directory that holds the `machine-id` file.

    Returns:
        The 32-character hex ID, or None when it cannot be read or created.
    """
    path = state_dir / MACHINE_ID_FILE
    try:
        try:
            return _read_machine_id(path)
        except FileNotFoundError:
            ensure_private_dir(state_dir)
            return _create_machine_id(path)
    except (OSError, UnicodeDecodeError):
        return None


def host_name() -> str | None:
    """Return the machine's host name as a display label, or None when it cannot be read."""
    try:
        return os.uname().nodename or None
    except AttributeError:
        # Windows has no uname; socket costs an import, so it is only the fallback.
        import socket

        try:
            return socket.gethostname() or None
        except OSError:
            return None
    except OSError:
        return None
