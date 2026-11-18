---
icon: lucide/folder-tree
---

# Scope a gate to paths

By default, a change to any file in the repository makes every gate run again. A gate with `--path` options runs again only when a file under its paths changes.

Imagine a repository with these parts:

```text
my-app/
├── api/              # the API, and its tests in api/tests/
├── web/              # the web front end
├── docs/             # the documentation
└── requirements.txt  # the dependencies of the API
```

This gate runs the API tests:

```sh
gate-cache --name api-test --path api/ --path requirements.txt -- pytest api/tests
```

It runs again only when a file under `api/`, or `requirements.txt`, changes. A change under `web/` or `docs/` does not make it run, because the API tests do not read those files.

Benefits of this approach:

- An edit to the docs or the front end does not run the API tests again.
- A rebase or a merge that brings in only changes to `web/` or `docs/` lets the gate skip.
- Coding agents that work on different parts of the repository, in different worktrees, do not run the tests of the other parts again.

## Choose the paths

!!! warning "A missing path hides a failure"

    The gate skips when nothing under its paths changed. If the command reads a file that is not in the list, a change to that file does not make the gate run, and a real failure stays hidden. If you are not sure that the command reads a file, include it. An extra path costs one run that was not necessary.

List every file that the command reads and that git tracks:

- The source and test directories that it checks.
- Lock files and dependency manifests, such as `requirements.txt`, `package.json`, `pnpm-lock.yaml`, `Cargo.lock`, or `go.sum`.
- Tool configuration, such as `pyproject.toml`, `tsconfig.json`, or `.eslintrc`.
- Shared fixtures, schemas, or generated files from other parts of the repository.
- The script, package file, or task-runner file that defines the gate.

Do not scope a gate whose command reads the whole repository, such as a spell check of every file.

## Path syntax

Each `--path` is a [git pathspec](https://git-scm.com/docs/gitglossary#Documentation/gitglossary.txt-aiddefpathspecapathspec).

- gate-cache reads each path from the top of the repository, whatever the current directory. A script that runs in `api/` also writes `--path api/`.
- A directory covers every file under it.
- The order of the paths has no effect.
- `*` also matches `/`, so `'*.toml'` matches a `.toml` file in every directory.
- `'**/package.json'` matches only a `package.json` inside a directory. To also match the one at the top, use `':(glob)**/package.json'`.
- `':(exclude)PATH'` removes files from the scope.
- Quote each path that holds `*`, `:(`, or `!`, so that the shell passes it unchanged.

```sh
gate-cache --name scripts-test \
  --path scripts/ --path ':(exclude)scripts/fixtures/' \
  -- pytest scripts
```

If a path matches no file, gate-cache runs the command without the cache and prints the path. A typo in a path therefore never makes a gate skip.

## Look up a scoped gate

To look up a scoped gate, give `gate-cache status` the same name and paths:

```sh
gate-cache status --name api-test --path api/ --path requirements.txt
```

## Keep the paths current

When a change makes the command read a new file or directory, add the path in the same change. When you move or rename a path, update every gate that names it.
