---
icon: lucide/pencil
---

# Write a gate

A gate is safe when its result depends only on its name and on the files that git sees. This page tells you how to choose the name, how to cover inputs that git does not see, and which commands not to wrap.

## Name each gate

Give each gate a short name with `--name`, such as `lint` or `test`. gate-cache matches a pass by the name and the files, so a named gate matches wherever it runs:

- By hand, in a terminal.
- In a script, a package script, or a task-runner recipe.
- In a coding agent, in any worktree of the repository.
- In a git hook, at commit or push time.

A pass in one of these places makes the gate skip in all of the others, as long as the hash of the files is the same. The dashboard also keeps all the runs of the gate under one name, even after you change the command.

## The syntax

```sh
gate-cache [--name NAME] [--path PATH]... -- COMMAND [ARGS...]
```

- `--` is required. The gate-cache options go before it, and the command goes after it.
- gate-cache runs the command exactly as given, without a shell. To use a pipe or `&&`, put the command in a script, or use `sh -c '...'`.
- gate-cache exits with the exit code of the command, or with 0 when it skips the command.

## Choose the name

gate-cache matches a pass by the gate name and the hash of the files. Two runs with the same name and the same hash are the same gate.

| You write | The name is | Use it when |
| --- | --- | --- |
| `gate-cache -- pytest -k unit` | `pytest -k unit` | The command line changes what the command checks, such as a test filter. Each command line is its own gate, so a pass of `-k unit` never skips the full suite. |
| `gate-cache --name test -- pytest` | `test` | The command line is fixed, such as in a task-runner recipe or a hook. |

Without a name, any change to the command line, such as a new option, starts a new gate with no history in the dashboard.

!!! warning "With `--name`, the command does not count"

    gate-cache matches a gate by its name and the files, not by the command after `--`. These two commands are the same gate, because both have the name `tests`:

    ```sh
    gate-cache --name tests -- pytest -k unit
    gate-cache --name tests -- pytest -k integration
    ```

    After the first one passes, the second one skips, and the integration tests never run. If the command line changes what the command checks, leave out `--name`. [Recipes](recipes.md#a-recipe-that-takes-arguments) shows a recipe that passes a test filter on to the command.

The working directory is not part of the match. For example, a lint command that checks `.` checks every file when it runs at the top of the repository, but only `src/` when it runs in `src/`. Both runs have the same name and the same hash, so a pass in `src/` makes the full check skip. Run such a command from one directory, or give each directory its own name.

## Cover inputs that git does not see

gate-cache sees the content of every file that git does not ignore, committed or not. It does not see anything outside those files, such as:

- A file that git ignores, such as an `.env` file that `.gitignore` lists.
- The environment variables of the shell that runs the gate.
- The version of a tool that is installed on the computer.
- An external service, such as a database or an API.

For example, your tests pass on Node 20, and then you upgrade to Node 22. No file changed, so `gate-cache --name test -- npm test` skips, and a test that fails on Node 22 stays hidden until a file changes.

If a gate depends on one of these inputs, put its value in the name, after an `@`. When the value changes, the name changes, so the command runs again:

```sh
# Run again when the Node version changes
gate-cache --name "test@node$(node --version)" -- npm test

# Run again when the ignored .env file changes
gate-cache --name "it@$(git hash-object .env)" -- pytest tests/it
```

`git hash-object` prints a hash of the file, so the name holds the hash and not the secrets in `.env`.

The dashboard counts every value after the `@` toward one gate, so `test@nodev20.11.0` and `test@nodev22.1.0` show as one gate, `test`. This works only when the name has no spaces. To cover more than one input, join the values after one `@`, such as `test@node22-3f2a9c`.

The shell expands `$(...)` before gate-cache starts. The hook configuration of prek and pre-commit does not go through a shell, so put such a gate in a script and call the script from the hook.

!!! danger "Never put a secret in a gate name"

    gate-cache stores the name as plain text. Without `--name`, the command line is the name, so give `--name` to a command whose command line holds a secret.

## What to wrap

Wrap a command whose result depends only on the files that git sees: lint, format check, type check, spell check, and test commands.

Do not wrap these commands:

- **A command that changes files**, such as a formatter or a linter with a fix option. gate-cache never records a pass for a command that changed files. Wrap the form that only checks, such as `prettier --check .` in place of `prettier --write .`.
- **A command whose output a later step needs**, such as a build. A skip produces no output.
- **A command with effects outside the repository**, such as a deploy or a release.
- **A check of the commit message, the branch name, or a remote.** gate-cache does not see them.

## Next steps

- If a gate checks only part of the repository, [scope it to its paths](scope-to-paths.md).
- If your project uses package scripts or a task runner, put the gate there. Read [Recipes](recipes.md).
