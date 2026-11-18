---
icon: lucide/book-open
---

# Recipes

Many projects give their checks short names, such as `lint` and `test`, in a package file or a task runner. A task runner is a tool that runs named commands for a project, such as make, just, mise, or Task. Node projects often use the scripts in `package.json` instead.

If your project does this, put gate-cache in those commands. Then you, your git hooks, and your coding agents all run the same gate under the same name, and a pass in one of them makes the others skip. Use the tab of the tool that your project uses. If your project uses none of them, you do not need this page. Run the gate-cache commands directly, as [Your first gate](../get-started/first-gate.md) shows.

## Lint and test

=== "just"

    ```just title="justfile"
    lint:
        gate-cache --name lint -- ruff check .

    test:
        gate-cache --name test -- pytest
    ```

=== "make"

    ```make title="Makefile"
    .PHONY: lint test

    lint:
    	gate-cache --name lint -- npx eslint .

    test:
    	gate-cache --name test -- npx vitest run
    ```

=== "npm scripts"

    ```json title="package.json"
    {
      "scripts": {
        "lint": "gate-cache --name lint -- eslint .",
        "test": "gate-cache --name test -- vitest run"
      }
    }
    ```

=== "mise"

    ```toml title="mise.toml"
    [tasks.lint]
    run = "gate-cache --name lint -- cargo clippy -- -D warnings"

    [tasks.test]
    run = "gate-cache --name test -- cargo test"
    ```

=== "Task"

    ```yaml title="Taskfile.yml"
    version: "3"

    tasks:
      lint:
        cmds:
          - gate-cache --name lint -- golangci-lint run
      test:
        cmds:
          - gate-cache --name test -- go test ./...
    ```

The rest of this page uses just in its examples. The same ideas work in the other tools.

## A recipe that takes arguments

If a recipe passes its own arguments on to the command, such as a test filter, leave out `--name`. The command line then changes with the arguments, and each command line is its own gate:

```just title="justfile"
test *args:
    gate-cache -- pytest {{ args }}
```

`just test` and `just test -k unit` are two gates, so a pass of the unit tests never skips the full suite.

Use relative paths in the command. An absolute path, such as `{{ justfile_directory() }}/tests`, puts the location of the worktree in the name, so a pass in one worktree never skips the gate in another.

## An input that git does not track

Put the value of the input in the name, after an `@`. The shell of the recipe computes the value before gate-cache starts:

=== "just"

    ```just title="justfile"
    # Run again when the Node version changes
    test:
        gate-cache --name "test@node$(node --version)" -- npm test

    # Run again when the ignored .env file changes
    integration:
        gate-cache --name "integration@$(git hash-object .env)" -- pytest tests/integration
    ```

=== "npm scripts"

    ```json title="package.json"
    {
      "scripts": {
        "test": "gate-cache --name \"test@node$(node --version)\" -- vitest run"
      }
    }
    ```

[Write a gate](write-a-gate.md#cover-inputs-that-git-does-not-see) explains these names.

## A gate for one part of the repository

```just title="justfile"
api-test:
    gate-cache --name api-test --path api/ --path requirements.txt --path justfile -- pytest api/tests
```

The gate runs again only when a file under `api/`, `requirements.txt`, or the `justfile` changes. Read [Scope a gate to paths](scope-to-paths.md).
