# Moss Canopy Ingredient: Storage Fraction Instead of Capped Wetted Fraction — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task, with the **custom orchestration loop** defined in the main plan's "Process" section (`docs/superpowers/plans/2026-08-19-moss-grass-pft.md`), which overrides the sub-skill's defaults where they differ. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the moss wetness proxies a canopy ingredient that spans 0-1, the filled fraction of the canopy's interception storage, without touching the wetted fraction CTSM uses for evaporation.

**Architecture:** CTSM passes FATES the components of each storage fraction, per patch, on `bc_in`: canopy liquid and snow (`liqcan`, `snocan`) and their capacities (`liqcanmx`, `snocanmx`). FATES forms the fractions itself. Where the patch has exposed leaf or stem area, the liquid proxy's canopy ingredient is `liqcan/liqcanmx` and the total proxy's is `max(liqcan/liqcanmx, snocan/snocanmx)`, each clamped to [0, 1]. Where it has none, the liquid ingredient is 0. The total ingredient is then 1 if the patch has foliage, which means it is snow-buried: snow counts as water for the total proxy, which keeps buried moss unburnable whatever the soil does. With no foliage, the total ingredient is 0.

FATES decides "exposed" and "has foliage" from its own leaf and stem area profiles, **unfloored**. `calc_areaindex` floors every area index it reports at `ai_min = 0.1` (`biogeochem/EDCanopyStructureMod.F90`; NGEET/fates#261, kept by Sam's decision, 2026-10-23). So the host's leaf and stem area, and hence the capacities, never reach zero, even on a fully buried patch or one with no cohorts. On such a patch CTSM keeps intercepting onto a phantom canopy of 0.2 area index, and the ratio there describes nothing; the unfloored test ignores it.

The capacity expressions in CTSM's `BulkFlux_CanopyExcess` move into two public functions that the excess calculation and the FATES fill share, so the formula lives in one place. The branch's `fwet_liq_patch` is removed, returning `BulkDiag_FracWet` and `WaterDiagnosticBulkType` to upstream. `fwet`, `fdry`, `fcansno`, `maximum_leaf_wetted_fraction` and `ai_min` are untouched.

**Tech Stack:** Fortran (CTSM + FATES submodule), FATES pFUnit unit tests (`src/fates/testing/run_unit_tests.py`), Python (`verify_moss_history.py`).

**Spec:** `docs/superpowers/specs/2026-08-19-moss-grass-pft-design.md` §5 and §7, amended by Task 1 Step 4 of this plan. Decisions: Sam, 2026-10-23.

**Where this sits:** Task 12 Step 3g of the main plan. It runs before Task 12 Step 3b, because 3b tunes against the proxy distribution this plan changes.

## Global Constraints

- **Tasks run strictly in order: 1, then 2.** Task 2 rewrites the history checks against the bound Task 1 establishes (canopy ingredient ≤ 1, not ≤ `maximum_leaf_wetted_fraction`); written first, it would be checking a run that does not exist yet.
- **Non-FATES and `use_fates_moss = .false.` runs are bit-for-bit in history** against a baseline from the current branch head. The restart file loses `FWET_LIQ` for every CTSM run, and nothing replaces it; that is expected.
- **All existing CTSM/FATES conservation (balance) checks remain fatal**, moss on and off.
- **Patch member and history names on the FATES side do not change.** `fwet_moss_canopy_liq`/`_tot` and `FATES_MOSS_FWET_CANOPY_LIQ`/`_TOT` name the moss proxy's canopy ingredient, which they still are; only their long names and comments change. The names that described CTSM's wetted fraction (`fwet_veg_pa`, `fwet_veg_liq_pa`, the `fwet_veg*` dummy arguments) go, because what they carried is gone.
- History long names are at most 199 characters (`fates_long_string_length`).
- **No whitespace-only changes.** Do not re-align declarations, `use` blocks, `=`, `::` or trailing comments to fit a new line. Do not strip trailing whitespace or reindent untouched lines. Before committing, `git diff --numstat` and `git diff -w --numstat` must report identical counts for every file, in both repositories.
- **Never run `git checkout`, `git restore`, `git stash` or `git clean` against a tracked file.** Uncommitted plan and spec edits in the CTSM tree are intentional. To undo your own edit, edit it back.
- **Two repositories.** `src/fates` is detached at the tip of its `daily-wetness-proxy` branch; switch to that branch (`git -C src/fates switch daily-wetness-proxy`) before the first FATES commit. FATES changes are committed first. The CTSM commit then moves the `src/fates` pointer **and** edits `[submodule "fates"] fxtag` in `.gitmodules` to the same hash, in the same commit. `git ls-tree HEAD src/fates` and `git config -f .gitmodules submodule.fates.fxtag` must print the same hash before every CTSM commit.
- **Never push.** Commit only. When a step is committed, tick its checkbox in this plan inside that commit.
- **Commit messages:** the body is at most 200 words, wrapped at 72 columns. It doesn't restate code comments, show derivations, cite unsourced numbers or recount development history. State verification status honestly, including "not run". End with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- **Testing division of labour.** Claude builds CTSM-FATES (`cd test-bld-adrianna-moss-grass-pft && qcmd -- ./case.build` from the top of the checkout; if that case is missing, ask Sam rather than creating one) and runs the FATES unit tests covering touched code. Claude runs nothing that runs CTSM-FATES, and does not run `verify_moss_history.py` on test output. Sam runs system tests and the script during review.
- **FATES test commands.** From `src/fates/testing/`, with `/glade/work/samrabin/conda-envs/ctsm_pylib/bin/python3`: `run_unit_tests.py -t moss_fwet`. Never create or modify a conda env. If `ctsm_pylib` cannot run the tests, stop and tell Sam.
- **Unit tests are written by a separate test-writing agent, dispatched before the implementer**, and committed on their own. The implementer must not edit any test file.
- **Skills to invoke before starting:** any agent whose work involves `.pf` files (writing, making pass, or reviewing) invokes `writing-tests-before-the-implementer`, `pfunit-tests` and `designing-unit-test-cases`. Any agent touching a testmod invokes `ctsm-system-tests`.
- **A failed verification is a stop.** When a step that exists to confirm something comes back negative, stop and report it to Sam. Don't document it as a limitation, work around it, or drop the affected part.

## Review Focus

1. **A snow-buried patch (unfloored exposed leaf plus stem area 0, unfloored total above 0), with or without water in its stores, and despite capacities the floor keeps positive.** The liquid canopy ingredient is 0, so the liquid proxy falls back to top-soil liquid saturation; the phantom-canopy ratio is never used. The total ingredient is 1, so the moss fuel-moisture map sees a wet mat under snow (Sam, 2026-10-23). A patch with no foliage at all, such as a moss patch after extinction that holds only `moss_fines` litter, is **not** buried: both ingredients are 0. *Task 1 Step 2: unit tests.*
2. **A canopy holding only snow.** The liquid ingredient is 0 and the total is the snow fraction. *Task 1 Step 2: unit tests.*
3. **A restart across a period with an inactive (zero-canopy-area) patch.** The fill must cover it from CTSM state that is itself on the restart file, so no FATES or CTSM restart variable is needed. *Task 1 Step 0 checks the fill; Step 5's moss ALP2 ERS test exercises it.*
4. **Moss off, and non-FATES runs.** History is bit-for-bit, including after the Step 1 refactors alone. *Task 1 Step 5.*
5. **A store above its capacity.** CTSM drains canopy excess only on timesteps with precipitation onto the canopy (`CanopyHydrologyMod.F90`, `check_point_for_interception_and_excess`). If FATES shrinks a patch's leaf area on a dry day, the store stays over the new capacity until the next rain or snow. The ingredient reads 1, a full store. *Task 1 Step 2: unit test.*

---

### Task 1: Pass canopy water and capacity to FATES; FATES forms the storage fractions

This is mostly interface plumbing: four new `bc_in` fields, two bit-for-bit refactors (CTSM's capacity formula, FATES's area-index integral) so neither formula is duplicated, and a small FATES change in how the canopy ingredient is formed. It changes answers for moss runs only.

**Why the order of steps matters:** Step 1 (the two refactors) is bit-for-bit and lands alone, so its b4b result shows the refactors changed nothing before Step 3 changes answers. The red tests (Step 2) are committed before the implementation (Step 3), per `writing-tests-before-the-implementer`.

**Files:**
- Modify: `src/biogeophys/CanopyHydrologyMod.F90` (two new public capacity functions, used in `BulkFlux_CanopyExcess`; `fwet_liq` removed from `BulkDiag_FracWet` and its call)
- Modify: `src/biogeophys/WaterDiagnosticBulkType.F90` (`fwet_liq_patch` and `FWET_LIQ` removed)
- Modify: `src/utils/clmfates_interfaceMod.F90` (`wrap_moss_wetness`: its arguments and the `bc_in` fill)
- Modify: `src/biogeophys/CanopyFluxesMod.F90` (the `wrap_moss_wetness` call, near line 881)
- Modify (FATES): `biogeochem/EDCanopyStructureMod.F90` (`calc_areaindex` split into an unfloored integral plus the floor), `main/FatesInterfaceTypesMod.F90`, `main/FatesInterfaceMod.F90` (`bc_in` declarations, allocation, zeroing), `main/EDMainMod.F90` (`UpdateMossWetness`), `biogeochem/FatesPatchMod.F90` (`UpdateMossFwetLiq`, `UpdateMossFwetTot`, a new storage-fraction function, member comments), `main/FatesHistoryInterfaceMod.F90` (long names of the canopy and proxy fields)
- Test (FATES): `testing/tests/unit/moss_fwet_test/test_MossFwet.pf`
- Modify: `cime_config/testdefs/testmods_dirs/clm/FatesNvp/user_nl_clm` (the comment at the `RAIN` request, which calls the canopy ingredient "CTSM's fwet_veg")
- Modify (orchestrator): `docs/superpowers/specs/2026-08-19-moss-grass-pft-design.md` §5, §7

**Interfaces:**
- Consumes: CTSM `waterstatebulk_inst%liqcan_patch`, `waterstatebulk_inst%snocan_patch`, `canopystate_inst%elai_patch`, `canopystate_inst%esai_patch`; FATES patch area profiles (`elai_profile`, `esai_profile`, `tlai_profile`, `tsai_profile`, `canopy_area_profile`, `nrad`, `NCL_p`).
- Produces:
  - CTSM `pure elemental real(r8) function CanopyLiqStorageCapacity(elai, esai)` and `CanopySnowStorageCapacity(elai, esai)`, public in `CanopyHydrologyMod`. They return `liq_canopy_storage_scalar*(elai+esai)` and `snow_canopy_storage_scalar*(elai+esai)` [kg H2O m-2], the same expressions `BulkFlux_CanopyExcess` uses now. `BulkFlux_CanopyExcess` calls them in place of its inline expressions.
  - FATES `function calc_areaindex_unfloored(cpatch, ai_type) result(ai)`, public in `EDCanopyStructureMod`: the integral `calc_areaindex` computes now, without the floor. `calc_areaindex` becomes `max(ai_min, calc_areaindex_unfloored(cpatch, ai_type))`, so its results are bit-identical.
  - `wrap_moss_wetness(this, nc, bounds_clump, soilstate_inst, waterstatebulk_inst, canopystate_inst)`. `waterdiagnosticbulk_inst` is no longer needed.
  - FATES `bc_in%liqcan_pa(:)`, `bc_in%liqcanmx_pa(:)`, `bc_in%snocan_pa(:)`, `bc_in%snocanmx_pa(:)` [kg H2O m-2]: canopy liquid, its capacity, canopy snow, its capacity, per patch. They replace `fwet_veg_pa` and `fwet_veg_liq_pa`.
  - FATES `pure function CanopyStorageFraction(water, capacity) result(storage_fraction)` in `FatesPatchMod`, beside `MossSoilSaturation`: `min(1, max(0, water/capacity))`, or 0 unless `capacity > nearzero`.
  - `UpdateMossFwetLiq(this, liqcan, liqcanmx, exposed_vai, h2o_liqvol_top, watsat_top)`. `fwet_moss_canopy_liq` is 0 unless `exposed_vai > 0`, and `CanopyStorageFraction(liqcan, liqcanmx)` otherwise. Otherwise unchanged.
  - `UpdateMossFwetTot(this, liqcan, liqcanmx, snocan, snocanmx, exposed_vai, total_vai, h2o_totvol_top, watsat_top)`. `fwet_moss_canopy_tot` is `max(CanopyStorageFraction(liqcan, liqcanmx), CanopyStorageFraction(snocan, snocanmx))` if `exposed_vai > 0`, 1 if `exposed_vai <= 0` and `total_vai > 0` (snow-buried), and 0 otherwise (no foliage). Otherwise unchanged.
  - `exposed_vai` and `total_vai` [m2 m-2] are the patch's **unfloored** leaf plus stem area indices, exposed and total. `UpdateMossWetness` computes them per patch, as `calc_areaindex_unfloored(currentPatch,'elai') + calc_areaindex_unfloored(currentPatch,'esai')` and the same with `'tlai'` and `'tsai'`, and passes them and the `bc_in` fields through.

- [x] **Step 0 (orchestrator):**
  - Confirm `fwet_veg_pa`, `fwet_veg_liq_pa` and `fwet_liq_patch` have no readers beyond those in the Files list (`src/`, including `src/fates/testing/`). An unlisted one joins Step 3.
  - Settled at Step 0 (2026-10-23): `wrap_moss_wetness` is the only fill of these `bc_in` fields. It runs in `CanopyFluxes` after interception and before canopy evaporation updates the stores, and FATES changes the host's leaf and stem area only in its daily dynamics. It loops over every FATES patch, inactive ones included (Review Focus 3). `WaterDiagnosticBulkType.F90` and `CanopyHydrologyMod.F90` differ from their merge-base with `origin/master` only by `fwet_liq` (CTSM `b9a7bfb62`, `ed55607f3`). Re-confirm these only if the branch has moved.
  - Settled at Step 0 (2026-10-23): a layer entirely below the snow has `elai_profile` and `esai_profile` exactly 0, and its `tlai_profile` and `tsai_profile` are unchanged. This holds both in the `preserve_b4b` branch of `leaf_area_profile` (`biogeochem/EDCanopyStructureMod.F90`), which is active, and in `VegAreaLayer` (`biogeochem/FatesAllometryMod.F90`). On a patch with no cohorts, `nleaf` and therefore `nrad` are 0 and the profiles are zeroed, so the unfloored integrals are exactly 0. The profiles are rebuilt daily and on restart, via `wrap_update_hlmfates_dyn` → `canopy_summarization` → `leaf_area_profile`. Burial status therefore updates once a day, from the same site snow depth that FATES photosynthesis uses.
  - Settled at Step 0 (2026-10-23), buried-moss carbon under the floor: on a fully snow-occluded moss cohort, GPP and leaf maintenance respiration are exactly 0. `ScaleLeafLayerFluxToCohort` weights both by each layer's exposed leaf area (`biogeophys/FatesPlantRespPhotosynthMod.F90`). That is the patch `elai_profile` under the default Norman solver, and `VegAreaLayer`'s exposed area under two-stream. Fine-root and live-stem maintenance respiration continue under snow, and no moss wetness term touches them. The liquid ingredient's 0 on buried patches therefore affects only the history, not moss carbon.
- [x] **Step 1: the two refactors (FATES, then CTSM; implementer agent).** Bit-for-bit.
  - **FATES:** split `calc_areaindex` per Produces. `ai_min` and its TODO comment stay with the floor in `calc_areaindex`, and the new function's header says it is unfloored and why moss needs it.
  - **CTSM:** add `CanopyLiqStorageCapacity` and `CanopySnowStorageCapacity` per Produces, with headers saying FATES's moss wetness fill uses them too. Use them in `BulkFlux_CanopyExcess`, keeping the operand order so results are bit-identical.

  Run `run_unit_tests.py -t moss_fwet` (unchanged, green), then build. Review, commit FATES, then CTSM (pointer bump and `fxtag`).
- [ ] **Step 2: FATES tests (test-writing agent).** Same skills. Red until Step 3. In `test_MossFwet.pf`:
  - **The 18 existing `UpdateMossFwetLiq_*` and `UpdateMossFwetTot_*` cases keep their names, purposes and expected values; only their calls change.** The routines now take water and capacity in place of a single canopy fraction:
    - `UpdateMossFwetLiq(fwet_veg_liq, …)` becomes `UpdateMossFwetLiq(liqcan, liqcanmx, exposed_vai, …)`;
    - `UpdateMossFwetTot(fwet_veg, …)` becomes `UpdateMossFwetTot(liqcan, liqcanmx, snocan, snocanmx, exposed_vai, total_vai, …)`.

    Each case's old canopy value `c` becomes `liqcan = c*liqcanmx`, so its expected canopy ingredient is still `c`, now derived as `liqcan/liqcanmx`. The two capacities differ from each other and from 1, e.g. `liqcanmx = 0.4`, `snocanmx = 8.0`, so a swapped argument is caught. In every existing case `exposed_vai > 0`, and in the `Tot` cases `total_vai > exposed_vai` (e.g. 0.5 and 1.25), and `snocan` gives a snow fraction that is nonzero but smaller than `c`, so the liquid side of the `max` sets the result and a routine that read only snow would fail. Rewrite each comment that calls the input a "canopy wetted fraction" to describe the filled fraction of canopy storage. Delete or correct each claim that rests on the old cap, e.g. the canopy-wins case's comment saying that configuration is rare because the host caps the canopy. The `MossWetnessScaler_*` and `MossCO2FilmFactor_*` cases and `test_MossFwetScalerLinear.pf` set the proxies directly and are untouched.
  - **New cases** (ten), each pinning behaviour that the old single-fraction input could not express. Unless a case says otherwise, `exposed_vai > 0` and the capacities are positive:
    - `UpdateMossFwetTot_SnowFracLarger_CanopyFollowsSnow` and `UpdateMossFwetTot_LiqFracLarger_CanopyFollowsLiquid`: each branch of the `max`.
    - `UpdateMossFwetTot_SnowOnly_CanopyIsSnowFrac`, and `UpdateMossFwetLiq_SnowOnly_CanopyZero`: `liqcan = 0`, `snocan > 0`.
    - `UpdateMossFwetTot_SnowBuried_CanopyOne`: `exposed_vai = 0`, `total_vai > 0`, capacities **positive** as the floor leaves them. Run it once with water in both stores (liquid over capacity) and once with both empty: canopy ingredient 1 each time.
    - `UpdateMossFwetLiq_SnowBuried_CanopyZero`: `exposed_vai = 0`, positive capacity, `liqcan` giving a ratio near 1. Canopy ingredient 0. The comment says this is the phantom-canopy case the area floor creates, and why its ratio must not reach the proxy.
    - `UpdateMossFwetTot_NoFoliage_CanopyZero`: `exposed_vai = total_vai = 0`, positive capacities, water in the stores: 0. The comment says this is the extinct-moss-patch case and why it must not read as buried.
    - `UpdateMossFwetLiq_NoCapacity_CanopyZero`: `exposed_vai > 0` but `liqcanmx = 0`, with `liqcan > 0`. The comment says the capacity guard is defensive, because the host's floor keeps capacity positive.
    - `UpdateMossFwetLiq_StoreAboveCapacity_CanopyClampedToOne`: `liqcan = 1.5*liqcanmx`. The comment says this is real: CTSM drains excess only on timesteps with precipitation onto the canopy, so a store stays over-full after a dry-day leaf area loss, and a full store reads 1.
    - `UpdateMossFwetLiq_StoreBelowZero_CanopyClampedToZero`: a roundoff below zero. The comment says this clamp is defensive.

  Commit the test file alone.
- [ ] **Step 3: the fill and the fractions (CTSM and FATES; implementer agent).** Answer-changing for moss only. The implementer invokes `pfunit-tests` first; the agent editing the testmod invokes `ctsm-system-tests`.
  - **FATES:** replace `fwet_veg_pa` and `fwet_veg_liq_pa` with the four `bc_in` fields: declaration (with units and a comment naming the CTSM source), allocation and zeroing, in the places the old ones had. Add `CanopyStorageFraction`, and change `UpdateMossFwetLiq`, `UpdateMossFwetTot` and `UpdateMossWetness`, all per Produces. At the no-exposed-area branches, comments say three things. The host's capacities are floored and describe a phantom canopy there, so the storage fraction is not used. Snow counts as water for the total proxy, which keeps buried moss unburnable, and with no foliage there is nothing to bury. In `UpdateMossFwetLiq`, the 0 is not a claim that the moss is dry: the proxy falls back to soil. In `CanopyStorageFraction`, the upper clamp is real behaviour (an over-full store after a dry-day leaf area loss reads 1); the lower clamp and the capacity guard are defensive. Rewrite caveat (2) in the `UpdateMossFwetLiq` header: the canopy ingredient is the filled fraction of canopy liquid storage, spanning 0-1, and the cap and the known-limitation text go. Update the member comments, and the long names of `FATES_MOSS_FWET_CANOPY_LIQ`, `FATES_MOSS_FWET_CANOPY_TOT`, `FATES_MOSS_FWET_LIQ` and `FATES_MOSS_FWET_TOT`, to match.
  - **CTSM, `wrap_moss_wetness`:** take `canopystate_inst` in place of `waterdiagnosticbulk_inst`, and update the call in `CanopyFluxesMod`. Fill the four `bc_in` fields from `liqcan_patch`, `snocan_patch`, `CanopyLiqStorageCapacity(elai_patch(p), esai_patch(p))` and `CanopySnowStorageCapacity(elai_patch(p), esai_patch(p))`.
  - **CTSM, remove `fwet_liq`:** from `BulkDiag_FracWet` (argument, assertion, assignments, header sentence), from its call, and from `WaterDiagnosticBulkType` (declaration and its comment, allocation, cold start, the `FWET_LIQ` restart variable and its comment).
  - **Testmod:** correct the `RAIN` comment in `FatesNvp/user_nl_clm` to name the new canopy ingredient. Field lists unchanged.

  Run `run_unit_tests.py -t moss_fwet` (Step 2's tests now pass), then build. Review, commit FATES, then CTSM (pointer bump and `fxtag`).
- [ ] **Step 4: amend the spec (orchestrator).** Spec §5, "fwet proxies" and "Interception supplies the thallus-wetness signal": the canopy ingredient is the filled fraction of the canopy's interception storage. That is `liqcan/liqcanmx` for the liquid proxy and `max(liqcan/liqcanmx, snocan/snocanmx)` for the total, formed in FATES from host-supplied water and capacity. FATES decides from its own unfloored leaf and stem area whether a patch has exposed area or foliage. On a snow-buried patch (foliage present, none exposed) the liquid ingredient is 0 and the total is 1, so buried moss reads wet for the CO₂ film and fuel moisture. It is not the wetted fraction, which `maximum_leaf_wetted_fraction` caps at 0.05 for evaporation's sake (Sam, 2026-10-23). §7: the `bc_in` fields are the four water and capacity fields, replacing the canopy wetted fraction. Commit with the plan tick.
- [ ] **Step 5: verify (Sam, during review).** Tests expected to change:
  - **Step 1:** none. b4b everywhere, FATES and non-FATES.
  - **Step 3:** moss ALP2 tests DIFF; moss-off FATES and non-FATES tests b4b in history. The moss ERS test passes, which covers Review Focus 3. `FATES_MOSS_FWET_CANOPY_LIQ` and `_TOT` exceed 0.05 (site units, before the area-fraction division) on some days and never exceed 1, and LIQ ≤ TOT on every record. On a day when every vegetated patch is snow-buried, `FATES_MOSS_FWET_CANOPY_TOT` equals the non-bareground area fraction (1 in patch units) and `FATES_MOSS_FWET_CANOPY_LIQ` is 0.

---

### Task 2: Bring `verify_moss_history.py` in line with the uncapped canopy ingredient

The script treats `maximum_leaf_wetted_fraction` as a hard ceiling on the canopy ingredient. That holds in its commutation precondition (`commutation_watch`), the Task 8 canopy report (`check_task8_proxy`) and the default constant, and it reads the cap from the run's parameter file. After Task 1 the ceiling is 1, the capacity, and the parameter no longer describes the ingredient. This is diagnostics-script work only: no model code.

**Files:**
- Modify: `verify_moss_history.py`

**Interfaces:**
- Consumes: Task 1's history (unchanged field names, new meaning).
- Produces: a script that reports against the 0-1 storage-fraction bound.

- [ ] **Step 0 (orchestrator):** Read Task 1's ALP2 tape (Sam supplies the path). The commutation precondition holds only while the soil ingredient beats the canopy ingredient on every vegetated patch; with the canopy ingredient able to reach 1, that can fail on rainy days. **Ask Sam** how the identity checks that rest on it should behave when the watch reports the margin narrowed: report the identity as not testable on those records, restrict it to the records where the margin holds, or something else. Any outcome that leaves an identity unchecked on every record is a stop, not a silent skip.
- [ ] **Step 1: rework (implementer agent).** Replace every use of `maximum_leaf_wetted_fraction` as the canopy ceiling with the structural bound of 1, and remove the parameter-file read if nothing else uses it. Implement Sam's Step 0 answer in `commutation_watch` and its callers. Rewrite the docstrings and report text that describe the canopy ingredient as CTSM's capped `fwet_veg`. Run `python3 -I -m py_compile verify_moss_history.py`. A review agent then checks the script before its first run (it is a diagnostics script). Commit.
- [ ] **Step 2: verify (Sam).** Sam runs the script on Task 1's moss ALP2 tape. Every check reports PASS, or the outcome Step 0 agreed. None reports a canopy value "ABOVE maximum_leaf_wetted_fraction".
