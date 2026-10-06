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

- **Tasks run strictly in order: A, B, C, then D.** A before B is load-bearing. Before
  #4198 the daily fill of `h2o_liqvol_sl` carries total water, so if B ran first, its liquid
  proxy would be fed total water at the daily call and the split would be meaningless. B
  before C is load-bearing too: B's bit-for-bit check is the evidence that the split itself
  changes nothing, and it can only be made before C changes answers. C before D is the
  project's ordering convention. It also lets C's checks isolate the liquid/total semantics
  before D changes when the proxies are sampled, and D's diurnal check reads C's tape.
- **`use_fates_moss = .false.` must be bit-for-bit with baseline**, including unchanged
  restart and history file shapes with a standard 6-litterclass parameter file. The one
  exception is Task A, which changes answers for every FATES run. From Task A on,
  "baseline" means one generated after Task A.
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
2. **A buried patch on a partly exposed column.** The column is in `wrap_btran`'s filter but
   the patch is not in the photosynthesis filter. Its proxies must keep their last values
   sub-daily, not be refreshed from the column's soil. *Task D, verify step.*
3. **Moss off.** No proxy routine runs, the restart variables stay unregistered, and the
   history fields exist and read zero. *Tasks B, C and D, b4b in moss-off tests.*
4. **The canopy-flux iteration calling photosynthesis several times in one timestep.** The
   sub-daily refresh must give the same proxies however many times it runs. *Task D: the
   refresh reads only inputs that are fixed within the timestep; the reviewer confirms it.*
5. **A porosity at or below `nearzero` (including the -999 sentinel), or water above
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
- [ ] **Step 9: verify (Sam, during review).** Tests expected to change:
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

- [ ] **Step 1: switch the CO₂ film and fuel moisture to the total proxy (FATES;
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
- [ ] **Step 2: 12-hourly history tape (CTSM; implementer agent).** The agent invokes
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
- [ ] **Step 3: verify (Sam, during review).** Tests expected to change:
  - **Moss ALP2 tests after Step 1: DIFF from Task B.** The CO₂ film and fuel moisture move
    to total water. `FATES_FUEL_MOISTURE_FC` for classes 7-8 rises on frozen days.
  - **Every test composing `FatesNvp` gains a 12-hourly `h1` file**, which baselines generated
    before Step 2 lack.
  - **Moss-off FATES tests: b4b against Task B.**

---

### Task D: Refresh both proxies every timestep

The sub-daily refresh runs at the top of `FatesPlantRespPhotosynthDrive`, only for patches
`wrap_photosynthesis` has flagged as exposed. The daily call keeps only the total proxy, so
snow-buried patches still get a fresh fuel-moisture input. The proxy history moves to the
high-frequency group.

**Files:**
- Modify (FATES): `biogeophys/FatesPlantRespPhotosynthMod.F90` (`FatesPlantRespPhotosynthDrive`,
  before the patch loop that tests `filter_photo_pa`, near line 367)
- Modify (FATES): `main/EDMainMod.F90` (daily call: total proxy only; comment)
- Modify (FATES): `biogeochem/FatesPatchMod.F90` (routine headers: who calls each, and when)
- Modify (FATES): `main/FatesHistoryInterfaceMod.F90` (move the six moss wetness
  registrations from the `if_dyn0` block to the `if_hifrq0` block near line 9398, with
  `upfreq=group_hifr_simple`; move their fill from `update_history_dyn_sitelevel` to a patch
  loop in `update_history_hifrq_sitelevel`)
- Modify: `src/utils/clmfates_interfaceMod.F90` (`wrap_btran`: fill `fwet_veg_pa` for the
  patches of filter columns; `dynamics_driv`: the comment above the `fwet_veg_pa` fill)

**Interfaces:**
- Consumes: `UpdateMossFwetLiq`, `UpdateMossFwetTot`, `bc_in%h2o_totvol_sl` and the patch
  members (Task B), and `bc_in%filter_photo_pa`, which is 2 for a patch in the current
  canopy-flux iteration (`wrap_photosynthesis`).
- Produces: both proxies current for the timestep before any moss cohort photosynthesizes;
  the total proxy also refreshed daily for every non-bareground patch; and the six
  `FATES_MOSS_*` wetness fields in `group_hifr_simple`.

- [ ] **Step 0 (orchestrator):** each check is a stop if it fails. A one-step lag would be
  a design change for Sam, not something to adopt.
  - **Canopy wetted fraction is current.** Confirm that CTSM updates
    `waterdiagnosticbulk_inst%fwet_patch` for the current timestep (`CanopyHydrologyMod`,
    near line 429) before `CanopyFluxes` calls `wrap_btran`, and for every patch on the
    filter columns. Trace the call order in `src/main/clm_driver.F90`.
  - **History is written after photosynthesis.** Confirm that FATES's high-frequency history
    update (`wrap_update_hifrq_hist`, `clm_driver.F90` near line 1183) runs after
    photosynthesis in the same timestep.
- [ ] **Step 1: implement (implementer agent).**
  - **`wrap_btran`, filter branch:** for each patch on the site, set
    `this%fates(nc)%bc_in(s)%fwet_veg_pa(ifp) = waterdiagnosticbulk_inst%fwet_patch(p)`,
    with `p = ifp + col%patchi(c)`, looping `ifp = 1, ...youngest_patch%patchno` as
    `dynamics_driv` does.
  - **`FatesPlantRespPhotosynthDrive`:** before the patch loop that tests `filter_photo_pa`,
    add:
    ```fortran
    ! Refresh both moss wetness proxies for every patch about to photosynthesize, before
    ! any cohort reads them. Gated on filter_photo_pa == 2, the flag photosynthesis itself
    ! is gated on: on a fully snow-buried column wrap_btran writes -999 into the soil
    ! fields, which would otherwise clamp to a dry soil ingredient. Buried patches keep
    ! their last values. This can run several times per timestep (once per canopy-flux
    ! iteration); its inputs are fixed within the timestep, so repeats are idempotent.
    if (hlm_use_moss == itrue) then
       do s = 1, nsites
          currentPatch => sites(s)%oldest_patch
          do while (associated(currentPatch))
             ifp = currentPatch%patchno
             if (currentPatch%nocomp_pft_label /= nocomp_bareground .and. &
                  bc_in(s)%filter_photo_pa(ifp) == 2) then
                call currentPatch%UpdateMossFwetLiq(bc_in(s)%fwet_veg_pa(ifp), &
                     bc_in(s)%h2o_liqvol_sl(1), bc_in(s)%watsat_sl(1))
                call currentPatch%UpdateMossFwetTot(bc_in(s)%fwet_veg_pa(ifp), &
                     bc_in(s)%h2o_totvol_sl(1), bc_in(s)%watsat_sl(1))
             end if
             currentPatch => currentPatch%younger
          end do
       end do
    end if
    ```
    Reuse the routine's existing locals and `use` imports where they exist, and add any that
    are missing.
  - **`EDMainMod`:** the daily call becomes `UpdateMossFwetTot` only. Rewrite the comment
    above it to state the contract:
    - the sub-daily refresh writes both proxies for exposed patches;
    - this daily call writes the total proxy for every non-bareground patch, so fire sees a
      current value under snow;
    - neither writer changes a proxy's meaning, because each reads a field whose water phase
      is the same at both host fills.
  - **`FatesPatchMod`:** each routine's header names its callers and when they run.
  - **`dynamics_driv`:** the comment above the `fwet_veg_pa` fill notes it is also filled
    sub-daily, in `wrap_btran`.
  - **History:** move the six registrations into the `if_hifrq0` block with
    `upfreq=group_hifr_simple`. Move the fill into `update_history_hifrq_sitelevel` as a
    patch loop inside `do_sites`, still inside `if (hlm_use_moss == itrue)`, area-weighted
    with `cpatch%area * AREA_INV`. Keep the comment about bareground dilution. Remove the
    `update_history_dyn_sitelevel` fill. Long names are unchanged.
- [ ] **Step 2: unit tests.** `run_unit_tests.py -t moss_fwet` passes, unchanged since Task B.
- [ ] **Step 3: build.** Claude builds CTSM-FATES.
- [ ] **Step 4: review the gating (reviewer).** Confirm three things:
  - the refresh is gated on `filter_photo_pa == 2`, not on `filter_btran` (Review Focus 2);
  - it reads nothing that changes between canopy-flux iterations (Review Focus 4);
  - the daily call no longer touches the liquid proxy.
- [ ] **Step 5: verify (Sam, during review).** Tests expected to change:
  - **Moss ALP2 tests: DIFF from the Task C baseline.** Moss photosynthesis now sees same-day
    wetness. The six `FATES_MOSS_*` wetness fields are high-frequency fields now. On a
    daily tape they become daily means rather than end-of-day snapshots.
  - **The wetness proxies change within the day,** on the 12-hourly `h1` tape Task C
    added. On snow-free days, the two 12-hour records of `FATES_MOSS_FWET_LIQ` and
    `FATES_MOSS_WETNESS_SCALER` differ on at least some days. Under Task C they were equal.
    If they are still equal on every snow-free day, that is a stop. Moss `FATES_GPP_PF` is
    on the tape for context but is not the test. It varies with light regardless of the
    proxy. ALP2 is at 7.28°E, so the history's UTC 00-12/12-24 split falls about half an
    hour from solar noon, and the two halves see nearly the same light.
  - **Buried patches hold their values.** On the `h1` tape, on days the moss patch is
    snow-buried, the two 12-hour records of `FATES_MOSS_FWET_LIQ` are equal.
  - **Moss ALP2 ERS test: PASS.**
- [ ] **Step 6: reviews, then commit.** Commit FATES, then CTSM with the pointer bump and
  `fxtag`.
