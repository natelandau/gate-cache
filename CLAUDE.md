# gate-cache

gate-cache is a CLI that wraps a lint or test command. It skips the command when the same named command already passed on the same git tree. The code is in `src/gate_cache/` and the tests are in `tests/`. `README.md` and `docs/how-it-works.md` hold the user documentation.

## Commands

Run linters and tests only through these duties, never directly, so every run shares the same gate-cache markers.

- `uv run duty lint` runs ruff, the ruff format check, ty, typos, and the prek hooks. To run one gate, use `uv run duty ruff`, `format`, `ty`, `typos`, or `prek`.
- `uv run duty test` runs the full test suite with coverage.
- `uv run duty test -k NAME --no-cov` runs a subset of the tests. Without `--no-cov`, the subset fails the 90% coverage threshold.

## Gates

The duties run each gate through the gate-cache of this working copy. If a change breaks gate-cache, the duties fail too. A gate that already passed on the same content, committed or not, prints `already passed on tree` and skips. To force a full run, set `GATE_CACHE_DISABLE=1`.
