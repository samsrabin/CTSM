# Brief: moss's rooting profile into the top soil layer, plus optional dormancy

**Written 2026-09-08 for a fresh session.** Branch `adrianna-moss-grass-pft` in
`/glade/work/samrabin/ctsm_adrianna-moss-grass-pft`. This is plan Step 3f
(`docs/superpowers/plans/2026-08-19-moss-grass-pft.md`, search "Step 3f"). Read spec §3
(`docs/superpowers/specs/2026-08-19-moss-grass-pft-design.md`) for what moss's roots are
for, and the Step 3e outcome block in the plan for the state this step inherits.

## The task

Two things, in one step because the second exists to make the first safe.

1. **Put moss's soil-water uptake genuinely in soil layer 1** — exactly 1.0 there, exactly
   0.0 below.
2. **Add moss dormancy** so that moss is not killed by hydraulic-failure mortality when
   layer 1 is desiccated. Make it optional on the CTSM namelist, **default on** (Sam,
   2026-09-08).

Moss is PFT 15 (1-based), arctic C3 grass is PFT 12. Prescribed nocomp cover: moss 0.5,
grass 0.3, bareground 0.2. Every `FATES_*_PF` history field is per m2 **land** area, so a
moss-patch-relative value is the tape value divided by 0.5.

**Ordering is load-bearing: this runs before Step 3b.** 3b tunes the moss wetness window
against the distribution of `FATES_MOSS_FWET`, and this step changes which soil layer moss
draws from and therefore that distribution. Run 3b first and its tuning is against a
wetness signal this step then moves, so it would have to be redone.

## Why the profile is not already concentrated

Spec §3 says moss's uptake is concentrated at the surface. It is not. Moss carries
`fates_allom_fnrt_prof_mode = 3` with `fates_allom_fnrt_prof_a` raised from grass's 11.0 to
30.0, while `fates_allom_fnrt_prof_b` was left at the grass value of 2.0. Mode 3
(`exponential_2p_root_profile`, `FatesAllometryMod.F90:2860-2911`) is a half-and-half sum of
two exponentials, so the `b` limb carries exactly half the profile with an e-folding depth
of 0.5 m. Cumulative uptake fraction above depth:

| z (m) | moss (a=30) | grass (a=11) |
|---|---|---|
| 0.02 | 0.245 | 0.118 |
| 0.12 | 0.593 | 0.473 |
| 0.50 | 0.816 | 0.814 |
| 1.00 | 0.932 | 0.932 |

Below about 0.5 m moss and grass are numerically indistinguishable, because that tail is
entirely the shared `b` limb. **Raising `a` alone cannot fix this**: with `b = 2.0` held, no
value of `a` puts more than 52% in the top 2 cm.

## The trap that makes the obvious approach useless

**Do not do this by making both exponentials steep.** `set_root_fraction` normalizes and
then forces the sum to exactly 1 by adding the residual to the largest layer
(`FatesAllometryMod.F90:2849-2851`), so a profile with large `a` *and* large `b` still leaves
order 1e-14 in the deep layers. That normalizes to a perfectly valid profile and keeps
`btran_ft(moss) > 0` whenever *any* layer has liquid water above the frozen threshold — so
moss goes on drinking from a metre down whenever its own layer is unavailable, which is the
behaviour this step exists to remove. It will look like it worked.

Getting uptake genuinely into layer 1 means exactly 1.0 there and exactly 0.0 elsewhere,
which needs a new `fnrt_prof_mode`, not new coefficients for mode 3. The NVP branch's mode 4
is the wrong thing to copy: that is *no roots*, this is *all in the first layer*.

## What the first version of this step got wrong

Recorded so it is not re-derived. The step originally claimed the live risk was a fatal CTSM
water-balance error: moss's stomatal conductance is floored at `gsmin0` so it never stops
transpiring, while an all-zero uptake profile would leave that demand nowhere to come from,
landing as unallocated demand in `BalanceCheckMod`.

**The demand half of that is wrong.** CTSM gates transpiration on btran —
`if (efpot > 0._r8 .and. btran(p) > btran0)`, else `qflx_tran_veg(p) = 0._r8`, with
`btran0 = 0.0` (`CanopyFluxesMod.F90:279, 1233, 1358`). Under nocomp fixed biogeography a
moss patch's `btran_pa` *is* `btran_ft(moss)` bit-exactly, because recruitment restricts each
patch to its label PFT (`EDPhysiologyMod.F90:2546`). The same condition that produces an
all-zero uptake profile therefore also produces `btran_pa == 0`, and CTSM contributes nothing
to either `rootr_col` or `qflx_tran_veg_col`. The floored conductance is real but inert:
moss's demand is order 1e-7 mm per timestep even when btran is positive, against
`error_thresh = 1e-5` mm (`BalanceCheckMod.F90:65`).

One genuine threshold mismatch survives, benign for moss but worth knowing: FATES zeroes
`root_resis` at `btran_ft <= nearzero = 1e-30` (`EDBtranMod.F90:182`) while CTSM's gate is
`btran(p) > 0.0`, leaving a window with an all-zero profile and nonzero demand.

## The real risk: hydraulic-failure mortality, and only when thawed

`hmort` fires only when three conditions hold together (`EDMortalityFunctionsMod.F90:192-195`):

1. the cohort is not deciduous-dormant,
2. `btran_ft` is at or below `hf_sm_threshold`,
3. the soil layers holding the first 75% of root biomass are all warmer than
   `soil_tfrz_thresh`.

Moss fails the first exemption permanently: `is_decid_dormant` requires a deciduous habit and
moss is `fates_phen_leaf_habit = 1` (evergreen). With `fates_mort_hf_sm_threshold = 1e-06`
and `fates_mort_scalar_hydrfailure = 0.6`, the response is effectively **binary** — btran
clears 1e-6 and there is no mortality, or btran is at zero and the full 0.6/yr applies. That
is enough to undo Step 3e's fix. `FATES_MORTALITY_HYDRAULIC_PF` was already nonzero on 19 of
moss's 401 days in the pre-3e reference run, so this is an existing mechanism about to be
amplified, not a new one.

**The frozen case is already handled, so do not build for it.** Condition 3 *is* the
frozen-soil exemption, and `soil_tfrz_thresh`'s own declaration comment says so: "Soil
temperature threshold below which hydraulic failure mortality is off (non-hydro only)"
(`EDParamsMod.F90:74`, value -2.0 degC). Better, this step improves it for free:
`get_thaw_layer_index` (`EDMortalityFunctionsMod.F90:412-451`) walks the root profile to the
layer holding 75% of root biomass, so moss is currently exempt only when everything down to
roughly 0.4 m is at or below -2 degC, whereas with the profile in layer 1 the exemption
becomes precisely "layer 1 is frozen" — the right physics, arrived at without new code.

## What dormancy therefore has to be

**One case: layer 1 desiccated while thawed.** Scope it that narrowly.

- It does **not** need to zero transpiration. The btran gate above already does that.
- It does **not** need to suppress respiration. Leaf maintenance respiration is already
  scaled by `moss_wetness_scaler`, which is zero at fwet = 0, and fine-root maintenance
  respiration went to zero with Step 3e's `fates_allom_l2fr = 0`.

Verify both of those rather than assuming them, and say so in the review — but resist adding
machinery for either. What dormancy must do is exempt dormant moss from `hmort`. The existing
`is_decid_dormant` (`EDMortalityFunctionsMod.F90:118-120`) is the shape to follow; it is
simply gated on a leaf habit moss does not have.

### The namelist switch

Per the plan's Global Constraints, a scalar switch goes on the CTSM namelist — `clm_inparm`,
through `set_fates_ctrlparms` as an `hlm_*` variable — never on the FATES parameter file. It
should follow the naming of the moss switches already there
(`hlm_moss_scale_resp_by_fwet`, `hlm_moss_vcmax_fwet_thresh`). Default `.true.`; the off
setting exists so the review can measure what dormancy buys.

### The trap in defining the trigger

`check_layer_water` is the natural predicate and is `public` (`EDBtranMod.F90:36-57`),
testing `h2o_liq_vol > 0` and `tempk > soil_tfrz_thresh + tfrz`. But **its two arguments mean
different things depending on when it is called.** The daily dynamics sequence fills
`bc_in%h2o_liqvol_sl` with `h2osoi_vol_col`, which is *total* water including ice
(`clmfates_interfaceMod.F90:1251-1257`); only the sub-daily `wrap_btran` fills it with liquid
only (`:2574-2575`). A dormancy flag set in the daily sequence from this predicate therefore
degenerates to a pure temperature test and misses the desiccated case — which is the only
case dormancy is for. Secondary trap: for a column outside the exposed-veg filter both fields
are filled with `-999`, so the predicate returns `.false.` — reading as "dormant" — by
accident rather than by design.

Note also that `soil_tfrz_thresh = -2.0` is a hard-coded Fortran `parameter`
(`EDParamsMod.F90:74`), not per-PFT and not on any input file. A moss-specific threshold would
be a code change; say why if one is wanted.

### Restart

Whether the flag needs a restart field turns on whether it is consumed before it is computed
within a timestep. Derived freshly from `bc_in` and consumed downstream in the same call:
none needed. Set in the daily sequence and consumed by sub-daily canopy code: needed. Any
hysteresis or running memory (a wet-up requirement, a minimum dormant duration): needed
unconditionally, plus a patch-fusion rule. The branch already carries the pattern —
`fates_fwet_moss` is a restart field while `moss_wetness_scaler` deliberately is not, being
recomputed from it on restart read, and `FatesPatchMod.F90:944-977` explains why all three
call sites are needed.

## The experiment, and what it cannot tell you

With moss's uptake genuinely at 1.0 in layer 1, run 730 days at ALP2 and see whether the
all-zero-profile path is reached at all and whether the water balance complains.

**A clean run is not evidence that the path is safe** (Sam, 2026-09-08). One site over two
years does not bound the behaviour, and the first version of this step shows how readily a
code reading of this area goes wrong in either direction. What the run buys is knowing
whether this configuration exercises the path at all, which decides whether the dormancy
machinery can be tested here or needs a contrived case.

## The case to run

Already built and reusable as-is — a parameter-file change needs no rebuild, a Fortran change
does.

```
CASEROOT  /glade/derecho/scratch/samrabin/mosscull
RUNDIR    /glade/derecho/scratch/samrabin/mosscull/run
```

`1x1_ALP2`, `I2000Clm60Fates`, `DEBUG=TRUE`, `mpi-serial`, `NTASKS=1`, composing the
`FatesColdNoCompFixedBioGeo`, `FatesNvp` and `FatesALP2BareGrassMoss` testmods. 730 days from
cold start takes about 17 minutes of model time. It currently holds the post-3e
(`l2fr = 0`) run, which is the comparison baseline; the pre-3e baseline is archived at
`/glade/derecho/scratch/samrabin/mosscull_baseline_l2fr0.67/hist`.

Analysis scripts from Step 3e, with a README explaining what each answers and the
normalization conventions, are in
`diagnostics/2026-09-08-moss-extinction-diagnosis/`. Run them with
`/glade/work/samrabin/conda-envs/ctsm_pylib/bin/python3`.

The moss column of the FATES parameter file is **generated**, not hand-edited:
`src/fates/tools/make_moss_params.py` builds
`src/fates/parameter_files/fates_params_moss.json` from the default file plus explicit
per-PFT overrides. Add overrides there and regenerate.

## Expect this, and report it

Concentrating withdrawal in the top 2 cm dries the layer that sets `FATES_MOSS_FWET_SOIL`,
which is top-layer effective saturation (`FatesPatchMod.F90:925-931`). Because the moss CO2
film factor wants *low* fwet, that should raise moss GPP — a useful interaction with Step 3b
rather than a problem.

## Traps

- **The NVP branch is not a guide here.** Its moss never transpires: photosynthesis is
  deliberately routed out of `CanopyFluxes` and its stomatal resistance explicitly discarded,
  and water leaves as ground evaporation rather than `qflx_tran_veg`. Its protection is that
  the moss patch carries zero leaf area into CLM and so runs `BareGroundFluxes`. It has **no
  dormancy of any kind** — no temperature gate on metabolism, no discrete state, nothing on
  its restart file but mat thickness — and it charges full leaf maintenance respiration to
  dry, frozen and snow-buried moss. There is nothing to harvest.
- **Moss changes are not isolable from grass.** The two nocomp patches share a CTSM soil
  column; Step 3e measured grass responding to a moss-column-only parameter change from day
  61 onward. A grass difference is not by itself evidence of a leak.
- **A comment in `make_moss_params.py:186-192` is wrong**, and it is near where this work
  lands: it says moss's three stomatal parameters are unused for moss, but
  `fates_leaf_stomatal_intercept` is what sets moss's whole-canopy `rssun`/`rssha`.
- **There is no Grep tool in this environment.** ToolSearch returns no match for it, so bash
  `grep` is the fallback the global instructions permit; do not spend turns rediscovering
  this.
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
- **A commit that moves `src/fates` must bump `.gitmodules`'s `fxtag` to the same hash**, and
  vice versa.
- **Sam handles all pushes.** Commit locally; do not push, and do not offer to.
