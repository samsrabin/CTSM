#!/usr/bin/env python3
"""Assess the moss PFT after setting its ``fates_allom_l2fr`` to zero.

Reads the daily ``*.clm2.h0a.*.nc`` tapes of two runs of the same
instrumented ALP2 nocomp FATES case -- the new one (moss
``fates_allom_l2fr = 0.0``) and the archived baseline (moss
``fates_allom_l2fr = 0.67``, inherited from arctic C3 grass) -- and
answers the nine questions the change was made to settle: whether the
moss cohort survives, what its storage carbon, NPP, leaf carbon,
plant density, crown area, LAI and GPP do, whether anything recruits,
whether grass is left alone, and whether the carbon balance stays
closed.

Simulation day numbering follows the tape: day 1 is the first history
file written, whose filename date is one day after ``RUN_STARTDATE``.

NOTE ON NORMALIZATION: every ``FATES_*_PF`` field is per m2 of LAND
area, not per m2 of the PFT's own patch. In this configuration the
prescribed nocomp patch areas are moss 0.5, grass 0.3, bareground 0.2,
so a patch-relative value is the printed value divided by that area.
Site-level fields (``FATES_NCOHORTS``, ``FATES_CBALANCE_ERROR``) are
whole-gridcell.
"""

import argparse
import glob
import os
import re
import sys
import warnings

import netCDF4 as nc
import numpy as np

# 1-based PFT indices in this configuration.
PFT_MOSS = 15
PFT_GRASS = 12

# Prescribed nocomp patch area fractions, used only to convert the
# per-m2-LAND crown area into a fraction of the PFT's own patch.
PATCH_AREA = {PFT_MOSS: 0.5, PFT_GRASS: 0.3}

# The day the baseline run culled the moss cohort.
BASELINE_CULL_DAY = 402

PF_FIELDS = [
    "FATES_STOREC_PF",
    "FATES_NPP_PF",
    "FATES_GPP_PF",
    "FATES_LEAFC_PF",
    "FATES_NPLANT_PF",
    "FATES_CROWNAREA_PF",
    "FATES_LAI_PF",
    "FATES_VEGC_PF",
    "FATES_SEED_BANK_PF",
    "FATES_SEEDS_IN_PF",
    "FATES_RECRUITMENT_PF",
    "FATES_MORTALITY_CSTARV_PF",
    "FATES_MORTALITY_PF",
    "FATES_MORTALITY_TERMINATION_PF",
    "FATES_NOCOMP_PATCHAREA_PF",
]

SITE_FIELDS = ["FATES_NCOHORTS", "FATES_CBALANCE_ERROR"]

DATE_RE = re.compile(r"\.clm2\.h0a\.(\d{4}-\d{2}-\d{2})-(\d{5})\.nc$")


def find_files(rundir):
    """Return (date, path) for the daily h0a files, sorted by date."""
    out = []
    for path in sorted(glob.glob(os.path.join(rundir, "*.clm2.h0a.*.nc"))):
        match = DATE_RE.search(path)
        if match:
            out.append((match.group(1), path))
    out.sort()
    if not out:
        sys.exit("No *.clm2.h0a.*.nc files found in %s" % rundir)
    return out


def scalar(dataset, name, pft=None):
    """Read one value out of a single-timestep, single-gridcell field."""
    if name not in dataset.variables:
        return np.nan
    arr = np.ma.filled(np.asarray(dataset.variables[name][:], dtype=float), np.nan)
    if pft is None:
        return float(arr.reshape(-1)[0])
    # (time, fates_levpft, lndgrid)
    return float(arr[0, pft - 1, 0])


def units_of(path, name):
    dataset = nc.Dataset(path)
    try:
        if name not in dataset.variables:
            return "(absent)"
        return getattr(dataset.variables[name], "units", "(none)")
    finally:
        dataset.close()


def load(rundir):
    """Load every field of interest for both PFTs over a whole run."""
    files = find_files(rundir)
    ndays = len(files)
    data = {}
    for name in PF_FIELDS:
        for pft in (PFT_MOSS, PFT_GRASS):
            data[(name, pft)] = np.full(ndays, np.nan)
    for name in SITE_FIELDS:
        data[(name, None)] = np.full(ndays, np.nan)
    for idx, (_, path) in enumerate(files):
        dataset = nc.Dataset(path)
        for name in PF_FIELDS:
            for pft in (PFT_MOSS, PFT_GRASS):
                data[(name, pft)][idx] = scalar(dataset, name, pft)
        for name in SITE_FIELDS:
            data[(name, None)][idx] = scalar(dataset, name)
        dataset.close()
    return [d for d, _ in files], [p for _, p in files], data


def stats(row):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return np.nanmin(row), np.nanmean(row), np.nanmax(row)


def fmt_stats(label, row, unit):
    lo, mean, hi = stats(row)
    return "%-32s min %13.6g  mean %13.6g  max %13.6g   [%s]" % (
        label, lo, mean, hi, unit)


def monthly_means(dates, row):
    """Mean of row by calendar month, for describing seasonality."""
    out = {}
    for month in range(1, 13):
        sel = [i for i, d in enumerate(dates) if int(d[5:7]) == month]
        if sel:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                out[month] = np.nanmean(row[sel])
    return out


def trend_description(row):
    """Say whether a series only ever falls, only ever rises, or turns."""
    finite = row[np.isfinite(row)]
    if finite.size < 2:
        return "too short to characterize"
    diffs = np.diff(finite)
    nup = int(np.sum(diffs > 0))
    ndown = int(np.sum(diffs < 0))
    nflat = int(np.sum(diffs == 0))
    if nup == 0 and ndown > 0:
        shape = "monotonically non-increasing"
    elif ndown == 0 and nup > 0:
        shape = "monotonically non-decreasing"
    else:
        shape = "non-monotonic"
    return ("%s (%d up, %d down, %d flat daily steps; first %.6g, "
            "last %.6g, net %+.6g)"
            % (shape, nup, ndown, nflat, finite[0], finite[-1],
               finite[-1] - finite[0]))


def hline(text):
    print()
    print("=" * 78)
    print(text)
    print("=" * 78)


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("rundir",
                        help="directory of the new run's daily h0a files")
    parser.add_argument("baselinedir",
                        help="directory of the archived baseline h0a files")
    parser.add_argument("--lndlog", default=None,
                        help="lnd.log of the new run, checked for a CTSM "
                             "water-balance endrun")
    args = parser.parse_args()

    dates, paths, new = load(args.rundir)
    bdates, bpaths, base = load(args.baselinedir)
    nday = len(dates)
    nbase = len(bdates)
    print("New run:      %d daily files, %s .. %s" % (nday, dates[0], dates[-1]))
    print("Baseline run: %d daily files, %s .. %s"
          % (nbase, bdates[0], bdates[-1]))
    if dates[:min(nday, nbase)] != bdates[:min(nday, nbase)]:
        sys.exit("The two runs' dates do not line up; refusing to compare.")
    print("Day N == the Nth file; day 1 = %s." % dates[0])
    print("All FATES_*_PF values are per m2 LAND area (moss patch area "
          "0.5, grass 0.3, bareground 0.2).")
    unit = {name: units_of(paths[-1], name) for name in PF_FIELDS + SITE_FIELDS}

    # ---- 1. does the moss cohort survive? -------------------------------
    hline("1 -- does the moss cohort survive all %d days?" % nday)
    for tag, dd, dat in (("new", dates, new), ("baseline", bdates, base)):
        leafc = dat[("FATES_LEAFC_PF", PFT_MOSS)]
        nplant = dat[("FATES_NPLANT_PF", PFT_MOSS)]
        ncoh = dat[("FATES_NCOHORTS", None)]
        zero_leaf = [i for i in range(len(dd)) if leafc[i] == 0.0]
        zero_npl = [i for i in range(len(dd)) if nplant[i] == 0.0]
        drops = [i for i in range(1, len(dd))
                 if np.isfinite(ncoh[i]) and np.isfinite(ncoh[i - 1])
                 and ncoh[i] < ncoh[i - 1]]
        print("[%s]" % tag)
        print("    moss FATES_LEAFC_PF first exactly zero: %s"
              % ("never" if not zero_leaf
                 else "day %d (%s)" % (zero_leaf[0] + 1, dd[zero_leaf[0]])))
        print("    moss FATES_NPLANT_PF first exactly zero: %s"
              % ("never" if not zero_npl
                 else "day %d (%s)" % (zero_npl[0] + 1, dd[zero_npl[0]])))
        print("    FATES_NCOHORTS decreases on: %s"
              % ("never" if not drops
                 else ", ".join("day %d (%s) %g->%g"
                                % (i + 1, dd[i], ncoh[i - 1], ncoh[i])
                                for i in drops)))
        print("    FATES_NCOHORTS first %g, last %g, min %g, max %g"
              % (ncoh[0], ncoh[-1], np.nanmin(ncoh), np.nanmax(ncoh)))

    # ---- 2. moss storage carbon -----------------------------------------
    hline("2 -- moss FATES_STOREC_PF (the pool whose zero triggered the "
          "baseline cull)")
    row = new[("FATES_STOREC_PF", PFT_MOSS)]
    print(fmt_stats("new, whole run", row, unit["FATES_STOREC_PF"]))
    print(fmt_stats("baseline, whole run",
                    base[("FATES_STOREC_PF", PFT_MOSS)],
                    unit["FATES_STOREC_PF"]))
    print("trend (new): %s" % trend_description(row))
    print("days at exactly zero (new): %d"
          % int(np.sum(row == 0.0)))
    print("day-of-minimum (new): day %d (%s)"
          % (int(np.nanargmin(row)) + 1, dates[int(np.nanargmin(row))]))
    print("day-of-maximum (new): day %d (%s)"
          % (int(np.nanargmax(row)) + 1, dates[int(np.nanargmax(row))]))
    print("monthly means (new), kg m-2 LAND:")
    for month, val in sorted(monthly_means(dates, row).items()):
        print("    %02d  %13.6g" % (month, val))
    print("value every 30th day (new), kg m-2 LAND:")
    for i in range(0, nday, 30):
        print("    day %4d %s  %13.6g" % (i + 1, dates[i], row[i]))
    print("    day %4d %s  %13.6g" % (nday, dates[-1], row[-1]))

    # ---- 3. moss NPP ------------------------------------------------------
    hline("3 -- moss FATES_NPP_PF")
    for tag, dat in (("new", new), ("baseline", base)):
        row = dat[("FATES_NPP_PF", PFT_MOSS)]
        npos = int(np.sum(row > 0.0))
        nneg = int(np.sum(row < 0.0))
        print("[%s] positive on %d of %d days, negative on %d"
              % (tag, npos, len(row), nneg))
        print("      " + fmt_stats("", row, unit["FATES_NPP_PF"]))
    print("monthly means (new), %s:" % unit["FATES_NPP_PF"])
    for month, val in sorted(
            monthly_means(dates, new[("FATES_NPP_PF", PFT_MOSS)]).items()):
        print("    %02d  %13.6g" % (month, val))

    # ---- 4. moss structure ----------------------------------------------
    hline("4 -- moss leaf carbon, plant density, crown area, LAI")
    for name in ("FATES_LEAFC_PF", "FATES_NPLANT_PF", "FATES_CROWNAREA_PF",
                 "FATES_LAI_PF"):
        row = new[(name, PFT_MOSS)]
        print(fmt_stats(name + " (new)", row, unit[name]))
        print("    trend: %s" % trend_description(row))
        print("    " + fmt_stats(name + " (baseline)",
                                 base[(name, PFT_MOSS)], unit[name]))
    ca = new[("FATES_CROWNAREA_PF", PFT_MOSS)]
    cab = base[("FATES_CROWNAREA_PF", PFT_MOSS)]
    print("moss crown area as a percentage of its own 0.5 patch:")
    print("    new      first %.6f%%  max %.6f%%  last %.6f%%"
          % (100 * ca[0] / PATCH_AREA[PFT_MOSS],
             100 * np.nanmax(ca) / PATCH_AREA[PFT_MOSS],
             100 * ca[-1] / PATCH_AREA[PFT_MOSS]))
    print("    baseline first %.6f%%  max %.6f%%  last %.6f%%"
          % (100 * cab[0] / PATCH_AREA[PFT_MOSS],
             100 * np.nanmax(cab) / PATCH_AREA[PFT_MOSS],
             100 * cab[-1] / PATCH_AREA[PFT_MOSS]))
    print("moss FATES_NOCOMP_PATCHAREA_PF (new) first %g last %g"
          % (new[("FATES_NOCOMP_PATCHAREA_PF", PFT_MOSS)][0],
             new[("FATES_NOCOMP_PATCHAREA_PF", PFT_MOSS)][-1]))

    # ---- 5. moss GPP vs baseline ----------------------------------------
    hline("5 -- moss FATES_GPP_PF, new vs baseline")
    compare_field("FATES_GPP_PF", PFT_MOSS, new, base, nbase, dates,
                  unit["FATES_GPP_PF"])

    # ---- 6. recruitment --------------------------------------------------
    hline("6 -- does anything recruit?")
    for name in ("FATES_SEED_BANK_PF", "FATES_SEEDS_IN_PF",
                 "FATES_RECRUITMENT_PF"):
        for pft, label in ((PFT_MOSS, "moss 15"), (PFT_GRASS, "grass 12")):
            row = new[(name, pft)]
            nz = np.nonzero(row > 0.0)[0]
            first = ("never" if nz.size == 0
                     else "day %d (%s)" % (nz[0] + 1, dates[nz[0]]))
            print("%-24s %-9s first > 0: %-22s  %s"
                  % (name, label, first, fmt_stats("", row, unit[name])))
            rowb = base[(name, pft)]
            nzb = np.nonzero(rowb > 0.0)[0]
            print("%-24s %-9s   baseline first > 0: %s"
                  % ("", "", "never" if nzb.size == 0
                     else "day %d (%s)" % (nzb[0] + 1, bdates[nzb[0]])))
    ncoh = new[("FATES_NCOHORTS", None)]
    print("FATES_NCOHORTS (new) daily values where they change:")
    print("    day 1 (%s): %g" % (dates[0], ncoh[0]))
    for i in range(1, nday):
        if np.isfinite(ncoh[i]) and np.isfinite(ncoh[i - 1]) \
                and ncoh[i] != ncoh[i - 1]:
            print("    day %d (%s): %g -> %g"
                  % (i + 1, dates[i], ncoh[i - 1], ncoh[i]))

    # ---- 7. grass must be unaffected -------------------------------------
    hline("7 -- grass (PFT 12) new vs baseline over the baseline's %d days"
          % nbase)
    for name in ("FATES_LEAFC_PF", "FATES_GPP_PF", "FATES_NPLANT_PF",
                 "FATES_CROWNAREA_PF"):
        compare_field(name, PFT_GRASS, new, base, nbase, dates, unit[name])

    # ---- 8. carbon balance ------------------------------------------------
    hline("8 -- FATES_CBALANCE_ERROR (site level)")
    for tag, dat in (("new", new), ("baseline", base)):
        row = dat[("FATES_CBALANCE_ERROR", None)]
        print("[%s] %s" % (tag, fmt_stats("", row,
                                          unit["FATES_CBALANCE_ERROR"])))
        print("      max |value| %13.6g on day %d"
              % (np.nanmax(np.abs(row)), int(np.nanargmax(np.abs(row))) + 1))
    if args.lndlog:
        check_balance_log(args.lndlog)

    # ---- 9. mortality -----------------------------------------------------
    hline("9 -- moss FATES_MORTALITY_CSTARV_PF and FATES_MORTALITY_PF")
    for name in ("FATES_MORTALITY_CSTARV_PF", "FATES_MORTALITY_PF",
                 "FATES_MORTALITY_TERMINATION_PF"):
        for tag, dd, dat in (("new", dates, new), ("baseline", bdates, base)):
            row = dat[(name, PFT_MOSS)]
            imax = int(np.nanargmax(row))
            print("%-34s [%-8s] %s" % (name, tag,
                                       fmt_stats("", row, unit[name])))
            print("%-34s %-10s peak on day %d (%s); days > 0: %d"
                  % ("", "", imax + 1, dd[imax], int(np.sum(row > 0.0))))


def compare_field(name, pft, new, base, nbase, dates, unit):
    """Print new-vs-baseline differences for one field and PFT."""
    a = new[(name, pft)][:nbase]
    b = base[(name, pft)][:nbase]
    diff = a - b
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        scale = np.nanmax(np.abs(b))
        pre = slice(0, BASELINE_CULL_DAY - 1)   # days 1 .. cull-1
        post = slice(BASELINE_CULL_DAY - 1, nbase)
        maxpre = np.nanmax(np.abs(diff[pre]))
        maxpost = np.nanmax(np.abs(diff[post]))
        ipre = int(np.nanargmax(np.abs(diff[pre])))
    print("%-22s PFT %2d  [%s]" % (name, pft, unit))
    print("    baseline max |value| %13.6g" % scale)
    print("    max |new-baseline| days 1-%d  %13.6g  (day %d, %s)%s"
          % (BASELINE_CULL_DAY - 1, maxpre, ipre + 1, dates[ipre],
             "" if scale == 0 else "  = %.3e of baseline max"
             % (maxpre / scale)))
    print("    max |new-baseline| days %d-%d %13.6g"
          % (BASELINE_CULL_DAY, nbase, maxpost))
    print("    days differing at all, 1-%d: %d of %d"
          % (BASELINE_CULL_DAY - 1,
             int(np.sum(diff[pre] != 0.0)), BASELINE_CULL_DAY - 1))


def check_balance_log(path):
    """Look for a CTSM balance-check endrun in the land log."""
    if not os.path.exists(path):
        print("lnd log %s not found; balance-check scan skipped" % path)
        return
    opener = open
    mode = "r"
    if path.endswith(".gz"):
        import gzip
        opener = gzip.open
        mode = "rt"
    # Deliberately narrow: the land log also lists history field names such
    # as FATES_CBALANCE_ERROR, and a needle like "ERROR" would match those
    # on every run and drown a real abort.
    needles = ("BalanceCheck", "WATER BALANCE ERROR", "ENERGY BALANCE ERROR",
               "balance error", "ERROR in water balance",
               "ENDRUN", "ERROR: Rank")
    hits = []
    with opener(path, mode, errors="replace") as handle:
        for lineno, line in enumerate(handle, 1):
            if any(needle in line for needle in needles):
                hits.append((lineno, line.rstrip()))
    if hits:
        print("Land log lines matching balance/endrun patterns:")
        for lineno, line in hits[:40]:
            print("    %6d  %s" % (lineno, line))
        if len(hits) > 40:
            print("    ... %d more" % (len(hits) - 40))
    else:
        print("No balance-check or endrun text in %s" % os.path.basename(path))


if __name__ == "__main__":
    main()
