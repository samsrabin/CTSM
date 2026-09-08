#!/usr/bin/env python3
"""Absolute-scale readout of the grass PFT and the site carbon balance.

Read-only companion to read_moss_tape.py.  Answers "is the grass PFT healthy
in this run, or is the whole simulation unproductive?" with numbers, in
explicitly-labelled normalizations.

Normalizations
--------------
FATES_*_PF variables are per m2 LAND area.  Three readings are printed:
  land   as it comes off the tape
  patch  divided by FATES_NOCOMP_PATCHAREA_PF for that PFT
  crown  divided by FATES_CROWNAREA_PF for that PFT (LAI/SAI only)

Site-level FATES diagnostics are patch-area weighted sums with bareground
contributing zero, so a site value is the patch value times the
non-bareground area fraction.  That fraction is read off
FATES_NOCOMP_PATCHAREA_PF (sum over vegetated PFTs), never assumed.

Usage:
    grass_health.py RUNDIR [--days D1:D2]
"""

import argparse
import glob
import os
import sys

import netCDF4
import numpy as np

MOSS_PFT = 15
GRASS_PFT = 12

SEC_PER_DAY = 86400.0
DAYS_PER_YEAR = 365.0
# kg m-2 s-1 -> kg m-2 yr-1
FLUX_TO_ANNUAL = SEC_PER_DAY * DAYS_PER_YEAR

PFT_VARS = [
    "FATES_GPP_PF",
    "FATES_LEAFC_PF",
    "FATES_LAI_PF",
    "FATES_SAI_PF",
    "FATES_CROWNAREA_PF",
    "FATES_NOCOMP_PATCHAREA_PF",
    "FATES_MORTALITY_TERMINATION_PF",
    "FATES_MORTALITY_HYDRAULIC_PF",
]

SITE_FLUX_VARS = [
    "FATES_GPP",
    "FATES_NPP",
    "FATES_AUTORESP",
    "FATES_MAINT_RESP",
    "FATES_GROWTH_RESP",
    "FATES_SEED_ALLOC",
    "FATES_LEAF_ALLOC",
    "FATES_FROOT_ALLOC",
    "FATES_STORE_ALLOC",
    "FATES_MORTALITY_CFLUX_CANOPY",
    "FATES_MORTALITY_CFLUX_USTORY",
    "FATES_LITTER_IN",
    "FATES_NEP",
    "FATES_HET_RESP",
]
SITE_STATE_VARS = [
    "FATES_LEAFC",
    "FATES_STOREC",
    "FATES_FROOTC",
    "FATES_SAPWOODC",
    "FATES_STRUCTC",
    "FATES_REPROC",
    "FATES_NONSTRUCTC",
    "FATES_VEGC",
    "FATES_SEED_BANK",
]
SITE_OTHER_VARS = [
    "FATES_NCOHORTS",
    "FATES_TRIMMING",
    "FATES_COLD_STATUS",
    "FATES_CBALANCE_ERROR",
    "FATES_GDD",
    "FATES_AREA_PLANTS",
    "FATES_CANOPY_VEGC",
    "FATES_USTORY_VEGC",
    "FATES_SEEDS_IN",
]


def load(rundir):
    files = sorted(glob.glob(os.path.join(rundir, "*.clm2.h0a.*.nc")))
    if not files:
        sys.exit(f"no h0a history files under {rundir}")
    want = PFT_VARS + SITE_FLUX_VARS + SITE_STATE_VARS + SITE_OTHER_VARS
    out = {}
    dates = []
    for i, f in enumerate(files):
        ds = netCDF4.Dataset(f)
        if i == 0:
            npft = len(ds.dimensions["fates_levpft"])
        dates.append(os.path.basename(f).split(".clm2.h0a.")[1][:10])
        for v in want:
            if v not in ds.variables:
                continue
            a = np.asarray(ds[v][:], dtype=float)
            a = np.squeeze(a)
            if v in PFT_VARS:
                out.setdefault(v, np.full((len(files), npft), np.nan))
                out[v][i, :] = a
            else:
                out.setdefault(v, np.full(len(files), np.nan))
                out[v][i] = float(a)
        ds.close()
    absent = [v for v in want if v not in out]
    return out, dates, absent


def stats(a):
    fin = a[np.isfinite(a)]
    if fin.size == 0:
        return (np.nan,) * 4
    return float(np.min(fin)), float(np.mean(fin)), float(np.max(fin)), float(fin[-1])


def jja_mask(dates):
    return np.array([d[5:7] in ("06", "07", "08") for d in dates])


def line(label, vals, fmt="{:13.5e}"):
    print(f"  {label:44s} " + " ".join(fmt.format(v) for v in vals))


def main():
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("rundir")
    p.add_argument("--days", default="395:410",
                   help="comma-separated D1:D2 windows of 1-based sim days")
    args = p.parse_args()

    d, dates, absent = load(args.rundir)
    n = len(dates)
    jja = jja_mask(dates)
    print(f"{n} daily samples, {dates[0]} .. {dates[-1]}; "
          f"JJA days = {int(jja.sum())}")
    if absent:
        print("absent from tape: " + ", ".join(absent))

    pa = d["FATES_NOCOMP_PATCHAREA_PF"]
    ig, im = GRASS_PFT - 1, MOSS_PFT - 1
    pa_g = np.nanmean(pa[:, ig])
    pa_m = np.nanmean(pa[:, im])
    veg_frac = np.nanmean(np.nansum(pa, axis=1))
    print(f"\nprescribed nocomp patch area: grass {pa_g:.6f} "
          f"(range {np.nanmin(pa[:, ig]):.6f}-{np.nanmax(pa[:, ig]):.6f}), "
          f"moss {pa_m:.6f} "
          f"(range {np.nanmin(pa[:, im]):.6f}-{np.nanmax(pa[:, im]):.6f})")
    print(f"non-bareground area fraction (sum of vegetated patch areas): "
          f"{veg_frac:.6f}  [site-to-patch factor for site-level vars]")

    # ---------------- item 1: grass in absolute terms ----------------
    for name, ip, parea in (("GRASS (PFT 12)", ig, pa_g),
                            ("MOSS (PFT 15)", im, pa_m)):
        print(f"\n=== {name}: peak / JJA mean, per normalization ===")
        print(f"  {'':44s} {'min':>13s} {'mean(all)':>13s} "
              f"{'max':>13s} {'mean(JJA)':>13s} {'max(JJA)':>13s}")
        crown = d["FATES_CROWNAREA_PF"][:, ip]
        for v in ("FATES_GPP_PF", "FATES_LEAFC_PF", "FATES_LAI_PF",
                  "FATES_SAI_PF", "FATES_CROWNAREA_PF",
                  "FATES_NOCOMP_PATCHAREA_PF"):
            a = d[v][:, ip]
            aj = a[jja]
            line(f"{v} [per m2 land]",
                 [np.nanmin(a), np.nanmean(a), np.nanmax(a),
                  np.nanmean(aj), np.nanmax(aj)])
            if v != "FATES_NOCOMP_PATCHAREA_PF" and parea > 0:
                b = a / parea
                bj = b[jja]
                line(f"{v} [per m2 patch, /{parea:g}]",
                     [np.nanmin(b), np.nanmean(b), np.nanmax(b),
                      np.nanmean(bj), np.nanmax(bj)])
            if v in ("FATES_LAI_PF", "FATES_SAI_PF", "FATES_LEAFC_PF"):
                with np.errstate(divide="ignore", invalid="ignore"):
                    c = np.where(crown > 0, a / crown, np.nan)
                cj = c[jja]
                line(f"{v} [per m2 crown]",
                     [np.nanmin(c), np.nanmean(c), np.nanmax(c),
                      np.nanmean(cj), np.nanmax(cj)])
            if v == "FATES_GPP_PF":
                for tag, f in (("land", 1.0), (f"patch /{parea:g}", 1.0 / parea)):
                    b = a * f * FLUX_TO_ANNUAL
                    bj = b[jja]
                    line(f"FATES_GPP_PF [kgC m-2 yr-1, per m2 {tag}]",
                         [np.nanmin(b), np.nanmean(b), np.nanmax(b),
                          np.nanmean(bj), np.nanmax(bj)])
        # crown-area fill of the prescribed patch
        fill = crown / parea
        print(f"  crown area / prescribed patch area: max {np.nanmax(fill):.6e} "
              f"({100 * np.nanmax(fill):.4f}% of patch), "
              f"mean {np.nanmean(fill):.6e}, last {fill[-1]:.6e}")
        # GPP per m2 CROWN area -- the per-plant rate, with the population
        # size divided out.  This is the reading that separates "the plants
        # photosynthesize slowly" from "there are almost no plants".
        gp = d["FATES_GPP_PF"][:, ip]
        with np.errstate(divide="ignore", invalid="ignore"):
            pc = np.where(crown > 0, gp / crown, np.nan)
        print(f"  FATES_GPP_PF per m2 CROWN: max {np.nanmax(pc):.5e} kg m-2 s-1 "
              f"= {np.nanmax(pc) * FLUX_TO_ANNUAL:.5e} kgC m-2crown yr-1; "
              f"JJA mean {np.nanmean(pc[jja]):.5e} "
              f"= {np.nanmean(pc[jja]) * FLUX_TO_ANNUAL:.5e} kgC m-2crown yr-1")

    # ---------------- item 2: does grass grow at all? ----------------
    print("\n=== item 2: growth / seasonality ===")
    for name, ip in (("grass", ig), ("moss", im)):
        for v in ("FATES_LEAFC_PF", "FATES_GPP_PF", "FATES_CROWNAREA_PF"):
            a = d[v][:, ip]
            diff = np.diff(a)
            nup = int(np.sum(diff > 0))
            ndn = int(np.sum(diff < 0))
            y1 = a[:365]
            y2 = a[365:]
            print(f"  {name:5s} {v:26s} day1 {a[0]:.5e} -> "
                  f"day{n} {a[-1]:.5e}; steps up {nup} down {ndn} "
                  f"flat {len(diff) - nup - ndn}; "
                  f"yr1 mean {np.nanmean(y1):.5e} max {np.nanmax(y1):.5e}; "
                  f"yr2 mean {np.nanmean(y2):.5e} max {np.nanmax(y2):.5e}")
        a = d["FATES_LEAFC_PF"][:, ip]
        # monotonic?
        diff = np.diff(a)
        print(f"  {name:5s} FATES_LEAFC_PF monotonic non-increasing: "
              f"{bool(np.all(diff <= 0))}; monotonic non-decreasing: "
              f"{bool(np.all(diff >= 0))}")
        # per-month means, per m2 land
        print(f"  {name:5s} FATES_LEAFC_PF monthly mean (per m2 land), "
              "yr2000 then yr2001:")
        for yr in ("2000", "2001"):
            row = []
            for mo in range(1, 13):
                m = np.array([dt[:4] == yr and dt[5:7] == f"{mo:02d}"
                              for dt in dates])
                row.append(np.nanmean(a[m]) if m.any() else np.nan)
            print("    " + yr + " " + " ".join(f"{x:10.3e}" for x in row))
        g = d["FATES_GPP_PF"][:, ip]
        print(f"  {name:5s} FATES_GPP_PF monthly mean (per m2 land):")
        for yr in ("2000", "2001"):
            row = []
            for mo in range(1, 13):
                m = np.array([dt[:4] == yr and dt[5:7] == f"{mo:02d}"
                              for dt in dates])
                row.append(np.nanmean(g[m]) if m.any() else np.nan)
            print("    " + yr + " " + " ".join(f"{x:10.3e}" for x in row))

    # ---------------- item 3: site carbon balance ----------------
    print("\n=== item 3: site carbon balance ===")
    print(f"  {'variable':30s} {'min':>13s} {'mean':>13s} {'max':>13s} "
          f"{'last':>13s}  {'n>0':>5s}")
    for v in SITE_FLUX_VARS + SITE_STATE_VARS + SITE_OTHER_VARS:
        if v not in d:
            continue
        a = d[v]
        mn, mu, mx, last = stats(a)
        npos = int(np.sum(a > 0))
        print(f"  {v:30s} {mn:13.5e} {mu:13.5e} {mx:13.5e} {last:13.5e}  "
              f"{npos:5d}")

    gpp = d["FATES_GPP"]
    npp = d["FATES_NPP"]
    ar = d["FATES_AUTORESP"]
    mr = d["FATES_MAINT_RESP"]
    gr = d["FATES_GROWTH_RESP"]
    print("\n  respiration decomposition (site, per m2 land, kg m-2 s-1):")
    print(f"    mean GPP {np.nanmean(gpp):.5e}  AUTORESP {np.nanmean(ar):.5e}"
          f"  MAINT {np.nanmean(mr):.5e}  GROWTH {np.nanmean(gr):.5e}")
    print(f"    mean NPP {np.nanmean(npp):.5e}; "
          f"NPP == GPP-AUTORESP to {np.nanmax(np.abs(npp - (gpp - ar))):.3e}")
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = np.where(gpp > 0, ar / gpp, np.nan)
    print(f"    AUTORESP/GPP: min {np.nanmin(ratio):.4e} "
          f"mean {np.nanmean(ratio):.4e} max {np.nanmax(ratio):.4e}")
    print(f"    MAINT share of AUTORESP: mean "
          f"{np.nanmean(np.where(ar > 0, mr / ar, np.nan)):.6f}")
    print(f"    days NPP < 0: {int(np.sum(npp < 0))}/{n}; "
          f"days GPP > 0: {int(np.sum(gpp > 0))}/{n}")
    print(f"    annual-equivalent site GPP {np.nanmean(gpp) * FLUX_TO_ANNUAL:.5e}"
          f" kgC m-2 yr-1, NPP {np.nanmean(npp) * FLUX_TO_ANNUAL:.5e},"
          f" AUTORESP {np.nanmean(ar) * FLUX_TO_ANNUAL:.5e}")
    print(f"    per-m2-patch (site/{veg_frac:g}): GPP "
          f"{np.nanmean(gpp) / veg_frac * FLUX_TO_ANNUAL:.5e} kgC m-2 yr-1, "
          f"NPP {np.nanmean(npp) / veg_frac * FLUX_TO_ANNUAL:.5e}")

    # Annual carbon budget, integrated from the daily means rather than
    # inferred from a mean rate, so the two calendar years can be compared.
    print("\n  calendar-year integrals (kgC m-2, from daily means x 86400):")
    for yr in ("2000", "2001"):
        mk = np.array([dt[:4] == yr for dt in dates])
        print(f"    {yr} ({int(mk.sum())} days on tape)")
        for tag, ip, parea in (("grass", ig, pa_g), ("moss", im, pa_m)):
            tot = np.nansum(d["FATES_GPP_PF"][mk, ip]) * SEC_PER_DAY
            print(f"      {tag:5s} GPP  land {tot:12.5e}   "
                  f"patch {tot / parea:12.5e}")
        for v in ("FATES_GPP", "FATES_NPP", "FATES_AUTORESP", "FATES_NEP",
                  "FATES_HET_RESP"):
            if v not in d:
                continue
            tot = np.nansum(d[v][mk]) * SEC_PER_DAY
            print(f"      site {v:16s} land {tot:+12.5e}   "
                  f"patch {tot / veg_frac:+12.5e}")
    print(f"    HET_RESP / GPP integrated over the run: "
          f"{np.nansum(d['FATES_HET_RESP']) / np.nansum(gpp):.5g}")

    print("\n  seed pools (site, per m2 land):")
    for v in ("FATES_SEED_BANK", "FATES_SEEDS_IN", "FATES_SEED_ALLOC"):
        if v not in d:
            continue
        a = d[v]
        nz = np.nonzero(a != 0)[0]
        msg = (f"    {v:18s} nonzero on {nz.size}/{n} days, "
               f"max {np.nanmax(a):.5e}, last {a[-1]:.5e}")
        if nz.size:
            msg += (f"; first nonzero sim day {nz[0] + 1} ({dates[nz[0]]}), "
                    f"last {nz[-1] + 1} ({dates[nz[-1]]})")
        print(msg)

    pools = ["FATES_LEAFC", "FATES_STOREC", "FATES_FROOTC", "FATES_SAPWOODC",
             "FATES_STRUCTC", "FATES_REPROC"]
    tot = np.zeros(n)
    for v in pools:
        tot = tot + np.nan_to_num(d[v])
    print("\n  total vegetation carbon (sum of the six pools, per m2 land):")
    print(f"    day 1 {tot[0]:.5e}  day {n} {tot[-1]:.5e}  "
          f"min {tot.min():.5e} max {tot.max():.5e} kg m-2")
    print(f"    FATES_VEGC day 1 {d['FATES_VEGC'][0]:.5e} "
          f"day {n} {d['FATES_VEGC'][-1]:.5e} kg m-2")
    dt = np.diff(tot)
    print(f"    pool-sum steps: up {int(np.sum(dt > 0))} "
          f"down {int(np.sum(dt < 0))} flat {int(np.sum(dt == 0))}; "
          f"monotonic non-increasing {bool(np.all(dt <= 0))}")
    print(f"    net CHANGE over run {tot[-1] - tot[0]:+.5e} kg m-2 "
          f"(x{tot[-1] / tot[0]:.3f} of initial); mean rate "
          f"{(tot[-1] - tot[0]) / (n * SEC_PER_DAY):+.5e} kg m-2 s-1")
    print(f"    cumulative NPP over run "
          f"{np.nansum(npp) * SEC_PER_DAY:.5e} kg m-2 (sum of daily means)")

    # ---------------- item 4: cohorts and the cull ----------------
    print("\n=== item 4: FATES_NCOHORTS timeline ===")
    nc = d["FATES_NCOHORTS"]
    vals, idx = np.unique(nc, return_index=True)
    print(f"  distinct values: {sorted(set(nc.tolist()))}")
    # run-length encode
    runs = []
    start = 0
    for i in range(1, n + 1):
        if i == n or nc[i] != nc[start]:
            runs.append((nc[start], start + 1, i, dates[start], dates[i - 1]))
            start = i
    for v, a, b, da, db in runs:
        print(f"  NCOHORTS = {v:g} on sim days {a}..{b} "
              f"({b - a + 1} days, {da} .. {db})")

    print("\n  which PFT owns the surviving cohort (per m2 land):")
    for tag, ip in (("grass", ig), ("moss", im)):
        for v in ("FATES_LEAFC_PF", "FATES_CROWNAREA_PF", "FATES_GPP_PF"):
            a = d[v][:, ip]
            print(f"    {tag:5s} {v:22s} last 10 days: "
                  + " ".join(f"{x:.4e}" for x in a[-10:]))
    for tag, ip in (("grass", ig), ("moss", im)):
        a = d["FATES_CROWNAREA_PF"][:, ip]
        nz = np.nonzero(a > 0)[0]
        print(f"    {tag:5s} FATES_CROWNAREA_PF > 0 on {nz.size} days"
              + (f", last on sim day {nz[-1] + 1} ({dates[nz[-1]]})"
                 if nz.size else ""))
        a = d["FATES_LEAFC_PF"][:, ip]
        nz = np.nonzero(a > 0)[0]
        print(f"    {tag:5s} FATES_LEAFC_PF     > 0 on {nz.size} days"
              + (f", last on sim day {nz[-1] + 1} ({dates[nz[-1]]})"
                 if nz.size else ""))

    print("\n  per-PFT mortality (m-2 yr-1):")
    for tag, ip in (("grass", ig), ("moss", im)):
        for v in ("FATES_MORTALITY_TERMINATION_PF",
                  "FATES_MORTALITY_HYDRAULIC_PF"):
            if v not in d:
                continue
            a = d[v][:, ip]
            print(f"    {tag:5s} {v:34s} mean {np.nanmean(a):.4e} "
                  f"max {np.nanmax(a):.4e} nonzero {int((a != 0).sum())}/{n}")

    rows = []
    for v in ("FATES_GPP_PF", "FATES_LEAFC_PF", "FATES_LAI_PF",
              "FATES_CROWNAREA_PF", "FATES_NOCOMP_PATCHAREA_PF"):
        for tag, ip in (("g12", ig), ("m15", im)):
            rows.append((f"{v}[{tag}]", d[v][:, ip]))
    for v in ("FATES_NCOHORTS", "FATES_GPP", "FATES_NPP", "FATES_AUTORESP",
              "FATES_MAINT_RESP", "FATES_GROWTH_RESP", "FATES_LEAFC",
              "FATES_STOREC", "FATES_FROOTC", "FATES_SAPWOODC",
              "FATES_STRUCTC", "FATES_REPROC", "FATES_SEED_ALLOC",
              "FATES_SEED_BANK", "FATES_SEEDS_IN",
              "FATES_MORTALITY_CFLUX_CANOPY", "FATES_MORTALITY_CFLUX_USTORY",
              "FATES_TRIMMING", "FATES_COLD_STATUS",
              "FATES_CBALANCE_ERROR"):
        if v in d:
            rows.append((v, d[v]))
    width = max(len(k) for k, _ in rows) + 1
    for window in args.days.split(","):
        d1, d2 = (int(x) for x in window.split(":"))
        idx = list(range(max(1, d1), min(n, d2) + 1))
        print(f"\n=== item 4: daily values, sim days {d1}..{d2} ===")
        print(f"{'day':{width}s} " + " ".join(f"{i:12d}" for i in idx))
        print(f"{'date':{width}s} "
              + " ".join(f"{dates[i - 1]:>12s}" for i in idx))
        for k, a in rows:
            print(f"{k:{width}s} "
                  + " ".join(f"{a[i - 1]:12.5e}" for i in idx))

    # ---------------- item 5: carbon balance error ----------------
    print("\n=== item 5: FATES_CBALANCE_ERROR (units kg s-1, NOT per m2) ===")
    cb = d["FATES_CBALANCE_ERROR"]
    mn, mu, mx, last = stats(cb)
    print(f"  min {mn:.5e} mean {mu:.5e} max {mx:.5e} last {last:.5e}")
    print(f"  max |value| {np.nanmax(np.abs(cb)):.5e}; "
          f"days nonzero {int(np.sum(cb != 0))}/{n}; "
          f"all exactly zero: {bool(np.all(cb == 0))}")
    if np.any(cb != 0):
        nz = np.nonzero(cb != 0)[0]
        print("  first 10 nonzero days: "
              + ", ".join(f"{i + 1}({dates[i]})={cb[i]:.3e}" for i in nz[:10]))


if __name__ == "__main__":
    main()
