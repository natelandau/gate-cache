# Set up gate-cache in this repository

1. Run `gate-cache --skill` and read the guide that it prints. If `gate-cache` is not on the `PATH`, run `uvx gate-cache --skill`.
2. Search the repository for `gate-cache` and `gate_cache`. Look in task-runner files, scripts, hook config, dependency manifests, and the agent instruction file. If gate-cache is already in use, do the steps in "Review an existing setup". If not, do the steps in "Add gate-cache".

## Add gate-cache

1. Find the lint, format check, type check, and test commands of this repository. Then ask the user these questions before you change anything:
   - Which of these commands do you want gate-cache to wrap? Show the list that you found.
   - How do you want to install gate-cache: as a dev dependency, in a tool manifest such as `mise.toml`, or with `uvx`?
   - Do you want to scope any gate to the paths that it reads, so that a change in another part of the repository does not run it again? Show the paths that you propose for each gate.
   - Do any of these commands depend on an input that git does not track, such as an `.env` file, a tool version, or an external service?
   - Do you want git hooks to run the gates?
2. Add gate-cache as the answers and the guide tell you. In the agent instruction file of the repository, such as `AGENTS.md` or `CLAUDE.md`, tell agents to run checks only through the wrapped commands and to run `gate-cache --skill` before they change a gate.
3. Do the steps in the "Make sure that a gate works" section of the guide for each gate. Do not commit. Report what you changed.

## Review an existing setup

The setup is probably correct. The user chose it, and it works for them. Do not change any file before the user answers your report. Make a recommendation only when you find a real defect or a gate-cache feature that the setup does not use and that helps this repository.

1. Find the gate-cache version that the repository pins, in a lock file, a hook `rev:`, or a tool manifest. Run `uvx gate-cache@latest --version`. If the pinned version is older, read the guide of the latest version with `uvx gate-cache@latest --skill`, and read the entries between the two versions in the changelog at https://github.com/natelandau/gate-cache/blob/main/CHANGELOG.md.
2. Compare each gate with the rules in the "Write a gate" section of the guide, the "Scope a gate with --path" section of the guide, and the "Rules" section of the guide. Also make sure that the agent instruction file tells agents to run checks only through the wrapped commands.
3. Look for features that the setup does not use and that help this repository. An example is `--path` for a gate that reads only one part of a repository with several parts. If a copy of the guide is saved as a skill file, compare it with the output of `uvx gate-cache@latest --skill`.
4. Report to the user. Give one line for each gate that says what it wraps and whether it is correct. Then list each defect and each recommendation, with the reason and the change that you propose. If you find nothing to change, say so. Ask the user which changes to make. Make only those changes, then do the steps in the "Make sure that a gate works" section of the guide for each gate that you changed. Do not commit.
