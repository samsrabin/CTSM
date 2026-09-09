# Moss top-layer rooting: which term zeroes btran

Analysis scripts from the effort that settled, by measurement rather than
inference, why the moss PFT's `btran` comes back exactly zero on 202 of the 730
days of the ALP2 nocomp run once its rooting profile is
`fates_fnrt_prof_mode = 5` (whole profile in soil layer 1), and why FATES's
hydraulic-failure mortality fires on 37 of those days.

The measurement needed four CLM fields the tape did not carry: `TSOI`,
`SOILLIQ`, `SOILICE` and `SOILPSI`, added to the `FatesNvp` testmod's
`hist_fincl1`, where the comment block explaining them lives.

## Running them

Use `/glade/work/samrabin/conda-envs/ctsm_pylib/bin/python3`. Both take a case
`run/` directory holding daily `*.clm2.h0a.*.nc` files, use `netCDF4` and
`numpy` only, and have `--help`.

## What each one answers

| script | question |
|---|---|
| `compare_runs_bfb.py` | Did adding the four history fields perturb the physics? Compares two run directories field-by-field, day-by-day, requiring exact equality (NaN counted equal to NaN) on every shared field. Lists the fields present in only one run rather than failing on them. |
| `btran_zero_routes.py` | On the days moss's `btran` is exactly zero, and on the subset where hydraulic mortality fires, which term did it? Attributes each day to one or more of the three routes below, reports layer-1 `TSOI` against the -2 C mortality exemption, and writes a per-day CSV with `--csv`. |

## The three routes to an exactly-zero btran

Following the CTSM side of the FATES btran path — `CanopyFluxesMod` →
`SoilMoistStressMod` → `clmfates_interfaceMod::wrap_btran` → FATES `btran_ed`.
Only the first also exempts hydraulic-failure mortality, so the other two are
the ones that can kill the cohort.

- **T** — layer 1 at or below `tfrz - 2` K. FATES's `get_active_suction_layers`
  drops the layer from root uptake and CLM never computes a suction for it at
  all (`clmfates_interfaceMod` fills `smp_sl` only on active layers), so
  `rootr(1)`, and hence `btran`, is zero.
- **A** — the liquid *volume* CLM hands FATES goes to zero, which is **not** the
  same as `SOILLIQ` going to zero. `calc_effective_soilporosity` forms
  `eff_porosity = watsat - min(watsat, h2osoi_ice/(denice*dz))` with no floor,
  and `calc_volumetric_h2oliq` then caps
  `vol_liq = min(eff_porosity, h2osoi_liq/(dz*denh2o))` — both in
  `biogeophys/SoilMoistStressMod.F90`. So once layer-1 ice reaches
  `watsat*denice*dz` (14.86 kg/m2 here), `bc_in%h2o_liqvol_sl(1)` is exactly
  zero however much liquid the layer holds, and the layer is dropped for want of
  water.
- **W** — the suction of the liquid that *is* there reaches
  `fates_nonhydro_smpsc = -255000` mm, where `btran_ed`'s `max(smpsc, smp)`
  clamp makes the root resistance identically zero.

`btran_zero_routes.py` prints a coverage check — how many of the observed zeros
the three routes reproduce, and how many days they contradict — so the
attribution is not taken on faith.

## Two traps in reading the output

**`SOILPSI` is not the suction `btran` sees, and must not be compared with
`smpsc` directly.** CLM's `SOILPSI` divides layer liquid volume by `watsat`
(`biogeophys/HydrologyNoDrainageMod.F90`); the root-resistance path divides it
by `eff_porosity`. Wherever there is ice, `SOILPSI` is the more negative of the
two — in this run 27 days have `SOILPSI` at or past `smpsc`, 22 of them pinned
at its `-15` MPa clip, while `btran` on those days runs up to 0.34. `SOILPSI` is additionally clipped to `[-15, 0]` MPa
and assigned `-15` outright wherever layer liquid water is zero, so `-15` means
"no liquid", not a measured potential. Reconstructing the form `btran` uses
needs `WATSAT`, `SUCSAT` and `BSW`; CLM writes all three, and `DZSOI`, to the
**first** history file of a run only, which is where the script reads them.

**Cadence mismatch.** `TSOI`, `SOILLIQ`, `SOILICE` and `SOILPSI` are daily means
(`avgflag='A'` with `hist_nhtfrq = -24`); `FATES_BTRAN_PF` is a once-daily
instantaneous sample at the dynamics call. A daily mean can straddle a threshold
the sampled value never crossed, which is what the handful of days the three
routes do not account for look like.

## Unit conversion for the wilting point

`fates_nonhydro_smpsc = -255000` mm of head, and `btran_ed` compares in mm, so
no conversion is involved in the model. For reading `SOILPSI`, CLM's own
mm-to-MPa factor is `9.8e-6` (`HydrologyNoDrainageMod.F90`), giving
**-2.499 MPa**; the round figure -2.55 MPa in circulation comes from a `1e-5`
factor. The script reports both, and they give the same verdict here.

## Normalization

Every `FATES_*_PF` field is per m2 of **land** area, not per m2 of the PFT's own
patch. `FATES_NOCOMP_PATCHAREA_PF` on the same tape reports the patch area
(0.5 for moss in this configuration, read from the tape rather than assumed), so
a PFT-relative mortality rate is `FATES_MORTALITY_HYDRAULIC_PF` divided by it.
Moss is PFT 15, arctic C3 grass PFT 12, both 1-based.

`SOILLIQ` and `SOILICE` are on `levsoi`, `TSOI` and `SOILPSI` on `levgrnd`;
`levsoi` is the first 20 of the 25 `levgrnd` layers, so index 0 is the same layer
in all four.

## Runs these were used against

Both under `/glade/derecho/scratch/samrabin/` and therefore subject to purge:

- `mosstoplayer/run` — the 730-day run with the four soil fields added
- `mosstoplayer_run_baseline_20260908/` — the 730 daily tapes from the same case
  *before* the fields were added, copied out of `mosstoplayer/run` so the re-run
  could not overwrite them, plus both runs' `lnd_in` and `lnd.log`. This is the
  `OLD_RUNDIR` argument to `compare_runs_bfb.py`.
