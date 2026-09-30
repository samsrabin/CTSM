#!/usr/bin/env python3
"""Bit-for-bit comparison of two daily-tape run directories.

Written to answer one question: did adding TSOI/SOILLIQ/SOILICE/SOILPSI to
hist_fincl1 perturb the physics of the mosstoplayer case?  Adding history
fields should not, but a DEBUG FATES run is exactly the kind of place where
"should not" is worth measuring.

Compares every variable the two runs have in common, on every day both runs
wrote, and requires exact equality of the raw bytes of the decoded arrays --
not a tolerance.  Fields present in only one run are listed and skipped;
that is the expected state for the four new ones.

Usage:
    compare_runs_bfb.py NEW_RUNDIR OLD_RUNDIR [--glob PATTERN]
"""

import argparse
import os
import sys
from glob import glob

import netCDF4 as nc
import numpy as np

DEFAULT_GLOB = "*.clm2.h0a.*.nc"

# Coordinate/bookkeeping variables that legitimately differ between two
# invocations of the same case.  Nothing here is a physics field.
IGNORE = frozenset(
    {
        "date_written",
        "time_written",
    }
)


def tape_days(rundir, pattern):
    """Map YYYY-MM-DD-SSSSS timestamp -> path, for one run directory."""
    out = {}
    for path in sorted(glob(os.path.join(rundir, pattern))):
        base = os.path.basename(path)
        # ...clm2.h0a.<stamp>.nc
        stamp = base.rsplit(".", 2)[-2]
        out[stamp] = path
    return out


def compare_file(path_new, path_old):
    """Return (n_compared, list of (varname, description) mismatches)."""
    mismatches = []
    n_compared = 0
    with nc.Dataset(path_new) as dnew, nc.Dataset(path_old) as dold:
        shared = sorted(set(dnew.variables) & set(dold.variables) - IGNORE)
        for name in shared:
            vnew = dnew.variables[name]
            vold = dold.variables[name]
            if vnew.shape != vold.shape:
                mismatches.append((name, f"shape {vnew.shape} vs {vold.shape}"))
                continue
            vnew.set_auto_mask(False)
            vold.set_auto_mask(False)
            anew = np.asarray(vnew[:])
            aold = np.asarray(vold[:])
            n_compared += 1
            if anew.dtype != aold.dtype:
                mismatches.append((name, f"dtype {anew.dtype} vs {aold.dtype}"))
                continue
            if np.issubdtype(anew.dtype, np.floating):
                # NaN == NaN must count as equal: spval/fill slots are legal.
                if not np.array_equal(anew, aold, equal_nan=True):
                    diff = np.abs(np.nan_to_num(anew) - np.nan_to_num(aold))
                    where = np.unravel_index(int(np.argmax(diff)), diff.shape)
                    mismatches.append(
                        (
                            name,
                            f"max |diff| {diff.max():.17g} at index {where} "
                            f"(new {anew[where]!r}, old {aold[where]!r})",
                        )
                    )
            elif np.issubdtype(anew.dtype, np.integer):
                if not np.array_equal(anew, aold):
                    where = np.unravel_index(int(np.argmax(np.abs(anew - aold))), anew.shape)
                    mismatches.append(
                        (name, f"integer values differ, first at {where} "
                               f"(new {anew[where]!r}, old {aold[where]!r})")
                    )
            else:
                if not np.array_equal(anew, aold):
                    mismatches.append((name, "non-numeric values differ"))
    return n_compared, mismatches


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("new_rundir")
    ap.add_argument("old_rundir")
    ap.add_argument("--glob", default=DEFAULT_GLOB)
    args = ap.parse_args(argv)

    new = tape_days(args.new_rundir, args.glob)
    old = tape_days(args.old_rundir, args.glob)
    if not new or not old:
        sys.exit(f"no tapes matched {args.glob!r} in one of the directories "
                 f"(new: {len(new)}, old: {len(old)})")

    common = sorted(set(new) & set(old))
    print(f"new run: {len(new)} tapes in {args.new_rundir}")
    print(f"old run: {len(old)} tapes in {args.old_rundir}")
    print(f"days in both: {len(common)}")
    for label, missing in (("only in new", set(new) - set(old)), ("only in old", set(old) - set(new))):
        if missing:
            print(f"  {label}: {len(missing)} -> {sorted(missing)[:5]}{' ...' if len(missing) > 5 else ''}")

    # Field inventory, from the first shared day.
    with nc.Dataset(new[common[0]]) as dnew, nc.Dataset(old[common[0]]) as dold:
        only_new = sorted(set(dnew.variables) - set(dold.variables))
        only_old = sorted(set(dold.variables) - set(dnew.variables))
        n_shared = len(set(dnew.variables) & set(dold.variables))
    print(f"\nfields shared: {n_shared}")
    print(f"fields only in new ({len(only_new)}): {only_new}")
    print(f"fields only in old ({len(only_old)}): {only_old}")

    bad_days = {}
    total_compared = 0
    for stamp in common:
        n, mism = compare_file(new[stamp], old[stamp])
        total_compared += n
        if mism:
            bad_days[stamp] = mism

    print(f"\ncompared {total_compared} (day, field) pairs across {len(common)} days")
    if not bad_days:
        print("RESULT: bit-for-bit identical on every shared field, every day")
        return 0

    offending = {}
    for stamp, mism in bad_days.items():
        for name, desc in mism:
            offending.setdefault(name, []).append((stamp, desc))
    print(f"RESULT: {len(bad_days)} day(s) differ, on {len(offending)} field(s)")
    for name, hits in sorted(offending.items()):
        stamp, desc = hits[0]
        print(f"  {name}: {len(hits)} day(s); first {stamp}: {desc}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
