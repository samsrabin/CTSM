#!/usr/bin/env python3
"""Per-PFT daily-tape comparison of two run directories.

The companion to compare_runs_bfb.py, for the case where a difference is
expected and the question is how big it is and where.  compare_runs_bfb.py
answers "did anything move at all"; this answers "what moved, for which PFT,
and by how much", over the whole 730-day record.

Every FATES_*_PF field is per m2 of *land* area, not per m2 of the PFT's own
nocomp patch, so a PFT-relative value is the tape value divided by
FATES_NOCOMP_PATCHAREA_PF read off the same tape (--normalize; the raw
land-area values are reported by default, since those are what the tape
carries and what conserves).

--fields accepts per-PFT fields only, i.e. those carrying the fates_levpft
dimension.  Anything else is rejected rather than indexed: these tapes also
carry TSOI, SOILLIQ, SOILICE and SOILPSI on levgrnd/levsoi, and a PFT index
applied to one of those would quietly report a soil layer.  FATES's own
size-by-PFT fields (fates_levscpf, e.g. FATES_MORTALITY_HYDRAULIC_SZPF) are
rejected for the same reason; use the _PF form.

Usage:
    compare_pft_timeseries.py NEW_RUNDIR OLD_RUNDIR
    compare_pft_timeseries.py NEW_RUNDIR OLD_RUNDIR --pft 15 --fields FATES_LAI_PF
"""

import argparse
import os
import sys
from glob import glob

import netCDF4 as nc
import numpy as np

DEFAULT_GLOB = "*.clm2.h0a.*.nc"

# 1-based FATES PFT indices in fates_params_moss.json.
DEFAULT_PFTS = {12: "arctic_c3_grass", 15: "moss"}

DEFAULT_FIELDS = [
    "FATES_MORTALITY_HYDRAULIC_PF",
    "FATES_NPLANT_PF",
    "FATES_LAI_PF",
    "FATES_VEGC_PF",
]

PATCHAREA = "FATES_NOCOMP_PATCHAREA_PF"
PFT_DIM = "fates_levpft"


def check_pft_dim(var, name, path):
    """Refuse to apply a PFT index to a field that is not dimensioned by PFT."""
    if PFT_DIM not in var.dimensions:
        sys.exit(f"{name} on {path} has dimensions {var.dimensions} and no "
                 f"{PFT_DIM}: a PFT index would select an element of some other "
                 f"dimension (a soil layer, a size class) and report it under a "
                 f"PFT heading. Use the per-PFT (_PF) form of this field.")


def tape_days(rundir, pattern):
    """Map YYYY-MM-DD-SSSSS timestamp -> path, for one run directory."""
    out = {}
    for path in sorted(glob(os.path.join(rundir, pattern))):
        stamp = os.path.basename(path).rsplit(".", 2)[-2]
        out[stamp] = path
    return out


def read_series(paths, fields, ipft0, normalize):
    """Return {field: array over days} for one 0-based PFT index."""
    series = {f: np.full(len(paths), np.nan) for f in fields}
    area = np.full(len(paths), np.nan)
    checked = set()
    for iday, path in enumerate(paths):
        with nc.Dataset(path) as d:
            if normalize:
                if PATCHAREA not in checked:
                    check_pft_dim(d[PATCHAREA], PATCHAREA, path)
                    checked.add(PATCHAREA)
                area[iday] = float(np.ravel(d[PATCHAREA][:])[ipft0])
            for f in fields:
                if f not in d.variables:
                    continue
                if f not in checked:
                    check_pft_dim(d[f], f, path)
                    checked.add(f)
                series[f][iday] = float(np.ravel(d[f][:])[ipft0])
    if normalize:
        # A PFT with no patch has zero area on every day; leave those days
        # undefined rather than dividing by zero.
        with np.errstate(invalid="ignore", divide="ignore"):
            for f in fields:
                series[f] = np.where(area > 0.0, series[f] / area, np.nan)
    return series, area


def summarize(name, new, old, days):
    """One field, one PFT: print the shape of the change over the record.

    Day positions are reported as the tape's own timestamp, and every index is
    into the full record, so the two below are on the same footing.
    """
    both = np.isfinite(new) & np.isfinite(old)
    if not both.any():
        print(f"    {name:<32} absent from one or both runs")
        return
    diff = new - old
    denom = np.maximum(np.abs(old), np.abs(new))
    with np.errstate(invalid="ignore", divide="ignore"):
        rel = np.where(denom > 0, np.abs(diff) / denom, 0.0)
    idiff = np.flatnonzero(both & (diff != 0))
    ishared = np.flatnonzero(both)
    iworst = int(ishared[np.argmax(np.abs(diff[both]))])
    fnew, fold = np.isfinite(new), np.isfinite(old)
    print(f"    {name:<32}")
    print(f"        new: first {new[0]:.6g}  last {new[-1]:.6g}  "
          f"min {np.nanmin(new):.6g}  max {np.nanmax(new):.6g}  "
          f"mean {np.nanmean(new):.6g}")
    print(f"        old: first {old[0]:.6g}  last {old[-1]:.6g}  "
          f"min {np.nanmin(old):.6g}  max {np.nanmax(old):.6g}  "
          f"mean {np.nanmean(old):.6g}")
    print(f"        days differing: {idiff.size} of {int(both.sum())}; "
          f"first differing day "
          f"{days[idiff[0]] if idiff.size else '-'}")
    print(f"        largest |new-old| {abs(diff[iworst]):.6g} on day "
          f"{days[iworst]} (new {new[iworst]:.6g}, old {old[iworst]:.6g}); "
          f"max relative {np.nanmax(rel[both]):.4g}")
    print(f"        nonzero days: new {int(np.count_nonzero(new[fnew]))} of "
          f"{int(fnew.sum())} present, "
          f"old {int(np.count_nonzero(old[fold]))} of {int(fold.sum())} present")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("new_rundir")
    ap.add_argument("old_rundir")
    ap.add_argument("--glob", default=DEFAULT_GLOB)
    ap.add_argument("--pft", type=int, action="append", dest="pfts",
                    help="1-based FATES PFT index; repeatable. Default: 12 and 15.")
    ap.add_argument("--fields", nargs="+", default=DEFAULT_FIELDS)
    ap.add_argument("--normalize", action="store_true",
                    help=f"divide by {PATCHAREA} to get per-patch rather than "
                         "per-land-area values")
    ap.add_argument("--csv", help="write the per-day series to this CSV")
    args = ap.parse_args(argv)

    new_days = tape_days(args.new_rundir, args.glob)
    old_days = tape_days(args.old_rundir, args.glob)
    shared = sorted(set(new_days) & set(old_days))
    print(f"new: {len(new_days)} tapes   old: {len(old_days)} tapes   "
          f"shared: {len(shared)}")
    only_new = sorted(set(new_days) - set(old_days))
    only_old = sorted(set(old_days) - set(new_days))
    if only_new:
        print(f"  only in new ({len(only_new)}): {only_new[:3]} ...")
    if only_old:
        print(f"  only in old ({len(only_old)}): {only_old[:3]} ...")
    if not shared:
        print("No shared days; nothing to compare.")
        return 1

    pfts = args.pfts or sorted(DEFAULT_PFTS)
    new_paths = [new_days[s] for s in shared]
    old_paths = [old_days[s] for s in shared]

    rows = {}
    for pft in pfts:
        label = DEFAULT_PFTS.get(pft, f"PFT {pft}")
        units = "per patch area" if args.normalize else "per land area"
        print(f"\n=== PFT {pft} ({label}), {units} ===")
        snew, anew = read_series(new_paths, args.fields, pft - 1, args.normalize)
        sold, aold = read_series(old_paths, args.fields, pft - 1, args.normalize)
        if args.normalize:
            print(f"    {PATCHAREA}: new {np.nanmin(anew):.6g}-{np.nanmax(anew):.6g}, "
                  f"old {np.nanmin(aold):.6g}-{np.nanmax(aold):.6g}")
            if not (np.any(anew > 0.0) and np.any(aold > 0.0)):
                print(f"    {PATCHAREA} is zero on every shared day: this PFT has "
                      f"no patch, so per-patch values do not exist for it. Drop "
                      f"--normalize to see its per-land-area values.")
                continue
        for f in args.fields:
            summarize(f, snew[f], sold[f], shared)
            rows[(pft, f, "new")] = snew[f]
            rows[(pft, f, "old")] = sold[f]

    if args.csv:
        keys = sorted(rows)
        with open(args.csv, "w") as fout:
            fout.write("date," + ",".join(f"pft{p}_{f}_{w}" for p, f, w in keys) + "\n")
            for iday, stamp in enumerate(shared):
                fout.write(stamp + "," +
                           ",".join(f"{rows[k][iday]:.10g}" for k in keys) + "\n")
        print(f"\nWrote {args.csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
