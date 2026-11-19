"""Read a repository's remote URL from its git config and reduce it to `host/owner/repo`."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

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
