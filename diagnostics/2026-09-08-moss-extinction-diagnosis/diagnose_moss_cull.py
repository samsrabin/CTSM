#!/usr/bin/env python3
"""Diagnose the moss-cohort cull in an instrumented ALP2 nocomp FATES run.

Reads the daily ``*.clm2.h0a.*.nc`` tape written by a CTSM/FATES case and
answers four questions about the fifteenth (moss) PFT:

1. Which of the moss-extinction diagnostic history fields actually reached
   the tape, with their shapes and units.
2. On which simulation day the moss cohort is culled, detected as
   ``FATES_NCOHORTS`` dropping and ``FATES_LEAFC_PF`` for the moss PFT
   reaching exactly zero.
3. A daily table around the cull for moss and for arctic C3 grass.
4. Whole-run min/mean/max and count-of-positive-days for the seed,
   recruitment and carbon-pool fields.

It also reports the termination-vs-continuous C-starvation discriminator:
``FATES_MORTALITY_CSTARV_CFLUX_PF`` minus
``FATES_MORT_CSTARV_CONT_CFLUX_PF``.

Simulation day numbering follows the tape: day 1 is the first history file
written, whose filename date is one day after ``RUN_STARTDATE``.

NOTE ON NORMALIZATION: every ``FATES_*_PF`` field is per m2 of LAND area,
not per m2 of the PFT's own patch. In this configuration the prescribed
nocomp patch areas are moss 0.5, grass 0.3, bareground 0.2, so a
moss-patch-relative value is the printed value divided by 0.5.
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

# The sixteen fields added by the moss-extinction instrumentation.
NEW_FIELDS = [
    "FATES_NPLANT_PF",
    "FATES_STOREC_PF",
    "FATES_VEGC_PF",
    "FATES_NPP_PF",
    "FATES_MORTALITY_CSTARV_CFLUX_PF",
    "FATES_MORT_CSTARV_CONT_CFLUX_PF",
    "FATES_MORTALITY_CSTARV_PF",
    "FATES_MORTALITY_PF",
    "FATES_MORTALITY_CFLUX_PF",
    "FATES_SEED_BANK_PF",
    "FATES_SEEDS_IN_PF",
    "FATES_SEEDLING_POOL_PF",
    "FATES_UNGERM_SEED_BANK_PF",
    "FATES_RECRUITMENT_PF",
    "FATES_RECRUITMENT_CFLUX_PF",
    "FATES_ELONG_FACTOR_PF",
]

# Per-PFT fields printed in the daily table around the cull.
TABLE_PF_FIELDS = [
    "FATES_NPLANT_PF",
    "FATES_LEAFC_PF",
    "FATES_STOREC_PF",
    "FATES_VEGC_PF",
    "FATES_NPP_PF",
    "FATES_GPP_PF",
    "FATES_MORTALITY_CSTARV_CFLUX_PF",
    "FATES_MORT_CSTARV_CONT_CFLUX_PF",
    "FATES_MORTALITY_CSTARV_PF",
    "FATES_MORTALITY_TERMINATION_PF",
    "FATES_MORTALITY_PF",
    "FATES_MORTALITY_CFLUX_PF",
    "FATES_ELONG_FACTOR_PF",
    "FATES_CROWNAREA_PF",
    "FATES_NOCOMP_PATCHAREA_PF",
]

# Site-level fields printed alongside the daily table.
TABLE_SITE_FIELDS = ["FATES_NCOHORTS", "FATES_CBALANCE_ERROR"]

# Fields summarized over the whole run.
SUMMARY_FIELDS = [
    "FATES_SEED_BANK_PF",
    "FATES_SEEDS_IN_PF",
    "FATES_SEEDLING_POOL_PF",
    "FATES_UNGERM_SEED_BANK_PF",
    "FATES_RECRUITMENT_PF",
    "FATES_RECRUITMENT_CFLUX_PF",
    "FATES_NPP_PF",
    "FATES_STOREC_PF",
    "FATES_NPLANT_PF",
]

DATE_RE = re.compile(r"\.clm2\.h0a\.(\d{4}-\d{2}-\d{2})-(\d{5})\.nc$")


def find_files(rundir):
    """Return the daily h0a files sorted by their filename date."""
    files = sorted(glob.glob(os.path.join(rundir, "*.clm2.h0a.*.nc")))
    out = []
    for path in files:
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
    arr = np.asarray(dataset.variables[name][:], dtype=float)
    arr = np.ma.filled(arr, np.nan)
    if pft is None:
        return float(arr.reshape(-1)[0])
    # (time, fates_levpft, lndgrid)
    return float(arr[0, pft - 1, 0])


def report_presence(path):
    """Item 1: which new fields are on the tape, with shape and units."""
    print("=" * 78)
    print("ITEM 1 -- presence, shape and units of the sixteen new fields")
    print("(read from %s)" % os.path.basename(path))
    print("=" * 78)
    dataset = nc.Dataset(path)
    missing = []
    print("%-34s %-8s %-26s %s" % ("field", "present", "dims/shape", "units"))
    for name in NEW_FIELDS:
        if name in dataset.variables:
            var = dataset.variables[name]
            dims = "%s %s" % (",".join(var.dimensions), tuple(var.shape))
            print(
                "%-34s %-8s %-26s %s"
                % (name, "yes", dims, getattr(var, "units", "(none)"))
            )
        else:
            missing.append(name)
            print("%-34s %-8s %-26s %s" % (name, "NO", "-", "-"))
    dataset.close()
    if missing:
        print("\nFINDING: absent from the tape: %s" % ", ".join(missing))
    else:
        print("\nAll sixteen fields present.")
    return missing


def load_series(files, fields_pf, fields_site, pfts):
    """Read a time series of the requested fields for the requested PFTs."""
    ndays = len(files)
    data = {}
    for name in fields_pf:
        for pft in pfts:
            data[(name, pft)] = np.full(ndays, np.nan)
    for name in fields_site:
        data[(name, None)] = np.full(ndays, np.nan)
    for idx, (_, path) in enumerate(files):
        dataset = nc.Dataset(path)
        for name in fields_pf:
            for pft in pfts:
                data[(name, pft)][idx] = scalar(dataset, name, pft)
        for name in fields_site:
            data[(name, None)][idx] = scalar(dataset, name)
        dataset.close()
    return data


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "rundir", help="directory holding the daily *.clm2.h0a.*.nc files"
    )
    parser.add_argument(
        "--table-start",
        type=int,
        default=395,
        help="first simulation day of the daily table (default 395)",
    )
    parser.add_argument(
        "--table-end",
        type=int,
        default=410,
        help="last simulation day of the daily table (default 410)",
    )
    args = parser.parse_args()

    files = find_files(args.rundir)
    dates = [d for d, _ in files]
    print("Found %d daily h0a files: %s .. %s" % (len(files), dates[0], dates[-1]))
    print(
        "Simulation day N == the Nth file; day 1 = %s.\n"
        "All FATES_*_PF values below are per m2 LAND area (moss patch area "
        "0.5, grass 0.3, bareground 0.2).\n" % dates[0]
    )

    report_presence(files[-1][1])

    pfts = [PFT_MOSS, PFT_GRASS]
    wanted_pf = sorted(set(TABLE_PF_FIELDS) | set(SUMMARY_FIELDS))
    data = load_series(files, wanted_pf, TABLE_SITE_FIELDS, pfts)

    # ---- Item 2: the cull day -------------------------------------------
    print()
    print("=" * 78)
    print("ITEM 2 -- when is the moss cohort culled?")
    print("=" * 78)
    ncoh = data[("FATES_NCOHORTS", None)]
    moss_leafc = data[("FATES_LEAFC_PF", PFT_MOSS)]
    zero_days = [i for i in range(len(files)) if moss_leafc[i] == 0.0]
    first_zero = zero_days[0] if zero_days else None
    drops = [
        i
        for i in range(1, len(files))
        if np.isfinite(ncoh[i]) and np.isfinite(ncoh[i - 1]) and ncoh[i] < ncoh[i - 1]
    ]
    print("FATES_NCOHORTS decreases on:")
    for i in drops:
        print(
            "    day %d (%s): %g -> %g"
            % (i + 1, dates[i], ncoh[i - 1], ncoh[i])
        )
    if not drops:
        print("    (never)")
    if first_zero is None:
        print("moss FATES_LEAFC_PF never reaches exactly zero")
    else:
        print(
            "moss FATES_LEAFC_PF first exactly zero on day %d (%s); "
            "previous day value %.6e kg m-2"
            % (
                first_zero + 1,
                dates[first_zero],
                moss_leafc[first_zero - 1] if first_zero > 0 else np.nan,
            )
        )
        peak = np.nanmax(moss_leafc)
        prev = moss_leafc[first_zero - 1] if first_zero > 0 else np.nan
        if peak > 0:
            print(
                "    peak moss LEAFC over the run %.6e kg m-2; last nonzero "
                "value is %.1f%% of peak" % (peak, 100.0 * prev / peak)
            )
        print("    (expected day 402 = 2001-02-07; delta = %d days)"
              % (first_zero + 1 - 402))

    # ---- Item 3: daily table --------------------------------------------
    print()
    print("=" * 78)
    print(
        "ITEM 3 -- daily values, simulation days %d-%d"
        % (args.table_start, args.table_end)
    )
    print("=" * 78)
    lo = max(1, args.table_start)
    hi = min(len(files), args.table_end)
    idxs = list(range(lo - 1, hi))
    hdr = "%-34s %-6s" % ("field", "PFT") + "".join(
        "%14d" % (i + 1) for i in idxs
    )
    print("day ->" + " " * 35 + "".join("%14s" % dates[i][5:] for i in idxs))
    print(hdr)
    print("-" * len(hdr))
    for name in TABLE_SITE_FIELDS:
        row = data[(name, None)]
        print(
            "%-34s %-6s" % (name, "site")
            + "".join("%14.6g" % row[i] for i in idxs)
        )
    for name in TABLE_PF_FIELDS:
        for pft, label in ((PFT_MOSS, "15 mos"), (PFT_GRASS, "12 grs")):
            row = data[(name, pft)]
            print(
                "%-34s %-6s" % (name, label)
                + "".join("%14.6g" % row[i] for i in idxs)
            )

    # ---- Item 4: whole-run summary --------------------------------------
    print()
    print("=" * 78)
    print("ITEM 4 -- whole-run min / mean / max / count of positive days")
    print("=" * 78)
    print(
        "%-34s %-6s %14s %14s %14s %8s"
        % ("field", "PFT", "min", "mean", "max", "npos")
    )
    with warnings.catch_warnings():
        # An absent field is all-NaN; report it as NaN rather than warning.
        warnings.simplefilter("ignore", RuntimeWarning)
        for name in SUMMARY_FIELDS:
            for pft, label in ((PFT_MOSS, "15 mos"), (PFT_GRASS, "12 grs")):
                row = data[(name, pft)]
                npos = int(np.sum(row > 0.0))
                print(
                    "%-34s %-6s %14.6g %14.6g %14.6g %8d"
                    % (name, label, np.nanmin(row), np.nanmean(row),
                       np.nanmax(row), npos)
                )

    # ---- Item 5: the discriminator --------------------------------------
    print()
    print("=" * 78)
    print("ITEM 5 -- C-starvation discriminator for moss (PFT 15)")
    print("CSTARV_CFLUX minus MORT_CSTARV_CONT_CFLUX; a nonzero difference")
    print("means C-starvation removed carbon by termination, not only by the")
    print("continuous route.")
    print("=" * 78)
    tot = data[("FATES_MORTALITY_CSTARV_CFLUX_PF", PFT_MOSS)]
    cont = data[("FATES_MORT_CSTARV_CONT_CFLUX_PF", PFT_MOSS)]
    if first_zero is None:
        centre = int(np.nanargmax(np.abs(tot - cont))) if len(tot) else 0
        print("no cull detected; centring on the largest |difference|")
    else:
        centre = first_zero
    print(
        "%-6s %-12s %18s %18s %18s"
        % ("day", "date", "CSTARV_CFLUX", "CONT_CFLUX", "difference")
    )
    for i in range(max(0, centre - 2), min(len(files), centre + 3)):
        tag = "  <-- cull day" if i == centre else ""
        print(
            "%-6d %-12s %18.9e %18.9e %18.9e%s"
            % (i + 1, dates[i], tot[i], cont[i], tot[i] - cont[i], tag)
        )
    print("\nUnits of both: %s (per m2 LAND area)." % "see item 1")


if __name__ == "__main__":
    main()
