"""Tests for the run context that stats events carry."""

import errno
import os
from pathlib import Path

import pytest

from gate_cache.remote import config_remote_url, normalize_remote
from gate_cache.stats import context
from gate_cache.stats.context import (
    branch_from_head,
    detect_source,
    find_worktree,
    head_commit,
    host_name,
    machine_id,
    max_rss_bytes,
    read_head,
    relative_subdir,
    worktree_git_dir,
)

TOKEN = "ghp_S3cretT0ken"  # noqa: S105  # gitleaks:allow


SHA1 = "0123456789abcdef0123456789abcdef01234567"
SHA256 = "ab" * 32


@pytest.mark.parametrize(
    ("environ", "isatty", "expected"),
    [
        ({"CI": "true", "PRE_COMMIT": "1", "CLAUDECODE": "1"}, True, ("ci", None, None)),
        ({"CI": "false", "PRE_COMMIT": "1"}, True, ("hook", None, None)),
        (
            {"PRE_COMMIT": "1", "PREK_HOOK_STAGE": "pre-push", "CLAUDECODE": "1"},
            False,
            ("hook", None, "pre-push"),
        ),
        ({"PRE_COMMIT": "1", "PREK_HOOK_STAGE": " "}, False, ("hook", None, None)),
        ({"PRE_COMMIT": "0", "PREK_HOOK_STAGE": "pre-commit"}, False, ("other", None, None)),
        ({"CLAUDECODE": "1"}, True, ("agent", "claude-code", None)),
        ({"GEMINI_CLI": "1"}, False, ("agent", "gemini-cli", None)),
        ({"CODEX_THREAD_ID": "0198-abc"}, False, ("agent", "codex", None)),
        ({"CODEX_THREAD_ID": ""}, True, ("terminal", None, None)),
        ({}, True, ("terminal", None, None)),
        ({}, False, ("other", None, None)),
    ],
)
def test_detect_source(
    environ: dict[str, str], *, isatty: bool, expected: tuple[str, str | None, str | None]
) -> None:
    """The first matching source of the run wins, with the agent and hook stage it names."""
    source = detect_source(environ, isatty=isatty)
    assert (source.trigger, source.agent, source.hook_stage) == expected


def test_git_dir_of_normal_and_linked_worktree(tmp_path: Path) -> None:
    """A .git directory is the git dir; a .git file points at one, absolute or relative."""
    (tmp_path / ".git").mkdir()
    assert worktree_git_dir(tmp_path) == tmp_path / ".git"
    git_dir = tmp_path / "main" / ".git" / "worktrees" / "wt"
    git_dir.mkdir(parents=True)
    work = tmp_path / "wt"
    work.mkdir()
    (work / ".git").write_text(f"gitdir: {git_dir}\n")
    assert worktree_git_dir(work) == git_dir
    (work / ".git").write_text("gitdir: ../main/.git/worktrees/wt\n")
    relative = worktree_git_dir(work)
    assert relative is not None
    assert relative.resolve() == git_dir.resolve()


def test_git_dir_missing_or_bad(tmp_path: Path) -> None:
    """No .git entry, a bad .git file, or no work tree gives no git dir."""
    assert worktree_git_dir(tmp_path) is None
    (tmp_path / ".git").write_text("not a pointer\n")
    assert worktree_git_dir(tmp_path) is None
    assert worktree_git_dir(None) is None


def test_read_head(tmp_path: Path) -> None:
    """HEAD is read as stripped text, or None when missing."""
    assert read_head(tmp_path) is None
    assert read_head(None) is None
    (tmp_path / "HEAD").write_text("ref: refs/heads/main\n")
    assert read_head(tmp_path) == "ref: refs/heads/main"
    (tmp_path / "HEAD").write_bytes(b"\xff\n")
    assert read_head(tmp_path) is None


@pytest.mark.parametrize(
    ("head", "expected"),
    [
        ("ref: refs/heads/feat/x", "feat/x"),
        ("ref: refs/heads/", None),
        ("ref: refs/heads/.invalid", None),
        ("ref: refs/heads/feat/.x", None),
        ("ref: refs/heads/f\u00fcr", "f\u00fcr"),
        ("ref: refs/heads/a\x1b]0;x\x07", None),
        ("ref: refs/heads/a b", None),
        ("ref: refs/heads/a..b", None),
        ("ref: refs/heads/a@{1}", None),
        ("ref: refs/heads/a//b", None),
        ("ref: refs/heads/a/", None),
        ("ref: refs/heads/a.", None),
        ("ref: refs/heads/x.lock", None),
        ("ref: refs/heads/-x", None),
        ("ref: refs/heads/@", None),
        ("ref: refs/heads/a~1", None),
        ("ref: refs/heads/a\\b", None),
        ("ref: refs/remotes/origin/main", None),
        (SHA1, None),
        (None, None),
    ],
)
def test_branch_from_head(head: str | None, expected: str | None) -> None:
    """Only a HEAD that points at a local branch names one."""
    assert branch_from_head(head) == expected


def test_head_commit_loose_ref(tmp_path: Path) -> None:
    """A branch's loose ref file in the common dir holds the commit."""
    ref = tmp_path / "refs" / "heads" / "feat" / "x"
    ref.parent.mkdir(parents=True)
    ref.write_text(f"{SHA1}\n")
    assert head_commit("ref: refs/heads/feat/x", common_dir=tmp_path) == SHA1


def test_head_commit_packed_ref(tmp_path: Path) -> None:
    """A branch with no loose ref is looked up in packed-refs."""
    (tmp_path / "packed-refs").write_text(
        "# pack-refs with: peeled fully-peeled sorted\n"
        f"{'1' * 40} refs/heads/other\n"
        f"{SHA1} refs/heads/main\n"
        f"^{'2' * 40}\n"
    )
    assert head_commit("ref: refs/heads/main", common_dir=tmp_path) == SHA1
    assert head_commit("ref: refs/heads/gone", common_dir=tmp_path) is None


def test_head_commit_detached_and_sha256(tmp_path: Path) -> None:
    """A detached HEAD is the commit, in SHA-1 or SHA-256 form."""
    assert head_commit(SHA1, common_dir=tmp_path) == SHA1
    assert head_commit(SHA256, common_dir=tmp_path) == SHA256
    ref = tmp_path / "refs" / "heads" / "main"
    ref.parent.mkdir(parents=True)
    ref.write_text(f"{SHA256}\n")
    assert head_commit("ref: refs/heads/main", common_dir=tmp_path) == SHA256


@pytest.mark.parametrize("value", ["", "abc", SHA1.upper(), SHA1[:-1], SHA1 + "0", "z" * 40])
def test_head_commit_rejects_invalid(tmp_path: Path, value: str) -> None:
    """Anything that is not a full lowercase hash gives no commit."""
    assert head_commit(value, common_dir=tmp_path) is None
    ref = tmp_path / "refs" / "heads" / "main"
    ref.parent.mkdir(parents=True, exist_ok=True)
    ref.write_text(f"{value}\n")
    assert head_commit("ref: refs/heads/main", common_dir=tmp_path) is None


def test_head_commit_missing(tmp_path: Path) -> None:
    """No HEAD, no common dir, or an unborn branch gives no commit."""
    assert head_commit(None, common_dir=tmp_path) is None
    assert head_commit("ref: refs/heads/main", common_dir=None) is None
    assert head_commit("ref: refs/heads/main", common_dir=tmp_path) is None
    assert head_commit("ref: refs/heads/../../x", common_dir=tmp_path) is None


@pytest.mark.parametrize(
    ("cwd", "expected"),
    [("/w", "."), ("/w/a/b", "a/b"), ("/other", None), ("/", None)],
)
def test_relative_subdir(cwd: str, expected: str | None) -> None:
    """The working directory is given relative to the top, or None outside it."""
    assert relative_subdir(Path(cwd), worktree=Path("/w")) == expected
    assert relative_subdir(Path(cwd), worktree=None) is None


@pytest.mark.parametrize(
    ("platform", "value", "expected"),
    [("darwin", 2048, 2048), ("linux", 2048, 2048 * 1024), ("freebsd", 3, 3 * 1024)],
)
def test_max_rss_bytes(platform: str, value: int, expected: int) -> None:
    """MacOS reports bytes and other systems KiB."""
    assert max_rss_bytes(value, platform=platform) == expected


def test_find_worktree(tmp_path: Path) -> None:
    """The nearest directory holding .git is the top of the working tree."""
    (tmp_path / ".git").mkdir()
    deep = tmp_path / "a" / "b"
    deep.mkdir(parents=True)
    assert find_worktree(deep) == tmp_path
    lone = tmp_path.parent / f"{tmp_path.name}-lone"
    lone.mkdir()
    assert find_worktree(lone) in {None, *lone.parents}


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://github.com/Owner/Repo.git", "github.com/Owner/Repo"),
        ("https://GitHub.COM/Owner/Repo/", "github.com/Owner/Repo"),
        (f"https://x-access-token:{TOKEN}@github.com/o/r.git", "github.com/o/r"),
        (f"https://{TOKEN}@github.com/o/r", "github.com/o/r"),
        ("http://example.com:80/o/r.git", "example.com/o/r"),
        ("https://example.com:443/o/r", "example.com/o/r"),
        ("https://example.com:8443/o/r", "example.com:8443/o/r"),
        ("git@github.com:owner/repo.git", "github.com/owner/repo"),
        (f"user:{TOKEN}@host.example:owner/repo", "host.example/owner/repo"),
        ("github.com:owner/repo", "github.com/owner/repo"),
        ("ssh://git@github.com:22/owner/repo.git", "github.com/owner/repo"),
        ("ssh://git@host:2222/owner/repo.git", "host:2222/owner/repo"),
        ("git+ssh://git@host/owner/repo", "host/owner/repo"),
        ("git://host.example/owner/repo.git", "host.example/owner/repo"),
        ("git://host.example:9418/owner/repo", "host.example/owner/repo"),
        ("https://host/group/sub/repo.git?x=1#frag", "host/group/sub/repo"),
        ("https://[::1]:8080/o/r", "[::1]:8080/o/r"),
        ("/srv/git/repo.git", None),
        ("../other", None),
        ("file:///srv/git/repo.git", None),
        ("C:\\repos\\x", None),
        ("", None),
        ("https://host", None),
        ("https:///o/r", None),
        (f"https://user:{TOKEN[:4]}/{TOKEN[4:]}@host/o/r", None),
        ("https://host:notaport/o/r", None),
        ("rsync://host/o/r", None),
    ],
)
def test_normalize_remote(url: str, expected: str | None) -> None:
    """Every URL form maps to host/owner/repo, and credentials never survive."""
    result = normalize_remote(url)
    assert result == expected
    assert TOKEN not in (result or "")
    assert TOKEN[:4] not in (result or "")


LEAKY_REMOTES = (
    (f"git::https://u:{TOKEN}@host.example/o/r", "host.example/o/r"),
    (f"https://tok:12/{TOKEN}@github.com/o/r.git", None),
    (f"https:/u:{TOKEN}@host.example/o/r", None),
    (f"user:to/{TOKEN}@host.example:o/r", None),
)


@pytest.mark.parametrize(("url", "expected"), LEAKY_REMOTES)
def test_normalize_remote_never_leaks_credentials(url: str, expected: str | None) -> None:
    """Odd URL forms that hide credentials give a clean remote or None, never the secret."""
    result = normalize_remote(url)
    assert result == expected
    for secret in (TOKEN, "u:", "tok", "to/"):
        assert secret not in (result or "")


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("ssh::git@host.example:o/r", "host.example/o/r"),
        ("codecommit::us-east-1://repo", None),
        ("https://host.example/o/a:b", None),
        ("https://host.example/o/r/@x", None),
        (f"https://host.example/o/r;token={TOKEN}", None),
        (f"git@host.example:o/r;{TOKEN}", None),
        (f"https://host.example/o/r/a=b{TOKEN}", None),
    ],
)
def test_normalize_remote_helpers_and_guard(url: str, expected: str | None) -> None:
    """A remote helper address is normalized on its own, and odd leftovers give None."""
    assert normalize_remote(url) == expected


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("gh:owner/repo", None),
        ("git@work:owner/repo", None),
        ("git@LocalHost:owner/repo", "localhost/owner/repo"),
        ("git@10.0.0.5:owner/repo", "10.0.0.5/owner/repo"),
        ("ssh://git@work/owner/repo", "work/owner/repo"),
        ("git@[::1]:owner/repo", "[::1]/owner/repo"),
        ("git@[fe80::1]:o/r.git", "[fe80::1]/o/r"),
        ("git@[::1]/owner/repo", None),
    ],
)
def test_normalize_remote_insteadof_alias(url: str, expected: str | None) -> None:
    """An scp-style host with no dot is an insteadOf alias and gives None."""
    assert normalize_remote(url) == expected


def write_config(common: Path, text: str) -> Path:
    """Write a git config file into a common directory."""
    common.mkdir(parents=True, exist_ok=True)
    (common / "config").write_text(text)
    return common


def test_remote_prefers_origin(tmp_path: Path) -> None:
    """The origin remote wins over earlier remotes."""
    common = write_config(
        tmp_path / ".git",
        '[core]\n\tbare = false\n[remote "upstream"]\n\turl = https://h/up/r.git\n'
        '[Remote "origin"]\n\tpushurl = https://h/push/r\n\tURL = "git@h:me/r.git" ; comment\n',
    )
    assert config_remote_url(common) == "git@h:me/r.git"


def test_remote_first_in_file_order(tmp_path: Path) -> None:
    """Without origin, the first remote section in the file wins."""
    common = write_config(
        tmp_path / ".git",
        '[remote "b"]\n  url=https://h/b/r # note\n[remote "a"]\n\turl = https://h/a/r\n',
    )
    assert config_remote_url(common) == "https://h/b/r"


def test_remote_quoting_and_escapes(tmp_path: Path) -> None:
    """Quoted values keep comment characters and decode escapes."""
    common = write_config(tmp_path / ".git", '[remote "o\\"x"]\n\turl = "https://h/o/r#1" \\\\ \n')
    assert config_remote_url(common) == "https://h/o/r#1 \\"


def test_remote_missing(tmp_path: Path) -> None:
    """No file, no remote section, or no url gives no remote."""
    assert config_remote_url(tmp_path / "nope") is None
    assert config_remote_url(None) is None
    common = write_config(tmp_path / ".git", '[core]\n\tbare = false\n[remote "o"]\n\tfetch = x\n')
    assert config_remote_url(common) is None


def test_remote_unparsable(tmp_path: Path) -> None:
    """An unterminated quote or a non UTF-8 file gives no remote."""
    common = write_config(tmp_path / "a", '[remote "o"]\n\turl = "https://h/o/r\n')
    assert config_remote_url(common) is None
    bad = tmp_path / "b"
    bad.mkdir()
    (bad / "config").write_bytes(b'[remote "o"]\n\turl = https://h/\xff/r\n')
    assert config_remote_url(bad) is None


def test_machine_id_created_then_reused(tmp_path: Path) -> None:
    """The first call creates a private ID file and later calls read it back."""
    state = tmp_path / "state"
    first = machine_id(state)
    assert first is not None
    assert len(first) == 32
    assert machine_id(state) == first
    path = state / "machine-id"
    assert path.read_text() == f"{first}\n"
    assert path.stat().st_mode & 0o777 == 0o600
    assert [p.name for p in state.iterdir()] == ["machine-id"]


def test_machine_id_race_keeps_the_first(tmp_path: Path) -> None:
    """A run that loses the create race reads back the winner's ID."""
    tmp_path.joinpath("machine-id").write_text(f"{'a' * 32}\n")
    assert context._create_machine_id(tmp_path / "machine-id") == "a" * 32
    assert tmp_path.joinpath("machine-id").read_text() == f"{'a' * 32}\n"
    assert [p.name for p in tmp_path.iterdir()] == ["machine-id"]


def test_machine_id_without_hard_links(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A file system without hard links falls back to an exclusive create of the ID file."""

    def no_links(self: Path, target: Path) -> None:
        raise OSError(1, "Operation not permitted", str(self))

    monkeypatch.setattr(Path, "hardlink_to", no_links)
    first = machine_id(tmp_path)
    assert first is not None
    path = tmp_path / "machine-id"
    assert path.read_text() == f"{first}\n"
    assert path.stat().st_mode & 0o777 == 0o600
    assert [p.name for p in tmp_path.iterdir()] == ["machine-id"]
    assert machine_id(tmp_path) == first


def test_machine_id_without_hard_links_race(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The exclusive-create fallback reads back an ID another run created first."""
    path = tmp_path / "machine-id"

    def no_links(self: Path, target: Path) -> None:
        path.write_text(f"{'b' * 32}\n")
        raise OSError(18, "Cross-device link", str(self))

    monkeypatch.setattr(Path, "hardlink_to", no_links)
    assert context._create_machine_id(path) == "b" * 32
    assert path.read_text() == f"{'b' * 32}\n"
    assert [p.name for p in tmp_path.iterdir()] == ["machine-id"]


def test_machine_id_disk_error_is_not_a_missing_hard_link(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A link that fails for a disk error gives no ID and leaves no file behind."""

    def disk_full(self: Path, target: Path) -> None:
        raise OSError(errno.ENOSPC, "No space left on device", str(self))

    monkeypatch.setattr(Path, "hardlink_to", disk_full)
    assert machine_id(tmp_path) is None
    assert list(tmp_path.iterdir()) == []


def test_machine_id_temp_write_failure_skips_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A temp file write that fails gives no ID and never creates machine-id."""

    def fail_write(fd: int, data: bytes) -> int:
        raise OSError(errno.EIO, "Input/output error")

    monkeypatch.setattr(context.os, "write", fail_write)
    assert machine_id(tmp_path) is None
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("written", [None, 3])
def test_machine_id_fallback_write_failure_removes_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, written: int | None
) -> None:
    """A failed or short write in the fallback removes the file so a later run can retry."""
    real_write = os.write
    path = tmp_path / "machine-id"

    def no_links(self: Path, target: Path) -> None:
        raise OSError(errno.EXDEV, "Cross-device link", str(self))

    def write(fd: int, data: bytes) -> int:
        if not path.exists():
            return real_write(fd, data)
        if written is None:
            raise OSError(errno.ENOSPC, "No space left on device")
        return real_write(fd, data[:written])

    monkeypatch.setattr(Path, "hardlink_to", no_links)
    monkeypatch.setattr(context.os, "write", write)
    assert machine_id(tmp_path) is None
    assert list(tmp_path.iterdir()) == []
    monkeypatch.setattr(context.os, "write", real_write)
    assert machine_id(tmp_path) is not None


@pytest.mark.parametrize("content", ["", "not-an-id\n", "A" * 32, "a" * 31, "a" * 32 + "b"])
def test_machine_id_corrupt_is_left_alone(tmp_path: Path, content: str) -> None:
    """A file that does not hold an ID gives no ID and stays as it is."""
    path = tmp_path / "machine-id"
    path.write_text(content)
    assert machine_id(tmp_path) is None
    assert path.read_text() == content


def test_machine_id_unreadable(tmp_path: Path) -> None:
    """A path that cannot be read or created gives no ID."""
    (tmp_path / "machine-id").mkdir()
    assert machine_id(tmp_path) is None
    blocker = tmp_path / "file"
    blocker.write_text("x")
    assert machine_id(blocker) is None


def test_host_name(monkeypatch: pytest.MonkeyPatch) -> None:
    """The host name is the node name, or None when it cannot be read."""
    assert host_name() == os.uname().nodename

    def broken() -> os.uname_result:
        raise OSError

    monkeypatch.setattr(context.os, "uname", broken)
    assert host_name() is None
