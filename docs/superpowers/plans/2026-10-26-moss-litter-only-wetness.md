# Moss Litter-Only Patches: Total Wetness Proxy Follows Soil — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task, with the **custom orchestration loop** defined in the main plan's "Process" section (`docs/superpowers/plans/2026-08-19-moss-grass-pft.md`), which overrides the sub-skill's defaults where they differ. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the total moss wetness proxy's behaviour on a patch with no foliage at all a decision rather than a placeholder: the canopy ingredient is 0, so the proxy, and with it the fuel moisture of the patch's `moss_fines` litter, is top-soil total saturation.

**Architecture:** No answer changes. `UpdateMossFwetTot` already sets `fwet_moss_canopy_tot = 0` when the patch's unfloored exposed and total leaf-plus-stem area are both 0, so `fwet_moss_tot = fwet_moss_soil_tot`. That branch was left by Step 3g as an unpinned placeholder for this step to replace. Sam's decision (2026-10-26): keep it. A patch with no foliage has no moss canopy, and the host's interception store there sits on the phantom canopy that the `ai_min = 0.1` floor creates, so its fill fraction describes nothing. The litter is wetted only through the soil. This plan pins that branch with unit tests, and records the decision in code comments, the spec and the main plan. Explicit dead-moss water content, a prognostic store for the litter itself, is a non-goal: it was judged a much larger job than the benefit warrants for now.

A patch with live moss of any size, however small, is **not** in scope. Its VAI is below the floor whenever it is under 0.1, and like every sparse live moss canopy it reads the fill fraction of a host store sized for 0.1. That is the existing live-moss behaviour, not a no-foliage case (Sam, 2026-10-26).

**Tech Stack:** Fortran (FATES submodule), FATES pFUnit unit tests (`src/fates/testing/run_unit_tests.py`).

**Spec:** `docs/superpowers/specs/2026-08-19-moss-grass-pft-design.md` §5 and §6, amended by Task 1 Step 3 of this plan. Decisions: Sam, 2026-10-26. No separate design document: the decision is one sentence, recorded in the spec amendment.

**Where this sits:** Task 12 Step 3h of the main plan, immediately after Step 3g. Because nothing changes answers, it does not move the proxy distribution that Step 3b tunes against. Its position relative to 3b is therefore conventional, not load-bearing.

## Global Constraints

- **Answers do not change, anywhere.** The FATES change is comments only, and the unit tests are new cases only. Every system test, moss on or off, FATES or not, is bit-for-bit against the current branch head.
- **Patch member, history and routine names do not change.**
- **No whitespace-only changes.** Do not re-align declarations, `use` blocks, `=`, `::` or trailing comments to fit a new line. Do not strip trailing whitespace or reindent untouched lines. Before committing, `git diff --numstat` and `git diff -w --numstat` must report identical counts for every file, in both repositories.
- **Never run `git checkout`, `git restore`, `git stash` or `git clean` against a tracked file.** Uncommitted plan and spec edits in the CTSM tree are intentional. To undo your own edit, edit it back.
- **Two repositories.** `src/fates` is detached at the tip of its `daily-wetness-proxy` branch; switch to that branch (`git -C src/fates switch daily-wetness-proxy`) before the first FATES commit. FATES changes are committed first. The CTSM commit then moves the `src/fates` pointer **and** edits `[submodule "fates"] fxtag` in `.gitmodules` to the same hash, in the same commit. `git ls-tree HEAD src/fates` and `git config -f .gitmodules submodule.fates.fxtag` must print the same hash before every CTSM commit.
- **Never push.** Commit only. When a step is committed, tick its checkbox in this plan inside that commit.
- **Commit messages:** the body is at most 200 words, wrapped at 72 columns. It doesn't restate code comments, show derivations, cite unsourced numbers or recount development history. State verification status honestly, including "not run". End with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- **Testing division of labour.** Claude builds CTSM-FATES (`cd test-bld-adrianna-moss-grass-pft && qcmd -- ./case.build` from the top of the checkout; if that case is missing, ask Sam rather than creating one) and runs the FATES unit tests covering touched code. Claude runs nothing that runs CTSM-FATES. Sam decides during review whether to run system tests.
- **FATES test commands.** From `src/fates/testing/`, with `/glade/work/samrabin/conda-envs/ctsm_pylib/bin/python3`: `run_unit_tests.py -t moss_fwet`. Never create or modify a conda env. If `ctsm_pylib` cannot run the tests, stop and tell Sam.
- **Unit tests are written by a separate test-writing agent, dispatched before the implementer**, and committed on their own. The implementer must not edit any test file.
- **Skills to invoke before starting:** any agent whose work involves `.pf` files (writing, making pass, or reviewing) invokes `writing-tests-before-the-implementer`, `pfunit-tests` and `designing-unit-test-cases`.
- **A failed verification is a stop.** When a step that exists to confirm something comes back negative, stop and report it to Sam. Don't document it as a limitation, work around it, or drop the affected part.

## Review Focus

1. **A litter-only patch whose host stores hold water.** The floor keeps the host's capacities positive, and CTSM keeps intercepting onto the phantom canopy, so the stores can be nearly full. The total canopy ingredient must still be 0, and the proxy must be the soil value, even when the phantom ratio would beat the soil. *Task 1 Step 1: unit test.*
2. **A litter-only patch with zero host capacity.** That is what the patch would see if the `ai_min` floor were removed (NGEET/fates#261). No abort, and the canopy ingredient is 0. *Task 1 Step 1: unit test.*
3. **A litter-only patch is not snow-buried.** Burial needs foliage (`total_vai > 0`). A no-foliage patch under deep snow therefore reads the soil, not the buried value of 1. The litter's wetness then follows the top soil layer's total saturation, ice included. *Task 1 Step 1: the first case's expected value of the soil saturation, not 1, pins this.*

---

### Task 1: Pin and document the no-foliage branch of the total proxy

This is test-and-documentation work that must leave every answer bit-for-bit. The new tests characterise code that already exists, so they pass on their first run. That is expected here, and a mutation check stands in for the red phase.

**Files:**
- Test (FATES): `testing/tests/unit/moss_fwet_test/test_MossFwet.pf`
- Modify (FATES): `biogeochem/FatesPatchMod.F90` (`UpdateMossFwetTot`: header and the no-foliage branch's comment)
- Modify (FATES): `fire/FatesFuelMod.F90` (the moss fuel-moisture comment in `UpdateFuelMoisture`)
- Modify (orchestrator): `docs/superpowers/specs/2026-08-19-moss-grass-pft-design.md` §5, §6; `docs/superpowers/plans/2026-08-19-moss-grass-pft.md` Task 12 Step 3h

**Interfaces:**
- Consumes: `UpdateMossFwetTot(this, liqcan, liqcanmx, snocan, snocanmx, exposed_vai, total_vai, h2o_totvol_top, watsat_top)` as it stands after Step 3g.
- Produces: no new interface. The no-foliage branch (`exposed_vai <= 0` and `total_vai <= 0`) becomes part of the contract: `fwet_moss_canopy_tot = 0`, so `fwet_moss_tot = fwet_moss_soil_tot`, regardless of `liqcan`, `snocan` or their capacities, and with no abort.

- [ ] **Step 0 (orchestrator):** Settled at plan time (2026-10-26); re-confirm only if the branch has moved.
  - The branch is reachable and exact. On a patch with no cohorts, the unfloored area integrals are exactly 0 (main plan 3g sub-plan, Task 1 Step 0).
  - On a no-foliage patch, `fwet_moss_tot`'s only consumer that changes anything is moss fuel moisture (`fire/SFMainMod.F90` → `FatesFuelMod.F90` `UpdateFuelMoisture`). The CO₂ film factor reads it only for moss cohorts, and there are none. The liquid proxy needs no change: `UpdateMossFwetLiq` takes no `total_vai`, its `exposed_vai <= 0` branch already returns 0, and `UpdateMossFwetLiq_SnowBuried_CanopyZero` covers that branch.
  - The comment that the 3g plan prescribed for this branch ("a placeholder... pointing to main-plan Task 12 Step 3h") is **not** in the code, and no test covers the branch.
- [ ] **Step 1: FATES tests (test-writing agent).** Two new cases in `test_MossFwet.pf`, placed after `UpdateMossFwetTot_SnowBuriedNoCapacity_CanopyOne` and modelled on the `SnowBuried` cases (same liquid-member marker assertions):
  - `UpdateMossFwetTot_NoFoliage_ProxyTakesSoil`: `exposed_vai = 0`, `total_vai = 0`, capacities positive, as the floor leaves them. Each store holds water, giving a fill fraction that beats the soil, and the two fractions differ from each other, e.g. `liqcan/liqcanmx = 1.5/2 = 0.75` and `snocan/snocanmx = 7/8 = 0.875`. The soil saturation lies strictly between 0 and 1 and below both fractions, e.g. `h2o_totvol_top = 0.125`, `watsat_top = 0.5` → 0.25. Assert `fwet_moss_canopy_tot = 0`, `fwet_moss_soil_tot = 0.25` and `fwet_moss_tot = 0.25`. The header comment says this is a patch with no live vegetation, such as a moss patch after extinction that holds only `moss_fines` litter. It says the host's stores there sit on the phantom canopy the area floor creates, so their fill fraction must not reach the proxy, and the litter is wetted only through the soil (Sam, 2026-10-26). It also says such a patch is not snow-buried, because burial needs foliage.
  - `UpdateMossFwetTot_NoFoliageNoCapacity_CanopyZero`: as above, but both capacities are `0.25_r8*nearzero`, with water in the stores. No abort; `fwet_moss_canopy_tot = 0` and `fwet_moss_tot` is the soil value. The comment says this is what the patch would see without the host's area floor.

  Run `run_unit_tests.py -t moss_fwet`; both cases **pass** on the first run, which is expected (characterisation). Then show that each case bites, using temporary edits to `FatesPatchMod.F90` that are reverted by editing back and never committed:
  - **(a)** Set the no-foliage branch to 1. `NoFoliage_ProxyTakesSoil` fails.
  - **(b)** Route the no-foliage case into the storage-fraction branch: change `exposed_vai <= 0._r8` to `exposed_vai <= 0._r8 .and. total_vai > 0._r8`. `NoFoliage_ProxyTakesSoil` fails, and `NoFoliageNoCapacity_CanopyZero` aborts or fails.

  A case that survives either mutation it is meant to catch is a stop. Report the mutation results in the hand-off. Confirm that `git diff` on `FatesPatchMod.F90` is empty before committing the test file alone. Then commit CTSM (pointer bump, `fxtag`, plan tick).
- [ ] **Step 2: comments (implementer agent).** Comments only; no executable line changes. The implementer invokes `pfunit-tests` first.
  - In `UpdateMossFwetTot`, give the no-foliage `else` branch (`fwet_moss_canopy_tot = 0._r8`) a comment saying three things. This is a patch with no live vegetation, whose only moss is `moss_fines` litter. The host's capacities there describe the floor's phantom canopy, so the storage fraction is not used. The 0 is a decision, not a claim that the litter is dry: the proxy, and so the litter's fuel moisture, follows top-soil total saturation. The litter has no water store of its own (Sam, 2026-10-26).
  - In the `UpdateMossFwetTot` header, add one sentence covering the three cases the canopy ingredient distinguishes: exposed foliage (storage fraction), buried foliage (1) and no foliage (0).
  - In `FatesFuelMod.F90`'s moss fuel-moisture comment, add one sentence: on a patch with no live vegetation, `fwet_moss_tot` is top-soil total saturation, so dead-moss fuel moisture there responds to rain only through the soil.

  Run `run_unit_tests.py -t moss_fwet` (all green), then build. Check that `git diff` shows only comment lines. Review, commit FATES, then CTSM (pointer bump, `fxtag`, plan tick).
- [ ] **Step 3: amend the spec and the main plan (orchestrator).**
  - Spec §5, at the end of "Interception supplies the thallus-wetness signal", add: On a patch with no foliage at all, such as a moss patch after extinction that holds only `moss_fines` litter, both canopy ingredients are 0. Both proxies are then top-soil saturation, and the litter is wetted only through the soil. Explicit dead-moss water content is out of scope (Sam, 2026-10-26).
  - Spec §6, at "Moss fuel moisture is diagnostic from the total-water fwet proxy": add a cross-reference to that sentence.
  - Main plan Task 12 Step 3h: rewrite in the style of the completed 3g entry. State the decision in one paragraph, say that answers do not change, point to this plan, and tick it.

  Commit with the plan tick.
- [ ] **Step 4: verify (Sam, during review).** Expected: no test changes answers. FATES unit tests green, including the two new cases. Whether to run any system test is Sam's call, since the source change is comments only.
