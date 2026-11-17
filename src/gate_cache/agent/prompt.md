# Add gate-cache to this repository

1. Run `gate-cache --skill` and read the guide that it prints. If `gate-cache` is not on the `PATH`, run `uvx gate-cache --skill`.
2. Find the lint, format check, type check, and test commands of this repository. Then ask the user these questions before you change anything:
   - Which of these commands do you want gate-cache to wrap? Show the list that you found.
   - How do you want to install gate-cache: as a dev dependency, in a tool manifest such as `mise.toml`, or with `uvx`?
   - Do you want to scope any gate to the paths that it reads, so that a change in another part of the repository does not run it again? Show the paths that you propose for each gate.
   - Do any of these commands depend on an input that git does not track, such as an `.env` file, a tool version, or an external service?
   - Do you want git hooks to run the gates?
3. Add gate-cache as the answers and the guide tell you. In the agent instruction file of the repository, such as `AGENTS.md` or `CLAUDE.md`, tell agents to run checks only through the wrapped commands and to run `gate-cache --skill` before they change a gate.
4. Do the steps in the "Make sure that a gate works" section of the guide for each gate. Do not commit. Report what you changed.
