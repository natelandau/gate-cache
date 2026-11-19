"""Detect the git tree that a gate command is about to test."""

from __future__ import annotations

import filecmp
import hashlib
import os
import re
import shutil
import stat
import sys
import tempfile
import unicodedata
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import TYPE_CHECKING

from gate_cache import scratch
from gate_cache.git import (
    GitError,
    GitNotFoundError,
    absolute_common_dir,
    git_common_dir,
    run_git,
)

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator


@dataclass(frozen=True)
class Snapshot:
    """The content a gate is about to test, or why that content is unknown.

    Attributes:
        tree: Git tree hash describing the whole working copy, or None when unknown.
        reason: Why the content is unknown, or None when it is known.
        scope: The `paths:` value covering only the gate's paths, or None for an unscoped gate.
        paths: The sorted, distinct pathspecs that scope the gate, or empty for the whole tree.
        root: Absolute top of the work tree, when git found one, even if the key is unknown.
        common_dir: The git common directory, as `git_common_dir()` returns it. A known
            snapshot always looks it up; an unknown one carries it only when found on the way.
    """

    tree: str | None
    reason: str | None
    scope: str | None = None
    paths: tuple[str, ...] = ()
    root: Path | None = field(default=None, compare=False)
    common_dir: Path | None = field(default=None, compare=False)

    @property
    def key(self) -> str | None:
        """Return the value a marker is keyed on: the scope when there is one, else the tree."""
        return self.scope if self.paths else self.tree

    @property
    def known(self) -> bool:
        """Return True when a key identifies the content under test."""
        return self.key is not None

    @property
    def label(self) -> str:
        """Name the key for one-line messages, such as `tree 1a2b3c4d5e6f`."""
        if self.paths:
            return f"paths {(self.scope or '').removeprefix(_SCOPE_PREFIX)[:12]}"
        return f"tree {(self.tree or '')[:12]}"


def _hook_work_tree(cwd: Path | None) -> Path | None:
    """Return the work tree that a GIT_DIR without GIT_WORK_TREE belongs to, if derivable.

    Git hands hooks GIT_DIR alone, and then takes the current directory for the top of the
    work tree. A hook that changes into a subdirectory would see every other file as changed.
    """
    git_dir = os.environ.get("GIT_DIR")
    if not git_dir or os.environ.get("GIT_WORK_TREE"):
        return None
    if run_git("config", "--get", "core.worktree", cwd=cwd, check=False).stdout.strip():
        return None
    base = Path(cwd) if cwd is not None else Path.cwd()
    path = (base / git_dir).resolve()
    # A linked worktree's git dir holds a `gitdir` file naming `<work tree>/.git`.
    gitdir_file = path / "gitdir"
    if gitdir_file.is_file():
        target = Path(gitdir_file.read_text(encoding="utf-8").strip())
        return (path / target).resolve().parent
    if path.name == ".git":
        return path.parent
    return None


def _git_env(cwd: Path | None) -> dict[str, str] | None:
    """Return an environment for gate-cache's own git probes, or None to inherit as is."""
    try:
        work_tree = _hook_work_tree(cwd)
    except OSError:
        return None
    if work_tree is None:
        return None
    return {**os.environ, "GIT_WORK_TREE": str(work_tree)}


def _work_tree_root(cwd: Path | None, env: dict[str, str] | None) -> Path | None:
    """Return the absolute top of the work tree, or None when there is none."""
    result = run_git("rev-parse", "--show-toplevel", cwd=cwd, env=env, check=False)
    output = result.stdout.strip()
    if result.returncode != 0 or not output or "\n" in output:
        return None
    return Path(output)


_GITLINK_MODE = "160000"


@dataclass(frozen=True, slots=True)
class _IndexListing:
    """Every index entry as `git ls-files -v --stage -z` prints it, parsed on demand.

    Each record reads `<tag> <mode> <object> <stage>`, a tab, then the path. Parsing per
    question keeps a large index from costing an object per entry.
    """

    output: str

    @classmethod
    def read(cls, directory: Path, env: dict[str, str] | None) -> _IndexListing:
        """List the index of the repository at DIRECTORY."""
        return cls(run_git("ls-files", "-v", "--stage", "-z", cwd=directory, env=env).stdout)

    def _records(self) -> Iterator[tuple[str, str]]:
        for record in self.output.split("\0"):
            info, _, path = record.partition("\t")
            if path:
                yield info, path

    @staticmethod
    def _hides_edits(info: str) -> bool:
        # `-v` tags assume-unchanged entries in lowercase and skip-worktree entries `S`.
        # Sparse checkout marks every path outside the cone skip-worktree, so it lands here too.
        return info[0].islower() or info[0] == "S"

    def blocking_reason(self) -> str | None:
        """Return why the index cannot vouch for the work tree, a conflict before a hidden entry."""
        hidden: str | None = None
        for info, path in self._records():
            if info[-1] != "0":
                return "unmerged index"
            if hidden is None and self._hides_edits(info):
                hidden = f"skip-worktree or assume-unchanged entry: {path}"
        return hidden

    def hidden_reason(self, label: str = "") -> str | None:
        """Return a reason when an entry tells git to ignore edits to its file."""
        for info, path in self._records():
            if self._hides_edits(info):
                return f"skip-worktree or assume-unchanged entry: {label}{path}"
        return None

    def gitlinks(self) -> list[str]:
        """Return the paths of every gitlink (submodule or embedded repo)."""
        return [path for info, path in self._records() if info[2:8] == _GITLINK_MODE]

    def paths(self) -> Iterator[str]:
        """Yield every indexed path."""
        return (path for _, path in self._records())

    def files(self) -> dict[str, str]:
        """Return the staged object of every regular file by path, the entries git converts."""
        return {
            path: info.split(" ")[2]
            for info, path in self._records()
            if info[2:8] in _REGULAR_FILE_MODES
        }


_REGULAR_FILE_MODES = ("100644", "100755")


@dataclass(frozen=True)
class _State:
    """Where the work tree is, or why no tree can describe it."""

    root: Path | None
    reason: str | None = None
    locations: _Locations | None = None


@dataclass(frozen=True)
class _StatusRecord:
    """One entry of `git status --porcelain=v2`."""

    kind: str
    submodule: str
    path: str

    @property
    def submodule_moved(self) -> bool:
        """Return True when a submodule's commit, tracked content, or untracked files differ."""
        return self.submodule.startswith("S") and any(flag in self.submodule for flag in "CMU")


def _status(directory: Path, env: dict[str, str] | None) -> list[_StatusRecord]:
    """List every difference git status sees, regardless of status and submodule config."""
    # Optional locks off: status would otherwise refresh and rewrite the index it reads,
    # taking index.lock from a concurrent git command. `-unormal` and
    # `--ignore-submodules=none` override config that would hide untracked files and
    # submodule changes.
    output = run_git(
        "--no-optional-locks",
        "status",
        "--porcelain=v2",
        "-z",
        "--untracked-files=normal",
        "--ignore-submodules=none",
        cwd=directory,
        env=env,
    ).stdout
    found: list[_StatusRecord] = []
    records = iter(output.split("\0"))
    for record in records:
        kind = record[:1]
        if kind in {"1", "2"}:
            fields = record.split(" ", 9 if kind == "2" else 8)
            if kind == "2":
                next(records, None)  # a rename record is followed by its original path
            found.append(_StatusRecord(kind=kind, submodule=fields[2], path=fields[-1]))
        elif kind == "u":
            fields = record.split(" ", 10)
            found.append(_StatusRecord(kind=kind, submodule=fields[2], path=fields[-1]))
        elif kind == "?":
            found.append(_StatusRecord(kind=kind, submodule="N...", path=record[2:]))
    return found


def _gitlink_reason(directory: Path, label: str, env: dict[str, str], checkout: Path) -> str | None:
    """Return why a submodule's checkout may hold content its recorded commit does not.

    The superproject's status runs the submodule's own status, which obeys the submodule's
    config and index flags, so each checkout is probed directly, recursively.

    Args:
        directory: The submodule's checkout.
        label: The submodule's path from the top of the superproject, for reasons.
        env: Environment for git, free of the superproject's repository variables.
        checkout: The directory under which each conversion check checks out files.
    """
    try:
        # An uninitialized submodule is an empty directory. `git submodule update --init`
        # later fills it without changing the tree, so an earlier pass proves nothing.
        if not (directory.is_dir() and any(directory.iterdir())):
            return f"submodule is not checked out: {label}"
        checked_out = (directory / ".git").exists()
    except OSError:
        checked_out = False
    if not checked_out:
        return f"submodule is not a checked-out repository: {label}"
    listing = _IndexListing.read(directory=directory, env=env)
    hidden = listing.hidden_reason(label=f"{label}/")
    if hidden:
        return hidden
    if _status(directory, env):
        return f"submodule not at its index state: {label}"
    mismatch = (
        _case_mismatch_reason(root=directory, paths=listing.paths(), label=f"{label}/")
        if _ignores_case(directory, env)
        else None
    )
    # Status reads a change that git's conversions erase as clean, as it does at the top.
    reason = mismatch or _ConversionCheck(
        root=directory, env=env, files=listing.files(), label=f"{label}/"
    ).reason(checkout / label)
    if reason:
        return reason
    nested = (
        _gitlink_reason(
            directory=directory / path, label=f"{label}/{path}", env=env, checkout=checkout
        )
        for path in listing.gitlinks()
    )
    return next((reason for reason in nested if reason), None)


def _ignores_case(directory: Path, env: dict[str, str]) -> bool:
    """Return True when the repository at DIRECTORY sets core.ignorecase."""
    result = run_git("config", "--bool", "core.ignorecase", cwd=directory, env=env, check=False)
    return result.stdout.strip() == "true"


@dataclass(frozen=True)
class _Locations:
    """The paths one `git rev-parse` call reports for a repository with a work tree.

    Attributes:
        root: Absolute top of the work tree.
        index: The index path as git printed it, possibly relative to the cwd.
        objects: The object store path as git printed it, possibly relative to the cwd.
        common_dir: The absolute common dir, or None when this lookup cannot vouch for it.
    """

    root: Path
    index: str
    objects: str
    common_dir: Path | None


def _locate(cwd: Path | None, env: dict[str, str] | None) -> _Locations | None:
    """Ask git for the work tree, index, object store, and common dir in one call.

    Return None unless the answer is one clean line per location, so the caller falls back
    to one call per lookup and keeps that path's error handling.
    """
    try:
        result = run_git(
            "rev-parse", "--show-toplevel", "--git-path", "index", "--git-path", "objects",
            "--git-common-dir", cwd=cwd, env=env, check=False,
        )  # fmt: skip
    except UnicodeDecodeError:
        return None
    lines = [line.strip() for line in result.stdout.split("\n")]
    if result.returncode != 0 or len(lines) != 4 or not all(lines):  # noqa: PLR2004
        return None
    root, index, objects, common = lines
    # `git_common_dir()` runs git with the inherited environment. A GIT_WORK_TREE added for a
    # hook changes how git prints the common dir, so only an inherited env may answer for it.
    return _Locations(
        root=Path(root),
        index=index,
        objects=objects,
        common_dir=absolute_common_dir(output=common, cwd=cwd) if env is None else None,
    )


def _from_cwd(path: str, cwd: Path | None) -> Path:
    """Anchor a path git printed relative to the directory it ran in; keep an absolute one."""
    return (Path(cwd) if cwd is not None else Path.cwd()) / path


def _inspect(cwd: Path | None, env: dict[str, str] | None) -> _State:
    """Probe the repository for anything that keeps one tree from describing the working copy."""
    locations = _locate(cwd, env)
    if (
        locations is None
        and run_git("rev-parse", "--git-dir", cwd=cwd, env=env, check=False).returncode != 0
    ):
        return _State(root=None, reason="not a git repository")
    # ls-files only lists paths under its cwd. Probing from the top avoids the `:/` pathspec,
    # which GIT_LITERAL_PATHSPECS turns into a literal path that matches nothing.
    root = locations.root if locations is not None else _work_tree_root(cwd, env)
    if root is None:
        return _State(root=None, reason="could not locate work tree")
    reason = _IndexListing.read(directory=root, env=env).blocking_reason()
    return _State(root=root, reason=reason, locations=locations)


def _git_path(name: str, cwd: Path | None, env: dict[str, str] | None) -> Path:
    """Return the absolute path git uses for NAME, honoring GIT_INDEX_FILE and friends."""
    output = run_git("rev-parse", "--git-path", name, cwd=cwd, env=env).stdout.strip()
    if not output or "\n" in output:
        msg = f"unexpected `git rev-parse --git-path {name}` output: {output!r}"
        raise OSError(msg)
    return _from_cwd(path=output, cwd=cwd)


def _require_private(env: dict[str, str], private: Path) -> None:
    """Refuse to run git unless its index and object store sit inside PRIVATE.

    The env is built a few lines earlier, so this never fires today. It stands between any
    future change to that env and a `git add -A` that would stage into the real index.
    """
    for key in ("GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY"):
        if not Path(env[key]).resolve().is_relative_to(private.resolve()):
            msg = f"{key}={env[key]!r} is outside {private}"
            raise OSError(msg)


def _submodule_env(env: dict[str, str]) -> dict[str, str]:
    """Return ENV without the variables that tie git to the superproject's repository."""
    local = run_git("rev-parse", "--local-env-vars", env=env).stdout.split()
    return {key: value for key, value in env.items() if key not in local}


_CONVERTING_ATTRIBUTES = frozenset(
    ("text", "eol", "crlf", "ident", "filter", "working-tree-encoding")
)


@dataclass(frozen=True)
class _ConversionCheck:
    """Find a file whose bytes differ from what git would check out for its staged object.

    `git add` stores each file after its clean conversions (line endings, ident, filters),
    and keeps the index's executable bit under core.fileMode=false. A change those erase
    leaves the tree unchanged while the command reads different bytes. Requiring every file
    to match its checkout form leaves one content per tree.
    """

    root: Path
    env: dict[str, str]
    files: dict[str, str]
    label: str = ""

    def reason(self, checkout: Path) -> str | None:
        """Return the first file that the tree does not describe, or None when it describes all.

        Args:
            checkout: An absent directory to check out the converted files into.
        """
        path = self._unlike_checkout(checkout)
        if path is not None:
            return f"file differs from its git checkout form: {self.label}{path}"
        path = self._mode_changed()
        if path is not None:
            return f"executable bit differs from the index: {self.label}{path}"
        return None

    def _unlike_checkout(self, checkout: Path) -> str | None:
        kept, rewritten = self._converted()
        if kept:
            output = run_git(
                "hash-object", "--no-filters", "--stdin-paths",
                cwd=self.root, env=self.env, stdin="".join(f"{path}\n" for path in kept).encode(),
            ).stdout  # fmt: skip
            for path, oid in zip(kept, output.splitlines(), strict=True):
                if oid != self.files[path]:
                    return path
        if rewritten:
            run_git(
                "checkout-index", "-z", "--stdin", f"--prefix={checkout.as_posix()}/",
                cwd=self.root, env=self.env, stdin=_nul_joined(rewritten),
            )  # fmt: skip
            for path in rewritten:
                if not filecmp.cmp(f1=self.root / path, f2=checkout / path, shallow=False):
                    return path
        return None

    def _converted(self) -> tuple[list[str], list[str]]:
        """Split the files that git converts into those checkout keeps as staged and the rest.

        A file that checkout keeps as staged matches when its raw hash equals the staged
        object. Every other converted file is compared with a real checkout, which costs a
        copy of the file.
        """
        autocrlf = self._config("core.autocrlf")
        all_text = autocrlf is not None and autocrlf not in _FALSE
        writes_lf = _checkout_writes_lf(autocrlf=autocrlf, eol=self._config("core.eol"))
        attributes = self._attributes()
        kept: list[str] = []
        rewritten: list[str] = []
        for path in self.files:
            specified = attributes.get(path, {})
            # Git LFS stores a pointer that names the SHA-256 of the file, so no change hides
            # in it, and its smudge filter can download every large file. Matched by name only.
            if specified.get("filter") == "lfs":
                continue
            active = {name: value for name, value in specified.items() if value != "unset"}
            text_off = specified.get("text") == "unset"
            if not active and (text_off or not all_text):
                continue
            if (
                active.keys() <= {"text", "eol"}
                and _stdin_paths_safe(path)
                and (text_off or active.get("eol", "lf" if writes_lf else "crlf") == "lf")
            ):
                kept.append(path)
            else:
                rewritten.append(path)
        return kept, rewritten

    def _config(self, key: str) -> str | None:
        """Return KEY's lowercase value, an empty string for a valueless key, or None when unset."""
        result = run_git("config", "--get", key, cwd=self.root, env=self.env, check=False)
        return result.stdout.strip().lower() if result.returncode == 0 else None

    def _attributes(self) -> dict[str, dict[str, str]]:
        """Return the conversion attributes each file sets or unsets, leaving out unspecified ones."""
        output = run_git(
            "check-attr", "-z", "--stdin", "--all",
            cwd=self.root, env=self.env, stdin=_nul_joined(self.files),
        ).stdout  # fmt: skip
        fields = output.split("\0")
        attributes: dict[str, dict[str, str]] = {}
        for path, name, value in zip(fields[0::3], fields[1::3], fields[2::3], strict=False):
            if name in _CONVERTING_ATTRIBUTES:
                attributes.setdefault(path, {})[name] = value
        return attributes

    def _mode_changed(self) -> str | None:
        """Return a file whose executable bit git ignores because core.fileMode is false."""
        # Windows filesystems have no executable bit to compare.
        if self._config("core.fileMode") not in _FALSE or sys.platform == "win32":
            return None
        output = run_git(
            "-c", "core.fileMode=true", "diff-files", "-z", "--ignore-submodules",
            cwd=self.root, env=self.env,
        ).stdout  # fmt: skip
        fields = output.split("\0")
        changed = [
            path
            for info, path in zip(fields[0::2], fields[1::2], strict=False)
            if _modes_differ(info)
        ]
        if not changed:
            return None
        git_dir = run_git("rev-parse", "--absolute-git-dir", cwd=self.root, env=self.env).stdout
        return changed[0] if _stores_exec_bit(Path(git_dir)) else None


_FALSE = ("false", "no", "off", "0")


def _modes_differ(info: str) -> bool:
    """Return True when a `git diff-files` raw record shows a mode change."""
    old_mode, new_mode = info.lstrip(":").split(" ")[:2]
    return old_mode != new_mode


def _stores_exec_bit(directory: Path) -> bool:
    """Return True when the filesystem of DIRECTORY keeps the executable bit that chmod sets.

    Mounts such as VFAT or a Windows drive under WSL report one fixed bit for every file, so
    git turns core.fileMode off there and the bit on disk says nothing about the index. A
    probe that cannot run counts as a filesystem that keeps the bit, which runs the command.
    """
    try:
        with tempfile.NamedTemporaryFile(dir=directory, prefix="gate-cache-probe-") as probe:
            path = Path(probe.name)
            path.chmod(0o700)
            set_bit = bool(path.stat().st_mode & stat.S_IXUSR)
            path.chmod(0o600)
            return set_bit and not path.stat().st_mode & stat.S_IXUSR
    except OSError:
        return True


def _checkout_writes_lf(autocrlf: str | None, eol: str | None) -> bool:
    """Return True when checkout writes LF for a text file with no `eol` attribute.

    A valueless `autocrlf` key means true. Anything not known to write LF counts as CRLF,
    which only sends the file to the slower, exact comparison.
    """
    if autocrlf == "input":
        return True
    if autocrlf is not None and autocrlf not in _FALSE:
        return False
    if eol in (None, "native"):
        return sys.platform != "win32"
    return eol == "lf"


def _stdin_paths_safe(path: str) -> bool:
    """Return True when `hash-object --stdin-paths` reads PATH back unchanged.

    It reads one path per line, drops a CR before the newline, and C-unquotes a line that
    starts with a double quote.
    """
    return "\n" not in path and not path.endswith("\r") and not path.startswith('"')


def _nul_joined(paths: Iterable[str]) -> bytes:
    """Encode PATHS as the NUL-terminated list that git's `--stdin -z` options read."""
    return "".join(f"{path}\0" for path in paths).encode()


def _staged_reason(root: Path, env: dict[str, str], private: Path) -> str | None:
    """Return why the staged private index may not describe what the command reads."""
    listing = _IndexListing.read(directory=root, env=env)
    links = listing.gitlinks()
    # Only gitlinks produce submodule records, so a repo without them skips a full status scan.
    if links:
        for record in _status(root, env):
            if record.submodule_moved:
                return f"submodule not at its index state: {record.path}"
        submodule_env = _submodule_env(env)
        for path in links:
            reason = _gitlink_reason(
                directory=root / path, label=path, env=submodule_env, checkout=private / "modules"
            )
            if reason:
                return reason
    if _ignores_case(root, env):
        reason = _case_mismatch_reason(root=root, paths=listing.paths())
        if reason:
            return reason
    # Last, because it can read every converted file.
    return _ConversionCheck(root=root, env=env, files=listing.files()).reason(private / "checkout")


def _case_mismatch_reason(root: Path, paths: Iterable[str], label: str = "") -> str | None:
    """Return a reason when an indexed path is spelled differently on disk than in the index.

    On a case-insensitive filesystem a case-only rename keeps the old index entry, so the tree
    would name a path the command does not see. Comparing each path component with the real
    directory entries is exact and does not depend on ignore rules.
    """
    listings: dict[Path, set[str]] = {}
    for path in paths:
        parent = root
        for part in path.split("/"):
            if parent not in listings:
                # With core.precomposeunicode the index holds the NFC form of a name that
                # macOS may store decomposed; both spell the same file.
                listings[parent] = {
                    name
                    for child in parent.iterdir()
                    for name in (child.name, unicodedata.normalize("NFC", child.name))
                }
            if part not in listings[parent]:
                return f"path differs from the index only by case: {label}{path}"
            parent = parent / part
    return None


_SCOPE_PREFIX = "paths:"
_SCOPE_TAG = "gate-cache-paths-v1"
# These would make the same --path values match different files in different environments.
_PATHSPEC_ENV = (
    "GIT_LITERAL_PATHSPECS",
    "GIT_GLOB_PATHSPECS",
    "GIT_NOGLOB_PATHSPECS",
    "GIT_ICASE_PATHSPECS",
)
_UNMATCHED = re.compile(r"^error: pathspec '(.*)' did not match", re.MULTILINE)


def _git_complaint(stderr: str) -> str | None:
    """Pick the line of git's stderr that explains a failure, preferring fatal and error lines."""
    lines = [line for line in stderr.splitlines() if line.strip()]
    errors = [line for line in lines if line.startswith(("fatal:", "error:"))]
    return (errors or lines or [None])[0]


def _scope(root: Path, env: dict[str, str], paths: tuple[str, ...], tree: str) -> Snapshot:
    """Hash the staged entries under PATHS, or explain why no scope can describe them.

    A path that selects nothing would give a constant scope that skips forever, so it
    leaves the scope unknown instead.
    """
    # C locale: the unmatched-path error is parsed below.
    scope_env = {key: value for key, value in env.items() if key not in _PATHSPEC_ENV}
    scope_env["LC_ALL"] = "C"
    try:
        listed = run_git(
            "ls-files", "--stage", "-z", "--error-unmatch", "--", *paths,
            cwd=root, env=scope_env, check=False,
        )  # fmt: skip
    except UnicodeDecodeError:
        # Kept to this path set, so one undecodable listing cannot blank the others.
        return Snapshot(
            tree=tree, reason="could not match --path: output is not UTF-8", paths=paths
        )
    if listed.returncode != 0:
        unmatched = _UNMATCHED.search(listed.stderr)
        if unmatched:
            reason = f"--path {unmatched.group(1)} matches no files"
        else:
            detail = _git_complaint(listed.stderr)
            reason = f"could not match --path: {detail}" if detail else "could not match --path"
        return Snapshot(tree=tree, reason=reason, paths=paths)
    if not listed.stdout:
        reason = f"--path {' '.join(paths)} matches no files"
        return Snapshot(tree=tree, reason=reason, paths=paths)
    head = "\0".join([_SCOPE_TAG, *paths]).encode()
    digest = hashlib.sha256(head + b"\0\0" + listed.stdout.encode()).hexdigest()
    return Snapshot(tree=tree, reason=None, scope=f"{_SCOPE_PREFIX}{digest}", paths=paths)


def _private_snapshots(
    root: Path,
    env: dict[str, str] | None,
    path_sets: list[tuple[str, ...]],
    index: Path,
    objects: Path,
) -> list[Snapshot]:
    """Stage the working copy into a private index once and key it for each path set.

    A copy of the index and a throwaway object store take every write, so the real index,
    its lock, and `.git/objects` stay untouched even by write-tree's cache-tree update.
    """
    base = dict(os.environ if env is None else env)
    with scratch.scratch_dir() as private:
        private_index = private / "index"
        private_objects = private / "objects"
        # copy2 keeps the mtime git compares against to spot racily clean entries. A fresh
        # mtime would make git trust stat data for a file edited in the same second.
        if index.exists():
            shutil.copy2(index, private_index)
        private_objects.mkdir()
        alternates = [str(objects), base.get("GIT_ALTERNATE_OBJECT_DIRECTORIES", "")]
        private_env = {
            **base,
            "GIT_INDEX_FILE": str(private_index),
            "GIT_OBJECT_DIRECTORY": str(private_objects),
            "GIT_ALTERNATE_OBJECT_DIRECTORIES": os.pathsep.join(filter(None, alternates)),
        }
        _require_private(private_env, private)
        # Split index mode would write a shared index file into the real git directory.
        no_split = ("-c", "core.splitIndex=false")
        added = run_git(*no_split, "add", "-A", cwd=root, env=private_env, check=False)
        if added.returncode != 0:
            # Name git's complaint, such as an embedded repository with no commit, so the
            # user can see what keeps the cache off.
            detail = _git_complaint(added.stderr)
            reason = "could not stage working copy"
            return _unknown(path_sets=path_sets, reason=f"{reason}: {detail}" if detail else reason)
        reason = _staged_reason(root=root, env=private_env, private=private)
        if reason:
            return _unknown(path_sets=path_sets, reason=reason)
        tree = run_git(*no_split, "write-tree", cwd=root, env=private_env).stdout
        return [
            _scope(root=root, env=private_env, paths=paths, tree=tree)
            if paths
            else Snapshot(tree=tree, reason=None)
            for paths in path_sets
        ]


def normalize_paths(paths: Iterable[str]) -> tuple[str, ...]:
    """Return pathspecs sorted and deduplicated, the form every key and record uses.

    Args:
        paths: Git pathspecs in any order, possibly repeated.

    Returns:
        The distinct pathspecs in sorted order.
    """
    return tuple(sorted(set(paths)))


def _unknown(
    path_sets: list[tuple[str, ...]],
    reason: str,
    root: Path | None = None,
    common_dir: Path | None = None,
) -> list[Snapshot]:
    """Return one unknown snapshot per path set, all for the same reason."""
    return [
        Snapshot(tree=None, reason=reason, paths=paths, root=root, common_dir=common_dir)
        for paths in path_sets
    ]


def take_snapshot(cwd: Path | None = None, paths: Iterable[str] = ()) -> Snapshot:
    """Identify the content a gate command is about to test.

    The tree is the one a commit of the working copy would get, so a pass on uncommitted work
    matches the later commit. Every situation where the tree might not describe what the
    command reads, including any git failure, resolves to unknown so the caller runs the
    command uncached.

    Args:
        cwd: Directory to run git in. Defaults to the process working directory.
        paths: Git pathspecs, from the top of the work tree, that scope the key to the files
            a gate reads. Empty keys on the whole tree.

    Returns:
        A Snapshot holding the tree hash and any scope, or the reason they are unknown.
    """
    return take_snapshots([paths], cwd=cwd)[0]


def take_snapshots(path_sets: Iterable[Iterable[str]], cwd: Path | None = None) -> list[Snapshot]:
    """Key the working copy for several path sets while staging it only once.

    Args:
        path_sets: One collection of pathspecs per snapshot wanted. An empty one keys on the
            whole tree.
        cwd: Directory to run git in. Defaults to the process working directory.

    Returns:
        One Snapshot per path set, in order.
    """
    normalized = [normalize_paths(paths) for paths in path_sets]
    try:
        env = _git_env(cwd)
        state = _inspect(cwd, env)
    except GitNotFoundError:
        return _unknown(path_sets=normalized, reason="git not found")
    except (GitError, UnicodeDecodeError):
        return _unknown(path_sets=normalized, reason="could not inspect git state")
    locations = state.locations
    common_dir = locations.common_dir if locations is not None else None
    if state.reason or state.root is None:
        return _unknown(
            path_sets=normalized,
            reason=state.reason or "could not locate work tree",
            root=state.root,
            common_dir=common_dir,
        )

    try:
        # Resolved from cwd, as git itself resolves an inherited relative GIT_INDEX_FILE.
        if locations is not None:
            index = _from_cwd(path=locations.index, cwd=cwd)
            objects = _from_cwd(path=locations.objects, cwd=cwd)
        else:
            index, objects = _git_path("index", cwd, env), _git_path("objects", cwd, env)
        snapshots = _private_snapshots(
            root=state.root, env=env, path_sets=normalized, index=index, objects=objects
        )
    except (GitError, OSError, UnicodeDecodeError):
        return _unknown(
            path_sets=normalized,
            reason="could not hash working copy",
            root=state.root,
            common_dir=common_dir,
        )
    if common_dir is None and any(snap.known for snap in snapshots):
        common_dir = git_common_dir(cwd)
    return [replace(snap, root=state.root, common_dir=common_dir) for snap in snapshots]
