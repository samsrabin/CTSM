#!/usr/bin/env python3
"""Dump the FATES time series needed for the moss-extinction diagnosis.

Reads a directory of CLM/FATES daily history files (h0a) and prints
per-PFT and site-level series for the variables that bear on why the moss
cohort is culled.  Read-only; writes nothing but stdout.

Usage:
    read_moss_tape.py RUNDIR [--vars V1,V2,...] [--days D1:D2] [--csv OUT.csv]

PFT indices are 1-based on the command line and in the output, matching
FATES: moss is 15, arctic C3 grass is 12 in this branch's parameter file.
"""

import argparse
import glob
import os
import sys

import numpy as np
import xarray as xr

MOSS_PFT = 15
GRASS_PFT = 12

# Site-level FATES diagnostics that are patch-area weighted sums; bareground
# contributes zero, so a site value is the patch value times the
# non-bareground area fraction.
DEFAULT_PFT_VARS = [
    "FATES_GPP_PF",
    "FATES_LEAFC_PF",
    "FATES_CROWNAREA_PF",
    "FATES_LAI_PF",
    "FATES_SAI_PF",
    "FATES_NOCOMP_PATCHAREA_PF",
    "FATES_MORTALITY_TERMINATION_PF",
    "FATES_MORTALITY_HYDRAULIC_PF",
]
DEFAULT_SITE_VARS = [
    "FATES_NCOHORTS",
    "FATES_GPP",
    "FATES_NPP",
    "FATES_AUTORESP",
    "FATES_MAINT_RESP",
    "FATES_GROWTH_RESP",
    "FATES_STOREC",
    "FATES_LEAFC",
    "FATES_FROOTC",
    "FATES_SAPWOODC",
    "FATES_STRUCTC",
    "FATES_REPROC",
    "FATES_SEED_ALLOC",
    "FATES_SEED_BANK",
    "FATES_SEEDS_IN",
    "FATES_MORTALITY_CFLUX_CANOPY",
    "FATES_MORTALITY_CFLUX_USTORY",
    "FATES_TRIMMING",
    "FATES_COLD_STATUS",
    "FATES_MOSS_FWET",
    "FATES_MOSS_HEIGHT",
    "FATES_CBALANCE_ERROR",
]


def open_tape(rundir):
    files = sorted(glob.glob(os.path.join(rundir, "*.clm2.h0a.*.nc")))
    if not files:
        files = sorted(glob.glob(os.path.join(rundir, "*.clm2.h0.*.nc")))
    if not files:
        sys.exit(f"no h0a/h0 history files under {rundir}")
    # Nested concat along time, not combine="by_coords". These tapes are one
    # timestep per file, and by_coords reads and aligns every file's coords up
    # front, which does not finish in five minutes over a couple of hundred
    # files. The filenames are date-stamped, so sorted() is already time order,
    # which is what nested concat requires.
    ds = xr.open_mfdataset(
        files, combine="nested", concat_dim="time",
        data_vars="minimal", coords="minimal", compat="override",
        decode_timedelta=False, decode_times=True,
    )
    return ds, files


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("rundir")
    p.add_argument("--vars", default=None,
                   help="comma-separated extra variables to include")
    p.add_argument("--days", default=None,
                   help="D1:D2 slice of 1-based day indices to print in full")
    p.add_argument("--pfts", default=f"{GRASS_PFT},{MOSS_PFT}",
                   help="comma-separated 1-based PFT indices")
    p.add_argument("--csv", default=None)
    args = p.parse_args()

    ds, files = open_tape(args.rundir)
    ntime = ds.sizes["time"]
    print(f"{len(files)} files, {ntime} times, "
          f"{str(ds.time.values[0])[:10]} .. {str(ds.time.values[-1])[:10]}")

    pfts = [int(x) for x in args.pfts.split(",")]
    extra = args.vars.split(",") if args.vars else []

    cols = {}
    for v in DEFAULT_PFT_VARS + [e for e in extra if e.endswith("_PF")]:
        if v not in ds:
            print(f"  (absent: {v})")
            continue
        for ip in pfts:
            cols[f"{v}[{ip}]"] = np.asarray(
                ds[v].isel(fates_levpft=ip - 1, lndgrid=0).values, dtype=float)
    for v in DEFAULT_SITE_VARS + [e for e in extra if not e.endswith("_PF")]:
        if v not in ds:
            print(f"  (absent: {v})")
            continue
        cols[v] = np.asarray(ds[v].isel(lndgrid=0).values, dtype=float)

    print("\n=== summary (min / mean / max / n>0) ===")
    for k, a in cols.items():
        finite = a[np.isfinite(a)]
        print(f"{k:42s} {np.nanmin(finite):13.5e} {np.nanmean(finite):13.5e} "
              f"{np.nanmax(finite):13.5e}  {int((finite > 0).sum()):4d}/{finite.size}")

    if args.days:
        d1, d2 = (int(x) for x in args.days.split(":"))
        idx = range(max(1, d1), min(ntime, d2) + 1)
        print(f"\n=== days {d1}:{d2} ===")
        keys = list(cols)
        width = max(len(k) for k in keys) + 1
        for k in keys:
            row = " ".join(f"{cols[k][i-1]:12.5e}" for i in idx)
            print(f"{k:{width}s} {row}")
        print(f"{'day':{width}s} " + " ".join(f"{i:12d}" for i in idx))
        print(f"{'date':{width}s} "
              + " ".join(f"{str(ds.time.values[i-1])[:10]:>12s}" for i in idx))

    if args.csv:
        import pandas as pd
        pd.DataFrame(cols, index=ds.time.values).to_csv(args.csv)
        print(f"\nwrote {args.csv}")


if __name__ == "__main__":
    main()
