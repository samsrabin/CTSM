#!/usr/bin/env python3
"""Checks 2b, 3 and 4 on the 2-year ALP2 nocomp moss test, after Task C.

Task C moved two moss consumers, the CO2 water film in photosynthesis and both
moss fuel classes' moisture, from the liquid-water wetness proxy
(FATES_MOSS_FWET_LIQ) to the total-water one (FATES_MOSS_FWET_TOT), and added a
12-hourly h1 tape.  These checks read the Task C run, and for 3 and 4 the Task B
run of the same test, which differs from it by that switch alone.

  2b  On the h1 tape, the two 12-hour records of each day are equal for every
      FATES_MOSS_FWET_* field and FATES_MOSS_WETNESS_SCALER.  Until Task D the
      proxies are refreshed once a day, at the FATES dynamics call on the first
      timestep of the day (clm_driver, is_beg_curr_day), so both halves of a day
      hold the same value.

  3   Moss GPP (FATES_GPP_PF) goes down or stays the same against Task B,
      never up.  More water in the film means more CO2 resistance, so GPP
      should be lower on partly frozen days and unchanged on thawed ones.  Both
      halves of that are identities only while the two runs are still in the
      same state, which ends at the first record on which moss GPP, LAI or
      biomass, the liquid proxy, or the burned fraction differs.  So the first
      GPP difference anywhere after the skipped years must fall on an affected
      day, come from identical state, and be a decrease.  The other two tests,
      never higher and unchanged on thawed days, read the first frozen period
      after the skipped years in which moss GPP is nonzero in either run on
      some affected record; a frozen period with zero GPP throughout can show
      neither a decrease nor a rise, so it is passed over and named.  The
      window opens just after the previous frozen period, so its thawed
      lead-in belongs to it.  A thawed day is required to be unchanged only
      when it comes from identical state; differences on later days are
      reported, not judged.  Divergence is tracked from the first record of the
      run, skipped years included.

  4   Moss fuel moisture (FATES_FUEL_MOISTURE_FC, classes 7 live moss and 8
      dead moss) rises against Task B on partly frozen days in the first
      frozen period after the skipped years, and is unchanged on thawed
      ones.  Fuel moisture is a function of the proxy alone, but the proxy is
      not: its soil ingredient moves with transpiration and its canopy
      ingredient with LAI, so once the runs diverge, Task B's liquid proxy can
      drift from Task C's.  Both halves are therefore judged only on days whose
      liquid proxy is the same in the two runs, and the days left out are
      counted.  The tape value is an area-weighted mean over every patch, grass
      included, whose moss fuel classes read the same switched proxy.

A day is PARTLY FROZEN when the run's FATES_MOSS_FWET_TOT exceeds its
FATES_MOSS_FWET_LIQ, i.e. ice raises the total proxy above the liquid one.  That
is exactly the condition under which the switch changes what the consumers
read: when ice is absent, or the canopy ingredient sets both proxies, they are
equal and the switch is a no-op.  It is read off the Task C run's own tape.

Checks 3 and 4 skip the first --skip-years calendar years of the record
(default 0).  A FROZEN PERIOD runs from its first partly frozen day to the last
partly frozen day before the first stretch of --thaw-run consecutive thawed
days that follows it, so its ragged end, partly frozen days interleaved with
thawed ones, belongs to it.  Check 4 reads the first one after the skipped
years, from the first day after them.

Timing.  The daily dynamics call runs on the first timestep of day d, after
that timestep's photosynthesis.  It refreshes the proxy, then copies the GPP
accumulated since the previous call into gpp_acc_hold, which is what
FATES_GPP_PF reports (EDMainMod, FatesHistoryInterfaceMod).  So the proxy on
daily record d is the one computed at the start of day d, while the GPP on
record d was accumulated over the previous day, every timestep of which saw
proxy record d-1.  GPP record d is therefore affected exactly when proxy record
d-1 is partly frozen; record 0's GPP saw only the initial proxy and is left
out.  Likewise moss LAI and biomass on record d-1 are the state that GPP record
d was produced from.  Fuel moisture is computed in the same call as the proxy,
after it, so fuel record d is compared with proxy record d.

Exit status: 0 if every check passed; 1 if any failed; 2 if none failed but
at least one could not be made (NO VERDICT).

Usage, in the ctsm_pylib env (numpy, netCDF4, cftime):

    /glade/work/samrabin/conda-envs/ctsm_pylib/bin/python3 checks.py \\
        [--new-rundir DIR] [--old-rundir DIR] [--skip-years N] [--thaw-run N]
        [--table]

The defaults are the run/ directories of the two fates_nvp suite runs: Task C
(tests_1007-104555de, the suite that generated daily-wetness-proxy.fce424d11)
and Task B (tests_1006-171735de, which generated daily-wetness-proxy.953d42eb).
The Task B baseline directory itself holds only the last day's tape, so the
day-by-day comparison has to read the Task B suite run.
"""

import argparse
import os
import sys
from glob import glob

import cftime
import netCDF4 as nc
import numpy as np

SCRATCH = "/glade/derecho/scratch/samrabin"
TESTNAME = ("SMS_Ly2_D_Mmpi-serial.1x1_ALP2.I2000Clm60Fates.derecho_intel."
            "clm-FatesColdNoCompFixedBioGeo--clm-FatesNvp--clm-FatesALP2BareGrassMoss.GC")
DEFAULT_NEW_RUNDIR = os.path.join(
    SCRATCH, "tests_1007-104555de", f"{TESTNAME}.1007-104555de_int", "run")
DEFAULT_OLD_RUNDIR = os.path.join(
    SCRATCH, "tests_1006-171735de", f"{TESTNAME}.1006-171735de_int", "run")

H0_GLOB = "*.clm2.h0a.*.nc"
H1_GLOB = "*.clm2.h1a.*.nc"

# 1-based FATES PFT index of moss in fates_params_moss.json.
MOSS_PFT = 15

# Fuel class indices, 1-based, in the order FatesFuelClassesMod.F90 defines them; the
# fates_levfuel coordinate on the tape is a bare integer axis with no names.
MOSS_FUEL_CLASSES = {"live moss": 7, "dead moss": 8}

FWET_LIQ = "FATES_MOSS_FWET_LIQ"
FWET_TOT = "FATES_MOSS_FWET_TOT"
GPP = "FATES_GPP_PF"
LAI = "FATES_LAI_PF"
VEGC = "FATES_VEGC_PF"
PATCHAREA = "FATES_NOCOMP_PATCHAREA_PF"
BURNFRAC = "FATES_BURNFRAC"
FUEL_MOISTURE = "FATES_FUEL_MOISTURE_FC"

H1_FIELDS = [
    "FATES_MOSS_FWET_LIQ",
    "FATES_MOSS_FWET_TOT",
    "FATES_MOSS_FWET_SOIL_LIQ",
    "FATES_MOSS_FWET_SOIL_TOT",
    "FATES_MOSS_FWET_CANOPY",
    "FATES_MOSS_WETNESS_SCALER",
]

PFT_DIM = "fates_levpft"
FUEL_DIM = "fates_levfuel"

# Anything at or above this is the history fill value (1e36), not a number.
FILL_THRESHOLD = 1e35

DEFAULT_THAW_RUN = 7

DEFAULT_SKIP_YEARS = 0

# How many offending days to list before eliding the rest.
MAX_LISTED = 15


class Report:
    """Collects PASS / FAIL / NO VERDICT / INFO lines and the exit status."""

    def __init__(self):
        self.counts = {"PASS": 0, "FAIL": 0, "NO VERDICT": 0}

    def line(self, status, label, detail=""):
        if status in self.counts:
            self.counts[status] += 1
        print(f"  {status:<10} {label}")
        for text in detail.splitlines() if detail else []:
            print(f"             {text}")

    def exit_code(self):
        if self.counts["FAIL"]:
            return 1
        if self.counts["NO VERDICT"]:
            return 2
        return 0


def unfill(values):
    """Float64 copy with the history fill value replaced by NaN."""
    out = np.array(values, dtype=np.float64)
    out[np.abs(out) >= FILL_THRESHOLD] = np.nan
    return out


def same(a, b):
    """Elementwise exact equality, with NaN equal to NaN."""
    return (a == b) | (np.isnan(a) & np.isnan(b))


def day_label(day_number, units, calendar):
    """YYYY-MM-DD for the day whose interval starts at day_number."""
    return cftime.num2date(day_number, units, calendar=calendar).strftime("%Y-%m-%d")


def require_dims(var, name, path, dims):
    if tuple(var.dimensions) != dims:
        sys.exit(f"{name} on {path} has dimensions {var.dimensions}; expected {dims}. "
                 f"Refusing to index it.")


def h0_tapes(rundir):
    """Map YYYY-MM-DD-SSSSS stamp -> path, for one run directory's daily tapes."""
    out = {}
    for path in sorted(glob(os.path.join(rundir, H0_GLOB))):
        stamp = os.path.basename(path).rsplit(".", 2)[-2]
        out[stamp] = path
    return out


def read_daily(paths):
    """Read the fields checks 3 and 4 need from a list of one-record daily tapes.

    Returns (series, day_start, units, calendar). day_start is each record's
    time_bounds start, in days.
    """
    n = len(paths)
    series = {
        FWET_LIQ: np.full(n, np.nan),
        FWET_TOT: np.full(n, np.nan),
        BURNFRAC: np.full(n, np.nan),
        GPP: np.full(n, np.nan),
        LAI: np.full(n, np.nan),
        VEGC: np.full(n, np.nan),
        PATCHAREA: np.full(n, np.nan),
    }
    for label in MOSS_FUEL_CLASSES:
        series[label] = np.full(n, np.nan)
    day_start = np.full(n, np.nan)
    units = calendar = None
    for i, path in enumerate(paths):
        with nc.Dataset(path) as d:
            d.set_auto_mask(False)
            if d.dimensions["time"].size != 1:
                sys.exit(f"{path} holds {d.dimensions['time'].size} records; this "
                         f"script expects one daily record per h0a file.")
            bounds = d["time_bounds"][0, :]
            if bounds[1] - bounds[0] != 1.0:
                sys.exit(f"{path} covers {bounds[1] - bounds[0]} days; expected a daily "
                         f"mean (hist_nhtfrq = -24).")
            day_start[i] = bounds[0]
            if units is None:
                units = d["time_bounds"].units
                calendar = d["time"].calendar
            for name in (FWET_LIQ, FWET_TOT, BURNFRAC):
                require_dims(d[name], name, path, ("time", "lndgrid"))
                series[name][i] = unfill(d[name][0, 0])
            for name in (GPP, LAI, VEGC, PATCHAREA):
                require_dims(d[name], name, path, ("time", PFT_DIM, "lndgrid"))
                series[name][i] = unfill(d[name][0, MOSS_PFT - 1, 0])
            require_dims(d[FUEL_MOISTURE], FUEL_MOISTURE, path,
                         ("time", FUEL_DIM, "lndgrid"))
            for label, iclass in MOSS_FUEL_CLASSES.items():
                series[label][i] = unfill(d[FUEL_MOISTURE][0, iclass - 1, 0])
    return series, day_start, units, calendar


def list_days(labels, indices, columns):
    """Format one line per listed day: date then the given columns."""
    lines = []
    for i in indices[:MAX_LISTED]:
        cells = "  ".join(f"{name} {values[i]:.6g}" for name, values in columns)
        lines.append(f"{labels[i]}  {cells}")
    if len(indices) > MAX_LISTED:
        lines.append(f"... and {len(indices) - MAX_LISTED} more")
    return "\n".join(lines)


# --------------------------------------------------------------------------------------
# Check 2b
# --------------------------------------------------------------------------------------

def check_2b(rundir, report):
    print("\n(2b) h1: the two 12-hour records of each day are equal")
    paths = sorted(glob(os.path.join(rundir, H1_GLOB)))
    if not paths:
        report.line("NO VERDICT", f"no {H1_GLOB} files in {rundir}")
        return
    print(f"  reading {len(paths)} h1 file(s)")

    starts, widths = [], []
    values = {f: [] for f in H1_FIELDS}
    missing = set()
    units = calendar = None
    for path in paths:
        with nc.Dataset(path) as d:
            d.set_auto_mask(False)
            bounds = np.asarray(d["time_bounds"][:, :], dtype=np.float64)
            starts.append(bounds[:, 0])
            widths.append(bounds[:, 1] - bounds[:, 0])
            if units is None:
                units = d["time_bounds"].units
                calendar = d["time"].calendar
            for f in H1_FIELDS:
                if f not in d.variables:
                    missing.add(f)
                    continue
                require_dims(d[f], f, path, ("time", "lndgrid"))
                values[f].append(unfill(d[f][:, 0]))
    if missing:
        report.line("FAIL", f"h1 lacks {sorted(missing)}")
        return
    starts = np.concatenate(starts)
    widths = np.concatenate(widths)
    values = {f: np.concatenate(v) for f, v in values.items()}

    if not np.all(widths == 0.5):
        report.line("FAIL", f"h1 records are not all 12-hourly: widths "
                            f"{sorted(set(widths.tolist()))} days")
        return
    if np.any(np.diff(starts) != 0.5):
        report.line("FAIL", "h1 records are not contiguous and in order across files")
        return

    # Pair the records by the day their interval starts in: [d, d+0.5) and [d+0.5, d+1).
    # The records are contiguous, so after dropping a half day at either end they
    # alternate first half, second half.
    day = np.floor(starts)
    keep = np.arange(starts.size)
    incomplete = []
    if starts[keep[0]] != day[keep[0]]:
        incomplete.append(day_label(day[keep[0]], units, calendar))
        keep = keep[1:]
    if keep.size % 2:
        incomplete.append(day_label(day[keep[-1]], units, calendar))
        keep = keep[:-1]
    first, second = keep[0::2], keep[1::2]
    labels = [day_label(x, units, calendar) for x in day[first]]
    print(f"  {len(first)} complete days, "
          f"{labels[0]} to {labels[-1]}"
          + (f"; dropped incomplete day(s) {incomplete}" if incomplete else ""))

    for f in H1_FIELDS:
        a, b = values[f][first], values[f][second]
        equal = same(a, b)
        # How many days the field moves from the previous day: an equality that holds
        # because a field never changes would establish nothing.
        moves = int(np.count_nonzero(~same(a[1:], a[:-1])))
        if np.isnan(a).all() or moves == 0:
            report.line("NO VERDICT", f"{f}: never changes between days "
                                      f"({'all fill' if np.isnan(a).all() else 'constant'}), "
                                      f"so equal halves would establish nothing")
            continue
        if equal.all():
            report.line("PASS", f"{f}: equal on all {a.size} days "
                                f"(value changes between days on {moves})")
            continue
        bad = np.flatnonzero(~equal)
        diff = np.abs(a[bad] - b[bad])
        detail = [f"max |difference| {np.nanmax(diff):.6g}",
                  list_days(labels, bad, [("00-12h", a), ("12-24h", b)])]
        # If the second half of each day matches the first half of the next instead,
        # the refresh is landing inside the day rather than at its boundary.
        shifted = same(b[:-1], a[1:])
        detail.append(f"12-24h of day d equals 00-12h of day d+1 on "
                      f"{int(shifted.sum())} of {shifted.size} day pairs")
        report.line("FAIL", f"{f}: the two halves differ on {bad.size} of {a.size} days",
                    "\n".join(detail))


# --------------------------------------------------------------------------------------
# Checks 3 and 4: shared setup
# --------------------------------------------------------------------------------------

def first_frozen_period(frozen, thaw_run, begin):
    """Return (begin, first frozen index, window end index inclusive) for the first
    frozen period at or after record `begin`, or None if there is none."""
    if not frozen[begin:].any():
        return None
    start = begin + int(np.argmax(frozen[begin:]))
    last_frozen = start
    thawed_streak = 0
    for i in range(start, frozen.size):
        if frozen[i]:
            last_frozen = i
            thawed_streak = 0
        else:
            thawed_streak += 1
            if thawed_streak >= thaw_run:
                break
    return begin, start, last_frozen


def load_pair(new_rundir, old_rundir):
    new_tapes = h0_tapes(new_rundir)
    old_tapes = h0_tapes(old_rundir)
    shared = sorted(set(new_tapes) & set(old_tapes))
    print(f"  daily tapes: new {len(new_tapes)}, old {len(old_tapes)}, shared {len(shared)}")
    for which, only in (("new", set(new_tapes) - set(old_tapes)),
                        ("old", set(old_tapes) - set(new_tapes))):
        if only:
            print(f"  only in {which}: {sorted(only)[:3]}{' ...' if len(only) > 3 else ''}")
    if not shared:
        sys.exit("No daily tapes shared between the two runs.")
    new, new_days, units, calendar = read_daily([new_tapes[s] for s in shared])
    old, old_days, _, _ = read_daily([old_tapes[s] for s in shared])
    if not np.array_equal(new_days, old_days):
        sys.exit("The two runs' shared tapes do not cover the same days.")
    if np.any(np.diff(new_days) != 1.0):
        sys.exit("The shared daily tapes have gaps; the d-1 timing rule needs consecutive days.")
    labels = [day_label(x, units, calendar) for x in new_days]
    return new, old, labels


# --------------------------------------------------------------------------------------
# Check 3
# --------------------------------------------------------------------------------------

def productive_frozen_period(frozen, thaw_run, begin, affected, g_new, g_old, labels,
                             report):
    """GPP window around the first frozen period, at or after record `begin`, in which
    moss GPP is nonzero in either run on at least one affected record; None if none is.

    A frozen period whose affected records all have zero GPP in both runs can show
    neither a decrease nor a rise, so it is reported and passed over. The window opens on the record after
    the previous frozen period ends, so the thawed lead-in belongs to it.
    """
    n = frozen.size
    lead_in = begin
    while lead_in < n:
        period = first_frozen_period(frozen, thaw_run, lead_in)
        if period is None:
            return None
        _, start, end = period
        # GPP record d saw proxy record d-1, so the GPP window runs one record past the
        # proxy window. Record 0 has no proxy record behind it and is left out.
        win = np.arange(max(lead_in, 1), min(end + 2, n))
        aff = win[affected[win]]
        if np.any((g_old[aff] > 0.0) | (g_new[aff] > 0.0)):
            return win
        report.line("INFO", f"frozen period {labels[start]} to {labels[end]} passed over: "
                            f"moss GPP is zero in both runs on all {aff.size} affected "
                            f"records")
        lead_in = end + 1
    return None


def check_3(new, old, labels, frozen, begin, thaw_run, table, report):
    print(f"\n(3) moss GPP ({GPP}, PFT {MOSS_PFT}) against Task B never rises")
    n = frozen.size
    # GPP record d was accumulated under proxy record d-1, from the moss state on record
    # d-1. Record 0 has no proxy record behind it and is left out.
    run = np.arange(max(begin, 1), n)
    affected = np.zeros(n, dtype=bool)
    affected[1:] = frozen[:-1]
    thawed = ~affected
    # Once anything feeding moss GPP differs between the runs, it stays different:
    # moss LAI or biomass, the liquid proxy (soil water moves with transpiration), a
    # burn (the fuel switch changes flammability from day 0), or GPP itself. A record
    # comes from diverged state when that has happened on any earlier record.
    g_new, g_old = new[GPP], old[GPP]
    # Record 0's GPP is left out (above), so only its GPP term is exempt; a day-0 burn
    # already runs on the switched fuel moisture.
    gpp_moved = ~same(g_new, g_old)
    gpp_moved[0] = False
    moved = (~same(new[LAI], old[LAI]) | ~same(new[VEGC], old[VEGC])
             | ~same(new[FWET_LIQ], old[FWET_LIQ]) | ~same(new[BURNFRAC], old[BURNFRAC])
             | gpp_moved)
    state_before = np.zeros(n, dtype=bool)
    state_before[1:] = np.maximum.accumulate(moved[:-1])

    if np.isnan(g_new[run]).any() or np.isnan(g_old[run]).any():
        report.line("NO VERDICT", f"{GPP} is missing on some days")
        return

    columns = [("new", g_new), ("old", g_old), ("LAI new", new[LAI]),
               ("LAI old", old[LAI]), ("TOT(d-1)", np.r_[np.nan, new[FWET_TOT][:-1]]),
               ("LIQ(d-1)", np.r_[np.nan, new[FWET_LIQ][:-1]])]

    # (3b) the first GPP difference anywhere in the run is the one record certain to
    # come from the film alone, provided nothing else has diverged before it. It has to
    # be affected and lower. No window is needed: until it, the runs are identical.
    differs = run[g_new[run] != g_old[run]]
    productive = run[affected[run] & (g_old[run] > 0.0)]
    if differs.size == 0:
        if productive.size:
            report.line("FAIL", f"identical on every record, including {productive.size} "
                                f"affected record(s) with nonzero Task B GPP: the switch "
                                f"left moss GPP untouched")
        else:
            report.line("NO VERDICT", "identical on every record, but Task B moss GPP is "
                                      "zero on every affected record, so a decrease was "
                                      "never possible")
    else:
        k = differs[0]
        first = f"first difference on {labels[k]}: " + list_days(labels, [k], columns)
        if state_before[k]:
            m = int(np.argmax(moved))
            report.line("NO VERDICT", f"the runs had already diverged on {labels[m]}, "
                                      f"before GPP first differs, so no GPP difference "
                                      f"can be attributed to the film alone", first)
        elif affected[k] and g_new[k] < g_old[k]:
            report.line("PASS", "lower on the first record that differs, which is "
                                "affected and comes from identical state", first)
        else:
            report.line("FAIL", f"the first record that differs is "
                                f"{'affected' if affected[k] else 'thawed'} and "
                                f"{'lower' if g_new[k] < g_old[k] else 'higher'}", first)

    # The rest of check 3 reads the first frozen period in which moss GPP is nonzero in
    # either run on some affected record.
    win = productive_frozen_period(frozen, thaw_run, begin, affected, g_new, g_old,
                                   labels, report)
    if win is None:
        report.line("NO VERDICT", "no frozen period has an affected record with nonzero "
                                  "moss GPP in either run; 'never higher' and 'unchanged "
                                  "on thawed days' have nothing to judge")
        return
    print(f"  GPP window: {labels[win[0]]} to {labels[win[-1]]} ({win.size} records, "
          f"{int(affected[win].sum())} affected)")

    higher = win[g_new[win] > g_old[win]]
    lower = win[g_new[win] < g_old[win]]
    equal = win[g_new[win] == g_old[win]]

    # (3a) never higher over the window.
    if higher.size == 0:
        report.line("PASS", f"never higher on any of the {win.size} window records "
                            f"(lower {lower.size}, equal {equal.size})")
    else:
        report.line("FAIL", f"higher on {higher.size} of {win.size} window records "
                            f"({int(affected[higher].sum())} affected, "
                            f"{int(thawed[higher].sum())} thawed; state going in had "
                            f"already diverged on "
                            f"{int(state_before[higher].sum())})",
                    list_days(labels, higher, columns))

    aff = win[affected[win]]
    aff_lower = aff[g_new[aff] < g_old[aff]]
    aff_equal = aff[g_new[aff] == g_old[aff]]
    aff_equal_productive = aff_equal[g_old[aff_equal] > 0.0]
    report.line("INFO", f"of {aff.size} affected records: lower {aff_lower.size} "
                        f"({int(state_before[aff_lower].sum())} of them from already "
                        f"diverged state), equal {aff_equal.size} "
                        f"({aff_equal.size - aff_equal_productive.size} with zero GPP in "
                        f"both runs)")
    if aff_equal_productive.size:
        report.line("INFO", f"{aff_equal_productive.size} affected record(s) with nonzero "
                            f"GPP left exactly unchanged",
                    list_days(labels, aff_equal_productive, columns))

    # (3c) unchanged on thawed days: an identity only where the state going in is the
    # same in both runs.
    th = win[thawed[win]]
    th_clean = th[~state_before[th]]
    th_clean_diff = th_clean[g_new[th_clean] != g_old[th_clean]]
    if th_clean.size == 0:
        report.line("NO VERDICT", f"no thawed record in the window comes from identical "
                                  f"state ({th.size} thawed records, all after "
                                  f"divergence), so 'unchanged on thawed days' cannot be "
                                  f"tested as an identity on this run")
    elif th_clean_diff.size == 0:
        report.line("PASS", f"identical on all {th_clean.size} thawed records from "
                            f"identical state")
    else:
        report.line("FAIL", f"differs on {th_clean_diff.size} of {th_clean.size} thawed "
                            f"records from identical state",
                    list_days(labels, th_clean_diff, columns))
    th_moved = th[state_before[th]]
    if th_moved.size:
        th_moved_diff = th_moved[g_new[th_moved] != g_old[th_moved]]
        report.line("INFO", f"thawed records from diverged state: {th_moved.size}; "
                            f"GPP differs on {th_moved_diff.size} (lower "
                            f"{int(np.count_nonzero(g_new[th_moved_diff] < g_old[th_moved_diff]))})",
                    list_days(labels, th_moved_diff, columns))

    # The rest of the run, for context only: feedbacks blur the sign later on.
    rest = np.arange(win[-1] + 1, n)
    if rest.size:
        report.line("INFO", f"after the window ({rest.size} records): higher "
                            f"{int(np.count_nonzero(g_new[rest] > g_old[rest]))}, lower "
                            f"{int(np.count_nonzero(g_new[rest] < g_old[rest]))}, equal "
                            f"{int(np.count_nonzero(g_new[rest] == g_old[rest]))}")

    if table:
        print("\n  window, record by record (GPP kg m-2 s-1 per land area; A = proxy "
              "record d-1 partly frozen, S = state diverged by record d-1):")
        print(f"  {'date':<10} A S {'new':>12} {'old':>12} {'new-old':>12} "
              f"{'LAI new':>9} {'LAI old':>9}")
        for i in win:
            print(f"  {labels[i]:<10} {'A' if affected[i] else '.'} "
                  f"{'S' if state_before[i] else '.'} {g_new[i]:12.5g} {g_old[i]:12.5g} "
                  f"{g_new[i] - g_old[i]:12.4g} {new[LAI][i]:9.4g} {old[LAI][i]:9.4g}")


# --------------------------------------------------------------------------------------
# Check 4
# --------------------------------------------------------------------------------------

def check_4(new, old, labels, frozen, window, report):
    print(f"\n(4) moss fuel moisture ({FUEL_MOISTURE}) against Task B rises on partly "
          f"frozen days")
    begin, _, end = window
    win = np.arange(begin, end + 1)
    fr = win[frozen[win]]
    th = win[~frozen[win]]
    # The fuel map reads each run's own proxy, which drifts between the runs once their
    # state diverges. Judge only records whose liquid proxy is the same in both: there,
    # Task B read exactly what Task C would have read without the switch.
    same_liq = same(new[FWET_LIQ], old[FWET_LIQ])
    fr_same_proxy = fr[same_liq[fr]]
    th_same_proxy = th[same_liq[th]]

    for label, iclass in MOSS_FUEL_CLASSES.items():
        f_new, f_old = new[label], old[label]
        name = f"class {iclass} ({label})"
        if np.isnan(f_new[win]).any() or np.isnan(f_old[win]).any():
            report.line("NO VERDICT", f"{name}: missing on some window days")
            continue
        if not (np.any(f_new[win] != 0.0) or np.any(f_old[win] != 0.0)):
            report.line("NO VERDICT", f"{name}: zero on every window day in both runs; "
                                      f"fuel moisture was never computed")
            continue
        columns = [("new", f_new), ("old", f_old), ("TOT new", new[FWET_TOT]),
                   ("LIQ old", old[FWET_LIQ])]

        not_up = fr_same_proxy[f_new[fr_same_proxy] <= f_old[fr_same_proxy]]
        skipped = fr.size - fr_same_proxy.size
        note = (f"; {skipped} partly frozen day(s) not compared because the liquid "
                f"proxy differs between runs" if skipped else "")
        if fr_same_proxy.size == 0:
            report.line("NO VERDICT", f"{name}: no partly frozen window day has the same "
                                      f"liquid proxy in both runs{note}")
        elif not_up.size == 0:
            rise = f_new[fr_same_proxy] - f_old[fr_same_proxy]
            report.line("PASS", f"{name}: higher on all {fr_same_proxy.size} partly frozen "
                                f"window days with the same liquid proxy (rise "
                                f"{rise.min():.4g} to {rise.max():.4g}){note}")
        else:
            report.line("FAIL", f"{name}: not higher on {not_up.size} of "
                                f"{fr_same_proxy.size} partly frozen window days with the "
                                f"same liquid proxy{note}", list_days(labels, not_up, columns))

        moved = th_same_proxy[f_new[th_same_proxy] != f_old[th_same_proxy]]
        skipped = th.size - th_same_proxy.size
        note = (f"; {skipped} thawed day(s) not compared because the liquid proxy "
                f"differs between runs" if skipped else "")
        if th_same_proxy.size == 0:
            report.line("NO VERDICT", f"{name}: no thawed window day has the same liquid "
                                      f"proxy in both runs{note}")
        elif moved.size == 0:
            report.line("PASS", f"{name}: unchanged on all {th_same_proxy.size} thawed "
                                f"window days with the same liquid proxy{note}")
        else:
            report.line("FAIL", f"{name}: changed on {moved.size} of "
                                f"{th_same_proxy.size} thawed window days with the same "
                                f"liquid proxy{note}", list_days(labels, moved, columns))

        rest = np.arange(end + 1, f_new.size)
        rest_fr = rest[frozen[rest]]
        if rest_fr.size:
            report.line("INFO", f"{name}, after the window: higher on "
                                f"{int(np.count_nonzero(f_new[rest_fr] > f_old[rest_fr]))} "
                                f"of {rest_fr.size} partly frozen days")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--new-rundir", default=DEFAULT_NEW_RUNDIR,
                    help="Task C run/ directory (default: %(default)s)")
    ap.add_argument("--old-rundir", default=DEFAULT_OLD_RUNDIR,
                    help="Task B run/ directory (default: %(default)s)")
    ap.add_argument("--thaw-run", type=int, default=DEFAULT_THAW_RUN,
                    help="consecutive thawed days that end the first frozen period "
                         "(default: %(default)s)")
    ap.add_argument("--skip-years", type=int, default=DEFAULT_SKIP_YEARS,
                    help="calendar years at the start of the record that checks 3 and 4 "
                         "skip (default: %(default)s)")
    ap.add_argument("--table", action="store_true",
                    help="print moss GPP day by day over check 3's window")
    args = ap.parse_args(argv)
    if args.thaw_run < 1:
        ap.error("--thaw-run must be at least 1")
    if args.skip_years < 0:
        ap.error("--skip-years must not be negative")

    print(f"new (Task C): {args.new_rundir}")
    print(f"old (Task B): {args.old_rundir}")
    report = Report()

    check_2b(args.new_rundir, report)

    print("\nreading daily tapes for checks 3 and 4")
    new, old, labels = load_pair(args.new_rundir, args.old_rundir)
    if not np.any(new[PATCHAREA] > 0.0):
        sys.exit(f"{PATCHAREA} for PFT {MOSS_PFT} is zero on every day: no moss patch, "
                 f"so PFT {MOSS_PFT} is not moss in this run or moss is absent.")

    frozen = new[FWET_TOT] > new[FWET_LIQ]
    old_frozen = old[FWET_TOT] > old[FWET_LIQ]
    print(f"  partly frozen days (Task C tape): {int(frozen.sum())} of {frozen.size}; "
          f"Task B's tape classifies {int(np.count_nonzero(frozen != old_frozen))} "
          f"day(s) differently")
    years = np.array([int(label[:4]) for label in labels])
    kept = np.flatnonzero(years >= years[0] + args.skip_years)
    window = first_frozen_period(frozen, args.thaw_run, kept[0]) if kept.size else None
    if window is None:
        report.line("NO VERDICT", f"no partly frozen day after skipping the first "
                                  f"{args.skip_years} year(s); checks 3 and 4 have "
                                  f"nothing to compare")
    else:
        begin, start, end = window
        print(f"  skipping {begin} record(s), the first {args.skip_years} year(s)")
        print(f"  first frozen period: first partly frozen day {labels[start]}, window "
              f"{labels[begin]} to {labels[end]} ({end + 1 - begin} days, "
              f"{int(frozen[begin:end + 1].sum())} partly frozen), ended by "
              f"{args.thaw_run} consecutive thawed days")
        check_3(new, old, labels, frozen, begin, args.thaw_run, args.table, report)
        check_4(new, old, labels, frozen, window, report)

    code = report.exit_code()
    print(f"\n{report.counts['PASS']} passed, {report.counts['FAIL']} failed, "
          f"{report.counts['NO VERDICT']} without a verdict; exit {code}")
    return code


if __name__ == "__main__":
    sys.exit(main())
