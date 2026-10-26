# Moss canopy ingredients as filled fractions of canopy storage

One script, written to check the system tests after Task 1 Step 3 of `docs/superpowers/plans/2026-10-23-moss-canopy-storage-fraction.md`, which made the moss wetness proxies' canopy ingredients the filled fraction of canopy storage instead of CTSM's capped wetted fraction. It checks the Step 5 assertions about `FATES_MOSS_FWET_CANOPY_LIQ` and `FATES_MOSS_FWET_CANOPY_TOT`.

## Running it

Use `/glade/work/samrabin/conda-envs/ctsm_pylib/bin/python3`. It needs `netCDF4`, `numpy` and `cftime`, and imports helpers from `../2026-10-07-moss-total-proxy-switch/checks.py`.

```
check_canopy_storage_fraction.py RUNDIR [RUNDIR ...]
```

Each RUNDIR is a case `run/` directory holding the one-record daily `*.clm2.h0a.*.nc` tapes. Intended for the two moss ALP2 tests that compose `FatesALP2BareGrassMoss`: the nocomp one and the FATES-SP one.

Exit codes: 0 if everything judged passed, 1 if anything failed, 2 if something could not be judged.

## What it checks, and what it cannot

1. Each canopy ingredient exceeds 0.05 (site units) on some day.
2. Neither exceeds 1.
3. LIQ ≤ TOT on every day, exactly.
4. On days when every vegetated patch is snow-buried, TOT equals the non-bareground area fraction and LIQ is exactly 0. Buried days are identified with `FATES_SNOW_BURIED_AREA`, which the `FatesNvp` testmod requests. Tapes written before that field existed get NO VERDICT on this check, and the other three still run.
