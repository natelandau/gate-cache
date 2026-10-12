# Changelog

## v0.6.0 (2026-10-12)

### Feat

- support python 3.15 (#4)

### Refactor

- **deps**: replace nclutils with stdlib helpers (#6)
- **cli**: replace cyclopts with argparse (#5)

## v0.5.0 (2026-10-12)

### Feat

- **cli**: default the gate name to the command (#3)

## v0.4.0 (2026-10-12)

### Feat

- **snapshot**: cache gate runs on uncommitted work (#2)

## v0.3.0 (2026-10-12)

### BREAKING CHANGE

- caching is off when CI is set, unless
GATE_CACHE_DISABLE is 0 or false. GATE_CACHE_DISABLE now reads empty,
0, and false (any case, trimmed) as off, so GATE_CACHE_DISABLE=false
keeps caching on instead of turning it off.

### Feat

- **status**: report missed gates and add --json output
- **gate**: run uncached when CI is set

### Fix

- **snapshot**: find the work tree when hooks set only GIT_DIR

## v0.2.0 (2026-10-11)

### Feat

- **status**: list every gate that passed when no name is given
- **gate**: make the marker age limit configurable

## v0.1.0 (2026-10-11)

### Feat

- **hooks**: add the prek and pre-commit hook manifest
- **cli**: add the gate-cache command line
- **gate**: add the cached run flow, status, and clear
- **runner**: run the wrapped command with exact exit and signal handling
- **snapshot**: detect the tree a gate is about to test
- **markers**: add the marker key contract and atomic marker files
