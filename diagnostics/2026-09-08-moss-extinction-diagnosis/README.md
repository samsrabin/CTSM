# Moss-extinction diagnosis (Task 12 Step 3e)

Throwaway-but-kept analysis scripts from the effort that found out why the moss
cohort was culled on simulation day 402 of the ALP2 nocomp run, and fixed it by
setting `fates_allom_l2fr = 0` for the moss column.

- Handoff brief that set the task up:
  `docs/superpowers/briefs/2026-09-08-moss-extinction-diagnosis.md`
- What was concluded: the plan's Task 12 Step 3e outcome block,
  `docs/superpowers/plans/2026-08-19-moss-grass-pft.md`

Kept because Step 3f and Step 3b work the same tapes and may want them again.
None of them is a curated tool: there is overlap between them, they hard-code
this configuration's PFT indices and patch areas, and only `read_moss_tape.py`
takes an arbitrary variable list.

## Running them

Use `/glade/work/samrabin/conda-envs/ctsm_pylib/bin/python3`. Each takes a
case `run/` directory holding daily `*.clm2.h0a.*.nc` files and has `--help`.
`read_moss_tape.py` needs `xarray` and takes about 45 s to open a 400-file tape;
the other three use `netCDF4` and are quicker.

`diagnose_moss_cull.py` and `verify_moss_l2fr_zero.py` expect the per-PFT
diagnostic fields that the `FatesNvp` testmod adds to `hist_fincl1`; against a
tape without them they will report the fields as absent rather than fail.

## What each one answers

| script | question |
|---|---|
| `read_moss_tape.py` | General-purpose dump of per-PFT and site series for an arbitrary variable list, with a day-range table and CSV export. |
| `grass_health.py` | Is the grass PFT healthy in absolute terms, or is the whole run unproductive? Prints land, patch and crown normalizations side by side. |
| `diagnose_moss_cull.py` | Which day is the moss cohort culled, and by which mortality route? Includes the termination-vs-continuous C-starvation discriminator. |
| `verify_moss_l2fr_zero.py` | Two-run comparison: does moss survive with zero fine-root carbon, and is grass left alone? Takes a new rundir and a baseline rundir. |

## Runs these were used against

All under `/glade/derecho/scratch/samrabin/` and therefore subject to purge:

- `tests_0907-130223de/SMS_Ly2_D_Mmpi-serial.1x1_ALP2.I2000Clm60Fates.derecho_intel.clm-FatesColdNoCompFixedBioGeo--clm-FatesNvp--clm-FatesALP2BareGrassMoss.GC.0907-130223de_int/run`
  — the original 730-day reference, without the per-PFT diagnostics
- `mosscull/` — the instrumented case, 730 days from cold start in ~17 min
- `mosscull_baseline_l2fr0.67/hist` — archived pre-fix baseline, 410 days

## Normalization, which is the easiest thing to get wrong

Every `FATES_*_PF` field is per m2 of **land** area, not per m2 of the PFT's own
patch. Prescribed nocomp areas here are moss 0.5, grass 0.3, bareground 0.2, so
a moss-patch-relative value is the tape value divided by 0.5, and a per-crown
value divides by `FATES_CROWNAREA_PF` instead. Site-level FATES diagnostics are
patch-area weighted sums with bareground contributing zero, so `max()` and
`min()` do not commute with that sum. Moss is PFT 15 and arctic C3 grass PFT 12,
both 1-based.
