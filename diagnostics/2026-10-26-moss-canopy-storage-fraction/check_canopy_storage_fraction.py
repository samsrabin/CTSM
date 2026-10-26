#!/usr/bin/env python3
"""Check a run after the moss canopy ingredients became filled fractions of canopy storage.

Reads the daily h0 tapes. Each record is a daily mean of site-level FATES fields, each
patch weighted by its area fraction, so bareground area (where the ingredients are not
diagnosed and stay 0) dilutes the site value. Four checks, from Task 1 Step 5 of
docs/superpowers/plans/2026-10-23-moss-canopy-storage-fraction.md:

  1. FATES_MOSS_FWET_CANOPY_LIQ and FATES_MOSS_FWET_CANOPY_TOT each exceed 0.05 on some
     day. Under the old wetted-fraction ingredient, CTSM capped every patch at
     maximum_leaf_wetted_fraction = 0.05, so no site value could exceed it. The values
     are compared in site units, before dividing by the non-bareground area fraction.

  2. Neither field exceeds 1 on any day.

  3. FATES_MOSS_FWET_CANOPY_LIQ <= FATES_MOSS_FWET_CANOPY_TOT on every day, exactly. On
     every patch the total ingredient is at least the liquid one (on an exposed patch it is
     the max of the liquid and snow fractions; on a buried patch liquid is 0), and both
     site sums use the same weights, so rounding cannot reverse the order.

  4. On a day when every vegetated patch is snow-buried, FATES_MOSS_FWET_CANOPY_TOT equals
     the non-bareground area fraction (1 in patch units) and FATES_MOSS_FWET_CANOPY_LIQ is
     exactly 0. FATES decides burial once a day, at the dynamics call on the first timestep
     of the day, after that timestep's history update; so a daily record carries the
     previous day's burial on its first timestep and the day's own on the rest. The fields
     compared all share that offset, so a day burial begins reads as partly buried rather
     than misjudged. A day counts as fully buried when
     FATES_SNOW_BURIED_AREA equals the non-bareground area fraction, which is the sum of
     FATES_NOCOMP_PATCHAREA_PF over PFTs. FATES_SNOW_BURIED_AREA uses the same burial
     criterion as the moss proxies (no exposed leaf or stem area, some leaf or stem area).
     Tapes written before that field existed get NO VERDICT on this check only.

Usage (ctsm_pylib env; needs netCDF4, numpy and cftime):
    check_canopy_storage_fraction.py RUNDIR [RUNDIR ...]

Each RUNDIR is a CIME case run/ directory holding one-record daily *.clm2.h0a.*.nc files.

Exit code: 1 if any check FAILed in any run, else 2 if any could not be judged
(NO VERDICT), else 0.
"""

import os
import sys

import netCDF4 as nc
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "2026-10-07-moss-total-proxy-switch"))
from checks import PFT_DIM, Report, day_label, h0_tapes, list_days, unfill  # noqa: E402

CANOPY_LIQ = "FATES_MOSS_FWET_CANOPY_LIQ"
CANOPY_TOT = "FATES_MOSS_FWET_CANOPY_TOT"
BURIED = "FATES_SNOW_BURIED_AREA"
PATCHAREA = "FATES_NOCOMP_PATCHAREA_PF"

# The old per-patch cap, maximum_leaf_wetted_fraction.
OLD_CAP = 0.05

# Relative tolerance for comparing two site-level area sums that FATES accumulates in
# different places (FATES_SNOW_BURIED_AREA and FATES_MOSS_FWET_CANOPY_TOT every timestep,
# FATES_NOCOMP_PATCHAREA_PF once a day). Both sum the same patch area fractions, so they
# differ by summation-order rounding at most.
AREA_RTOL = 1e-9


def read_daily(rundir):
    """Return (values by field, day labels), or a string saying why the tapes could not be
    read. values[BURIED] is None if the tapes lack that field."""
    paths = list(h0_tapes(rundir).values())
    if not paths:
        return "no *.clm2.h0a.*.nc files"
    n = len(paths)
    values = {CANOPY_LIQ: np.full(n, np.nan), CANOPY_TOT: np.full(n, np.nan),
              PATCHAREA: np.full(n, np.nan), BURIED: np.full(n, np.nan)}
    have_buried = None
    starts = np.full(n, np.nan)
    units = calendar = None
    for i, path in enumerate(paths):
        name = os.path.basename(path)
        with nc.Dataset(path) as d:
            d.set_auto_mask(False)
            if d.dimensions["time"].size != 1:
                return f"{name} holds {d.dimensions['time'].size} records; expected one"
            bounds = np.asarray(d["time_bounds"][0, :], dtype=np.float64)
            if bounds[1] - bounds[0] != 1.0:
                return f"{name} covers {bounds[1] - bounds[0]} days; expected a daily mean"
            starts[i] = bounds[0]
            if units is None:
                units = d["time_bounds"].units
                calendar = d["time"].calendar
            for f in (CANOPY_LIQ, CANOPY_TOT):
                if f not in d.variables:
                    return f"{name} lacks {f}"
                if tuple(d[f].dimensions) != ("time", "lndgrid"):
                    return f"{f} on {name} has dimensions {d[f].dimensions}"
                values[f][i] = unfill(d[f][0, 0])
            if PATCHAREA not in d.variables:
                return f"{name} lacks {PATCHAREA}"
            if tuple(d[PATCHAREA].dimensions) != ("time", PFT_DIM, "lndgrid"):
                return f"{PATCHAREA} on {name} has dimensions {d[PATCHAREA].dimensions}"
            values[PATCHAREA][i] = np.sum(unfill(d[PATCHAREA][0, :, 0]))
            here = BURIED in d.variables
            if have_buried is None:
                have_buried = here
            elif here != have_buried:
                return f"{BURIED} is on some tapes but not others (first change at {name})"
            if here:
                if tuple(d[BURIED].dimensions) != ("time", "lndgrid"):
                    return f"{BURIED} on {name} has dimensions {d[BURIED].dimensions}"
                values[BURIED][i] = unfill(d[BURIED][0, 0])
    if np.any(np.diff(starts) != 1.0):
        return "daily records are not contiguous and in order"
    if not have_buried:
        values[BURIED] = None
    labels = [day_label(x, units, calendar) for x in starts]
    return values, labels


def check_exceeds_old_cap(values, labels, report):
    print(f"\n(1) each canopy ingredient exceeds {OLD_CAP} (site units) on some day")
    for f in (CANOPY_LIQ, CANOPY_TOT):
        v = values[f]
        if np.isnan(v).all():
            report.line("NO VERDICT", f"{f}: all fill values")
            continue
        above = np.flatnonzero(v > OLD_CAP)
        summary = (f"{f}: above {OLD_CAP} on {above.size} of {v.size} days, "
                   f"max {np.nanmax(v):.6g}")
        if above.size:
            report.line("PASS", summary, "first such days:\n"
                        + list_days(labels, above, [(f, v)]))
        else:
            report.line("FAIL", summary)


def check_at_most_one(values, labels, report):
    print("\n(2) neither canopy ingredient exceeds 1")
    for f in (CANOPY_LIQ, CANOPY_TOT):
        v = values[f]
        if np.isnan(v).all():
            report.line("NO VERDICT", f"{f}: all fill values")
            continue
        n_nan = int(np.isnan(v).sum())
        bad = np.flatnonzero(v > 1)
        summary = f"{f}: max {np.nanmax(v):.6g}"
        if n_nan:
            summary += f"; {n_nan} days are fill values"
        if bad.size:
            report.line("FAIL", f"{summary}; above 1 on {bad.size} days",
                        list_days(labels, bad, [(f, v)]))
        else:
            report.line("PASS", summary)


def check_liq_le_tot(values, labels, report):
    print(f"\n(3) {CANOPY_LIQ} <= {CANOPY_TOT} on every day")
    liq, tot = values[CANOPY_LIQ], values[CANOPY_TOT]
    judged = ~np.isnan(liq) & ~np.isnan(tot)
    if not judged.any():
        report.line("NO VERDICT", "no day has both fields")
        return
    bad = np.flatnonzero(judged & (liq > tot))
    summary = f"judged on {int(judged.sum())} of {liq.size} days"
    if bad.size:
        report.line("FAIL", f"{summary}; LIQ > TOT on {bad.size} days, "
                            f"max excess {np.max((liq - tot)[bad]):.6g}",
                    list_days(labels, bad, [("LIQ", liq), ("TOT", tot)]))
    else:
        report.line("PASS", summary)


def check_buried_days(values, labels, report):
    print("\n(4) on days every vegetated patch is snow-buried, TOT is the non-bareground "
          "area fraction and LIQ is 0")
    buried = values[BURIED]
    if buried is None:
        report.line("NO VERDICT", f"the tapes lack {BURIED}, so buried days cannot be "
                                  f"identified")
        return
    area = values[PATCHAREA]
    liq, tot = values[CANOPY_LIQ], values[CANOPY_TOT]
    full = (area > 0) & np.isclose(buried, area, rtol=AREA_RTOL, atol=0)
    partial = (buried > 0) & ~full
    print(f"  {int(full.sum())} of {buried.size} days fully buried, {int(partial.sum())} "
          f"partly buried")
    if not full.any():
        report.line("NO VERDICT", "no day has every vegetated patch snow-buried")
        return
    idx = np.flatnonzero(full)
    tot_bad = idx[~np.isclose(tot[idx], area[idx], rtol=AREA_RTOL, atol=0)]
    liq_bad = idx[~(liq[idx] == 0)]
    columns = [("area", area), ("buried", buried), ("TOT", tot), ("LIQ", liq)]
    if tot_bad.size:
        report.line("FAIL", f"{CANOPY_TOT} differs from the non-bareground area fraction "
                            f"on {tot_bad.size} of {idx.size} fully buried days",
                    list_days(labels, tot_bad, columns))
    else:
        report.line("PASS", f"{CANOPY_TOT} equals the non-bareground area fraction on all "
                            f"{idx.size} fully buried days")
    if liq_bad.size:
        report.line("FAIL", f"{CANOPY_LIQ} is not 0 on {liq_bad.size} of {idx.size} fully "
                            f"buried days", list_days(labels, liq_bad, columns))
    else:
        report.line("PASS", f"{CANOPY_LIQ} is 0 on all {idx.size} fully buried days",
                    "first such days:\n" + list_days(labels, idx, columns))


def main(argv=None):
    rundirs = (argv if argv is not None else sys.argv[1:])
    if not rundirs:
        print(__doc__)
        return 2
    report = Report()
    for rundir in rundirs:
        print(f"\n=== {rundir}")
        got = read_daily(rundir)
        if isinstance(got, str):
            report.line("NO VERDICT", f"h0 tapes unreadable: {got}")
            continue
        values, labels = got
        print(f"  {len(labels)} daily records, {labels[0]} to {labels[-1]}")
        check_exceeds_old_cap(values, labels, report)
        check_at_most_one(values, labels, report)
        check_liq_le_tot(values, labels, report)
        check_buried_days(values, labels, report)
    print(f"\nSummary: {report.counts}")
    return report.exit_code()


if __name__ == "__main__":
    sys.exit(main())
