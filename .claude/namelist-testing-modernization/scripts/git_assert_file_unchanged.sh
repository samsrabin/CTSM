#!/usr/bin/env bash
#
# git_assert_file_unchanged.sh — assert a file was NOT modified by a commit.
#
# General-purpose verification helper. Used when a spec says "commit X
# must not touch file Y" and a reviewer needs a binary yes/no.
#
# Usage:
#   git_assert_file_unchanged.sh <sha> <path>
#
# Exits 0 if the file is identical at <sha>^ and <sha>.
# Exits 1 if the file changed (prints the diff to stderr).
# Exits 2 on usage error or invalid SHA / path.

set -euo pipefail

if [ $# -ne 2 ]; then
    echo "usage: git_assert_file_unchanged.sh <sha> <path>" >&2
    exit 2
fi

sha="$1"
path="$2"

if ! git rev-parse --verify --quiet "${sha}^{commit}" >/dev/null; then
    echo "ERROR: not a valid commit: $sha" >&2
    exit 2
fi

# git diff exits zero whether or not there are changes, so we use its
# output rather than its exit code as the signal.
diff_output="$(git diff "${sha}^" "$sha" -- "$path")"

if [ -z "$diff_output" ]; then
    echo "OK: $path was not modified by $sha"
    exit 0
fi

echo "CHANGED: $path was modified by $sha" >&2
printf '%s\n' "$diff_output" >&2
exit 1
