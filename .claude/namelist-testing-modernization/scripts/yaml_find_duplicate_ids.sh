#!/usr/bin/env bash
#
# yaml_find_duplicate_ids.sh — find duplicate `id:` values in a YAML file.
#
# Tuned for our case-manifest shape (`- id: <slug>` at column 0 or
# `  id: <slug>` at column 2), but works for any YAML where IDs appear as
# `id: <value>` on their own line.
#
# Usage:
#   yaml_find_duplicate_ids.sh <yaml-file>
#
# Exits 0 if no duplicates (also prints the total ID count).
# Exits 1 if any duplicates (prints "<count> <id>" lines for each duplicate
# to stdout; the surrounding "DUPLICATES FOUND:" header goes to stdout too).
# Exits 2 on usage error or missing file.

set -euo pipefail

if [ $# -ne 1 ]; then
    echo "usage: yaml_find_duplicate_ids.sh <yaml-file>" >&2
    exit 2
fi

file="$1"

if [ ! -f "$file" ]; then
    echo "ERROR: file not found: $file" >&2
    exit 2
fi

# Match lines like "- id: foo" or "  id: foo" — i.e., 'id:' at the start of
# the line or preceded by exactly one of leading "- " or two spaces. The
# last whitespace-delimited token on the matching line is the id value.
ids="$(grep -E '^(- id: |  id: )' "$file" | awk '{print $NF}')"

if [ -z "$ids" ]; then
    echo "OK: no ids found (file may not be a case-manifest)."
    exit 0
fi

total="$(printf '%s\n' "$ids" | wc -l | tr -d ' ')"

# uniq -c needs sorted input. Each output line is "<count> <id>"; filter to
# count > 1.
dupes="$(printf '%s\n' "$ids" | sort | uniq -c | awk '$1 > 1')"

if [ -z "$dupes" ]; then
    echo "OK: $total ids, no duplicates."
    exit 0
fi

echo "DUPLICATES FOUND ($total total ids):"
printf '%s\n' "$dupes"
exit 1
