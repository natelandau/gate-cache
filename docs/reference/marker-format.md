---
icon: lucide/file-code
---

# Marker format

A marker is the file in which gate-cache records a pass of a gate. This page is for tools that read or write markers without calling gate-cache. To use gate-cache, you do not need it.

The marker format is a public contract, and any change to it is a breaking change.

The marker key is the lowercase hex SHA-256 of the tree hash, a NUL byte, and the gate name:

```text
key    = sha256( tree_hash + "\0" + name )
marker = $(git rev-parse --git-common-dir)/gate-cache/<key>
```

The name is the value of `--name`, or the quoted command line when `--name` is not given. The tree hash is the tree that `git add -A` followed by `git write-tree` gives, computed on a copy of the index so that the real index does not change. This shell snippet computes it on a copy of the index, then finds the marker for the `pytest` name:

```bash
index=$(mktemp)
cp -p "$(git rev-parse --git-path index)" "$index"
GIT_INDEX_FILE="$index" git add -A
tree=$(GIT_INDEX_FILE="$index" git write-tree)
rm -f "$index"
key=$(printf '%s\0%s' "$tree" pytest | shasum -a 256 | cut -d' ' -f1)
marker="$(git rev-parse --git-common-dir)/gate-cache/$key"
```

If the working copy matches the index and has no untracked, non-ignored files, `git write-tree` alone gives the same tree. The snippet writes objects for new content into `.git/objects`, as `git add` does. On Linux systems without `shasum`, `sha256sum` gives the same digest.

A gate scoped with `--path` uses the same formula with a scope value in place of the tree hash. The scope value starts with `paths:`, so it never equals a tree hash:

```text
scope  = "paths:" + sha256_hex( "gate-cache-paths-v1" + "\0" + join(paths, "\0") + "\0\0" + listing )
key    = sha256( scope + "\0" + name )
```

`paths` holds the `--path` values, sorted by byte value, with duplicates removed. `listing` is the output of `git ls-files --stage -z` for those paths, run at the top of the work tree on the staged copy of the index. This shell snippet finds the marker of the `pytest` gate scoped to `src` and `tests`:

```bash
name=pytest
paths=(src tests) # sorted by byte value, with no duplicates
index=$(mktemp)
listing=$(mktemp)
cp -p "$(git rev-parse --git-path index)" "$index"
top=$(git rev-parse --show-toplevel)
(
  cd "$top" || exit 1
  unset GIT_LITERAL_PATHSPECS GIT_GLOB_PATHSPECS GIT_NOGLOB_PATHSPECS GIT_ICASE_PATHSPECS
  GIT_INDEX_FILE="$index" git add -A
  GIT_INDEX_FILE="$index" git ls-files --stage -z -- "${paths[@]}" >"$listing"
)
digest=$({
  printf 'gate-cache-paths-v1'
  printf '\0%s' "${paths[@]}"
  printf '\0\0'
  cat "$listing"
} | shasum -a 256 | cut -d' ' -f1)
rm -f "$index" "$listing"
key=$(printf '%s\0%s' "paths:$digest" "$name" | shasum -a 256 | cut -d' ' -f1)
marker="$(git rev-parse --git-common-dir)/gate-cache/$key"
```

The listing goes through a file because the shell drops NUL bytes from the output of `$(...)`.

The existence of the marker file is the signal. gate-cache writes a small JSON object with `tree`, `name`, `command`, `timestamp`, and `duration` keys. `duration` is the run time of the command in seconds, and the skip line, `gate-cache status --name`, and `gate-cache status -- COMMAND` show it. gate-cache ignores a `duration` that is not a number from 0 to 30 days, and it does not read a marker that is larger than 16 MiB or is not a regular file. In these cases the skip line shows no saved time. A scoped gate writes its scope value in `tree`, and adds `paths`, the sorted path list, and `full_tree`, the tree of the whole working copy at the time of the run. `gate-cache status` without `--name` or a command reads this JSON to list the gates, so it does not list a marker that another tool wrote without that content. Such a marker still makes its gate skip.

When a command fails, or exits 0 but changes the tree, gate-cache writes a miss record at `<key>.miss` in the same directory. The record holds the same JSON keys as a marker, except `duration`, plus `exit_code` and `reason`. A miss record never makes a gate skip. Only `gate-cache status` reads it, to list the missed gates. A pass of the same name on the same tree deletes the miss record. A run that a signal to gate-cache stopped, such as Ctrl-C, writes no miss record. A spot check whose command fails or changes the tree deletes the marker. Pruning and `gate-cache clear` delete miss records with the markers.
