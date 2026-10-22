# Moss Wetness Proxy: Liquid/Total Split and Sub-Daily Refresh — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> to implement this plan task-by-task, with the **custom orchestration loop** defined in the
> main plan's "Process" section (`docs/superpowers/plans/2026-08-19-moss-grass-pft.md`),
> which overrides the sub-skill's defaults where they differ. Steps use checkbox (`- [ ]`)
> syntax for tracking.

**Goal:** Split the moss wetness proxy into a liquid-water proxy (photosynthetic capacity,
respiration) and a total-water proxy (CO₂ water film, fuel moisture), and refresh both every
timestep so moss's wetness limitation follows within-day changes in water.

**Architecture:** First bring in ESCOMP/CTSM#4198, so that `bc_in%h2o_liqvol_sl` is
liquid-only at both host fills, and fix its off-filter defect locally. Then add a
`bc_in%h2o_totvol_sl` field and two patch routines, `UpdateMossFwetLiq` and
`UpdateMossFwetTot`, each defining one proxy. Finally, call both from the top of the FATES
photosynthesis driver for exposed patches, and keep only the total proxy's daily refresh
ahead of fire.

**Tech Stack:** Fortran (CTSM + FATES submodule), FATES pFUnit unit tests
(`src/fates/testing/run_unit_tests.py`), FATES functional tests
(`src/fates/testing/run_functional_tests.py`), CTSM testmods.

**Spec:** `docs/superpowers/specs/2026-10-02-moss-fwet-subdaily-design.md`. It amends the
main spec, `docs/superpowers/specs/2026-08-19-moss-grass-pft-design.md`.

**Where this sits:** this plan replaces Task 12 Step 3a of the main plan and runs before
Task 12 Step 3b.

## Global Constraints

- **Tasks run strictly in order: A, B, C, R, then D.** A before B is load-bearing. Before
  #4198 the daily fill of `h2o_liqvol_sl` carries total water, so if B ran first, its liquid
  proxy would be fed total water at the daily call and the split would be meaningless. B
  before C is load-bearing too: B's bit-for-bit check is the evidence that the split itself
  changes nothing, and it can only be made before C changes answers. C before D is the
  project's ordering convention. It also lets C's checks isolate the liquid/total semantics
  before D changes when the proxies are sampled, and D's diurnal check reads C's tape. R
  before D is load-bearing: D's sub-daily refresh calls `UpdateMossFwetLiq` with the
  liquid canopy field R adds, and D's history move covers the canopy members R renames
  and adds.
- **`use_fates_moss = .false.` must be bit-for-bit with baseline**, including unchanged
  restart and history file shapes with a standard 6-litterclass parameter file. The
  exceptions are Task A, which changes answers for every FATES run, and two steps of Task
  D, each stated at its step (Sam, 2026-10-20). From Task A on, "baseline" means one
  generated after Task A.
- **All existing CTSM/FATES conservation (balance) checks remain fatal**, with
  `use_fates_moss` on and off.
- New moss history variables register **unconditionally** in
  `main/FatesHistoryInterfaceMod.F90` (`use_default='active'`, `hlms='CLM:ALM'`), each with a
  `! TODO: Before merge, change these to default 'inactive'` comment. Every moss history
  variable added or renamed is mirrored in
  `cime_config/testdefs/testmods_dirs/clm/FatesNvp/user_nl_clm` **in the same task**, using
  `hist_fincl1 += 'VAR'`, never a plain assignment.
- History long names are at most 199 characters (`fates_long_string_length`).
- **No whitespace-only changes.** Do not re-align declarations, `use` blocks, `=`, `::` or
  trailing comments to fit a new line. Do not strip trailing whitespace or reindent untouched
  lines. Before committing, `git diff --numstat` and `git diff -w --numstat` must report
  identical counts for every file, in both repositories.
- **Never run `git checkout`, `git restore`, `git stash` or `git clean` against a tracked
  file.** Uncommitted plan and spec edits in the CTSM tree are intentional. To undo your own
  edit, edit it back.
- **Two repositories.** FATES changes are committed in `src/fates/` (branch
  `daily-wetness-proxy`, from Task B on; Sam, 2026-10-05) first. The CTSM commit then moves the `src/fates` pointer **and**
  edits `[submodule "fates"] fxtag` in `.gitmodules` to the same hash, in the same commit.
  These two must print the same hash before every CTSM commit:
  `git ls-tree HEAD src/fates` and `git config -f .gitmodules submodule.fates.fxtag`.
- **Never push.** Commit only. When a step is committed, tick its checkbox in this plan.
- **Commit messages:** the body is at most 200 words, wrapped at 72 columns. It doesn't
  restate code comments, show derivations, cite unsourced numbers or recount development
  history. State verification status honestly, including "not run". End with
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- **Testing division of labour.** Claude builds CTSM-FATES
  (`cd test-bld-adrianna-moss-grass-pft && qcmd -- ./case.build` from the top of the checkout;
  if that case is missing, ask Sam rather than creating one) and runs the FATES unit and
  functional tests covering touched code. Claude runs nothing that runs CTSM-FATES. Sam
  runs system tests during review. A task's verify step names only the tests expected to
  **change** and what the change should look like.
- **FATES test commands.** Run them from `src/fates/testing/` with
  `/glade/work/samrabin/conda-envs/ctsm_pylib/bin/python3`:
  - unit tests: `run_unit_tests.py -t <name>`
  - functional tests: `MPLBACKEND=Agg <python> run_functional_tests.py --save-figs -t <name>`

  Never create or modify a conda env. If `ctsm_pylib` cannot run the tests, stop and tell
  Sam.
- **Unit tests are written by a separate test-writing agent, dispatched before the
  implementer**, and committed on their own. The implementer must not edit any test file.
- **Skills to invoke before starting:** any agent whose work involves `.pf` files (writing,
  making pass, or reviewing) invokes `writing-tests-before-the-implementer`,
  `pfunit-tests` and `designing-unit-test-cases`. Any agent touching `testlist_clm.xml`,
  a testmod, or `ExpectedTestFails.xml` invokes `ctsm-system-tests`.
- **A failed verification is a stop.** When a step that exists to confirm something comes
  back negative, stop and report it to Sam. Don't document it as a limitation, work around
  it, or drop the affected part.

## Review Focus

1. **A column snow-buried at cold start, or across a restart.** The daily fill must hand
   FATES real liquid water there, not NaN or a stale value, and a restarted run must match a
   straight-through run. *Task A, verify step: the moss ALP2 ERS test, whose restart falls in
   a snow-covered period.*
2. **A snow-buried patch, on a partly or a fully buried column.** Its proxies must be refreshed every timestep from real soil water, never from the -999 `wrap_btran` writes outside its filter. *Task D, Steps 1 and 4, and the verify step.*
3. **Moss off.** No proxy routine runs, the FATES moss restart variables stay unregistered, and the history fields exist and read zero. *Tasks B, C and D, b4b in moss-off tests, apart from Task D's two stated exceptions.*
4. **A porosity at or below `nearzero` (including the -999 sentinel), or water above
   porosity.** Each proxy's soil ingredient is clamped to [0, 1], and the porosity guard
   zeroes it. *Task B: unit tests for both routines.*

---

### Task A: Bring in ESCOMP/CTSM#4198 and fix its off-filter defect

The upstream PR makes the daily `dynamics_driv` fill of `bc_in%h2o_liqvol_sl`, and the
`s_node` behind `smp_sl`, use liquid water instead of total water. As written, it reads
`waterdiagnosticbulk_inst%h2osoi_liqvol_col`, which is only valid on some columns. That
field has a single writer, `calc_volumetric_h2oliq` (`src/biogeophys/SoilMoistStressMod.F90:171-217`),
called only from `CanopyFluxes` (`src/biogeophys/CanopyFluxesMod.F90:851`) over the columns
of the `filter_exposedvegp` patches. It is allocated as NaN
(`src/biogeophys/WaterDiagnosticBulkType.F90:202`), with no cold-start value, no restart
variable and no history field. So at the daily call, a column with no exposed patch holds
NaN if it has been buried since the run segment began, and a stale value otherwise. A
restart resets it to NaN. The local fix computes liquid water in `dynamics_driv` from
prognostic fields valid on every column, using the same routines `CanopyFluxes` uses.

The task makes three commits, in this order:
1. **CTSM:** the cherry-pick, unchanged.
2. **FATES:** comment corrections.
3. **CTSM:** the local fix, plus the FATES pointer bump and the matching `fxtag`.

**Files:**
- Cherry-pick: `9040710b0` (from local ref `refs/remotes/escomp-pr/4198`), touching
  `src/utils/clmfates_interfaceMod.F90`
- Modify: `src/utils/clmfates_interfaceMod.F90` (`dynamics_driv`: declarations, the soil
  water fill near line 1250, the `s_node` line near line 1285; module `use` lines)
- Modify (FATES, comments only): `main/EDMainMod.F90` (comment above the `UpdateMossFwet`
  call, near lines 215-236), `biogeochem/FatesPatchMod.F90` (`UpdateMossFwet` header item (1),
  near lines 897-905, and the `h2o_vol_top` dummy-argument comment)
- Modify: `.gitmodules` (`fxtag`), `src/fates` pointer

**Interfaces:**
- Consumes: nothing from this plan.
- Produces: `bc_in%h2o_liqvol_sl` is liquid volumetric water `[m3/m3]` at both host fills,
  and valid on every FATES column at the daily fill. The moss proxy (still the single
  `fwet_moss`, still daily) is therefore liquid-based until Task B.

- [x] **Step 0 (orchestrator):**
  - Confirm the cherry-pick still applies cleanly, without touching the working tree:
    `git merge-tree --write-tree --merge-base 9040710b0^ HEAD 9040710b0`. Conflict markers
    in the output are a stop.
  - Confirm the facts in this task's preamble still hold:
    - `h2osoi_liqvol_col` has a single writer, `calc_volumetric_h2oliq`;
    - that writer is called only from `CanopyFluxes`, and only on filter columns;
    - the field is allocated as NaN, with no restart or history variable.

    Search all of `src` outside `src/fates` for `h2osoi_liqvol`. If any of these is false,
    stop and report: the fix below assumes them.
- [x] **Step 1: cherry-pick.** `git cherry-pick -x 9040710b0`. Commit as-is. The `-x` line
  records the upstream source.
- [x] **Step 2: comment corrections (FATES).** After Step 1, three comments state that the
  daily fill carries total water. Make each state what is now true, and nothing about
  later tasks:
  - `EDMainMod.F90`, above the `UpdateMossFwet` call: `h2o_liqvol_sl` holds liquid water at
    both fills, so the "only writer" rationale based on the field's phase no longer applies.
    Keep the parts about the SP/ST3 gate and the fire ordering.
  - `FatesPatchMod.F90`, `UpdateMossFwet` header item (1) and the `h2o_vol_top` argument
    comment: the soil ingredient is now liquid volumetric water. A frozen top layer reads as
    dry.

  The CTSM comment in `dynamics_driv` is corrected in Step 3, because Step 3 rewrites the
  fill it sits on. Commit in `src/fates/`.
- [x] **Step 3: local fix (CTSM).** In `dynamics_driv`:

  Add to the module `use` block (alongside the existing `denice` line):
  ```fortran
     use clm_varcon        , only : denh2o
     use SoilMoistStressMod, only : calc_effective_soilporosity, calc_volumetric_h2oliq
  ```
  Add locals:
  ```fortran
      integer  :: num_fatesc               ! number of columns hosting FATES sites
      integer  :: filter_fatesc(bounds_clump%endc-bounds_clump%begc+1) ! columns hosting FATES sites
      integer  :: jtop(bounds_clump%begc:bounds_clump%endc)            ! top soil layer for each column
      real(r8) :: eff_por(bounds_clump%begc:bounds_clump%endc, 1:nlevgrnd)       ! effective porosity [m3/m3]
      real(r8) :: h2osoi_liqvol(bounds_clump%begc:bounds_clump%endc, 1:nlevgrnd) ! liquid volumetric water [m3/m3]
  ```
  Before the site loop that fills `bc_in`, compute liquid water on every FATES column:
  ```fortran
      ! Liquid volumetric soil water for every column hosting a FATES site. The HLM's own
      ! h2osoi_liqvol_col is computed in CanopyFluxes only for columns with an exposed
      ! (snow-free) vegetated patch, and is NaN or stale elsewhere, so it cannot feed this
      ! daily fill. This uses the same routines, from prognostic water valid on every column.
      num_fatesc = this%fates(nc)%nsites
      do s = 1, num_fatesc
         filter_fatesc(s) = this%f2hmap(nc)%fcolumn(s)
      end do
      call calc_effective_soilporosity(bounds_clump, &
           ubj = nlevgrnd, &
           numf = num_fatesc, &
           filter = filter_fatesc(1:num_fatesc), &
           watsat = soilstate_inst%watsat_col(bounds_clump%begc:bounds_clump%endc, 1:nlevgrnd), &
           h2osoi_ice = waterstatebulk_inst%h2osoi_ice_col(bounds_clump%begc:bounds_clump%endc, 1:nlevgrnd), &
           denice = denice, &
           eff_por = eff_por(bounds_clump%begc:bounds_clump%endc, 1:nlevgrnd))
      jtop(bounds_clump%begc:bounds_clump%endc) = 1
      call calc_volumetric_h2oliq(bounds_clump, &
           jtop = jtop(bounds_clump%begc:bounds_clump%endc), &
           lbj = 1, &
           ubj = nlevgrnd, &
           numf = num_fatesc, &
           filter = filter_fatesc(1:num_fatesc), &
           eff_porosity = eff_por(bounds_clump%begc:bounds_clump%endc, 1:nlevgrnd), &
           h2osoi_liq = waterstatebulk_inst%h2osoi_liq_col(bounds_clump%begc:bounds_clump%endc, 1:nlevgrnd), &
           denh2o = denh2o, &
           vol_liq = h2osoi_liqvol(bounds_clump%begc:bounds_clump%endc, 1:nlevgrnd))
  ```
  Then use the local arrays in the two lines #4198 changed:
  - the `bc_in(s)%h2o_liqvol_sl(1:nlevsoil)` fill takes `h2osoi_liqvol(c,1:nlevsoil)`;
  - the `s_node` line becomes
    `s_node = max(h2osoi_liqvol(c,j)/eff_por(c,j), 0.01_r8)`.

  The denominator replaces `soilstate_inst%eff_porosity_col` (Sam, 2026-10-05). That field
  has two writers with different formulas:
  - `calc_effective_soilporosity`, from `CanopyFluxes`, on exposed-vegetation columns, with
    no floor;
  - `SetSoilWaterFractions` (`SoilHydrologyMod.F90:202-257`), on every soil column, floored
    at 0.01 and counting excess ice.

  ESCOMP/CTSM#4244 reports the same duplication. Using the local `eff_por` gives the daily
  `s_node` exactly the formula `wrap_btran` uses (`clmfates_interfaceMod.F90:2613`), and the
  daily value no longer depends on which writer ran last. Division by zero cannot occur:
  `s_node` is computed only for layers in `active_suction_sl`, which requires liquid > 0, and
  `calc_volumetric_h2oliq` clamps liquid to at most `eff_por`. Say this in a short comment
  at the `s_node` line.

  Rewrite the comment above the `h2o_liqvol_sl` fill so it says the fill is liquid water
  computed from prognostic state for every column. Drop the old claim about total water and
  the moss proxy.

  If `dynamics_driv` declares `s` only after the point where the loop needs it, or uses a
  different site count than `this%fates(nc)%nsites`, follow the routine's existing
  conventions. If `f2hmap(nc)%fcolumn` does not cover every site, stop and report.
- [x] **Step 4: build.** Claude builds CTSM-FATES. A build failure is fixed in Step 3's code,
  not worked around.
- [ ] **Step 5: verify (Sam, during review).** Tests expected to change:
  - **Every FATES test against its baseline: DIFF.** Daily `smp_sl` and `h2o_liqvol_sl` are
    now liquid, and daily `smp_sl` uses the unfloored effective porosity. That moves
    `smp_memory`, drought phenology, and `FATES_MEANLIQVOL_DROUGHTPHEN_PF`. New baselines are
    generated after this task.
  - **Moss ALP2 tests:** `FATES_MOSS_FWET_SOIL` is lower on frozen days than before. It is
    now liquid saturation, so it should fall towards 0 when layer 1 is below freezing.
    Moss GPP on those days should fall with it.
  - **Moss ALP2 ERS test: PASS.** This exercises Review Focus 1 when the restart falls in a
    snow-covered period. If it fails, that is a stop.
- [x] **Step 6: reviews, then commit.** The spec-compliance and code reviewers see the
  cherry-pick, the FATES comment commit and the local fix together. Commit the local fix
  with the FATES pointer bump and matching `fxtag`.

---

### Task B: Add the total-water field and split the proxy into liquid and total

Both proxies are refreshed once a day. This task adds them with every consumer still
reading the liquid proxy, so the split can be shown to change no answers (Sam, 2026-10-06).
Task C then moves the CO₂ film and fuel moisture to the total proxy.

Before the split, two refactoring commits tidy the argument that carries the proxy into
the moss CO₂ solve:
- a pure rename, so the name says which proxy it carries;
- replacing its sign encoding with an explicit logical, which takes away the reason the
  sentinel existed.

Commit order:
1. **FATES:** the rename.
2. **FATES:** the logical argument.
3. **FATES:** the split's tests.
4. **FATES:** the split, with every consumer on the liquid proxy.
5. **CTSM:** the split's host changes, testmod rename (plus `H2OSOI:I`), FATES pointer bump
   and `fxtag`. Bit-for-bit in every shared history field.

Each commit goes through the main plan's review loop before it is made.

**Files:**
- Modify (FATES): `biogeophys/LeafBiophysicsMod.F90`:
  - `MossCO2FilmFactor` (near line 938), `CiFunc` (near line 1002), `CiBisection` (near
    line 1234), `LeafLayerPhotosynthesis` (near line 1425): dummy argument rename, the new
    `is_moss` argument, and the moss-branch tests near lines 1183, 1204 and 1350;
  - the sentinel `fwet_moss_vascular` and its comment, near lines 119-129 (deleted).
- Modify (FATES): `biogeophys/FatesPlantRespPhotosynthMod.F90`:
  - the `use LeafBiophysicsMod, only : fwet_moss_vascular` line, near line 74 (deleted);
  - the `fwet_moss_arg` local, near line 187;
  - the NaN tripwire and proxy reads, near lines 430-459;
  - the `LeafLayerPhotosynthesis` call, near lines 835-868.
- Modify (FATES): `main/FatesInterfaceTypesMod.F90` (declare `h2o_totvol_sl` beside
  `h2o_liqvol_sl`, near line 584)
- Modify (FATES): `main/FatesInterfaceMod.F90` (allocate beside `h2o_liqvol_sl` near line
  536; zero in `zero_bcs` near line 301)
- Modify (FATES): `biogeochem/FatesPatchMod.F90`:
  - members, near lines 227-235;
  - `NanValues`, near line 539;
  - `ZeroValues`, near line 635;
  - procedure list, near line 281;
  - replace `UpdateMossFwet`, near lines 881-940;
  - `UpdateMossWetnessScaler`, near line 975.
- Modify (FATES): `main/EDMainMod.F90` (daily call, near line 233)
- Modify (FATES): `fire/SFMainMod.F90` (near line 182)
- Modify (FATES): `main/FatesHistoryInterfaceMod.F90` (index declarations near line 486;
  registration near lines 6961-7000; fill near lines 2785-2797)
- Modify (FATES): `main/FatesRestartInterfaceMod.F90` (index declarations near line 218;
  registration near lines 1071-1086; write near lines 2822-2824; read near lines 3874-3890)
- Modify (FATES): `biogeochem/EDPatchDynamicsMod.F90` (fusion, near lines 3321-3336)
- Modify: `src/utils/clmfates_interfaceMod.F90` (`h2o_totvol_sl` fill in `dynamics_driv`
  and in `wrap_btran`; `wrap_btran` gains a `waterstatebulk_inst` argument)
- Modify: `src/biogeophys/CanopyFluxesMod.F90` (the `wrap_btran` call, near line 878: pass
  `waterstatebulk_inst`)
- Modify: `cime_config/testdefs/testmods_dirs/clm/FatesNvp/user_nl_clm` (field renames at
  lines 28-30, and in the comments near lines 138 and 170; `H2OSOI:I`)
- Test (FATES): `testing/tests/unit/moss_fwet_test/test_MossFwet.pf`

**Interfaces:**
- Consumes: `bc_in%h2o_liqvol_sl` liquid at both fills (Task A).
- Produces:
  - **The moss CO₂ argument.** `CiFunc`, `CiBisection` and `LeafLayerPhotosynthesis` take
    `logical, intent(in) :: is_moss`, immediately before their last argument. That last
    argument is renamed `fwet_moss_tot`: an ordinary `real(r8)` in [0, 1], used only when
    `is_moss` is true. `MossCO2FilmFactor(fwet_moss_tot)` is renamed likewise. The sentinel
    `fwet_moss_vascular` no longer exists.
  - `bc_in%h2o_totvol_sl(:)`, a `real(r8)` allocatable on soil layers: total volumetric
    soil water `[m3/m3]` from `waterstatebulk_inst%h2osoi_vol_col`. It is filled in
    `dynamics_driv` for every FATES column, ungated. In `wrap_btran` it is filled beside
    `h2o_liqvol_sl`, with -999 off-filter.
  - Patch members, all `real(r8)` in [0, 1]: `fwet_moss_liq`, `fwet_moss_tot`,
    `fwet_moss_soil_liq`, `fwet_moss_soil_tot` and `fwet_moss_canopy`, plus the existing
    `moss_wetness_scaler`. `fwet_moss` and `fwet_moss_soil` no longer exist.
  - `subroutine UpdateMossFwetLiq(this, fwet_veg, h2o_liqvol_top, watsat_top)` sets
    `fwet_moss_soil_liq`, `fwet_moss_canopy` and `fwet_moss_liq`, then calls
    `UpdateMossWetnessScaler`.
  - `subroutine UpdateMossFwetTot(this, fwet_veg, h2o_totvol_top, watsat_top)` sets
    `fwet_moss_soil_tot`, `fwet_moss_canopy` and `fwet_moss_tot`. It touches nothing else.
  - Both routines compute the soil ingredient the same way the current `UpdateMossFwet`
    does: `max(0, min(water/watsat, 1))` when `watsat > nearzero`, else 0. The proxy is
    `max(soil ingredient, fwet_veg)`. Share that guarded saturation computation, for
    example as a private module function, rather than writing it twice.
  - `UpdateMossWetnessScaler` computes `min(1, fwet_moss_liq/hlm_moss_vcmax_fwet_thresh)`.
  - History: `FATES_MOSS_FWET_LIQ`, `FATES_MOSS_FWET_TOT`, `FATES_MOSS_FWET_SOIL_LIQ`,
    `FATES_MOSS_FWET_SOIL_TOT`, `FATES_MOSS_FWET_CANOPY`, `FATES_MOSS_WETNESS_SCALER`
    (`group_dyna_simple` in this task).
  - Restart: `fates_fwet_moss_liq`, `fates_fwet_moss_tot`, `fates_fwet_moss_soil_liq`,
    `fates_fwet_moss_soil_tot`, `fates_fwet_moss_canopy`.
  - Every consumer (capacity, respiration, the CO₂ film argument, fuel moisture) reads
    `fwet_moss_liq`.

- [x] **Step 0 (orchestrator):**
  - Confirm that no unit or functional test calls `CiFunc`, `CiBisection` or
    `LeafLayerPhotosynthesis`, or names `fwet_moss_vascular`. Search
    `src/fates/testing`. If one does, Steps 1-2 would need a test change, which only a
    test-writing agent may make. Stop and re-plan those steps.
  - Confirm that `waterstatebulk_inst` is in scope at the `wrap_btran` call in
    `CanopyFluxesMod.F90`. It is a `CanopyFluxes` dummy argument at present (line 261).
  - Confirm that `h2osoi_vol_col` is CTSM's history field `H2OSOI`
    (`WaterStateType.F90:222`).
  - Confirm that the moss ALP2 tape carries layer-1 porosity (`WATSAT`) and `H2OSOI`, which
    Step 9's check needs. Settled 2026-10-06: `WATSAT` is time-constant in the first
    history file, and `H2OSOI` was absent, so Step 4 adds `H2OSOI:I` (Sam's choice).
- [x] **Step 1: rename (FATES; implementer agent).** A pure rename, bit-for-bit:
  - in `LeafBiophysicsMod`, the dummy argument `fwet_moss` becomes `fwet_moss_tot` in
    `MossCO2FilmFactor`, `CiFunc`, `CiBisection` and `LeafLayerPhotosynthesis`;
  - in `FatesPlantRespPhotosynthMod`, the local `fwet_moss_arg` becomes `fwet_moss_tot_arg`.

  Update comments that name the argument so they say it carries the total-water moss
  wetness proxy. The patch member `currentPatch%fwet_moss` keeps its name in this step; the
  split renames it. Leave the sentinel alone: Step 2 deletes it. Build, run
  `run_unit_tests.py -t moss_fwet`, review, and commit in `src/fates/`.
- [x] **Step 2: logical argument instead of the sign sentinel (FATES; implementer agent).**
  Bit-for-bit for moss and vascular PFTs.
  - **`LeafBiophysicsMod`:**
    - Add `logical, intent(in) :: is_moss ! true for a moss (non-vascular) cohort` to
      `CiFunc`, `CiBisection` and `LeafLayerPhotosynthesis`, immediately before
      `fwet_moss_tot` in each argument list and each call between them.
    - Replace every `fwet_moss_tot >= 0.0_r8` test with `is_moss`.
    - Delete `fwet_moss_vascular` and its comment block.
    - Rewrite the "SIGN OF fwet_moss" banners so they say the logical selects the path,
      and that `fwet_moss_tot` is used only when it is true.
  - **`FatesPlantRespPhotosynthMod`:**
    - Delete the `fwet_moss_vascular` import.
    - Pass the existing `is_moss` local (set near line 439) to `LeafLayerPhotosynthesis`.
    - For a vascular cohort, set `fwet_moss_tot_arg = 0._r8`, an ignored value.
    - Keep the NaN tripwire on `currentPatch%fwet_moss`, but replace its comment. Its job is
      now to catch a proxy that was never set (it is NaN-initialised in `NanValues`), not
      a silently wrong path. The `endrun` messages stay.
    - Rewrite the sign-encoding commentary near lines 430-436 and 835-868 to describe the
      logical.

  Build, run `run_unit_tests.py -t moss_fwet`, review, and commit in `src/fates/`.
- [x] **Step 3: the split's tests first (test-writing agent, dispatched before the
  implementer).** The agent invokes `writing-tests-before-the-implementer`, `pfunit-tests`
  and `designing-unit-test-cases` first. It receives this task's text up to the end of
  **Interfaces**, plus the spec. It is given no description of how the implementation will
  be structured beyond those signatures.

  It rewrites `test_MossFwet.pf` for the two routines. The `UpdateMossFwet` cases there now
  carry over to both `UpdateMossFwetLiq` and `UpdateMossFwetTot`:
  - soil ingredient wetter than the canopy, and the reverse;
  - water at porosity;
  - water above porosity (clamped to 1);
  - negative water (clamped to 0);
  - the -999 sentinel porosity;
  - porosity just below and just above `nearzero`.

  It adds:
  - **Each routine leaves the other proxy's members alone.** Seed all six members with
    distinct markers. Call one routine and assert that the other proxy's two members, and
    for `UpdateMossFwetTot` the scaler, still hold their markers.
  - **The scaler follows the liquid proxy, not the total one.** Set `fwet_moss_liq` and
    `fwet_moss_tot` to values that give different scalers, call `UpdateMossWetnessScaler`,
    and assert the liquid-derived value.

  The existing `UpdateMossWetnessScaler` cases switch from `fwet_moss` to `fwet_moss_liq`.
  The `MossCO2FilmFactor` cases are unchanged.

  Run with `run_unit_tests.py -t moss_fwet` and label every test red-first or
  green-throughout, as the skill requires. The suite does not compile against the current
  API, which is the red evidence for every test that names the new routines or members.
  Commit the test file alone in `src/fates/`.
- [x] **Step 4: implement the split (implementer agent; must not edit any test file).** The
  implementer invokes `pfunit-tests` first. It makes the remaining Files entries match the
  Interfaces block:
  - **Patch:** add the members, set to NaN in `NanValues` and 0 in `ZeroValues`. Replace
    `UpdateMossFwet` with the two routines. Rewrite the header so each routine states its
    water phase and its consumers. Keep the `fwet_veg` cap caveat, item (2) of the current
    header.
  - **Daily call (`EDMainMod`):** call `UpdateMossFwetLiq` with `bc_in%h2o_liqvol_sl(1)` and
    `UpdateMossFwetTot` with `bc_in%h2o_totvol_sl(1)`, both with `bc_in%watsat_sl(1)` and
    `bc_in%fwet_veg_pa(currentPatch%patchno)`. In the comment above the call, keep "this is
    the only writer". The reason becomes that each proxy reads a field whose water phase is
    the same at both host fills.
  - **Consumers stay on the liquid proxy in this step.** Every consumer reads
    `fwet_moss_liq`, so this step changes no answers. Task C moves the film and fuel
    moisture.
  - **Fire:** `SFMainMod` passes `currentPatch%fwet_moss_liq`.
  - **Photosynthesis:**
    - `fwet_moss_tot_arg = currentPatch%fwet_moss_liq` for moss, with a one-line comment
      that a later change switches it to the total proxy. Task C removes the comment.
    - `moss_wetness_scaler_arg = currentPatch%moss_wetness_scaler` stays as it is.
    - The NaN check tests both `currentPatch%fwet_moss_tot` and `currentPatch%fwet_moss_liq`,
      and its message names the one that was never set (Sam, 2026-10-05).
  - **History:** replace the three registrations and fills with the five fields; keep
    `FATES_MOSS_WETNESS_SCALER`. All stay `group_dyna_simple`, area-weighted with
    `cpatch%area * AREA_INV` inside the existing `hlm_use_moss` block. Long names:
    - `FATES_MOSS_FWET_LIQ`: `'moss wetness proxy from liquid water: the wetter of top soil layer liquid saturation and canopy wetted fraction; drives moss photosynthetic capacity and respiration'`
    - `FATES_MOSS_FWET_TOT`: `'moss wetness proxy from total (liquid plus ice) water: the wetter of top soil layer total saturation and canopy wetted fraction; drives the moss CO2 water film and fuel moisture'`
    - `FATES_MOSS_FWET_SOIL_LIQ`: `'top soil layer liquid-water saturation ingredient of the liquid moss wetness proxy'`
    - `FATES_MOSS_FWET_SOIL_TOT`: `'top soil layer total-water (liquid plus ice) saturation ingredient of the total moss wetness proxy'`
    - `FATES_MOSS_FWET_CANOPY`: `'canopy wetted fraction ingredient of both moss wetness proxies'`
    - `FATES_MOSS_WETNESS_SCALER`: `'moss wetness scaler from the liquid-water proxy, applied to photosynthetic capacity and, unless hlm_moss_scale_resp_by_fwet is false, leaf maintenance respiration; not to CO2 film or fuel moisture'`

    These long names describe the consumers as they stand after Task C. Until then,
    `FATES_MOSS_FWET_TOT`'s name overstates what it drives. That is accepted. Update the comment above the scaler's registration to match.
  - **Restart:** five variables, still inside `if (hlm_use_moss == itrue)`. On read, restore
    all five, then `call cpatch%UpdateMossWetnessScaler()`. The moss-off branch zeroes all
    five and the scaler. Restart files written before this task do not carry the new names.
    That is accepted: tests start cold.
  - **Fusion:** area-weight the five members, then recompute the scaler as now.
  - **Host:**
    - `dynamics_driv`: `this%fates(nc)%bc_in(s)%h2o_totvol_sl(1:nlevsoil) = waterstatebulk_inst%h2osoi_vol_col(c,1:nlevsoil)`,
      directly after the `h2o_liqvol_sl` fill, ungated.
    - `wrap_btran`: add a `type(waterstatebulk_type), intent(in) :: waterstatebulk_inst`
      argument. In the filter branch, `h2o_totvol_sl(j) = waterstatebulk_inst%h2osoi_vol_col(c,j)`.
      In the else branch, `h2o_totvol_sl(:) = -999._r8`.
    - Update the call in `CanopyFluxesMod.F90`.
  - **Testmod field names:** replace `hist_fincl1 += 'FATES_MOSS_FWET'` and
    `'FATES_MOSS_FWET_SOIL'` with `_LIQ`, `_TOT`, `_SOIL_LIQ` and `_SOIL_TOT` entries. Keep
    `_CANOPY` and the scaler. Update the field names in the comments near lines 138 and
    170. Line 170 refers to the soil ingredient the Task 10b work measured, which was total
    water, so it becomes `FATES_MOSS_FWET_SOIL_TOT`. Also add `hist_fincl1 += 'H2OSOI:I'`
    (Sam, 2026-10-06), with a comment saying it is the instantaneous total soil water
    `FATES_MOSS_FWET_SOIL_TOT` is checked against. The empty-tapes setting from `clm/Fates`
    removes it otherwise, and a daily mean would not match the FATES field's once-daily
    value. The agent touching this file invokes `ctsm-system-tests`.
- [x] **Step 5: unit tests.** `run_unit_tests.py -t moss_fwet` and `-t fire_fuel` both pass,
  with the test files untouched since Step 3.
- [x] **Step 6: functional test.**
  `MPLBACKEND=Agg <python> run_functional_tests.py --save-figs -t fuel` passes. Its driver
  passes the proxy positionally, so it needs no change.
- [x] **Step 7: build.** Claude builds CTSM-FATES.
- [x] **Step 8: reviews, then commit the split.** The reviewers see the union of the Step 3
  test commit and the implementation, and confirm the test file is unchanged since Step 3.
  Commit FATES, then CTSM with the pointer bump and `fxtag`.
- [x] **Step 9: verify (Sam, during review).** Tests expected to change:
  - **Moss and vascular, Steps 1-2: b4b.** The rename and the logical argument change no
    answers.
  - **The split commit (Step 8's CTSM commit): b4b against post-Task-A baselines** in every
    history field the two share, for moss and moss-off tests alike. The field list differs,
    with renamed and new moss fields and `H2OSOI`. A value difference in any shared field is
    a stop: the split was meant to change nothing.
  - **The total ingredient reads the CTSM field it is filled from.** On the moss ALP2 tape,
    `FATES_MOSS_FWET_SOIL_TOT` equals `min(1, H2OSOI/WATSAT)` for layer 1 times the vegetated
    area fraction, exactly. Use the instantaneous `H2OSOI` added in Step 4. `WATSAT` is a
    time-constant field in the run's first history file. The vegetated area fraction is
    the sum of `FATES_NOCOMP_PATCHAREA_PF` over the PFTs present, as main plan Task 12 Step
    3b describes. Not yet confirmed: that the instantaneous `H2OSOI` sample and the FATES
    daily call fall in the same timestep. If they differ by a constant one-step offset on
    every day, report that rather than calling it a mismatch. Any other mismatch is a stop:
    `h2o_totvol_sl` is then not what the spec says.
  - **Liquid never exceeds total.** `FATES_MOSS_FWET_SOIL_LIQ` ≤ `FATES_MOSS_FWET_SOIL_TOT`
    on every day, with equality on days layer 1 is thawed. A violation is a stop.
  - **Moss-off FATES tests: b4b against post-Task-A baselines**, except for history field
    lists, where the renamed moss fields appear and read zero.

---

### Task C: Move the CO₂ film and fuel moisture to the total proxy

The answer-changing half of the split: the two consumers that represent water in any phase
switch from the liquid proxy to the total one. The task ends with a 12-hourly history tape,
so Task D's diurnal check has something to read.

Commit order:
1. **FATES:** the CO₂ film and fuel moisture switch to the total proxy.
2. **CTSM:** FATES pointer bump and `fxtag`. Answer-changing for moss.
3. **CTSM:** the 12-hourly tape.

**Files:**
- Modify (FATES): `fire/SFMainMod.F90` (near line 182), `fire/FatesFuelMod.F90`
  (`UpdateFuelMoisture` dummy argument and comments, near lines 224-277)
- Modify (FATES): `biogeophys/FatesPlantRespPhotosynthMod.F90` (where `fwet_moss_tot_arg` is
  set for moss)
- Modify: `cime_config/testdefs/testmods_dirs/clm/FatesNvp/user_nl_clm` (the 12-hourly tape)

**Interfaces:**
- Consumes: the patch members `fwet_moss_liq` and `fwet_moss_tot`, and the history field
  names (Task B).
- Produces:
  - the CO₂ film argument and fuel moisture read `fwet_moss_tot`; capacity and respiration
    still read the liquid proxy through `moss_wetness_scaler`;
  - a second history tape (`h1`), 12-hourly, in every test that composes `FatesNvp`.

- [x] **Step 1: switch the CO₂ film and fuel moisture to the total proxy (FATES;
  implementer agent).**
  - `SFMainMod` passes `currentPatch%fwet_moss_tot` to `UpdateFuelMoisture`. Rename that
    routine's dummy argument `fwet_moss` to `fwet_moss_tot`, with matching comments.
  - In `FatesPlantRespPhotosynthMod`, `fwet_moss_tot_arg = currentPatch%fwet_moss_tot` for
    moss. Remove Task B's interim comment there.
  - In `verify_moss_history.py` (CTSM), set `FUEL_MOISTURE_PROXY = "FATES_MOSS_FWET_TOT"`
    and reword the prose that says fuel moisture or "every moss consumer" reads the liquid
    proxy: the module docstring's section 4 bullet, the section 1 and section 4
    explainers, the `check_task8_proxy` docstring, and the comment on
    `FUEL_MOISTURE_PROXY`. The scaler, canopy and productivity checks stay on liquid.

  Run `run_unit_tests.py -t moss_fwet` and `-t fire_fuel`, and the `fuel` functional test,
  then build. Review, commit FATES, then commit the CTSM pointer bump and `fxtag`, with the
  `verify_moss_history.py` change.
- [x] **Step 2: 12-hourly history tape (CTSM; implementer agent).** The agent invokes
  `ctsm-system-tests` first. In `FatesNvp/user_nl_clm`, add a second, 12-hourly tape
  (Sam, 2026-10-05: small files, still enough to see sub-daily change) carrying the moss
  wetness fields and moss GPP:
  ```
  hist_nhtfrq = -24, -12
  hist_mfilt  = 1, 730
  hist_fincl2 += 'FATES_GPP_PF'
  hist_fincl2 += 'FATES_MOSS_FWET_LIQ'
  hist_fincl2 += 'FATES_MOSS_FWET_TOT'
  hist_fincl2 += 'FATES_MOSS_FWET_SOIL_LIQ'
  hist_fincl2 += 'FATES_MOSS_FWET_SOIL_TOT'
  hist_fincl2 += 'FATES_MOSS_FWET_CANOPY'
  hist_fincl2 += 'FATES_MOSS_WETNESS_SCALER'
  ```
  `clm/Fates/user_nl_clm` sets `hist_nhtfrq = -24` and `hist_mfilt = 1` as scalars. CIME
  applies testmods in order and the later one wins, so both entries are restated here with
  tape 1 unchanged. Before committing, the agent checks two things in the testmod chain:
  - that `hist_empty_htapes` leaves tape 2 holding only these fields;
  - that each field exists at the FATES history dimension level the chain sets.

  If either is false, that is a stop. `hist_mfilt(2) = 730` puts one model year in each
  file. Add a comment saying the tape exists to check that the moss wetness proxies change
  within the day. Until Task D, the wetness fields hold their daily values through each
  day, so the two 12-hour records of a day are equal. Review, and commit in CTSM.
- [x] **Step 3: verify (Sam, during review).** Tests expected to change:
  - **Moss ALP2 tests after Step 1: DIFF from Task B.** The CO₂ film and fuel moisture move
    to total water. `FATES_FUEL_MOISTURE_FC` for classes 7-8 rises on frozen days.
  - **Every test composing `FatesNvp` gains a 12-hourly `h1` file**, which baselines generated
    before Step 2 lack.
  - **Moss-off FATES tests: b4b against Task B.**

---

### Task R: Review fixes for Tasks B and C

Fixes from Sam's review of Tasks B and C (2026-10-07). The work is mostly bit-for-bit
tidying of the moss wetness unit tests and patch routines. Most commits change no
answers. The exception is the last step, which gives the liquid proxy a liquid-only
canopy ingredient and changes answers for moss.

Each step below is its own commit, reviewed before it is made (Sam: no single "review
fix" commit). FATES commits come first. A CTSM commit with the pointer bump and `fxtag`
follows Steps 5, 7 and 9, each carrying that step's CTSM changes. Test steps are done by
a test-writing agent dispatched before the step's implementer, and the implementer must
not edit any test file.

**Why the order matters:** Steps 2-3 reshape the scaler tests against the current API, so
their green run shows the reshaping changed no expectation. Only then does Step 4 move
the tests to the new API. The rename (Steps 6-7) comes before the liquid canopy
ingredient (Steps 8-9), so the new `_liq` member has a `_tot` counterpart to sit beside,
and the only answer-changing step is last and isolated.

**Files:**
- Modify (FATES): `biogeochem/FatesPatchMod.F90`:
  - members near lines 227-239;
  - `NanValues`/`ZeroValues`;
  - the procedure list;
  - `UpdateMossFwetLiq`, `UpdateMossFwetTot`, `UpdateMossWetnessScaler` (near lines
    890-1033).
- Modify (FATES): `biogeophys/FatesPlantRespPhotosynthMod.F90` (scaler reads near lines
  460 and 692)
- Modify (FATES): `main/FatesHistoryInterfaceMod.F90` (moss wetness registrations near
  6961-7023, fill near 2785-2802, index declarations near 486-491)
- Modify (FATES): `main/FatesRestartInterfaceMod.F90` (moss wetness restart variables:
  declarations, registration, write, read near 3874-3907)
- Modify (FATES): `biogeochem/EDPatchDynamicsMod.F90` (fusion near 3321-3337)
- Modify (FATES): `main/EDMainMod.F90` (daily call near line 233)
- Modify (FATES): `main/FatesInterfaceTypesMod.F90`, `main/FatesInterfaceMod.F90`
  (`bc_in%fwet_veg_liq_pa`, Step 9)
- Test (FATES): `testing/tests/unit/moss_fwet_test/test_MossFwet.pf`. The parameterized
  case of Step 3 may need its own `.pf` file in that directory, registered in its
  `CMakeLists.txt`.
- Modify: `src/biogeophys/WaterDiagnosticBulkType.F90`, `src/biogeophys/CanopyHydrologyMod.F90`
  (`BulkDiag_FracWet`), `src/utils/clmfates_interfaceMod.F90` (`dynamics_driv`) (Step 9)
- Modify: `cime_config/testdefs/testmods_dirs/clm/FatesNvp/user_nl_clm`,
  `verify_moss_history.py`,
  `diagnostics/2026-10-07-moss-total-proxy-switch/check_total_proxy_switch.py` (Steps 7
  and 9)

**Interfaces:**
- Consumes: the Task B members and routines, as amended by Task C.
- Produces:
  - `real(r8) function MossWetnessScaler(this)`, type-bound on `fates_patch_type`,
    returning `min(1, this%fwet_moss_liq/hlm_moss_vcmax_fwet_thresh)`. The member
    `moss_wetness_scaler` and the subroutine `UpdateMossWetnessScaler` no longer exist.
    `UpdateMossFwetLiq` no longer touches anything but its own members.
  - Patch members `fwet_moss_canopy_tot` (renamed from `fwet_moss_canopy`; the host's
    canopy wetted fraction from snow plus liquid) and, from Step 9,
    `fwet_moss_canopy_liq` (from liquid alone).
  - `subroutine UpdateMossFwetLiq(this, fwet_veg_liq, h2o_liqvol_top, watsat_top)`
    sets `fwet_moss_soil_liq`, `fwet_moss_canopy_liq` and `fwet_moss_liq`.
    `subroutine UpdateMossFwetTot(this, fwet_veg, h2o_totvol_top, watsat_top)` sets
    `fwet_moss_soil_tot`, `fwet_moss_canopy_tot` and `fwet_moss_tot`. Neither touches
    the other's members.
  - `bc_in%fwet_veg_liq_pa(:)`, beside `fwet_veg_pa`: CTSM's canopy wetted fraction
    computed from canopy liquid alone, from `waterdiagnosticbulk_inst%fwet_liq_patch`.
  - History: `FATES_MOSS_FWET_CANOPY_TOT` (renamed from `FATES_MOSS_FWET_CANOPY`) and
    `FATES_MOSS_FWET_CANOPY_LIQ` (new). `FATES_MOSS_WETNESS_SCALER` keeps its name and
    is filled from `MossWetnessScaler()`.
  - Restart: `fates_fwet_moss_canopy_tot` (renamed) and `fates_fwet_moss_canopy_liq`
    (new). The scaler has no restart variable, as before.

- [x] **Step 0 (orchestrator):**
  - Confirm the stale comments of Step 1 are still there.
  - List every reader and writer of `moss_wetness_scaler` and `UpdateMossWetnessScaler`
    in `src/fates`, including `testing/`, against the Files list above. An unlisted one
    joins Step 5. One in a functional test is a stop: Step 5 would need a test change
    that no step provides.
  - List every reference to `fwet_moss_canopy` and `FATES_MOSS_FWET_CANOPY` outside
    `docs/` against the Files list. Untracked logs are left alone.
  - Confirm `BulkDiag_FracWet` is the only writer of `fwet_patch`. (Settled 2026-10-07:
    `fwet_patch` is a restart variable, `FWET`, for `SurfaceAlbedo`'s sake. The new liquid
    fraction gets none, because its only readers run after `BulkDiag_FracWet` in the same
    timestep; see Step 9.)
- [x] **Step 1: correct the comments Task C left stale (FATES; implementer agent).** Three
  comments still say the CO₂ film and fuel moisture read the liquid proxy, or will move
  "in a later change". Make each state what is now true:
  - `FatesPatchMod.F90`, `UpdateMossFwetLiq` header: the liquid proxy drives capacity and
    respiration only;
  - `FatesPatchMod.F90`, `UpdateMossFwetTot` header: "is meant to drive" becomes "drives";
  - `FatesHistoryInterfaceMod.F90`, the comment above the scaler's registration: drop the
    parenthetical about a later change.

  Comments only, bit-for-bit. Build, review, commit.
- [x] **Step 2: test comments and the porosity bracket (FATES; test-writing agent).** The
  agent invokes `writing-tests-before-the-implementer`, `pfunit-tests` and
  `designing-unit-test-cases` first. In `test_MossFwet.pf`:
  - **Twin comments.** Each `UpdateMossFwetTot` case that says "Identical inputs and
    expectations to" its `Liq` twin says instead that it uses the same numbers, and that
    it asserts the total-proxy members where the twin asserts the liquid ones. The twins
    stay separate tests (Sam).
  - **Name the guard.** Wherever a comment says "the guard", say what it is: the
    porosity check in `MossSoilSaturation`, which zeroes the soil ingredient unless
    `watsat_top > nearzero`.
  - **Derive the porosity bracket from `nearzero`.** `watsat_below_nearzero = 0.25_r8*nearzero`
    and `watsat_above_nearzero = 2.0_r8*nearzero`, with `nearzero` from
    `FatesConstantsMod`. Any soil water those cases set relative to the porosity is
    derived from it the same way. Rewrite their comment: the cases test the guard relative
    to `nearzero`, not the value of `nearzero`.

  Green throughout: no implementation changes. Run `run_unit_tests.py -t moss_fwet`.
  Review, commit the test file alone.
- [x] **Step 3: reshape the scaler tests on the current API (FATES; test-writing agent).**
  Same skills. Every expected scaler is derived from the threshold its test sets
  (`test_vcmax_thresh_scaler` in the scaler cases), never written as a literal:
  - `UpdateMossWetnessScaler_ProxyBelowThreshold_ScalesLinearly` becomes a three-member
    parameterized test, over three values of `fwet_moss_liq` below the threshold, each
    expecting `fwet_moss_liq/test_vcmax_thresh_scaler`. Use pFUnit's parameterized test
    case as the `pfunit-tests` skill describes. If it cannot run in this harness, stop and
    report rather than falling back to a loop.
  - The at-threshold and above-threshold cases set `fwet_moss_liq` from the threshold (at
    it, and a stated multiple above it) and expect 1.
  - `UpdateMossWetnessScaler_LiqAndTotProxiesDiffer_FollowsLiquid` splits in two: the
    total proxy wetter than the liquid one, and the liquid one wetter. The second cannot
    happen in the model. Its comment says so, and says it is there to pin which proxy
    the scaler reads.

  Green throughout. Run, review, commit the test file(s) alone.
- [x] **Step 4: the scaler as a function, tests first (FATES; test-writing agent).** Same
  skills. The tests move to the Produces signature:
  - the scaler cases set `fwet_moss_liq` and assert `this%patch%MossWetnessScaler()`;
  - the `UpdateMossFwetLiq` cases drop their scaler assertions and `expect_scaler`;
  - `marker_scaler` and its seeding go, and the marker comment loses its scaler argument.

  Red: the suite does not compile against the current API. Commit the test file(s) alone.
- [x] **Step 5: the scaler as a function (FATES; implementer agent).** The implementer
  invokes `pfunit-tests` first. Bit-for-bit:
  - **Patch:** add `MossWetnessScaler` to the procedure list and define it where
    `UpdateMossWetnessScaler` is now. Its header says it is evaluated where it is used,
    so it is never stale and needs no refresh after restart, fusion or a proxy update.
    Delete the member, its `NanValues`/`ZeroValues` lines, `UpdateMossWetnessScaler`, and
    the call and comment at the end of `UpdateMossFwetLiq`.
  - **Photosynthesis:** `moss_wetness_scaler_arg = currentPatch%MossWetnessScaler()`. The
    leaf maintenance respiration scaling near line 692 reads `moss_wetness_scaler_arg`
    rather than evaluating the function again inside the loop. Check that it is set on
    every path that reaches line 692.
  - **History:** the scaler fill uses `cpatch%MossWetnessScaler()`.
  - **Restart:** delete the recompute call on read and the zeroing on the moss-off branch.
  - **Fusion:** delete the recompute call and any comment that justified it.
  - Rewrite any comment that names `UpdateMossWetnessScaler` or the stored scaler.

  Run `-t moss_fwet` and `-t fire_fuel`, then build. Review, commit FATES, then CTSM
  (pointer bump and `fxtag`).
- [x] **Step 6: canopy rename, tests first (FATES; test-writing agent).** Same skills.
  `fwet_moss_canopy` becomes `fwet_moss_canopy_tot` throughout `test_MossFwet.pf`,
  including `marker_canopy` (now `marker_canopy_tot`) and comments. Red. Commit the test
  file alone.
- [x] **Step 7: canopy rename (FATES, then CTSM; implementer agent).** Bit-for-bit, except
  for history field names. The member, restart variable and history field are renamed
  per Produces. The member and history long names say the canopy wetted fraction comes
  from canopy snow plus liquid (CTSM `BulkDiag_FracWet`, `h2ocan = snocan + liqcan`).
  The `FATES_MOSS_FWET_LIQ` long name still says "canopy wetted fraction"; it stays
  accurate until Step 9. CTSM, in the commit with the pointer bump and `fxtag`:
  - `FatesNvp/user_nl_clm`: rename the field in `hist_fincl1` and `hist_fincl2`;
  - `verify_moss_history.py` and `check_total_proxy_switch.py`: rename the field.

  The agent touching the testmod invokes `ctsm-system-tests`. Run, build, review, commit
  FATES, then CTSM.
- [x] **Step 8: liquid-only canopy ingredient, tests first (FATES; test-writing agent).**
  Same skills. Against the Produces signatures:
  - `UpdateMossFwetLiq` cases pass `fwet_veg_liq` and assert `fwet_moss_canopy_liq`;
  - every `UpdateMossFwetLiq` case also asserts `fwet_moss_canopy_tot` still holds its
    marker, and every `UpdateMossFwetTot` case asserts `fwet_moss_canopy_liq` still holds
    a new, distinct `marker_canopy_liq`.
  - The "leaves the other proxy alone" cases cover both canopy members.

  Red. Commit the test file alone.
- [x] **Step 9: liquid-only canopy ingredient (CTSM and FATES; implementer agent).**
  Answer-changing for moss.
  - **CTSM, `WaterDiagnosticBulkType`:** a new patch field
    `fwet_liq_patch(:)` ("fraction of canopy that is wet from canopy liquid alone, 0 to
    1"). It is allocated as NaN beside `fwet_patch`, zeroed in cold start beside it,
    and has no restart variable and no history field. Its declaration comment says it is
    the liquid-only counterpart of `fwet_patch`, which is computed from canopy snow plus
    liquid. `fwet_patch` keeps its name and is not touched, and there is no
    `fwet_tot_patch` (Sam, 2026-10-07). No restart variable (Sam, 2026-10-07): in
    `clm_driver.F90`, `CanopyInterceptionAndThroughfall` (which calls `BulkDiag_FracWet`)
    runs before both readers, `CanopyFluxes` (`wrap_btran`, Task D) and the daily
    `dynamics_driv`, in every timestep including the first after a restart. A restart
    variable would also change the restart file shape of every CTSM run. Say this in a
    short comment at the declaration.
  - **CTSM, `BulkDiag_FracWet`:** beside `fwet`, set
    `fwet_liq(p) = min((liqcan(p)/(vegt*params_inst%liq_canopy_storage_scalar))**0.666666666666_r8, params_inst%maximum_leaf_wetted_fraction)`
    when `liqcan(p) > 0`, else 0. That is the same expression, exponent and cap as
    `fwet`, with `liqcan` in place of `h2ocan`. It is 0 on every path where `fwet` is set
    to 0. `fwet` and `fdry` are untouched, so non-FATES runs are bit-for-bit. Pass the new
    array through the call at `CanopyHydrologyMod.F90:421`.
  - **CTSM, `dynamics_driv`:** fill `bc_in(s)%fwet_veg_liq_pa(ifp)` from
    `waterdiagnosticbulk_inst%fwet_liq_patch(p)`, beside the `fwet_veg_pa` fill.
  - **FATES:** declare, allocate and zero `bc_in%fwet_veg_liq_pa` beside `fwet_veg_pa`.
    Add the member `fwet_moss_canopy_liq` (NaN/zero), restart variable
    `fates_fwet_moss_canopy_liq` (inside the moss block, zeroed on the moss-off branch),
    fusion (area-weighted), and history `FATES_MOSS_FWET_CANOPY_LIQ`
    (`group_dyna_simple`, area-weighted, long name `'canopy wetted fraction from canopy
    liquid alone; ingredient of the liquid moss wetness proxy'`). `UpdateMossFwetLiq`
    takes `fwet_veg_liq` per Produces. `EDMainMod` passes it
    `bc_in%fwet_veg_liq_pa(currentPatch%patchno)`. Update the `FATES_MOSS_FWET_LIQ` and
    `FATES_MOSS_FWET_CANOPY_TOT` long names: the liquid proxy uses the liquid canopy
    ingredient, and the total proxy the snow-plus-liquid one.
  - **CTSM testmod and scripts:** add `FATES_MOSS_FWET_CANOPY_LIQ` to `hist_fincl1` and
    `hist_fincl2`. In `verify_moss_history.py`, the liquid proxy's
    max-of-ingredients identity reads `FATES_MOSS_FWET_CANOPY_LIQ`, and the total
    proxy's reads `FATES_MOSS_FWET_CANOPY_TOT`. Add `FATES_MOSS_FWET_CANOPY_LIQ` to
    `check_total_proxy_switch.py`'s `h1` field list.

  Run `-t moss_fwet` and `-t fire_fuel`, then the `fuel` functional test, then build.
  Review, commit FATES, then CTSM.
- [x] **Step 10: verify (Sam, during review).** Tests expected to change:
  - **Steps 1-5: b4b**, every test.
  - **Step 7: moss tests FIELDLIST** (the renamed canopy field, on `h0` and `h1`);
    values b4b.
  - **Step 9: moss ALP2 tests DIFF; moss-off and non-FATES tests b4b.**
    - `FATES_MOSS_FWET_CANOPY_LIQ` ≤ `FATES_MOSS_FWET_CANOPY_TOT` on every day, with
      equality on days with no canopy snow.
    - On frozen, snow-free days, `FATES_MOSS_FWET_LIQ` falls below its Task C value
      wherever canopy snow was setting it. In the nocomp run that was the 0.04 site
      value.
    - `verify_moss_history.py` passes both max-of-ingredients identities.

    A violation of the inequality is a stop: the new field is then not what this step
    says.
  - **Moss ALP2 ERS tests: PASS.** If one fails from Step 9 on, check first that
    `fwet_liq_patch` really is written before it is read after a restart. It has no
    restart variable, by the call-order argument in Step 9 (Sam, 2026-10-07).

---

### Task D: Refresh both proxies every timestep

A new interface method, `wrap_moss_wetness`, runs every timestep immediately after `wrap_btran` in `CanopyFluxes`. It hands FATES real soil water on the columns `wrap_btran` leaves at -999, fills both canopy wetted fractions for every patch, and refreshes both proxies for every non-bareground patch, exposed or snow-buried. That refresh becomes the proxies' only writer: the daily call in `ed_ecosystem_dynamics` is removed, and fire reads the value refreshed earlier in its own timestep. The proxy history moves to the high-frequency group (Sam, 2026-10-20).

**Step 1 comes first, and alone, because it is the step most likely to change the design.** It replaces `wrap_btran`'s -999 soil values with real ones, and the task stops there for a suite run. If any consumer other than plant-hydraulics history turns out to read those values, Steps 2 onward are rewritten; doing them first would mean building the refresh on inputs that may have to change.

**Files:**
- Modify: `src/utils/clmfates_interfaceMod.F90` (new `wrap_moss_wetness` method; a liquid-water helper factored out of `dynamics_driv`; `dynamics_driv` loses its moss-only fills)
- Modify: `src/biogeophys/CanopyFluxesMod.F90` (call `wrap_moss_wetness` right after `wrap_btran`, near line 878)
- Modify: `src/biogeophys/WaterDiagnosticBulkType.F90` (restart variable for `fwet_liq_patch`)
- Modify (FATES): `main/EDMainMod.F90` (new public `UpdateMossWetness`; the daily proxy call and its comment removed)
- Modify (FATES): `biogeochem/FatesPatchMod.F90` (routine headers: who calls each, and when)
- Modify (FATES): `main/FatesHistoryInterfaceMod.F90` (move the seven moss wetness registrations from the `if_dyn0` block to the `if_hifrq0` block near line 9398, with `upfreq=group_hifr_simple`; move their fill from `update_history_dyn_sitelevel` to a patch loop in `update_history_hifrq_sitelevel`)

**Interfaces:**
- Consumes: `UpdateMossFwetLiq`, `UpdateMossFwetTot`, `bc_in%h2o_totvol_sl`, `bc_in%fwet_veg_pa`, `bc_in%fwet_veg_liq_pa` and the patch members (Task B, as amended by Task R); `bc_in%filter_btran`, which `wrap_btran` sets per site.
- Produces: `wrap_moss_wetness`; FATES `UpdateMossWetness`; both proxies current for the timestep, for every non-bareground patch, before the canopy-flux iteration; a CTSM restart variable `FWET_LIQ`; the seven `FATES_MOSS_*` wetness fields in `group_hifr_simple`.

- [x] **Step 0 (orchestrator):** each check is a stop if it fails. A one-step lag would be a design change for Sam, not something to adopt.
  - **Canopy wetted fraction is current.** Confirm that CTSM updates `waterdiagnosticbulk_inst%fwet_patch` for the current timestep (`CanopyHydrologyMod`, near line 429) before `CanopyFluxes` calls `wrap_btran`, and for every patch on the filter columns. Trace the call order in `src/main/clm_driver.F90`.
  - **History is written after photosynthesis.** Confirm that FATES's high-frequency history update (`wrap_update_hifrq_hist`, `clm_driver.F90` near line 1183) runs after photosynthesis in the same timestep.
- [ ] **Step 1: real soil water and canopy inputs for every site (implementer agent), then a suite stop.** CTSM only. No FATES change and no proxy refresh in this step.
  - [x] **Liquid-water helper.** Move `dynamics_driv`'s inline computation of liquid volumetric water for every FATES column (`calc_effective_soilporosity`, then `calc_volumetric_h2oliq`; Task A) into a private helper of the interface type that returns both the effective porosity and the liquid volumetric water. `dynamics_driv` calls the helper in place of the inline code. This refactor must be bit-for-bit.
  - [x] **`wrap_moss_wetness`**, a new method taking `nc`, the clump bounds, `soilstate_inst`, `waterstatebulk_inst` and `waterdiagnosticbulk_inst`. `CanopyFluxes` calls it immediately after `wrap_btran`, inside the same `if (use_fates)` block, so it runs every timestep, including one where no patch on the clump is exposed. It is not gated on `use_fates_moss` (Sam, 2026-10-20), so moss-off tests exercise the fill. For every site:
    - if `bc_in(s)%filter_btran` is false, set `h2o_liqvol_sl(1:nlevsoil)` from the helper, `h2o_totvol_sl(1:nlevsoil)` from `waterstatebulk_inst%h2osoi_vol_col` and `watsat_sl(1:nlevsoil)` from `soilstate_inst%watsat_col`. Sites in the filter keep `wrap_btran`'s values untouched. `wrap_btran`'s fills of all three, -999 branch included, stay as they are, with their kin (Sam, 2026-10-20).
    - for `ifp = 1, ...youngest_patch%patchno`, with `p = ifp + col%patchi(c)`, set `fwet_veg_pa(ifp)` from `waterdiagnosticbulk_inst%fwet_patch(p)` and `fwet_veg_liq_pa(ifp)` from `waterdiagnosticbulk_inst%fwet_liq_patch(p)`.
    - a comment says why overwriting the sentinel is safe at this point: `wrap_btran`'s own consumers (`get_active_suction_layers`, `btran_ed`) have already run on it, and the only other sub-daily reader of these fields is plant-hydraulics history.
  - [x] **Delete the `watsat_sl` fill from `dynamics_driv`**: No longer needed now that `wrap_moss_wetness` is filling the sites `wrap_btran` filled with -999.
  - **Exception to the moss-off bit-for-bit constraint (Sam, 2026-10-20).** In plant-hydraulics runs, `FATES_ROOTWGT_SOILVWC`, `FATES_ROOTWGT_SOILVWCSAT`, `FATES_ROOTWGT_SOILMATPOT`, `FATES_SOILVWC_SL`, `FATES_SOILVWCSAT_SL` and `FATES_SOILMATPOT_SL` change on timesteps when the column has no exposed vegetation. `update_history_hydraulics` averaged the -999 sentinel there and now reads real soil water. Nothing else may change.
  - [x] **Unit tests, build, review, commit CTSM.** `run_unit_tests.py -t moss_fwet` passes and Claude builds CTSM-FATES. The reviewer confirms the call sits after `wrap_btran` and outside the canopy-flux iteration, that filter sites' values are untouched, and that the helper refactor is bit-for-bit by inspection.
  - [x] **Stop: ask Sam to run the `fates_nvp` suite**, against a baseline from the commit before this step, and wait for the result. Expected: every test bit-for-bit, moss on and off, except the six plant-hydraulics fields above. **Any other DIFF, or any failure, is a stop.** It means a consumer reads these fields off the filter, and this task's strategy changes. Report it to Sam; do not start Step 2, and do not work around it. **Result 2026-10-22 16:36 MDT: No diffs at all, actually. None of the plant hydraulics history variables are saved in the `fates_nvp` suite.**
- [x] **Step 2: restart variable for `fwet_liq_patch` (implementer agent).** CTSM only.
  - [x] Register it in `WaterDiagnosticBulkType`'s restart routine beside `FWET`, in the same form (`fname('FWET_LIQ')`, `pft` dimension, `interpinic_flag='interp'`), with a long name saying it comes from canopy liquid alone. Rewrite the declaration comment that says it is deliberately not a restart variable.
  - Why it is needed now: `BulkDiag_FracWet` rewrites the field only for active patches, and `InitBulkCold` zeroes it at every start, restarts included. A FATES patch with zero canopy area is inactive. Without a restart variable, such a patch holds its last active value in a straight-through run but 0 after a restart, and from Step 3 on the refresh reads the field for every patch. `fwet_patch` already has a restart variable.
  - **Exception to the moss-off bit-for-bit constraint (Sam, 2026-10-20):** the restart file gains `FWET_LIQ` in every run, moss on or off. Register it unconditionally.
  - [x] **Unit tests, build, review, commit CTSM.** `run_unit_tests.py -t moss_fwet` passes and Claude builds CTSM-FATES. No suite stop here; Sam's run in Step 5 covers it.
- [ ] **Step 3: the per-timestep refresh (implementer agent).**
  - [ ] **`EDMainMod`:** add a public `UpdateMossWetness(nsites, sites, bc_in)`. When `hlm_use_moss == itrue`, for every site and every patch with `nocomp_pft_label /= nocomp_bareground`, call `UpdateMossFwetLiq(bc_in(s)%fwet_veg_liq_pa(ifp), bc_in(s)%h2o_liqvol_sl(1), bc_in(s)%watsat_sl(1))` and `UpdateMossFwetTot(bc_in(s)%fwet_veg_pa(ifp), bc_in(s)%h2o_totvol_sl(1), bc_in(s)%watsat_sl(1))`. No exposure gate. Its header states the contract:
    - it is the proxies' only writer, and runs every timestep for every non-bareground patch, snow-buried ones included;
    - its caller, `wrap_moss_wetness`, has filled every input with real values for every site, and runs before the canopy-flux iteration, so every photosynthesis call in a timestep sees the same proxies;
    - fire, at the day boundary, reads the value refreshed earlier in the same timestep.
  - [ ] **`ed_ecosystem_dynamics`:** remove the daily proxy call and the comment above it.
  - [ ] **`wrap_moss_wetness`:** call `UpdateMossWetness` after its fills.
  - [ ] **`dynamics_driv`:** remove the fills that only the daily proxy call read: `fwet_veg_pa` and `fwet_veg_liq_pa`. The `h2o_totvol_sl` fill stays beside `h2o_liqvol_sl`'s.
  - [ ] **`FatesPatchMod`:** each routine's header names its caller (`UpdateMossWetness`) and when it runs.
  - [ ] **History:** move the seven registrations into the `if_hifrq0` block with `upfreq=group_hifr_simple`. Move the fill into `update_history_hifrq_sitelevel` as a patch loop inside `do_sites`, still inside `if (hlm_use_moss == itrue)`, area-weighted with `cpatch%area * AREA_INV`. Keep the comment about bareground dilution. Remove the `update_history_dyn_sitelevel` fill. Long names are unchanged.
  - [ ] **Unit tests, build, review, commit.** `run_unit_tests.py -t moss_fwet` passes and Claude builds CTSM-FATES. `UpdateMossWetness` is a site and patch loop around the two tested routines and gets no unit test of its own; Step 4 reviews its gating. After Step 4's review, commit FATES, then CTSM with the pointer bump and `fxtag`.
- [ ] **Step 4: review the refresh (reviewer, for Step 3).** Confirm three things:
  - `UpdateMossWetness` runs once per timestep, after all of `wrap_moss_wetness`'s fills and before the canopy-flux iteration, including on a timestep with no exposed patch (Review Focus 2);
  - it refreshes every non-bareground patch, with no exposure gate;
  - nothing else writes either proxy, and the daily moss-only fills are gone.
- [ ] **Step 5: verify (Sam, during review).** Tests expected to change:
  - **Moss ALP2 tests: DIFF from a baseline generated after Step 1.** Moss photosynthesis now sees same-timestep wetness, and fire reads proxies refreshed earlier in its own timestep rather than computed from end-of-timestep water. The seven `FATES_MOSS_*` wetness fields are high-frequency fields now. On a daily tape they become daily means rather than end-of-day snapshots.
  - **The wetness proxies change within the day,** on the 12-hourly `h1` tape Task C added. On snow-free days, the two 12-hour records of `FATES_MOSS_FWET_LIQ` and `FATES_MOSS_WETNESS_SCALER` differ on at least some days. Under Task C they were equal. If they are still equal on every snow-free day, that is a stop. Moss `FATES_GPP_PF` is on the tape for context but is not the test. It is filled from `gpp_acc_hold`, the previous day's accumulated GPP, so it holds one value per day on any tape.
  - **Buried patches are refreshed from real soil water.** On the `h1` tape, on days the moss patch is snow-buried, `FATES_MOSS_FWET_SOIL_TOT` is nonzero. Total water includes ice, so it stays positive under snow; a zero there means the refresh read the -999 sentinel, and is a stop.
  - **Moss-off tests: bit-for-bit** with a baseline generated after Step 1.
  - **Moss ALP2 ERS test: PASS.** This also covers Step 2's restart variable.
