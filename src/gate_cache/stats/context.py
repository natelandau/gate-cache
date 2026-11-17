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
from gate_cache.stats.config import STATE_DIR_MODE

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
_GITDIR_PREFIX = "gitdir:"
# SHA-1 and SHA-256 object names.
_COMMIT_RE = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")
_REMOTE_SECTION_RE = re.compile(r'\[\s*remote\s+"((?:[^"\\\n]|\\.)*)"\s*\]', re.IGNORECASE)
_CONFIG_ESCAPES = {"n": "\n", "t": "\t", "b": "\b", "\\": "\\", '"': '"'}
_DEFAULT_PORTS = {
    "ssh": "22",
    "git+ssh": "22",
    "ssh+git": "22",
    "git": "9418",
    "http": "80",
    "https": "443",
}
_HOST_RE = re.compile(r"[a-z0-9]([a-z0-9.-]*[a-z0-9])?|\[[0-9a-f:.]+\]")
_SCHEME_RE = re.compile(r"([A-Za-z][A-Za-z0-9+.-]*)://(.*)", re.DOTALL)
_HELPER_RE = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*::(.*)", re.DOTALL)


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
    """Return the branch a HEAD value points at, or None when detached or not a branch."""
    if head is None or not head.startswith(_REF_PREFIX + _BRANCH_PREFIX):
        return None
    branch = head.removeprefix(_REF_PREFIX + _BRANCH_PREFIX)
    # A reftable repository's HEAD file holds the placeholder `refs/heads/.invalid`, and no
    # valid ref has a component that starts with a dot.
    if not branch or any(part.startswith(".") for part in branch.split("/")):
        return None
    return branch


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


def _config_value(text: str) -> str | None:
    """Decode a git config value: quotes, escapes, comments, and outer whitespace.

    Returns:
        The value, or None when a quote is left open or an escape is unknown.
    """
    out: list[str] = []
    quoted = False
    # Whitespace outside quotes counts only when more value follows it.
    pending = ""
    chars = iter(text)
    for char in chars:
        if char == "\\":
            escaped = next(chars, None)
            if escaped is None or escaped not in _CONFIG_ESCAPES:
                return None
            out.append(pending + _CONFIG_ESCAPES[escaped])
            pending = ""
        elif char == '"':
            quoted = not quoted
            out.append(pending)
            pending = ""
        elif quoted:
            out.append(char)
        elif char in "#;":
            break
        elif char.isspace():
            pending += char if out else ""
        else:
            out.append(pending + char)
            pending = ""
    if quoted:
        return None
    return "".join(out)


def _section_name(raw: str) -> str:
    """Decode the escapes of a quoted subsection name."""
    return re.sub(r"\\(.)", r"\1", raw)


def config_remote_url(common_dir: Path | None) -> str | None:
    """Read the URL of the origin remote, or else the first remote, from a git config file.

    Only `[remote "<name>"]` sections and their `url` key count. Includes, `insteadOf`
    rewrites, and `pushurl` are ignored.

    Args:
        common_dir: Git common directory whose `config` file to read.

    Returns:
        The raw URL, or None when there is no remote or the file cannot be read or parsed.
    """
    if common_dir is None:
        return None
    try:
        text = (common_dir / "config").read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    urls: dict[str, str | None] = {}
    current: str | None = None
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("["):
            match = _REMOTE_SECTION_RE.match(stripped)
            current = _section_name(match.group(1)) if match else None
            if current is not None:
                urls.setdefault(current, None)
            continue
        if current is None or urls[current] is not None:
            continue
        key, sep, value = stripped.partition("=")
        if sep and key.strip().lower() == "url":
            decoded = _config_value(value)
            if decoded is None:
                return None
            urls[current] = decoded
    found = [url for url in urls.values() if url]
    origin = urls.get("origin")
    return origin or (found[0] if found else None)


def _clean_path(path: str) -> str | None:
    """Strip slashes and a `.git` suffix from a repository path, or None when nothing is left."""
    path = path.strip("/").removesuffix(".git").rstrip("/")
    return path or None


def _host_port(authority: str, *, scheme: str) -> str | None:
    """Return the lowercase host with any non-default port, or None when it is not valid."""
    host_port = authority.rpartition("@")[2].lower()
    if host_port.startswith("["):
        host, bracket, rest = host_port.partition("]")
        host += bracket
        if rest and not rest.startswith(":"):
            return None
        port = rest.removeprefix(":")
    else:
        host, _, port = host_port.partition(":")
    if not _HOST_RE.fullmatch(host) or (port and not port.isdigit()):
        return None
    if port and port != _DEFAULT_PORTS.get(scheme):
        return f"{host}:{port}"
    return host


def normalize_remote(url: str) -> str | None:
    """Reduce a remote URL to `host/owner/repo` so clones of one project match.

    Credentials, the user, a default port, and a `.git` suffix are dropped. A
    `<transport>::<address>` remote is reduced from its address. Local paths, `file://` URLs,
    scp-style insteadOf aliases, and any URL whose result could still hold credentials give
    None.

    Args:
        url: The remote URL as written in the git config.

    Returns:
        The normalized remote, or None when the URL does not name a network repository.
    """
    url = url.strip()
    while helper := _HELPER_RE.fullmatch(url):
        url = helper.group(1)
    if match := _SCHEME_RE.fullmatch(url):
        scheme = match.group(1).lower()
        if scheme not in _DEFAULT_PORTS:
            return None
        rest = re.split(r"[?#]", match.group(2), maxsplit=1)[0]
        authority, _, path = rest.partition("/")
        host = _host_port(authority, scheme=scheme)
    else:
        # scp-like `[user@]host:path`: git reads it so only when a colon precedes any slash.
        head, slash, tail = url.partition("/")
        if ":" not in head:
            return None
        user_host = head.rpartition("@")[2]
        if user_host.startswith("["):
            bracketed, sep, path_head = user_host.partition("]:")
            authority = f"{bracketed}]" if sep else ""
        else:
            authority, _, path_head = user_host.partition(":")
        path = path_head + slash + tail
        # A host with no dot is a Windows drive letter or an insteadOf alias such as
        # `gh:`, and neither names the real host.
        is_host = "." in authority or authority.lower() == "localhost" or authority.startswith("[")
        host = _host_port(authority, scheme="ssh") if is_host else None
    cleaned = _clean_path(path)
    # An `@` or `:` left in the path means userinfo the parse did not strip, and `;` or `=`
    # marks path parameters; any of them may carry a credential.
    if host is None or cleaned is None or any(char in cleaned for char in "@:;="):
        return None
    return f"{host}/{cleaned}"


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
            state_dir.mkdir(mode=STATE_DIR_MODE, parents=True, exist_ok=True)
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
