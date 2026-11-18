---
icon: lucide/download
---

# Install

gate-cache is a Python program, and it needs Python 3.11 or later on macOS or Linux. Your project can use any language. gate-cache only needs git and the commands that it wraps.

Install gate-cache as a command-line tool. Pick the installer that you already have:

=== "pipx"

    [pipx](https://pipx.pypa.io) installs Python command-line tools, each in its own environment.

    ```sh
    pipx install gate-cache
    ```

=== "uv"

    [uv](https://docs.astral.sh/uv/) is a Python package manager that can also install command-line tools.

    ```sh
    uv tool install gate-cache
    ```

=== "pip"

    Install into the Python environment of your user account:

    ```sh
    python3 -m pip install --user gate-cache
    ```

To make sure that gate-cache works, run:

```sh
gate-cache --version
```

## Run gate-cache without an install

pipx and uv can also download gate-cache and run it once, with no install:

```sh
pipx run gate-cache --help
uvx gate-cache --help
```

## Other ways to add gate-cache to a project

- **As a dev dependency.** In a Python project, add gate-cache to the dev dependencies of the project. Then each developer gets the same version.
- **As a git hook.** If your project uses prek or pre-commit to run its git hooks, their gate-cache hook installs gate-cache itself. Read [Git hooks](../guides/git-hooks.md).

!!! note "The dashboard needs a copy from PyPI"

    Only a copy of gate-cache installed from PyPI includes the stats dashboard, such as the copies that the commands on this page install. A copy that the prek or pre-commit hook installs, or a copy installed from a git URL or a local path, has no dashboard.

## Upgrade

=== "pipx"

    ```sh
    pipx upgrade gate-cache
    ```

=== "uv"

    ```sh
    uv tool upgrade gate-cache
    ```

=== "pip"

    ```sh
    python3 -m pip install --user --upgrade gate-cache
    ```

Read the [changelog](https://github.com/natelandau/gate-cache/blob/main/CHANGELOG.md) for the changes in each release.
