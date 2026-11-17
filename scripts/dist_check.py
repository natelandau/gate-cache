"""Check that built distributions ship the dashboard UI and the agent guides."""  # noqa: INP001

from __future__ import annotations

import glob
import tarfile
import zipfile
from pathlib import Path

# Package files that a build must ship, as paths inside the wheel
REQUIRED_FILES = (
    "gate_cache/dashboard/static/index.html",
    "gate_cache/agent/skill.md",
    "gate_cache/agent/prompt.md",
)
WHEEL_MAX_BYTES = 300 * 1024


def expand(patterns: tuple[str, ...]) -> list[str]:
    """Expand paths or glob patterns into a sorted list of unique existing paths.

    Args:
        patterns (tuple[str, ...]): File paths or glob patterns.

    Returns:
        list[str]: Matching paths.
    """
    return sorted({match for pattern in patterns for match in glob.glob(pattern)})  # noqa: PTH207


def check_dist(path: str) -> list[str]:
    """Return the problems found in one wheel or sdist.

    Args:
        path (str): Path to a `.whl` or `.tar.gz` file.

    Returns:
        list[str]: Problem descriptions, empty when the file is fine.
    """
    problems = []
    if path.endswith(".whl"):
        size = Path(path).stat().st_size
        with zipfile.ZipFile(path) as archive:
            names = set(archive.namelist())
        if size > WHEEL_MAX_BYTES:
            problems.append(f"{path} is {size} bytes, over the {WHEEL_MAX_BYTES} byte limit")
    elif path.endswith(".tar.gz"):
        with tarfile.open(path) as archive:
            # An sdist holds `<name>-<version>/src/<package path>`
            names = {name.split("/src/", 1)[1] for name in archive.getnames() if "/src/" in name}
    else:
        return [f"{path} is neither a wheel nor an sdist"]
    problems.extend(
        f"{path} is missing {required}" for required in REQUIRED_FILES if required not in names
    )
    return problems


def check_dists(patterns: tuple[str, ...]) -> tuple[list[str], list[str]]:
    """Check every distribution matched by the given paths or globs.

    Args:
        patterns (tuple[str, ...]): File paths or glob patterns.

    Returns:
        tuple[list[str], list[str]]: Report lines and problems. A non-empty problem list means failure.
    """
    lines = []
    problems = []
    if not patterns:
        problems.append("no distribution path given")
    for pattern in patterns:
        paths = expand((pattern,))
        if not paths:
            problems.append(f"no distribution matched: {pattern}")
        for path in paths:
            found = check_dist(path)
            problems.extend(found)
            if not found:
                lines.append(f"ok: {path} ({Path(path).stat().st_size} bytes)")
    return lines, problems
