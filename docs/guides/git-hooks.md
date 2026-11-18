---
icon: lucide/git-commit-horizontal
---

# Git hooks

A git hook is a script that git runs at a set time, such as before a commit or before a push. Hooks that run your tests make each commit and each push slow, even when you ran the same tests a minute ago. With gate-cache, a hook skips a gate that already passed with the same hash of your files:

1. You run the test gate in your terminal, or a coding agent runs it. The tests pass.
2. You commit. The pre-commit hook runs the same gate, and it skips.
3. You push. The pre-push hook skips too.

If you change a file between these steps, the hook runs the tests. The hook still protects every commit, and it costs time only when the files changed.

## Add a gate to a hook

Use the same gate name in the hook as in your terminal, so that a pass in one makes the other skip. Pick the way that matches how your project runs its hooks:

=== "A plain git hook"

    A plain git hook needs no other tool. Put a script in `.git/hooks/` and make it executable:

    ```sh title=".git/hooks/pre-push"
    #!/bin/sh
    exec gate-cache --name test -- pytest
    ```

    ```sh
    chmod +x .git/hooks/pre-push
    ```

    git does not share `.git/hooks/` through the repository, so each developer adds the script. The script needs `gate-cache` on the `PATH`.

=== "prek or pre-commit"

    [prek](https://github.com/j178/prek) and [pre-commit](https://pre-commit.com) are tools that run the git hooks of a project from a `.pre-commit-config.yaml` file. gate-cache works with prek and with pre-commit 3.2 or later. Its hook installs gate-cache itself, so developers do not need to install it. The `args` are the same as the command line:

    ```yaml title=".pre-commit-config.yaml"
    repos:
      - repo: https://github.com/natelandau/gate-cache
        rev: v0.10.0
        hooks:
          - id: gate-cache
            name: test
            args: [--name, test, --, npm, test]
    ```

    The hook runs at commit time and at push time. To limit it to one stage, add `stages: [pre-push]`. At commit time, prek and pre-commit put aside the changes that you did not stage, so gate-cache matches the content that you commit.

    Read [Start the command in the project environment](#start-the-command-in-the-project-environment) before you use this hook.

=== "prek or pre-commit, with your own command"

    If your project already runs its gates from a script, a package script, or a task runner, a local hook can call that command. A commit, a push, an agent, and your terminal then all run the same command:

    ```yaml title=".pre-commit-config.yaml"
    repos:
      - repo: local
        hooks:
          - id: test
            name: test
            entry: npm test
            language: system
            pass_filenames: false
            stages: [pre-commit, pre-push]
    ```

    This form needs `gate-cache` on the `PATH` of each developer.

## Start the command in the project environment

This section applies only to the gate-cache hook of prek and pre-commit. That hook runs in its own Python environment, and that environment comes first on the `PATH` of the command. A bare tool name, such as `pytest`, finds the copy in the hook environment, or finds nothing.

Start the command in one of these ways:

- With the command that your project uses to run its tools, such as `npm test`, `bundle exec rspec`, or `poetry run pytest`.
- With an absolute path, such as `.venv/bin/pytest`.

Some Python project tools print a warning that `VIRTUAL_ENV` does not match the project. The warning comes from the hook environment and has no effect on the run.

## Things that hooks do not support

- A hook configuration of prek or pre-commit does not go through a shell, so `$(...)` does not expand in `args`. Put a gate with such a name in a script, and call the script from the hook. [Write a gate](write-a-gate.md#cover-inputs-that-git-does-not-see) shows these names.
- The copy of gate-cache that the prek or pre-commit hook installs has no dashboard. It still records stats when recording is on. To open the dashboard, use a copy from PyPI. Read [Install](../get-started/install.md).
