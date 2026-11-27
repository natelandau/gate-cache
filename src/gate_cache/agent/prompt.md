# Set up gate-cache in this repository

1. Run `gate-cache --skill` and read the guide. Not on `PATH`: `pipx run gate-cache --skill` or `uvx gate-cache --skill`, whichever exists. The guide is long enough that agent tools often cut it short: redirect each `--skill` command in this prompt to a temporary file, then read the whole file.
2. Search the repository for `gate-cache` and `gate_cache`: scripts, package files, task-runner files, hook config, dependency manifests, agent instruction file. Found: follow "Review an existing setup". Not found: follow "Add gate-cache".

## Add gate-cache

1. Find the repository's lint, format check, type check, and test commands. Before changing anything, ask the user:
   - Which of these commands should gate-cache wrap? Show the list found. Recommend leaving out commands that finish in about a second.
   - How to install gate-cache: project dev dependency, a tool the project or user already uses, or a CLI installer such as pipx or uv? Offer only choices that fit this repository and computer.
   - Scope any gate to the paths it reads, so changes elsewhere do not rerun it? Show proposed paths per gate.
   - Does any command depend on input git does not track: an ignored `.env`, an installed tool version, an external service?
   - Run the gates from git hooks?
   - Record runs on this computer to find flaky and slow checks? `gate-cache dashboard` shows the record.
2. Add gate-cache per the answers and the guide. User wants the record: `gate-cache stats on`. In the repository's agent instruction file (e.g. `AGENTS.md`, `CLAUDE.md`), tell agents to run checks only through the wrapped commands and to run `gate-cache --skill` before changing a gate.
3. Follow the "Check a gate" section of the guide for each gate. Report what changed. No commit.

## Review an existing setup

The user chose this setup and it works for them; assume it is correct. Change no file before the user answers your report. Recommend only real defects, or unused gate-cache features that help this repository.

1. Find the pinned gate-cache version: lock file, hook `rev:`, or tool manifest. Get the latest without installing: `pipx run gate-cache --version` or `uvx gate-cache@latest --version`. Pinned is older: read the latest guide the same way with `--skill`, and the changelog entries between the two versions at https://github.com/natelandau/gate-cache/blob/main/CHANGELOG.md.
2. Check each gate against the "Write a gate" section of the guide, the "Scope a gate with --path" section of the guide, and the "Rules" section of the guide. Check that the agent instruction file tells agents to run checks only through the wrapped commands.
3. Look for unused features that help this repository, e.g. `--path` for a gate reading one part of a multi-part repository, or run recording when `gate-cache stats` shows it off. A saved copy of the guide as a skill file: compare it with the latest guide.
4. Report: one line per gate with what it wraps and whether it is correct; then each defect and recommendation with reason and proposed change; or "nothing to change". Ask which changes to make. Make only those, then follow the "Check a gate" section of the guide for each changed gate. No commit.
