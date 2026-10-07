# Moss CO2 film and fuel moisture on the total-water proxy

One script, written to check the system tests after Task C of
`docs/superpowers/plans/2026-10-02-moss-fwet-subdaily.md`. That task moved the
moss CO2 water film and both moss fuel classes' moisture from
`FATES_MOSS_FWET_LIQ` (liquid soil water) to `FATES_MOSS_FWET_TOT` (liquid plus
ice). Photosynthetic capacity and respiration stay on the liquid proxy.

## Running it

Use `/glade/work/samrabin/conda-envs/ctsm_pylib/bin/python3`. It needs
`netCDF4` and `numpy`.

```
check_total_proxy_switch.py NEW_RUNDIR OLD_RUNDIR [--pft-moss N]
```

Both arguments are case `run/` directories from runs on the same forcing:
NEW_RUNDIR after the switch, OLD_RUNDIR before it. Both need the daily
`*.clm2.h0a.*.nc` files, and NEW_RUNDIR also needs the 12-hourly
`*.clm2.h1a.*.nc` tape the `FatesNvp` testmod adds. The moss PFT is read from
the parameter file named in NEW_RUNDIR's `lnd_in`.

Exit codes:
- 0: something was judged and passed.
- 1: a check failed.
- 2: nothing could be judged. This is normal for a FATES-SP run in which moss
  GPP never changed.
- 3: the input could not be interpreted.

## What it checks

1. **The `h1` tape** (INFO): two records per day, with equal halves for every
   moss wetness field.
2. **Moss GPP timing:** the first day moss GPP differs between the runs must
   follow a day on which the total proxy exceeds the liquid one.
3. **Moss fuel moisture:** while the two runs' liquid proxies agree, moss fuel
   moisture is higher where total exceeds liquid and unchanged where the two
   are equal. Skipped in runs without fire.

The script's docstring explains each check's reasoning and what it cannot
establish.

## Traps in reading the output

- **The `h1` check cannot show how often the proxies are refreshed.** The
  wetness fields are in FATES's daily history group, so the tape holds one
  value per day whatever the patch variables do within the day.
- **`FATES_GPP_PF` on the daily tape lags the proxies by a day.** It comes from
  `gpp_acc_hold`, the previous day's accumulated GPP, so GPP on day d is paired
  with the proxies of day d-1.
- **GPP direction is reported, not judged.** A thicker film usually lowers GPP.
  But where moss is net-respiring it raises ci and so raises gross GPP, and the
  film factor's floors can leave GPP unchanged. Check 2 therefore cannot tell a
  film switch that never happened from one that never mattered.
