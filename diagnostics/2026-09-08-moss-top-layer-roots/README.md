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

Use `/glade/work/samrabin/conda-envs/ctsm_pylib/bin/python3`. All three take
case `run/` directories holding daily `*.clm2.h0a.*.nc` files —
`compare_runs_bfb.py` and `compare_pft_timeseries.py` take two, `NEW_RUNDIR`
then `OLD_RUNDIR`, and `btran_zero_routes.py` one — use `netCDF4` and `numpy`
only, and have `--help`.

## What each one answers

| script | question |
|---|---|
| `compare_runs_bfb.py` | Did adding the four history fields perturb the physics? Compares two run directories field-by-field, day-by-day, requiring exact equality (NaN counted equal to NaN) on every shared field. Lists the fields present in only one run rather than failing on them. |
| `btran_zero_routes.py` | On the days moss's `btran` is exactly zero, and on the subset where hydraulic mortality fires, which term did it? Attributes each day to one or more of the three routes below, reports layer-1 `TSOI` against the -2 C mortality exemption, and writes a per-day CSV with `--csv`. |
| `compare_pft_timeseries.py` | When two runs are *expected* to differ, what moved, for which PFT, and by how much? Per-PFT, per-field summary over every shared day: range and mean in each run, how many days differ, the largest difference and where, and the nonzero-day counts. Defaults to moss (PFT 15) and arctic C3 grass (PFT 12) on the four fields the hmort-off comparison needed; `--pft`, `--fields`, `--normalize` and `--csv` generalize it. |

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

The `FATES_MOSS_FWET*` site means are diluted too, but not by moss's own patch
area. They accumulate area-weighted over **every** patch, and the proxy is
diagnosed only on vegetated ones (`EDMainMod`, where the `hlm_use_moss` loop
skips `nocomp_bareground`), so bareground contributes a hard 0 to the mean. The
soil ingredient is a soil-column quantity and so is identical on the moss and
grass patches, which makes `FATES_MOSS_FWET_SOIL` exactly the **vegetated** area
fraction — 0.8 here, moss 0.5 plus grass 0.3 — times the moss patch's own
saturation: the field's run minimum of 0.3194 is a patch value of 0.3993.
Divide by the sum of `FATES_NOCOMP_PATCHAREA_PF` over the PFTs present before
comparing the field with anything expressed as patch saturation, such as the 0.6
full-capacity threshold. `FATES_MOSS_FWET` and `FATES_MOSS_WETNESS_SCALER` also
carry the per-patch canopy ingredient, so that clean rescaling holds for them
only while the soil ingredient dominates — which it does on every day of this
run, CTSM capping the canopy wetted fraction at 0.05.

`SOILLIQ` and `SOILICE` are on `levsoi`, `TSOI` and `SOILPSI` on `levgrnd`;
`levsoi` is the first 20 of the 25 `levgrnd` layers, so index 0 is the same layer
in all four.

## Runs these were used against

All three under `/glade/derecho/scratch/samrabin/` and therefore subject to
purge:

- `mosstoplayer/run` — the current contents: the 730-day run with moss's
  `fates_mort_scalar_hydrfailure` zeroed. This is the `NEW_RUNDIR` argument to
  `compare_pft_timeseries.py`.
- `mosstoplayer_run_baseline_20260908/` — the 730 daily tapes from the same case
  *before* the fields were added, copied out of `mosstoplayer/run` so the re-run
  could not overwrite them, plus both runs' `lnd_in` and `lnd.log`. This is the
  `OLD_RUNDIR` argument to `compare_runs_bfb.py`.
- `mosstoplayer_run_hmort_on_20260922/` — the 730 daily tapes from the same case
  with the four soil fields present and moss's hydraulic-failure mortality still
  at its grass-inherited 0.6/yr, copied out for the same reason, plus that run's
  `lnd_in` (as `lnd_in.hmort_on`), `lnd.log` and `cesm.log`. This is the
  `OLD_RUNDIR` argument to `compare_pft_timeseries.py`. Nothing but the
  parameter file differs between it and the current `mosstoplayer/run`: same
  executable, same namelist, same cold start.

**`compare_runs_bfb.py`'s `NEW_RUNDIR` is no longer `mosstoplayer/run`.** The
fields-vs-no-fields check was run while `mosstoplayer/run` still held the
hmort-on run; the hmort-off re-run has since overwritten that directory. Those
tapes are `mosstoplayer_run_hmort_on_20260922/`, so the check as documented is
now

```
compare_runs_bfb.py mosstoplayer_run_hmort_on_20260922 mosstoplayer_run_baseline_20260908
```

Pointed at `mosstoplayer/run` it would instead compare a parameter-changed run
against the pre-fields baseline, and report that adding history fields perturbed
the physics.
