#!/usr/bin/env python3
"""Which term zeroes moss's btran in the top-layer-rooting run?

With fates_fnrt_prof_mode = 5 the moss PFT draws soil water from soil layer 1
alone, and its btran comes back exactly zero on a large minority of days, with
FATES's hydraulic-failure mortality firing on some of them.  This script decides,
per day, which term did it, from TSOI, SOILLIQ, SOILICE and SOILPSI in layer 1.

There are three routes to an exactly-zero btran, not two.  Following the CTSM
side of the FATES btran path (CanopyFluxesMod -> SoilMoistStressMod ->
clmfates_interfaceMod wrap_btran -> FATES btran_ed):

  T  Layer 1 is at or below tfrz - 2 K.  FATES's get_active_suction_layers drops
     the layer from root uptake, CLM never even computes a suction for it
     (clmfates_interfaceMod only fills smp_sl on active layers), and rootr(1),
     hence btran, is zero.  This is also the condition under which
     hydraulic-failure mortality is exempt, so a zero btran here costs nothing.

  A  The liquid volume CLM hands FATES is exactly zero.  This is NOT the same as
     SOILLIQ being zero.  calc_effective_soilporosity computes
     eff_porosity = watsat - min(watsat, h2osoi_ice/(denice*dz)) with no floor,
     and calc_volumetric_h2oliq then caps
     vol_liq = min(eff_porosity, h2osoi_liq/(dz*denh2o))
     (both in biogeophys/SoilMoistStressMod.F90).  So once layer-1 ice reaches
     watsat*denice*dz the effective porosity is exactly zero, the liquid volume
     passed in bc_in%h2o_liqvol_sl(1) is exactly zero however much liquid the
     layer actually holds, and the layer is dropped for want of water.

  W  The suction of the liquid that is there has reached the PFT's wilting point,
     fates_nonhydro_smpsc = -255000 mm.  btran_ed clamps
     smp_node = max(smpsc, smp_sl) and then rresis is identically zero.

Only T exempts the mortality, so A and W are the routes that can kill the cohort.

Two things about the diagnostics are worth knowing before reading the output.

1. SOILPSI on the tape is NOT the suction btran sees.  CLM's SOILPSI divides
   liquid volume by watsat (biogeophys/HydrologyNoDrainageMod.F90); the
   root-resistance path divides it by eff_porosity = watsat - vol_ice.  With ice
   present SOILPSI is the more negative of the two, and it is additionally
   clipped to [-15, 0] MPa and set to -15 outright wherever liquid water is zero.
   This script reconstructs the eff_porosity form from SOILLIQ, SOILICE, WATSAT,
   SUCSAT and BSW -- all on the tape -- and tests route W on that, in mm of head,
   the units smpsc is actually compared in.

2. TSOI, SOILLIQ, SOILICE and SOILPSI are daily means (avgflag 'A' with
   hist_nhtfrq -24); FATES_BTRAN_PF is a once-daily instantaneous sample at the
   dynamics call.  A daily mean can straddle a threshold the sampled value never
   crossed, so the attribution is exact only to the extent the three routes
   reproduce the observed zeros -- which the output reports as its own check.

Usage:
    btran_zero_routes.py RUNDIR [--pft 15] [--csv OUT.csv]
"""

import argparse
import os
import sys
from glob import glob

import netCDF4 as nc
import numpy as np

TFRZ = 273.15                  # K, shr_const_tkfrz
FROZEN_LIMIT = TFRZ - 2.0      # K; route T, and the mortality's frozen exemption
SMPSC_MM = -255000.0           # fates_nonhydro_smpsc for this PFT, mm of head
MM_TO_MPA = 9.8e-6             # CLM's conversion factor; smpsc is -2.499 MPa, not -2.55
DENH2O = 1000.0
DENICE = 917.0
SOILPSI_FLOOR = -15.0          # MPa, the clip in HydrologyNoDrainageMod

REQUIRED = ("FATES_BTRAN_PF", "FATES_MORTALITY_HYDRAULIC_PF",
            "FATES_NOCOMP_PATCHAREA_PF", "TSOI", "SOILLIQ", "SOILICE", "SOILPSI")
PROPS = ("WATSAT", "SUCSAT", "BSW", "DZSOI")


def read_run(rundir, ipft):
    """Per-day layer-1 and per-PFT series, plus layer-1 soil properties."""
    paths = sorted(glob(os.path.join(rundir, "*.clm2.h0a.*.nc")))
    if not paths:
        sys.exit(f"no *.clm2.h0a.*.nc tapes in {rundir}")

    with nc.Dataset(paths[0]) as d:
        missing = [f for f in REQUIRED if f not in d.variables]
        if missing:
            sys.exit(f"tape {paths[0]} lacks required fields: {missing}")
        # CLM writes the time-invariant soil properties to the first tape only.
        missing = [f for f in PROPS if f not in d.variables]
        if missing:
            sys.exit(f"first tape {paths[0]} lacks soil properties: {missing}")
        props = {n: float(d.variables[n][0, 0]) for n in PROPS}

    n = len(paths)
    keys = ("mcdate", "btran", "mort_land", "patcharea", "tsoi1",
            "soilliq1", "soilice1", "soilpsi1", "fwet_soil", "nplant")
    out = {k: np.full(n, np.nan) for k in keys}
    for i, path in enumerate(paths):
        with nc.Dataset(path) as d:
            v = d.variables
            out["mcdate"][i] = float(v["mcdate"][0])
            out["btran"][i] = float(v["FATES_BTRAN_PF"][0, ipft, 0])
            out["mort_land"][i] = float(v["FATES_MORTALITY_HYDRAULIC_PF"][0, ipft, 0])
            out["patcharea"][i] = float(v["FATES_NOCOMP_PATCHAREA_PF"][0, ipft, 0])
            out["tsoi1"][i] = float(v["TSOI"][0, 0, 0])
            out["soilliq1"][i] = float(v["SOILLIQ"][0, 0, 0])
            out["soilice1"][i] = float(v["SOILICE"][0, 0, 0])
            out["soilpsi1"][i] = float(v["SOILPSI"][0, 0, 0])
            if "FATES_MOSS_FWET_SOIL" in v:
                out["fwet_soil"][i] = float(v["FATES_MOSS_FWET_SOIL"][0, 0])
            if "FATES_NPLANT_PF" in v:
                out["nplant"][i] = float(v["FATES_NPLANT_PF"][0, ipft, 0])
    out["paths"] = paths
    out["props"] = props
    return out


def fates_layer1_water(liq, ice, props):
    """Reproduce what CLM hands FATES for layer 1, and the suction it computes.

    Mirrors calc_effective_soilporosity and calc_volumetric_h2oliq in
    biogeophys/SoilMoistStressMod.F90, then the s_node/soil_suction step in
    clmfates_interfaceMod wrap_btran.  Returns (eff_por, vol_liq, smp_mm), with
    smp_mm NaN where the effective porosity is zero -- exactly the case in which
    CLM computes no suction at all.
    """
    dz, watsat = props["DZSOI"], props["WATSAT"]
    vol_ice = np.minimum(watsat, ice / (DENICE * dz))
    eff_por = watsat - vol_ice
    vol_liq = np.minimum(eff_por, liq / (dz * DENH2O))
    with np.errstate(divide="ignore", invalid="ignore"):
        s_node = np.where(eff_por > 0.0,
                          np.maximum(vol_liq / np.where(eff_por > 0.0, eff_por, 1.0), 0.01),
                          np.nan)
        smp_mm = -props["SUCSAT"] * s_node ** (-props["BSW"])
    return eff_por, vol_liq, smp_mm


def block(title, lines):
    return ["=" * 74, title, "=" * 74] + lines + [""]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("rundir")
    ap.add_argument("--pft", type=int, default=15,
                    help="1-based FATES PFT index (default 15, moss)")
    ap.add_argument("--csv", default=None, help="write the per-day table here")
    args = ap.parse_args(argv)

    ipft = args.pft - 1
    r = read_run(args.rundir, ipft)
    props = r["props"]
    nday = len(r["paths"])
    dz, watsat = props["DZSOI"], props["WATSAT"]

    liq, ice, tsoi = r["soilliq1"], r["soilice1"], r["tsoi1"]
    eff_por, vol_liq, smp_mm = fates_layer1_water(liq, ice, props)
    ice_lock_kgm2 = watsat * DENICE * dz          # ice at which eff_porosity hits zero
    liq_frac = liq / (liq + ice)
    sat_frac = (liq / (dz * DENH2O) + ice / (DENICE * dz)) / watsat

    btran0 = r["btran"] == 0.0
    mort = r["mort_land"] > 0.0
    with np.errstate(invalid="ignore", divide="ignore"):
        mort_pft = np.where(r["patcharea"] > 0, r["mort_land"] / r["patcharea"], np.nan)

    route_T = tsoi <= FROZEN_LIMIT
    route_A = vol_liq <= 0.0
    route_W = np.where(np.isnan(smp_mm), False, smp_mm <= SMPSC_MM)
    any_route = route_T | route_A | route_W

    L = []
    L += [f"run directory : {args.rundir}",
          f"days on tape  : {nday}",
          f"PFT           : {args.pft} (1-based), fates_levpft index {ipft}",
          f"layer 1       : dz={dz:.4f} m, watsat={watsat:.4f}, "
          f"sucsat={props['SUCSAT']:.3f} mm, bsw={props['BSW']:.4f}",
          f"                ice at which eff_porosity reaches zero: "
          f"{ice_lock_kgm2:.4f} kg/m2",
          f"patch area    : {np.nanmin(r['patcharea']):.4f} to "
          f"{np.nanmax(r['patcharea']):.4f} m2/m2 land",
          f"wilting point : smpsc = {SMPSC_MM:.0f} mm = "
          f"{SMPSC_MM * MM_TO_MPA:.4f} MPa (CLM's 9.8e-6 factor)",
          ""]

    L += [f"days with FATES_BTRAN_PF exactly 0         : {int(btran0.sum())}",
          f"days with FATES_MORTALITY_HYDRAULIC_PF > 0 : {int(mort.sum())}",
          f"  of those, btran also exactly 0           : {int((mort & btran0).sum())}",
          f"  of those, btran nonzero                  : {int((mort & ~btran0).sum())}"]
    if mort.any():
        L.append(f"  per-PFT hydraulic mortality rate         : "
                 f"{np.nanmin(mort_pft[mort]):.6g} to {np.nanmax(mort_pft[mort]):.6g} /yr")
    L.append("")

    # --- the three questions the four new fields were added to answer ---
    for label, sel in (("btran == 0 days", btran0), ("hydraulic-mortality days", mort)):
        n = int(sel.sum())
        if not n:
            L += block(f"{label}  (n = 0)", ["  none"])
            continue
        b = []
        b += ["  layer-1 TSOI (daily mean):",
              f"    <= -2 C ({FROZEN_LIMIT:.2f} K), mortality-exempt : {int((tsoi[sel] <= FROZEN_LIMIT).sum()):4d}",
              f"    in (-2 C, 0 C), mortality NOT exempt            : "
              f"{int(((tsoi[sel] > FROZEN_LIMIT) & (tsoi[sel] < TFRZ)).sum()):4d}",
              f"    >= 0 C ({TFRZ:.2f} K)                             : {int((tsoi[sel] >= TFRZ).sum()):4d}",
              f"    range {tsoi[sel].min():.3f} to {tsoi[sel].max():.3f} K "
              f"({tsoi[sel].min() - TFRZ:+.3f} to {tsoi[sel].max() - TFRZ:+.3f} C)",
              "",
              "  layer-1 water (daily mean):",
              f"    SOILLIQ                       : {liq[sel].min():.6g} to {liq[sel].max():.6g} kg/m2",
              f"    SOILICE                       : {ice[sel].min():.6g} to {ice[sel].max():.6g} kg/m2",
              f"    days with SOILLIQ exactly 0   : {int((liq[sel] == 0).sum())}",
              f"    ice as fraction of layer water: {1 - liq_frac[sel].max():.6g} to "
              f"{1 - liq_frac[sel].min():.6g} (median {1 - np.median(liq_frac[sel]):.6g})",
              f"    total water / saturation      : {sat_frac[sel].min():.4f} to {sat_frac[sel].max():.4f}",
              f"    days with SOILICE >= {ice_lock_kgm2:.3f} (eff_porosity zero) : "
              f"{int((ice[sel] >= ice_lock_kgm2).sum())}",
              "",
              "  layer-1 matric potential:",
              f"    SOILPSI on tape                        : {r['soilpsi1'][sel].min():.6g} to "
              f"{r['soilpsi1'][sel].max():.6g} MPa",
              f"    days SOILPSI <= smpsc ({SMPSC_MM * MM_TO_MPA:+.3f} MPa) : "
              f"{int((r['soilpsi1'][sel] <= SMPSC_MM * MM_TO_MPA).sum())}",
              f"    days SOILPSI <= -2.55 MPa (round form) : "
              f"{int((r['soilpsi1'][sel] <= -2.55).sum())}",
              f"    days SOILPSI at the -15 MPa clip       : "
              f"{int((r['soilpsi1'][sel] <= SOILPSI_FLOOR + 1e-9).sum())}",
              f"    suction btran sees (eff_porosity form) : "
              f"{np.nanmin(smp_mm[sel]):.6g} to {np.nanmax(smp_mm[sel]):.6g} mm "
              f"({int(np.isnan(smp_mm[sel]).sum())} day(s) undefined, eff_porosity zero)",
              f"    days that suction <= smpsc             : {int(route_W[sel].sum())}"]
        L += block(f"{label}  (n = {n})", b)

    # --- route attribution ---
    b = []
    b.append("  Coverage check: do the three routes reproduce the observed zeros?")
    for nm, pred in (("T  (TSOI <= tfrz-2)", route_T),
                     ("A  (vol_liq handed to FATES == 0)", route_A),
                     ("W  (suction <= smpsc)", route_W),
                     ("T or A or W", any_route)):
        tp = int((pred & btran0).sum())
        fp = int((pred & ~btran0).sum())
        fn = int((~pred & btran0).sum())
        b.append(f"    {nm:34s} predicts {tp:4d} of the zeros, "
                 f"{fp:3d} false positive(s), {fn:3d} unexplained")
    b.append("")
    for label, sel in (("btran == 0 days", btran0), ("hydraulic-mortality days", mort)):
        n = int(sel.sum())
        if not n:
            continue
        b.append(f"  {label} (n={n}) by route:")
        for nm, m in (("T only", route_T & ~route_A & ~route_W),
                      ("A only", route_A & ~route_T & ~route_W),
                      ("W only", route_W & ~route_T & ~route_A),
                      ("T and A", route_T & route_A & ~route_W),
                      ("T and W", route_T & route_W & ~route_A),
                      ("A and W", route_A & route_W & ~route_T),
                      ("all three", route_T & route_A & route_W),
                      ("NONE of the three", ~any_route)):
            b.append(f"    {nm:20s} {int((m & sel).sum()):4d}")
        b.append(f"    (totals: T {int((route_T & sel).sum())}, "
                 f"A {int((route_A & sel).sum())}, W {int((route_W & sel).sum())})")
        b.append("")
    L += block("ROUTE ATTRIBUTION", b)

    # --- days the three routes do not account for ---
    odd = (btran0 & ~any_route) | (~btran0 & any_route)
    b = [f"  {int(odd.sum())} day(s) of {nday}. Each is a candidate daily-mean artifact:",
         "  the four soil fields are daily means, FATES_BTRAN_PF an instantaneous sample.",
         ""]
    if odd.any():
        b.append("   day    mcdate   btran     mort    TSOI(C)  SOILLIQ  SOILICE  eff_por"
                 "   vol_liq      smp(mm)  T A W")
        for i in np.where(odd)[0]:
            b.append(f"  {i+1:4d} {int(r['mcdate'][i]):9d} {r['btran'][i]:8.5f} "
                     f"{r['mort_land'][i]:8.5f} {tsoi[i]-TFRZ:+8.3f} {liq[i]:8.4f} "
                     f"{ice[i]:8.4f} {eff_por[i]:8.5f} {vol_liq[i]:9.6f} "
                     f"{smp_mm[i]:12.1f}  {int(route_T[i])} {int(route_A[i])} {int(route_W[i])}")
    L += block("DAYS NOT ACCOUNTED FOR", b)

    # --- the mortality days, day by day ---
    b = ["   day    mcdate  mort/m2land  mort/PFT   TSOI(C)  SOILLIQ  SOILICE"
         "  eff_por     smp(mm)  route"]
    for i in np.where(mort)[0]:
        rt = "".join(c for c, m in (("T", route_T[i]), ("A", route_A[i]), ("W", route_W[i])) if m) or "-"
        b.append(f"  {i+1:4d} {int(r['mcdate'][i]):9d} {r['mort_land'][i]:11.5f} "
                 f"{mort_pft[i]:9.5f} {tsoi[i]-TFRZ:+8.3f} {liq[i]:8.4f} {ice[i]:8.4f} "
                 f"{eff_por[i]:8.5f} {smp_mm[i]:11.1f}  {rt}")
    L += block("HYDRAULIC-MORTALITY DAYS", b)

    print("\n".join(L))

    if args.csv:
        hdr = ("mcdate,day,btran,mort_hyd_land,mort_hyd_pft,nplant_pf,tsoi1_K,tsoi1_C,"
               "soilliq1,soilice1,ice_frac,sat_frac,soilpsi1_MPa,eff_porosity,vol_liq,"
               "smp_mm,route_T,route_A,route_W,fwet_soil")
        with open(args.csv, "w") as fh:
            fh.write(hdr + "\n")
            for i in range(nday):
                fh.write(
                    f"{int(r['mcdate'][i])},{i+1},{r['btran'][i]:.17g},"
                    f"{r['mort_land'][i]:.17g},{mort_pft[i]:.17g},{r['nplant'][i]:.17g},"
                    f"{tsoi[i]:.17g},{tsoi[i]-TFRZ:.17g},{liq[i]:.17g},{ice[i]:.17g},"
                    f"{1-liq_frac[i]:.17g},{sat_frac[i]:.17g},{r['soilpsi1'][i]:.17g},"
                    f"{eff_por[i]:.17g},{vol_liq[i]:.17g},{smp_mm[i]:.17g},"
                    f"{int(route_T[i])},{int(route_A[i])},{int(route_W[i])},"
                    f"{r['fwet_soil'][i]:.17g}\n")
        print(f"wrote {args.csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
