# Changelog

## v0.12.0 (2026-11-19)

### Feat

- **cli**: scope clear and stats clear, and preview what they delete (#37)

### Fix

- **security**: harden state files, terminal output, and releases (#42)
- **gate**: run uncached when a file differs from its checkout form (#41)
- **clear**: stop clear and pruning from deleting through a symlink (#40)
- **gate**: stop skipping on markers older than the max age (#39)
- **snapshot**: catch case-only renames inside submodules (#38)

## v0.11.0 (2026-11-19)

### Feat

- **cli**: add styled output and --json to every subcommand (#36)
- **config**: add per-project settings to the config file (#35)
- **stats**: add the stats report command (#34)
- **spot-check**: run a sample of skips to check the cache (#33)
- **stats**: record per-test detail from JUnit reports (#32)
- **cli**: print a gate's usual run time before it runs (#31)

### Fix

- **dashboard**: stretch overview charts to fill their card
- **hooks**: run the hook's command with the user's PATH (#30)

### Refactor

- **dashboard**: drop the redirect for old repo links

## v0.10.0 (2026-11-18)

### Feat

- **dashboard**: plot gate run time by run with gaps marked (#28)

## v0.9.0 (2026-11-18)

### Feat

- **dashboard**: group a gate's keyed names into one gate (#27)
- **dashboard**: redesign the dashboard around a shared design system (#26)
- **dashboard**: show what each gate costs to run (#25)
- **cli**: have --prompt review an existing gate-cache setup

### Fix

- **duties**: reinstall frontend packages when the lockfile changes
- **dashboard**: name the source checkout when the UI is missing

## v0.8.0 (2026-11-17)

### Feat

- **dashboard**: drill down from overview charts into runs (#24)
- **dashboard**: group overview runs by source, branch, or machine (#23)
- **dashboard**: show net time saved and waits for concurrent runs (#22)
- **dashboard**: send browser security headers (#21)
- **dashboard**: tell apart repos that share a folder name (#19)
- **gate**: wait for a concurrent run of the same gate, then skip
- **stats**: let GATE_CACHE_DATA_DIR and data_dir move stats data
- **dashboard**: turn the overview into a homepage of modules
- **cli**: look up a gate in status by its command
- **cli**: add --skill and --prompt guides for coding agents (#16)
- **cli**: confirm before clearing markers or stats (#14)
- **dashboard**: add opt-in run stats and a local dashboard (#12)

### Fix

- **dashboard**: explain how to get the UI when an install lacks it

### Perf

- **dashboard**: cache hashed UI assets in the browser (#20)
- **snapshot**: cut the git calls a gate run makes (#13)

## v0.7.0 (2026-11-16)

### Feat

- **cli**: show the time a skipped gate saved (#11)
- **cli**: limit a gate's cache to the paths it reads (#9)

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
