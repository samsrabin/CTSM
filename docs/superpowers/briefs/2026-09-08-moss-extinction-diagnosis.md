# Brief: why the moss cohort is culled on day 402

**Written 2026-09-08 for a fresh session.** Branch `adrianna-moss-grass-pft` in
`/glade/work/samrabin/ctsm_adrianna-moss-grass-pft`. This is plan Step 3e
(`docs/superpowers/plans/2026-08-19-moss-grass-pft.md`, search "Step 3e"). Read the spec at
`docs/superpowers/specs/2026-08-19-moss-grass-pft-design.md` for what moss is supposed to be.

## The task

The branch adds moss as a fifteenth, non-woody, non-vascular FATES PFT. In the ALP2 nocomp
runs it does not survive: the moss cohort declines from the cold-start recruit on every
single day, and on day 402 it is removed outright while still holding 44% of its peak leaf
carbon. Nothing recruits behind it. Find out what removes it and why, and fix it. This is
the central science question the branch faces — a moss PFT that cannot hold the patch it
is handed does not yet have a fuel-loading or fuel-moisture problem.

**Ordering constraint, load-bearing:** this runs before plan Steps 3b, 3c and 3d. Each of
those tunes a parameter against diagnosed moss — the wetness window against moss GPP,
height against `FATES_MOSS_HEIGHT`, leaf allometry against moss LAI. Run them first and
every number they read comes from a single starving recruit or from days with no moss at
all, so the tuning would be against an artifact and would have to be redone. Step 3a (the
sub-daily wetness signal) is independent.

## Reference run

```
/glade/derecho/scratch/samrabin/tests_0907-130223de/SMS_Ly2_D_Mmpi-serial.1x1_ALP2.I2000Clm60Fates.derecho_intel.clm-FatesColdNoCompFixedBioGeo--clm-FatesNvp--clm-FatesALP2BareGrassMoss.GC.0907-130223de_int/run
```

730 daily files, 2000-01-02 to 2002-01-01, single gridcell, `DEBUG=TRUE`, `mpi-serial`.
Moss is PFT 15, grass PFT 12 (1-based). Prescribed nocomp cover: moss 0.5, grass 0.3,
bareground 0.2. The gnu twin at the same path behaves identically — the cull is on the
same day under both compilers, so this is not a numerics accident.

Everything below came from `verify_moss_history.py` in the repo root (run it with
`/glade/work/samrabin/conda-envs/ctsm_pylib/bin/python3`, pass the `run/` directory, and
read its `--help`) plus direct reads of the tape.

## What the tape already establishes

**Moss never grows at all.** `FATES_LEAFC_PF` peaks on day 1 at 2.87e-08 kg m-2 and falls
on 400 of the 400 day-to-day steps it exists for — strictly monotonic, e-folding 489 days
(R² 0.99). `FATES_MOSS_HEIGHT` reads exactly 0.02 m — `fates_recruit_height_min` — on every
day moss is present, so the cohort never leaves recruit size. Moss crown area tops out at
1.20e-04 m2 m-2 against a prescribed patch of 0.5, i.e. moss fills **0.024% of the patch it
was given**.

**The removal is discontinuous.** Day 401 (2001-02-06) holds 1.269e-08 kg m-2, 44.2% of
peak. Day 402 (2001-02-07) reads exactly zero. That final step is 324x the median daily
step. `FATES_NCOHORTS` goes 2 → 1 on the same day and stays at 1 for the remaining 329
days. This is a cohort being taken out at substantial standing biomass, not a decay tail
reaching a floor — do not reason about it as starvation-to-zero.

**The moss patch survives the cohort.** `FATES_NOCOMP_PATCHAREA_PF` for moss stays at 0.5
for all 329 remaining days. The patch is there and empty, so the failure to come back is a
recruitment failure, not patch loss.

**No seed, ever.** Site-level `FATES_SEED_BANK` and `FATES_SEEDS_IN` are identically zero on
all 730 days — for both PFTs, not just moss. Spec §3's reproduction fix (drop the dbh
reproduction threshold so moss sits on the mature branch and collects `seed_alloc_mature`)
is the thing to confirm is actually firing.

**Moss carbon uptake is negligible.** `FATES_GPP_PF` for moss averages 1.87e-16 and peaks at
2.25e-15 kg m-2 s-1, positive on only 161 of 730 days; grass peaks 5.4e+04x higher. Binned
by wetness, moss GPP is largest in the *driest* decile (`FATES_MOSS_FWET` 0.319–0.352) and
falls monotonically as the site gets wetter — corr(fwet, GPP) = -0.384. Site `FATES_NPP` is
negative every day of the run.

## The finding that most narrows it

**`FATES_MORTALITY_TERMINATION_PF` reading zero is not evidence that no termination
happened — that variable is defined to exclude carbon-starvation termination, and
carbon-starvation termination is almost certainly what happened.**

Three facts:

1. `FATES_MORTALITY_TERMINATION_SZPF`, which the `_PF` variant on this branch sums, is
   accumulated as `sum(term_nindivs_*(i_term_mort_type_canlev:n_term_mort_types, ...))`
   (`src/fates/main/FatesHistoryInterfaceMod.F90:4374-4377`). The type constants are
   `cstarv = 1`, `canlev = 2`, `numdens = 3` (`src/fates/main/FatesConstantsMod.F90:379-381`),
   so the sum starts at index 2 and drops C-starvation. Its own long name says so:
   "termination mortality (excluding C-starvation)". The excluded part is routed into the
   C-starvation diagnostics instead (`FatesHistoryInterfaceMod.F90:4385-4393`).
2. The other two types *are* included, and the variable is exactly zero on day 402. So the
   removal was neither the number-density route nor the canopy-layer route.
3. `FATES_MORTALITY_CFLUX_CANOPY` sits at a 4.44e-13 kg m-2 s-1 background and spikes to
   7.077e-13 on day 402 alone, returning to 4.439e-13 the next day. The excess integrates to
   2.28e-08 kg m-2 over the day, against moss leaf carbon of 1.27e-08 kg m-2 the day before —
   the whole cohort's mass, dumped to litter. `term_carbonflux_canopy` is written in exactly
   one place, inside `terminate_cohort` (`src/fates/biogeochem/EDCohortDynamicsMod.F90:468`).

So the cohort went through `terminate_cohorts` (`EDCohortDynamicsMod.F90:283`) at level 2
with `termination_type = i_term_mort_type_cstarv`, which means one of these fired at
`:367-375`:

```fortran
if ( ( sapw_c+leaf_c+fnrt_c ) < 1e-10_r8  .or.  store_c  < 1e-10_r8) then
```

Both are **absolute per-plant carbon thresholds in kg**, with no scaling by plant size.
Moss is a physically tiny plant. Worth holding as a live hypothesis alongside "moss is
starving": a threshold chosen for trees may simply be too large for a moss individual, in
which case the fix is not to make moss grow but to make the criterion size-relative. Check
which of the two disjuncts fires before choosing. For reference the neighbouring
number-density thresholds are `min_npm2 = 1e-7` and `min_n_safemath = 1e-12`
(`src/fates/main/EDTypesMod.F90:120,128`).

Confirm the route, do not assume it. The decisive per-PFT instrument already exists:
`FATES_MORTALITY_CSTARV_CFLUX_PF` carries continuous plus termination C-starvation
(`FatesHistoryInterfaceMod.F90:3954, :4360`) while `FATES_MORT_CSTARV_CONT_CFLUX_PF`
carries the continuous part alone (`:3958`). **Their difference isolates the termination
event, per PFT.** Neither is on this tape.

## Instrumentation: a namelist change, not a code change

`clm/Fates` sets `hist_empty_htapes = .true.`
(`cime_config/testdefs/testmods_dirs/clm/Fates/user_nl_clm:4`), and this test reaches it via
`FatesColdNoCompFixedBioGeo → FatesColdNoComp → FatesCold, Fates`. So `use_default='active'`
buys nothing here: an explicit `hist_fincl1 += 'NAME'` is the only route to the tape. The
branch's own additions go in
`cime_config/testdefs/testmods_dirs/clm/FatesNvp/user_nl_clm`.

All of these already exist in FATES and are absent from this tape. Adding them needs no
recompile — change `user_nl_clm` and resubmit:

- `FATES_NPLANT_PF` — the number density the termination thresholds test
- `FATES_STOREC_PF`, `FATES_VEGC_PF` — `store_c` is one of the two C-starvation disjuncts
- `FATES_NPP_PF` — is moss net-negative from day 1, and which term dominates
- `FATES_MORTALITY_CSTARV_CFLUX_PF`, `FATES_MORT_CSTARV_CONT_CFLUX_PF` — the discriminator above
- `FATES_MORTALITY_PF`, `FATES_MORTALITY_CFLUX_PF`
- `FATES_SEED_BANK_PF`, `FATES_SEEDS_IN_PF`, `FATES_SEEDLING_POOL_PF`,
  `FATES_UNGERM_SEED_BANK_PF`, `FATES_RECRUITMENT_PF`, `FATES_RECRUITMENT_CFLUX_PF` —
  whether the seed bank is empty (the spec §3 fix did not take) or full with nothing
  germinating (the germination or establishment gate is the problem)
- `FATES_ELONG_FACTOR_PF` — phenology

There is no `FATES_MORTALITY_CSTARV_PF` (individuals, per PFT); only the `_SZPF` form
exists, `use_default='inactive'`. Sam prefers per-PFT over size-by-PFT, and adding a `_PF`
variant is about four lines on the pattern of `ih_m2_si_pft` / `ih_m6_si_pft` already in
`FatesHistoryInterfaceMod.F90`. Do that rather than post-processing the duplexed one.

## Fast iteration: a case that restarts just before the cull

The reference run is a CIME *test*, and it sets `REST_OPTION=none` — there is no restart to
resume from, so every experiment currently costs 402 days of debug-mode integration. Build a
plain case instead, spin it up once to just before the cull, and save that restart.

```bash
cd /glade/work/samrabin/ctsm_adrianna-moss-grass-pft
T=cime_config/testdefs/testmods_dirs/clm
./cime/scripts/create_newcase \
  --case /glade/derecho/scratch/$USER/mosscull \
  --res 1x1_ALP2 --compset I2000Clm60Fates \
  --machine derecho --compiler intel --run-unsupported \
  --user-mods-dirs $PWD/$T/FatesColdNoCompFixedBioGeo \
                   $PWD/$T/FatesNvp \
                   $PWD/$T/FatesALP2BareGrassMoss
cd /glade/derecho/scratch/$USER/mosscull
./xmlchange MPILIB=mpi-serial,NTASKS=1,DEBUG=TRUE,DOUT_S=FALSE
./xmlchange RUN_STARTDATE=2000-01-01,STOP_OPTION=ndays,STOP_N=385
./xmlchange REST_OPTION=ndays,REST_N=385
./case.setup && ./case.build && ./case.submit
```

`DEBUG=TRUE` matters: the reference run is a `_D` test, and dropping debug may move the cull
day. Keep it until the cull is reproduced, then drop it if the loop is too slow — and
re-check the day.

Day 1 of the tape is 2000-01-02, so day 401 is 2001-02-06 and the cull is on day 402,
2001-02-07. A 385-day leg lands the restart around 2001-01-21; check the actual
`*.clm2.r.*.nc` date rather than trusting the arithmetic. Then save the restart set aside so
the same window can be replayed indefinitely:

```bash
RUNDIR=$(./xmlquery --value RUNDIR)
mkdir -p saved_d385 && cp $RUNDIR/*.r*.nc $RUNDIR/rpointer.* saved_d385/
```

Each iteration: restore, extend, run ~25 days across the cull.

```bash
cp saved_d385/* $RUNDIR/
./xmlchange CONTINUE_RUN=TRUE,STOP_N=25,REST_OPTION=never
./case.submit
```

Restoring the `rpointer.*` files is the part that is easy to forget — without it each
resubmit advances past the window and the next one starts somewhere else. History variables
and restart files are independent, so a `user_nl_clm` change needs no rebuild; adding a
`write(fates_log(),*)` does.

`terminate_cohorts` already has `if ( debug )` writes on every branch
(`EDCohortDynamicsMod.F90:342, 357, 371, 381, 394`) that print which criterion fired, the
PFT and the call index. Turning FATES's `debug` on is the cheapest possible confirmation of
the route, and it costs one rebuild.

## Traps

- **`FATES_MORTALITY_TERMINATION_PF` is not "all termination".** See above. The plan text
  currently says no mortality diagnostic records the removal; that is too strong, and this
  brief supersedes it.
- **Site-level diagnostics are area-weighted, patch values are not.** Every site-level moss
  diagnostic here is a patch-area weighted sum with bareground contributing zero, so a site
  value is the patch value times the non-bareground fraction, 0.8. `max()` and `min()` do not
  commute with that sum. `verify_moss_history.py` documents the two conversion factors and
  which checks need which; read that before hand-computing anything from the tape.
- **Nothing burns in this run.** SPITFIRE is on (`fates_spitfire_mode = 1`) and
  `FATES_BURNFRAC` is identically zero on all 730 days, so fire is not what removes moss and
  no burn-side diagnostic here says anything.
- **The moss wetness proxy is pure top-soil saturation in this run.** The canopy ingredient
  tops out at CTSM's `maximum_leaf_wetted_fraction` of 0.05 against a soil ingredient that
  never falls below 0.399 in patch units, so `max()` always picks soil. If a hypothesis
  depends on the canopy branch, it is untested here.
- **Never write under `$DIN_LOC_ROOT`.** Hand Sam a `ctsm_pylib` script instead if an input
  dataset needs changing.
- **Never create a Python environment** — no conda/mamba/venv/pip, not even `--user`, and do
  not survey which environments exist. Use
  `/glade/work/samrabin/conda-envs/ctsm_pylib/bin/python3`; ask Sam if something is missing.
- **Never modify git state to make a build succeed.** If `./case.build` fails for a
  git-related reason the invocation is wrong, not the repo — stop and ask.
- **Never pipe `qcmd -- ./case.build` into `tail` or `head`** — the exit status becomes the
  pager's and a failed build reads as success. Redirect to a file, echo `$?`, and grep for
  `MODEL BUILD HAS FINISHED SUCCESSFULLY`.
- **Sam handles all commits and pushes.** Do not push, and do not offer to.
