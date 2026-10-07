#!/usr/bin/env python3
"""Check a run after the moss CO2 film and fuel moisture moved to the total-water proxy.

Before the switch, every moss consumer read FATES_MOSS_FWET_LIQ (liquid soil water). After
it, the CO2 water film in the moss Ci solve and both moss fuel classes' moisture read
FATES_MOSS_FWET_TOT (liquid plus ice). Capacity and respiration stay on the liquid proxy.
The two proxies differ only when the top soil layer holds ice, so the switch can act only
on those days. This script compares a run made after the switch (NEW_RUNDIR) with one made
just before it (OLD_RUNDIR), on the same forcing.

  1. The 12-hourly h1 tape (INFO only). Each day should have two records, and every moss
     wetness field should hold the same value in both. This shows that the tape is
     written as intended, and it is the "before" picture for the change that will refresh
     the proxies sub-daily. It cannot show that the proxies are refreshed only once a day:
     these fields are in FATES's daily history group, so the tape holds one value per day
     whatever the patch variables do in between. Unequal halves are still a FAIL.

  2. Moss GPP (FATES_GPP_PF at the moss PFT, daily h0a tape). The tape's GPP for day d
     is the GPP accumulated over day d-1 (gpp_acc_hold), so it was produced under the
     proxies recorded for day d-1. Every comparison below pairs GPP on day d with the
     proxies on day d-1. The switch reaches GPP only through the film, and the film reads
     a different value only when total exceeds liquid. So, as long as the runs' liquid
     proxies still agree, the first day moss GPP differs must follow a total > liquid day.
     That timing is the only thing judged here.
     The direction is reported, not judged. A thicker film usually lowers GPP, but in a
     timestep where moss is net-respiring (gross below leaf respiration) it raises ci and
     so raises gross GPP. The film factor also has floors (co2_film_dryfrac_min,
     moss_co2_film_min), so a total > liquid day need not change GPP at all. Identical GPP
     is therefore not a failure, and this check cannot tell a film switch that never
     happened from one that never mattered. The timing claim also assumes no fire outcome
     differed before the first GPP difference: moss fuel moisture changes on the same icy
     days, and a different fire can change moss state without moving the liquid proxy.
     A timing FAIL should be read against the fire fields first. Days from the first one
     where the runs' liquid proxies differ are reported, not judged, because by then soil
     water has diverged for reasons the switch only started.

  3. Moss fuel moisture (FATES_FUEL_MOISTURE_FC, fuel classes 7 and 8, daily h0a tape).
     This is computed the same day as the proxies, and it is a rising linear map of the
     proxy it reads, floored at zero. On days where the runs' liquid proxies agree:
       - it must be higher in the new run where the new run's total exceeds its liquid;
       - it must be unchanged where total equals liquid.
     Days where either run's value is zero (no moss fuel, or the floor) are left out.
     Runs without fire (FATES-SP) carry no fuel moisture, and the check is skipped.

FWET values on the tape are patch-area weighted site means, and each patch's proxy is
max(soil ingredient, its own canopy wetted fraction). So site total == liquid means every
patch is equal, but site total > liquid means only that some patch is wetter. Check 3's
"must be higher" rests on that wetter patch carrying moss fuel; if its loading is at or
below nearzero its moisture reads 0 and the day can FAIL although the code is right. With
one soil column and a canopy term that rarely sets the proxy on icy days, that is unlikely.

Dates printed are the day each record averages over (from time_bounds), not the file
name's stamp, which is the end of that day.

Usage (ctsm_pylib env; needs netCDF4 and numpy):
    check_total_proxy_switch.py NEW_RUNDIR OLD_RUNDIR [--pft-moss N]

Both arguments are CIME case run/ directories holding daily *.clm2.h0a.*.nc files. NEW_RUNDIR
must also hold the 12-hourly *.clm2.h1a.*.nc files. The moss PFT is the one non-vascular
PFT on the FATES parameter file named in NEW_RUNDIR/lnd_in; --pft-moss (1-based) overrides
that.

Exit code, from checks 2 and 3 only: 1 if any FAILed, else 0 if any PASSed, else 2 (nothing
could be judged). A FAIL in check 1 also gives 1. 3 means the input could not be
interpreted (e.g. non-consecutive days, unexpected dimensions), so nothing was judged.
"""

import argparse
import json
import os
import re
import sys
from glob import glob

import netCDF4 as nc
import numpy as np

H0_GLOB = "*.clm2.h0a.*.nc"
H1_GLOB = "*.clm2.h1a.*.nc"

LIQ = "FATES_MOSS_FWET_LIQ"
TOT = "FATES_MOSS_FWET_TOT"
GPP = "FATES_GPP_PF"
FUEL_MOISTURE = "FATES_FUEL_MOISTURE_FC"

H1_WETNESS_FIELDS = [
    "FATES_MOSS_FWET_LIQ",
    "FATES_MOSS_FWET_TOT",
    "FATES_MOSS_FWET_SOIL_LIQ",
    "FATES_MOSS_FWET_SOIL_TOT",
    "FATES_MOSS_FWET_CANOPY",
    "FATES_MOSS_WETNESS_SCALER",
]

# 1-based, in the order FatesFuelClassesMod.F90 defines them (as in verify_moss_history.py).
MOSS_FUEL_CLASSES = {"live_moss": 7, "dead_moss": 8}

# How many example days to print under a FAIL or an INFO list.
N_EXAMPLES = 5


class Report:
    def __init__(self):
        self.counts = {"PASS": 0, "FAIL": 0, "SKIP": 0, "INFO": 0}
        self.judged_fail_h1 = False

    def line(self, status, text):
        self.counts[status] += 1
        print(f"  {status:4s}  {text}")

    @staticmethod
    def detail(text):
        print(f"        {text}")


def abort(message):
    """Stop on input the script cannot interpret (exit 3, distinct from a failed check)."""
    print(message, file=sys.stderr)
    sys.exit(3)


def stamp_of(path):
    """The YYYY-MM-DD-SSSSS part of a CLM history file name."""
    return os.path.basename(path).rsplit(".", 2)[-2]


def fates_paramfile(rundir):
    path = os.path.join(rundir, "lnd_in")
    if not os.path.exists(path):
        return None
    pattern = re.compile(r"^\s*fates_paramfile\s*=\s*'([^']+)'")
    with open(path) as handle:
        for line in handle:
            match = pattern.match(line)
            if match:
                return match.group(1)
    return None


def moss_pft_from_params(rundir):
    """1-based index of the single non-vascular PFT, or None with the reason."""
    paramfile = fates_paramfile(rundir)
    if paramfile is None or not os.path.exists(paramfile):
        return None, f"no readable fates_paramfile in {rundir}/lnd_in"
    if paramfile.endswith(".json"):
        with open(paramfile) as handle:
            vascular = json.load(handle)["parameters"]["fates_vascular"]["data"]
    else:
        with nc.Dataset(paramfile) as ds:
            vascular = ds["fates_vascular"][:]
    nonvascular = [i + 1 for i, v in enumerate(np.ravel(vascular)) if int(v) == 0]
    if len(nonvascular) != 1:
        return None, f"{paramfile} has non-vascular PFTs {nonvascular}, not exactly one"
    return nonvascular[0], f"the one non-vascular PFT on {paramfile}"


def as_float(var, path):
    """A variable's values as a float array, masked/fill values as NaN."""
    return np.ma.filled(np.ma.asarray(var[:], dtype=float), np.nan)


def period_labels(ds):
    """YYYY-MM-DD of the start of each record's averaging period."""
    tb = ds["time_bounds"]
    calendar = getattr(ds["time"], "calendar", "standard")
    starts = nc.num2date(np.asarray(tb[:, 0]), ds["time"].units, calendar=calendar)
    return [s.strftime("%Y-%m-%d") for s in starts]


def one_value(values, var, path, axis_name=None, index=None):
    """Pull a single value (or one per index) out of a one-record, one-gridcell array."""
    if axis_name is not None:
        values = np.take(values, index, axis=var.dimensions.index(axis_name))
    if values.size != 1:
        abort(f"{var.name} on {path} has {values.size} values where one was expected "
                 f"(dims {var.dimensions}); this script expects one record and one "
                 "gridcell per daily file.")
    return values.item()


def read_daily(rundir, stamps, fields, moss_pft0):
    """({field: array over days}, [day labels], period starts) from the daily h0a files.

    Per-PFT fields give the moss column. FATES_FUEL_MOISTURE_FC gives (nday, 2): the live-
    and dead-moss classes. A field absent from every file is absent from the dict; one
    absent from some files is NaN on those days.
    """
    paths = {stamp_of(p): p for p in glob(os.path.join(rundir, H0_GLOB))}
    out = {}
    labels = []
    starts = np.full(len(stamps), np.nan)
    for iday, stamp in enumerate(stamps):
        path = paths[stamp]
        with nc.Dataset(path) as ds:
            day = period_labels(ds)
            if len(day) != 1:
                abort(f"{path} has {len(day)} records; expected one per daily file.")
            labels.append(day[0])
            starts[iday] = float(ds["time_bounds"][0, 0])
            for field in fields:
                if field not in ds.variables:
                    continue
                var = ds[field]
                values = as_float(var, path)
                if "fates_levpft" in var.dimensions:
                    npft = ds.dimensions["fates_levpft"].size
                    if not 0 <= moss_pft0 < npft:
                        abort(f"moss PFT {moss_pft0 + 1} is outside fates_levpft (1-{npft}).")
                    value = one_value(values, var, path, "fates_levpft", moss_pft0)
                elif "fates_levfuel" in var.dimensions:
                    nfuel = ds.dimensions["fates_levfuel"].size
                    if max(MOSS_FUEL_CLASSES.values()) > nfuel:
                        continue
                    value = [one_value(values, var, path, "fates_levfuel", c - 1)
                             for c in MOSS_FUEL_CLASSES.values()]
                else:
                    value = one_value(values, var, path)
                if field not in out:
                    out[field] = np.full((len(stamps),) + np.shape(value), np.nan)
                out[field][iday] = value
    return out, labels, starts


def describe_days(labels, idx):
    idx = list(idx)
    shown = ", ".join(labels[i] for i in idx[:N_EXAMPLES])
    more = f" (and {len(idx) - N_EXAMPLES} more)" if len(idx) > N_EXAMPLES else ""
    return shown + more


def check_h1(report, rundir):
    print("\n1. Is the 12-hourly h1 tape written as intended? (INFO: these fields are in the "
          "daily history group,\n   so equal halves are expected and do not test the proxies' "
          "refresh frequency)")
    paths = sorted(glob(os.path.join(rundir, H1_GLOB)))
    if not paths:
        report.line("SKIP", f"no {H1_GLOB} files in {rundir}")
        return
    records = {f: [] for f in H1_WETNESS_FIELDS}
    starts, labels = [], []
    for path in paths:
        with nc.Dataset(path) as ds:
            missing = [f for f in H1_WETNESS_FIELDS if f not in ds.variables]
            if missing:
                report.line("FAIL", f"{os.path.basename(path)} lacks {missing}")
                report.judged_fail_h1 = True
                return
            starts.append(np.asarray(ds["time_bounds"][:, 0], dtype=float))
            labels.extend(period_labels(ds))
            for field in H1_WETNESS_FIELDS:
                values = as_float(ds[field], path)
                if values.shape[0] * ds.dimensions["lndgrid"].size != values.size:
                    abort(f"{field} on {path} has dims {ds[field].dimensions}; expected "
                             "(time, lndgrid) with one gridcell.")
                records[field].append(np.ravel(values))
    start = np.concatenate(starts)
    order = np.argsort(start, kind="stable")
    start = start[order]
    labels = [labels[i] for i in order]
    day = np.floor(start + 1e-9).astype(int)
    days, first_rec, per_day = np.unique(day, return_index=True, return_counts=True)
    bad = np.flatnonzero(per_day != 2)
    if bad.size:
        report.line("FAIL", f"{bad.size} of {days.size} days do not have exactly two 12-hour "
                    f"records (first: {labels[first_rec[bad[0]]]})")
        report.judged_fail_h1 = True
        return
    day_labels = [labels[i] for i in first_rec]
    report.line("INFO", f"{days.size} days ({day_labels[0]} to {day_labels[-1]}), two "
                f"12-hour records each, over {len(paths)} file(s)")
    for field in H1_WETNESS_FIELDS:
        values = np.concatenate(records[field])[order]
        first, second = values[0::2], values[1::2]
        nan_days = np.flatnonzero(np.isnan(first) | np.isnan(second))
        differ = np.flatnonzero(~((first == second) | (np.isnan(first) & np.isnan(second))))
        changes = int(np.count_nonzero(second[1:] != second[:-1]))
        if differ.size:
            report.line("FAIL", f"{field}: the two halves differ on {differ.size} of "
                        f"{days.size} days, by up to {np.nanmax(np.abs(first - second)):.3g}")
            report.detail(f"first such days: {describe_days(day_labels, differ)}")
            report.judged_fail_h1 = True
        else:
            report.line("INFO", f"{field}: halves equal on every day; the value changed "
                        f"from the day before on {changes} days")
        if nan_days.size:
            report.detail(f"{field} is missing/NaN in {nan_days.size} days: "
                          f"{describe_days(day_labels, nan_days)}")


def first_liq_divergence(new, old):
    """Index of the first day the two runs' liquid proxies differ (len if never)."""
    differ = np.flatnonzero(new[LIQ] != old[LIQ])
    return differ[0] if differ.size else len(new[LIQ])


def check_gpp(report, labels, new, old):
    print("\n2. Does moss GPP first change only after a day where total water exceeds liquid? "
          "(daily h0a tape;\n   GPP on day d was produced under the proxies of day d-1)")
    if GPP not in new or GPP not in old:
        report.line("SKIP", f"{GPP} missing from one of the runs")
        return
    gpp_new, gpp_old = new[GPP], old[GPP]
    nday = len(labels)
    # Proxies in force while each tape day's GPP was accumulated: the previous record's.
    wetter_prev = np.zeros(nday, dtype=bool)
    wetter_prev[1:] = new[TOT][:-1] > new[LIQ][:-1]
    nan_days = np.flatnonzero(np.isnan(gpp_new) | np.isnan(gpp_old))
    valid = ~(np.isnan(gpp_new) | np.isnan(gpp_old))
    if nan_days.size:
        report.line("INFO", f"moss GPP is NaN in one run on {nan_days.size} days, left out: "
                    f"{describe_days(labels, nan_days)}")
    differ = np.flatnonzero(valid & (gpp_new != gpp_old))
    active = valid & wetter_prev & ((gpp_new > 0) | (gpp_old > 0))
    report.line("INFO", f"{np.count_nonzero(wetter_prev)} of {nday} tape days follow a day with "
                f"total > liquid (new run); on {np.count_nonzero(active)} of those moss had GPP")
    if differ.size == 0:
        report.line("INFO", "moss GPP is identical on every day. Possible if moss was buried "
                    "or the film factor sat at its floors whenever layer 1 held ice; also what "
                    "a film switch that never happened would look like. Nothing judged")
        return

    split = first_liq_divergence(new, old)
    first = differ[0]
    # GPP on day d depends on day d-1's state, so day `split` already carries a day of
    # diverged soil water: the runs are judged comparable only on days before it.
    if first < split:
        if wetter_prev[first]:
            report.line("PASS", f"moss GPP first differs on {labels[first]}, after a day "
                        "with total > liquid")
        else:
            why = (f"total == liquid the day before ({new[TOT][first - 1]:.4g})"
                   if first > 0 else "it is the first day on the tape")
            report.line("FAIL", f"moss GPP first differs on {labels[first]}, but {why}")
    else:
        report.line("INFO", f"moss GPP first differs on {labels[first]}, on or after "
                    f"{labels[split] if split < nday else '-'}, when the runs' liquid proxies "
                    "first differ; timing not judged")

    # Direction is reported, not judged: with net assimilation below zero (gross < leaf
    # respiration), a thicker film raises ci and so raises gross GPP.
    before = np.arange(split)
    after_wet = before[valid[before] & wetter_prev[before]]
    lower = np.count_nonzero(gpp_new[after_wet] < gpp_old[after_wet])
    higher = after_wet[gpp_new[after_wet] > gpp_old[after_wet]]
    if after_wet.size:
        report.line("INFO", f"before the liquid proxies differ, on {after_wet.size} days after "
                    f"a total > liquid day moss GPP is lower on {lower}, higher on "
                    f"{higher.size}, equal on {after_wet.size - lower - higher.size} (higher is "
                    "possible where moss is net-respiring)")
        if higher.size:
            report.detail(f"higher on: {describe_days(labels, higher)}")
    off = before[valid[before] & ~wetter_prev[before] & (gpp_new[before] != gpp_old[before])]
    if off.size:
        report.line("INFO", f"before the liquid proxies differ, moss GPP also differs on "
                    f"{off.size} days that do not follow a total > liquid day (carry-over of "
                    f"carbon state): {describe_days(labels, off)}")
    if split < nday:
        report.line("INFO", f"the runs' liquid proxies first differ on {labels[split]}")
    all_higher = np.count_nonzero(valid & (gpp_new > gpp_old))
    all_lower = np.count_nonzero(valid & (gpp_new < gpp_old))
    report.line("INFO", f"over the whole run moss GPP differs on {differ.size} days: lower on "
                f"{all_lower}, higher on {all_higher}")


def check_fuel_moisture(report, labels, new, old):
    print("\n3. Did moss fuel moisture rise where total water exceeds liquid? (daily h0a tape)")
    if FUEL_MOISTURE not in new or FUEL_MOISTURE not in old:
        report.line("SKIP", f"{FUEL_MOISTURE} (classes 7-8) missing from one of the runs "
                    "(no fire model, e.g. FATES-SP)")
        return
    wetter = new[TOT] > new[LIQ]
    same_liq = new[LIQ] == old[LIQ]
    equal_proxies = new[TOT] == new[LIQ]
    for icls, (name, cls) in enumerate(MOSS_FUEL_CLASSES.items()):
        fm_new, fm_old = new[FUEL_MOISTURE][:, icls], old[FUEL_MOISTURE][:, icls]
        usable = ~(np.isnan(fm_new) | np.isnan(fm_old)) & (fm_new > 0) & (fm_old > 0)
        if not usable.any():
            report.line("SKIP", f"{name} (class {cls}): no day with nonzero fuel moisture in "
                        "both runs")
            continue
        judged = np.flatnonzero(usable & wetter & same_liq)
        if judged.size == 0:
            report.line("SKIP", f"{name} (class {cls}): no usable day with total > liquid on "
                        "which the runs' liquid proxies agree")
        else:
            not_higher = judged[~(fm_new[judged] > fm_old[judged])]
            if not_higher.size:
                report.line("FAIL", f"{name} (class {cls}): not higher on {not_higher.size} of "
                            f"{judged.size} days with total > liquid and the liquid proxy "
                            "unchanged")
                report.detail(f"those days: {describe_days(labels, not_higher)}")
            else:
                report.line("PASS", f"{name} (class {cls}): higher in the new run on all "
                            f"{judged.size} days with total > liquid and the liquid proxy "
                            "unchanged")
        dry = np.flatnonzero(usable & equal_proxies & same_liq)
        changed = dry[fm_new[dry] != fm_old[dry]]
        if dry.size == 0:
            report.line("SKIP", f"{name} (class {cls}): no usable day with total == liquid "
                        "and the liquid proxy unchanged")
        elif changed.size:
            report.line("FAIL", f"{name} (class {cls}): changed on {changed.size} of "
                        f"{dry.size} days with total == liquid and the liquid proxy unchanged")
            report.detail(f"those days: {describe_days(labels, changed)}")
        else:
            report.line("PASS", f"{name} (class {cls}): unchanged on all {dry.size} days "
                        "with total == liquid and the liquid proxy unchanged")
        left_out = np.count_nonzero(~usable)
        unjudged = np.count_nonzero(usable & ~same_liq)
        report.line("INFO", f"{name} (class {cls}): not judged: {left_out} days with zero or "
                    f"missing fuel moisture in a run, {unjudged} days where the runs' liquid "
                    "proxies differ")


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("new_rundir", help="run/ directory after the switch")
    parser.add_argument("old_rundir", help="run/ directory before the switch")
    parser.add_argument("--pft-moss", type=int, help="1-based moss PFT index")
    args = parser.parse_args()
    for rundir in (args.new_rundir, args.old_rundir):
        if not os.path.isdir(rundir):
            abort(f"No such directory: {rundir}")

    if args.pft_moss is not None:
        if args.pft_moss < 1:
            abort("--pft-moss is 1-based and must be at least 1.")
        moss_pft, why = args.pft_moss, "from --pft-moss"
    else:
        moss_pft, why = moss_pft_from_params(args.new_rundir)
        if moss_pft is None:
            abort(f"Cannot identify the moss PFT: {why}. Pass --pft-moss.")
    print(f"Moss PFT: {moss_pft} ({why})")

    report = Report()
    check_h1(report, args.new_rundir)
    h1_counts = dict(report.counts)

    stamps_new = {stamp_of(p) for p in glob(os.path.join(args.new_rundir, H0_GLOB))}
    stamps_old = {stamp_of(p) for p in glob(os.path.join(args.old_rundir, H0_GLOB))}
    stamps = sorted(stamps_new & stamps_old)
    print(f"\nDaily h0a files: {len(stamps_new)} new, {len(stamps_old)} old, {len(stamps)} shared")
    if stamps:
        fields = [LIQ, TOT, GPP, FUEL_MOISTURE]
        new, labels, starts = read_daily(args.new_rundir, stamps, fields, moss_pft - 1)
        old, _, _ = read_daily(args.old_rundir, stamps, fields, moss_pft - 1)
        print(f"  covering {labels[0]} to {labels[-1]}")
        # Check 2 pairs each record with the one before it as "the previous day".
        gaps = np.flatnonzero(np.abs(np.diff(starts) - 1.0) > 1e-6)
        if gaps.size:
            abort(f"The daily h0a files shared by the two runs are not one per consecutive "
                     f"day (first break after {labels[gaps[0]]}); check 2 pairs each record "
                     "with the one before it as the previous day.")
        missing = [f for f in (LIQ, TOT) if f not in new or f not in old]
        if missing:
            report.line("SKIP", f"{missing} missing from one of the runs; checks 2 and 3 need "
                        "both proxies")
        else:
            check_gpp(report, labels, new, old)
            check_fuel_moisture(report, labels, new, old)
    else:
        report.line("SKIP", "no daily h0a files shared by the two runs; checks 2 and 3 not made")

    counts = report.counts
    print(f"\n{counts['PASS']} PASS, {counts['FAIL']} FAIL, {counts['SKIP']} SKIP, "
          f"{counts['INFO']} INFO")
    judged_pass = counts["PASS"] - h1_counts["PASS"]
    judged_fail = counts["FAIL"] - h1_counts["FAIL"]
    if judged_fail or report.judged_fail_h1:
        return 1
    if judged_pass == 0:
        print("Nothing in checks 2 and 3 could be judged (exit 2).")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
