#!/usr/bin/env bash
#
# Regenerate baseline_checksum.txt for a perf_testing/<routine>/ subdir.
#
# Usage (from inside the routine subdir):
#     ../regen_baseline.sh
# or (with explicit target):
#     perf_testing/regen_baseline.sh perf_testing/<routine>
#
# Steps: source ../env.sh, make clean, make, ./driver, cp last_run.txt
# -> baseline_checksum.txt, print before/after diff. Does NOT git add or
# git commit — review the diff and commit yourself.

set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ "$#" -ge 1 ]; then
    target="$1"
else
    target="$(pwd)"
fi
cd "$target"

if [ ! -f Makefile ] || [ ! -f driver.F90 ]; then
    echo "regen_baseline: $target does not look like a perf_testing/<routine>/ subdir" >&2
    echo "  (expected Makefile and driver.F90)" >&2
    exit 1
fi

# Save old baseline (if any) for diff reporting.
old_baseline=""
if [ -f baseline_checksum.txt ]; then
    old_baseline="$(mktemp)"
    cp baseline_checksum.txt "$old_baseline"
fi

# shellcheck disable=SC1091
. "$script_dir/env.sh"

echo "==> make clean && make"
make clean
make

echo
echo "==> ./driver"
./driver

if [ ! -f last_run.txt ]; then
    echo "regen_baseline: ./driver did not produce last_run.txt" >&2
    exit 1
fi

cp last_run.txt baseline_checksum.txt

echo
echo "==> baseline_checksum.txt updated:"
cat baseline_checksum.txt

if [ -n "$old_baseline" ]; then
    echo
    echo "==> diff vs old baseline (- old, + new):"
    diff "$old_baseline" baseline_checksum.txt || true
    rm -f "$old_baseline"
fi

echo
echo "Next steps:"
echo "    git diff baseline_checksum.txt"
echo "    git add baseline_checksum.txt && git commit"
