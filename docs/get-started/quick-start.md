---
icon: lucide/rocket
---

# Quick start

A coding agent can add gate-cache to a project in any language. gate-cache prints the instructions for the agent, so the instructions always match the version that the agent runs.

1. [Install gate-cache](install.md).
2. Open a coding agent, such as Claude Code, Codex, or Gemini CLI, at the top of your repository.
3. Give the agent this prompt:

    ```text
    Run `gate-cache --prompt` and follow the instructions that it prints.
    ```

4. Answer the questions of the agent.
5. Read the changes of the agent, then commit them.

The agent finds the lint, type check, and test commands of the project. Then it asks you:

- Which commands to wrap.
- How to install gate-cache in the project.
- Which gates to limit to the files that they read.
- Which commands depend on inputs that git does not track, such as an ignored `.env` file or the installed version of a tool.
- Whether git hooks run the gates.
- Whether to record stats, so that you can find flaky and slow checks.

The agent then wraps the commands, makes sure that each gate skips on a second run, and stops before it commits.

!!! tip "Review an existing setup"

    Give the same prompt in a project that already uses gate-cache. The agent then reviews the setup, reports what it found, and changes nothing until you answer.

## Next steps

- Run `gate-cache --help` to see the commands and options.
- Read [Your first gate](first-gate.md) to learn what the agent did.
- Read [Record stats](../stats/record-stats.md) to turn on the dashboard.
