"""Open and create files without trusting what others can change."""

from __future__ import annotations

import contextlib
import errno
import os
import stat
from typing import TYPE_CHECKING, BinaryIO

if TYPE_CHECKING:
    from pathlib import Path

PRIVATE_DIR_MODE = 0o700


class UnsafeDirectoryError(PermissionError):
    """A directory gate-cache writes in is owned or writable by another user."""


def ensure_private_dir(path: Path) -> None:
    """Create a directory readable only by the user, or check that an existing one is safe.

    Files inside are written on the trust that no other user can add or replace entries, which
    holds only when the user owns the directory and nobody else can write to it. A folder that
    is shared or was made by hand can break that, such as one set with GATE_CACHE_DATA_DIR.

    Args:
        path: The directory.

    Raises:
        UnsafeDirectoryError: When another user owns the directory or can write to it.
    """
    try:
        info = path.stat()
    except FileNotFoundError:
        path.mkdir(mode=PRIVATE_DIR_MODE, parents=True, exist_ok=True)
        info = path.stat()
    if info.st_uid != os.getuid():
        msg = "another user owns this directory"
        raise UnsafeDirectoryError(errno.EPERM, msg, str(path))
    if info.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
        msg = "other users can write to this directory; run chmod go-w on it"
        raise UnsafeDirectoryError(errno.EPERM, msg, str(path))


def open_regular(path: Path, *, max_bytes: int) -> BinaryIO:
    """Open a file for reading only when it is a regular file no larger than max_bytes.

    The checks run on the open file, not the path, so the file cannot be swapped between the
    check and the read.

    Args:
        path: The file to open.
        max_bytes: The largest size accepted.

    Returns:
        The open file, in binary mode.

    Raises:
        ValueError: When the file is not a regular file or is larger than max_bytes.
    """
    with contextlib.ExitStack() as on_error:
        # O_NONBLOCK keeps a FIFO from blocking the open, so fstat can reject it.
        handle = on_error.enter_context(open(os.open(path, os.O_RDONLY | os.O_NONBLOCK), "rb"))  # noqa: PTH123
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode):
            msg = f"{path} is not a regular file"
            raise ValueError(msg)
        if info.st_size > max_bytes:
            msg = f"{path} is larger than {max_bytes} bytes"
            raise ValueError(msg)
        on_error.pop_all()
    return handle
