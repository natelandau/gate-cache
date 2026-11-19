"""Where the user config file lives and how to read a key for the current repo."""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, TypeVar

from platformdirs import user_config_path

from gate_cache.console import say
from gate_cache.git import GitError, git_common_dir, run_git
from gate_cache.remote import config_remote_url, normalize_remote

if TYPE_CHECKING:
    from collections.abc import Callable

_APP = "gate-cache"
_T = TypeVar("_T")
# Far beyond any real setting, and small enough to add to a float clock without overflow.
MAX_WHOLE_NUMBER = 10**15


def config_path() -> Path:
    """Return the path of the user config file."""
    return user_config_path(_APP, appauthor=False) / "config.toml"


_PROJECTS_KEY = "projects"
KNOWN_KEYS = frozenset(
    {"stats_enabled", "stats_data_dir", "wait_timeout", "wait_on_failure", "spot_check_one_run_in"}
)
_TABLE_EXAMPLE = '[projects."github.com/owner/repo"]'
_Stamp = tuple[Path, int, int]
_FileKey = tuple[int, int] | None


def table_location(pattern: str | None) -> str:
    """Name a top-level key or a `[projects]` table in a message about the config file."""
    if pattern is None:
        return "the config file"
    return f'[projects."{pattern}"] in the config file'


@dataclass(frozen=True)
class ConfigEntry:
    """One value of a key, and the `[projects]` table that set it.

    Attributes:
        value: The raw value from the file.
        table: The table's pattern, or None for a top-level key.
    """

    value: object
    table: str | None


@dataclass(frozen=True)
class _RepoIdentity:
    """What a `[projects]` pattern is matched against."""

    paths: tuple[str, ...]
    remote: str | None


@dataclass(frozen=True)
class _Table:
    """One well-formed `[projects]` table, with its pattern ready to match."""

    pattern: str
    forms: tuple[str, ...]
    values: dict[str, object]

    @property
    def is_path(self) -> bool:
        return self.pattern.startswith(("/", "~"))

    @property
    def rank(self) -> tuple[bool, int, str]:
        """Exact beats a glob, then more fixed characters, then the text."""
        form = self.forms[0]
        return ("*" not in form, len(form) - form.count("*"), form)


@dataclass(frozen=True)
class _Loaded:
    stamp: _Stamp
    data: dict[str, object]
    tables: list[_Table]


_loaded: _Loaded | None = None
# Each entry keeps the stat of the file that invalidates it, the git config file for a
# repo, so a long-running dashboard sees a new remote.
_identities: dict[Path, tuple[Path, _FileKey, _RepoIdentity]] = {}
_matches: tuple[tuple[_Stamp, _RepoIdentity], list[_Table]] | None = None
_warned: set[str] = set()


def _load() -> _Loaded | None:
    """Return the parsed config file, or None when it is missing or invalid."""
    global _loaded  # noqa: PLW0603
    path = config_path()
    try:
        info = path.stat()
    except OSError:
        return None
    # A recorded gate run looks keys up several times; re-parse only when the file
    # changes, so a long-running dashboard still sees edits.
    stamp = (path, info.st_mtime_ns, info.st_size)
    if _loaded is not None and _loaded.stamp == stamp:
        return _loaded
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
        return None
    _warned.clear()
    _loaded = _Loaded(stamp=stamp, data=data, tables=_valid_tables(data))
    return _loaded


def _warn_once(message: str) -> None:
    """Print a warning once for each version of the config file."""
    if message not in _warned:
        _warned.add(message)
        say(message)


def current_dir() -> Path | None:
    """Return the resolved working directory, or None when it is gone."""
    try:
        return Path.cwd().resolve()
    except (OSError, RuntimeError):
        return None


def expand_user(value: str) -> Path:
    """Expand a leading `~`, keeping the value as written when no home can be found.

    A shell leaves `~unknown-user` as written too, so an unresolvable value never stops
    a command with a traceback.
    """
    path = Path(value)
    try:
        return path.expanduser()
    except RuntimeError:
        return path


def _file_key(path: Path) -> _FileKey:
    try:
        info = path.stat()
    except OSError:
        return None
    return (info.st_mtime_ns, info.st_size)


def _repo_identity(cwd: Path) -> _RepoIdentity:
    """Return the main checkout path and normalized remote of the repo that holds cwd."""
    cached = _identities.get(cwd)
    if cached is not None and _file_key(cached[0]) == cached[1]:
        return cached[2]
    common = git_common_dir(cwd)
    if common is None:
        identity = _RepoIdentity(paths=(), remote=None)
        # Watch for a `git init` or clone into cwd, so a long-running process notices it.
        _identities[cwd] = (cwd / ".git", _file_key(cwd / ".git"), identity)
        return identity
    if common.name == ".git":
        # Linked worktrees share the main checkout's common dir, so they match its path.
        paths = _path_forms(str(common.parent))
    else:
        # A submodule, a separate git dir, or a bare repo keeps its git files away from the
        # checkout, so match both the checkout and the git dir that its worktrees share.
        try:
            result = run_git("rev-parse", "--show-toplevel", cwd=cwd, check=False)
        except (GitError, UnicodeDecodeError):
            top = ""
        else:
            top = result.stdout.strip() if result.returncode == 0 else ""
        paths = tuple(
            dict.fromkeys((*(_path_forms(top) if top else ()), *_path_forms(str(common))))
        )
    url = config_remote_url(common)
    remote = normalize_remote(url) if url else None
    identity = _RepoIdentity(
        paths=paths,
        remote=remote.casefold() if remote else None,
    )
    _identities[cwd] = (common / "config", _file_key(common / "config"), identity)
    return identity


def _path_forms(path: str) -> tuple[str, ...]:
    """Return an expanded path or path pattern as written and with its fixed part resolved.

    Comparing both forms lets a pattern written through a symlink, such as macOS `/tmp`,
    match the real checkout, and the reverse.
    """
    cut = next((i for i, char in enumerate(path) if char == "*"), None)
    try:
        if cut is None:
            resolved = str(Path(path).resolve())
        else:
            base = path[:cut].rpartition("/")[0] or "/"
            resolved = str(Path(base).resolve()).rstrip("/") + path[len(base.rstrip("/")) :]
    except (OSError, RuntimeError, ValueError):
        resolved = path
    return tuple(dict.fromkeys((path, resolved)))


def _pattern_forms(pattern: str) -> tuple[str, ...] | None:
    """Return what a pattern matches against, or warn and return None when it never can."""
    where = table_location(pattern)
    if "\0" in pattern:
        _warn_once(f"warning: ignoring {where}; the pattern holds a NUL character")
        return None
    if pattern.startswith(("/", "~")):
        expanded = str(expand_user(pattern))
        if expanded.startswith("~"):
            _warn_once(f"warning: ignoring {where}; no home directory found for it")
            return None
        return _path_forms(expanded)
    remote = pattern
    # Accept a clone URL, such as git@host:owner/repo.git, and reduce it the way remotes are.
    host = pattern.partition("/")[0]
    # `host:owner/repo` is scp-style, but `host:2222/owner/repo` is a normalized remote's port.
    if (
        "://" in pattern
        or "@" in pattern
        or (":" in host and not host.rpartition(":")[2].isdigit())
    ):
        remote = normalize_remote(pattern) or ""
    remote = remote.removesuffix(".git")
    if not remote:
        _warn_once(f"warning: ignoring {where}; use a remote such as github.com/owner/repo")
        return None
    return (remote.casefold(),)


def _valid_tables(data: dict[str, object]) -> list[_Table]:
    """Return the well-formed `[projects]` tables, warning about the rest."""
    projects = data.get(_PROJECTS_KEY)
    if projects is None:
        return []
    if not isinstance(projects, dict):
        _warn_once(
            "warning: ignoring projects in the config file; "
            f"each entry must be a table such as {_TABLE_EXAMPLE}"
        )
        return []
    tables = []
    for pattern, values in projects.items():
        if not isinstance(values, dict):
            _warn_once(
                f'warning: ignoring projects."{pattern}" in the config file; '
                f"it must be a table such as {_TABLE_EXAMPLE}"
            )
        elif (forms := _pattern_forms(pattern)) is not None:
            tables.append(_Table(pattern=pattern, forms=forms, values=values))
    return tables


@lru_cache(maxsize=256)
def _glob(pattern: str) -> re.Pattern[str]:
    """Compile a pattern where only `*` is special, so `?` and `[` in a folder name match as written."""
    return re.compile(".*".join(re.escape(part) for part in pattern.split("*")), re.DOTALL)


def _matches_repo(table: _Table, identity: _RepoIdentity) -> bool:
    if table.is_path:
        return any(_glob(form).fullmatch(path) for path in identity.paths for form in table.forms)
    return (
        identity.remote is not None and _glob(table.forms[0]).fullmatch(identity.remote) is not None
    )


def _matching_tables(loaded: _Loaded) -> list[_Table]:
    """Return the tables that match the current repo, most specific first."""
    global _matches  # noqa: PLW0603
    # Skip git entirely for a file with no tables.
    if not loaded.tables or (cwd := current_dir()) is None:
        return []
    key = (loaded.stamp, _repo_identity(cwd))
    if _matches is not None and _matches[0] == key:
        return _matches[1]
    identity = key[1]
    matching = sorted(
        (t for t in loaded.tables if _matches_repo(t, identity)),
        key=lambda t: t.rank,
        reverse=True,
    )
    for table in matching:
        for unknown in sorted(set(table.values) - KNOWN_KEYS):
            _warn_once(
                f"warning: ignoring unknown key {unknown!r} in {table_location(table.pattern)}"
            )
    _matches = (key, matching)
    return matching


def config_entries(key: str) -> list[ConfigEntry]:
    """Return every value of a key that applies to the current repo, the one that wins first.

    Values from matching `[projects]` tables come first, most specific pattern first, then
    the top-level value. A caller that validates values walks the list and takes the first
    valid one, so an invalid table value falls through.

    Args:
        key: The key name, such as `stats_enabled` or `wait_timeout`.

    Returns:
        The entries, empty when the file or key is missing or the file is invalid.
    """
    if (loaded := _load()) is None:
        return []
    entries = [
        ConfigEntry(value=table.values[key], table=table.pattern)
        for table in _matching_tables(loaded)
        if key in table.values
    ]
    if key in loaded.data:
        entries.append(ConfigEntry(value=loaded.data[key], table=None))
    return entries


def parse_whole_number(text: str) -> int | None:
    """Parse a non-negative whole number, or return None when the text is not one.

    Args:
        text: The value to parse; padded spaces are allowed.

    Returns:
        The number, capped at MAX_WHOLE_NUMBER, or None.
    """
    stripped = text.strip()
    if not (stripped.isascii() and stripped.isdigit()):
        return None
    # int() refuses strings past a few thousand digits, so cap by length first.
    digits = stripped.lstrip("0") or "0"
    if len(digits) > len(str(MAX_WHOLE_NUMBER)):
        return MAX_WHOLE_NUMBER
    return min(int(digits), MAX_WHOLE_NUMBER)


def config_whole_number(value: object) -> int | None:
    """Return a config value as a capped non-negative integer, or None when it is not one."""
    # bool is an int subclass, so reject it first.
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return min(value, MAX_WHOLE_NUMBER)
    return None


def valid_config_value(key: str, *, parse: Callable[[object], _T | None], hint: str) -> _T | None:
    """Return the first valid value of a key, as `valid_config_entry` finds it, or None."""
    found = valid_config_entry(key, parse=parse, hint=hint)
    return None if found is None else found[0]


def valid_config_entry(
    key: str, *, parse: Callable[[object], _T | None], hint: str
) -> tuple[_T, ConfigEntry] | None:
    """Read one key like `valid_config_value`, and also return the entry that won.

    Use it when a message must name the `[projects]` table that decided.

    Args:
        key: The key name.
        parse: Turns the raw value into the setting, or None when it is invalid.
        hint: What a valid value looks like, for the warning.

    Returns:
        The first valid parsed value and its entry, or None when no value is set and valid.
    """
    for entry in config_entries(key):
        if (parsed := parse(entry.value)) is not None:
            return parsed, entry
        _warn_once(
            f"warning: ignoring invalid {key} {entry.value!r} in {table_location(entry.table)}; {hint}"
        )
    return None
