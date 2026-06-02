#!/usr/bin/env bash
#
# git_show_commit.sh — show a commit's stat (and optionally its full patch).
#
# General-purpose verification helper, used by reviewer subagents that need
# to see "what did this commit actually touch" without spending a Bash call
# composing the right git invocation every time.
#
# Usage:
#   git_show_commit.sh <sha>                # commit message + stat only
#   git_show_commit.sh <sha> --with-patch   # message + stat + full patch
#
# Exits 0 on success, 1 on usage error or invalid SHA.

set -euo pipefail

if [ $# -lt 1 ]; then
    echo "usage: git_show_commit.sh <sha> [--with-patch]" >&2
    exit 1
fi

sha="$1"
shift

with_patch=0
for arg in "$@"; do
    case "$arg" in
        --with-patch) with_patch=1 ;;
        -h|--help)
            echo "usage: git_show_commit.sh <sha> [--with-patch]"
            exit 0
            ;;
        *)
            echo "unknown argument: $arg" >&2
            exit 1
            ;;
    esac
done

# Verify the SHA is real before invoking git show (clearer error on typos).
if ! git rev-parse --verify --quiet "${sha}^{commit}" >/dev/null; then
    echo "ERROR: not a valid commit: $sha" >&2
    exit 1
fi

if [ "$with_patch" -eq 1 ]; then
    git show "$sha" --stat
else
    git show "$sha" --stat --no-patch
fi
