# Moss Wetness Proxy Standalone Tests — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> to implement this plan task-by-task, with the **custom orchestration loop** defined in
> "Process" below (it overrides the sub-skill's defaults where they differ). Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the moss wetness proxy `fwet_moss` standalone test coverage — pFUnit
assertions on the behaviour that is FATES's own, and a functional test that draws the
proxy and everything it drives over a year of real weather.

**Architecture:** Two artifacts. A new pFUnit directory `tests/unit/moss_fwet_test/`
asserts on `UpdateMossFwet`, `UpdateMossWetnessScaler` and `MossCO2FilmFactor`. A new
functional-test group `tests/functional/moss/fwet/` builds a standalone driver that runs
those routines over (a) a designed scenario ladder and (b) a year-long trajectory
synthesized from `BONA_datm.nc` by a deliberately simple surrogate for CTSM's canopy and
soil hydrology, writes netCDF, and plots both.

**Tech Stack:** Fortran (FATES only — no CTSM source is touched), the FATES test harness
under `src/fates/testing/` (CMake + pFUnit 4.8.0 + a Python runner), netCDF via
`FatesUnitTestIOMod`, matplotlib/xarray for the plotters.

**Spec:** `docs/superpowers/specs/2026-09-04-moss-fwet-tests-design.md`
(parent spec: `docs/superpowers/specs/2026-08-19-moss-grass-pft-design.md`, §5, §6, §9;
parent plan: `docs/superpowers/plans/2026-08-19-moss-grass-pft.md`, Task 8).

---

## Orientation

Read this before Task 1's Step 0. It is what is true of the whole plan.

**What is already built.** Task 8 of the parent plan landed the proxy. It is a patch
member trio — `fwet_moss`, `fwet_moss_soil`, `fwet_moss_canopy` — diagnosed once per day
in the FATES dynamics sequence by `fates_patch_type::UpdateMossFwet`
(`src/fates/biogeochem/FatesPatchMod.F90`), restarted, fused, and reported as
`FATES_MOSS_FWET`, `FATES_MOSS_FWET_SOIL`, `FATES_MOSS_FWET_CANOPY`. Tasks 9 and 10
landed its consumers. **This plan adds tests only.** The one exception is a visibility
change in Task 1, called out there.

**The finding that shapes this plan.** `UpdateMossFwet` holds no state and does no
hydrology: it clamps a soil saturation, takes a `max()` against a canopy wetted fraction
it is *handed*, and refreshes a derived scaler. The Task 8 Step 4 language about the
canopy ingredient spiking with precipitation and the soil ingredient varying smoothly
describes the *inputs*, which CTSM manufactures. A standalone driver has to synthesize
them. So this plan can assert on the `max()` and the clamps, and can only *draw* the
rain-tracking behaviour. See spec §2.

**This plan does not close Task 8 Step 4.** The CTSM-side plumbing, the daily-vs-subdaily
meaning of `h2o_liqvol_sl`, restart, and the area-weighted history fill still need an ALP2
run. Task 5 records that in the parent plan rather than quietly marking Step 4 done.

**Two harness traps, both confirmed by experiment in this tree.**

- A new `.pf` **file** added to an **existing** pFUnit directory is compiled, linked, and
  never called; the run is green and proves nothing. A new *directory* is safe. Task 1
  creates a new directory for this reason, and its evidence step reads the test
  executable's own `(N tests)` line rather than the runner's summary, which always says
  `out of 1`.
- `run_functional_tests.py` ends in an unconditional `plt.show()`, so a run without
  `MPLBACKEND=Agg` blocks on X windows and reads as a hang.

Both are documented in the `pfunit-tests` and `fates-functional-tests` skills. Invoke them
rather than working from this paragraph.

## Global Constraints

`.claude/CLAUDE.md` and `~/.claude/CLAUDE.md` apply in full and are **not** restated here —
whitespace churn, pronouns, Python environments, question handling, task ordering, summary
style. So do the skills each dispatch names. What follows is only what those do not already
carry, or where this plan overrides them.

- **FATES-only.** No file outside `src/fates/` is modified by Tasks 0–4. CTSM does not
  compile `src/fates/testing/`, so those tasks need no CTSM build. Task 1 touches one
  non-test FATES source file and does need one.
- **The test harness runs in `ctsm_pylib`** —
  `/glade/work/samrabin/conda-envs/ctsm_pylib/bin/python3` (Sam, 2026-08-21). This
  **overrides** the `fates-functional-tests` and `pfunit-tests` skills, which both name the
  `fates_testing` env that `testing/environment.yml` defines. If `ctsm_pylib` cannot run
  the tests, STOP and tell Sam.
- **A run launched by an agent is always unattended,** so `MPLBACKEND=Agg` is not the
  conditional the `fates-functional-tests` skill presents it as. Without it the run blocks
  on `plt.show()` and reads as a hang.
- **Never run `git checkout`, `git restore`, `git stash` or `git clean` against a tracked
  file.** This loop leaves work uncommitted on purpose; a dirty tree is the normal state.
  To undo your own edit, edit it back. To undo a commit, `git revert` it.
- **Deliver the clean implementation, not the literal-minimum one.** Integrate into the
  shared code path its analogues already use, rename when scope generalizes, replace
  repeated literal thresholds with a named predicate. Where this plan's text and a clean
  design conflict — especially if the plan's premise turns out to be wrong — raise it in
  Step 0 rather than shipping the worse version to satisfy a reviewer.

### Git choreography

All work is in the FATES submodule. Per task: commit in `src/fates/` first, then commit in
CTSM with the submodule pointer bump **and** the matching `[submodule "fates"] fxtag` in
`.gitmodules` in that same commit — `git commit` updates only the gitlink. Verify before
committing that these two print the same hash:

```
git ls-tree HEAD src/fates
git config -f .gitmodules submodule.fates.fxtag
```

One logical task = one CTSM commit (carrying the FATES pointer bump) + at most one FATES
commit. Never push; Sam handles that.

**Task 1 is the exception**, because its mutation round (Step 7) commits each routine's
perturbations and reverts them by a commit, so the red-green record lives in history. One
pair per routine under test (Sam, 2026-09-04), so seven FATES commits: the tests, then
three mutation/revert pairs — plus one more pair for any single assertion Step 7 has to
split out for attribution. Its single CTSM commit is deferred to the end so the pointer
lands on the last of them.

## Process (custom orchestration loop — REQUIRED)

The main session is the **orchestrator**. For each task, in order:

1. **Step 0 (orchestrator, not a subagent):** work out the details this plan deliberately
   left open. Re-read the task and the spec sections it cites, explore the relevant code,
   verify the task's assumptions still hold, and settle the concrete choices — exact test
   values, variable names, netCDF layout, figure composition — recording each ruling in
   the task's Step 0 block so the implementer and the reviewers see the same decisions.
   Check that the task's "Produces" names are still what later tasks expect. Ask Sam
   anything genuinely unresolved.
2. **Dispatch an implementer subagent** with the task text as amended by Step 0, the spec
   path, and the Global Constraints — never the whole plan. **Name the skills it must
   invoke, in the dispatch itself**, as "invoke these before you start": every task here
   names `fates-functional-tests`; Task 1 additionally names `pfunit-tests`,
   `designing-unit-test-cases` and `writing-tests-before-the-implementer`. If the tree
   carries uncommitted orchestrator edits, tell the agent to leave those files alone.
3. **Dispatch a spec-compliance reviewer** (diff against the spec and the task's
   requirements) and a **code-review subagent** (correctness, conventions, test design),
   plus any extra reviewer the task names for a concern those two would not catch. Address
   all findings — re-dispatching the implementer as needed — before committing. The
   orchestrator adjudicates; it does not take over the implementation. Where a judgement
   call in a task looks like it needs the orchestrator's own reading of the code, prefer a
   scoped reviewer over doing the work in the main session.
4. **Commit** only after reviewer findings are accounted for, per Git choreography.
5. **Present the commit to Sam and STOP.** Do not begin the next task until Sam approves.
   A task's review gate is never delegated: subagents cannot ask Sam anything.

**Tasks run strictly in order.** Task N+1 does not begin until Task N is finished, even
where they touch different files. Where an ordering here is load-bearing rather than
conventional, the task says so.

**A failed verification is a stop.** Distinguish two negative results. A *claim that turns
out false* — a trap that no longer reproduces, a documented behaviour that is not real —
is cut, recorded, reported, and the work continues. A *capability that does not work* is a
stop: if a step exists to confirm something, comes back negative, and the consequence is
that the deliverable can no longer do what it was scoped to do, stop and report it. Do not
pick a fallback. Documenting it as a known limitation, dropping the affected panel, and
working around it are the same move — shrinking the deliverable without Sam choosing that.

---

### Task 0: fix the fuel test's hardcoded litter-class coordinate

**Summary for another engineer.** A shared netCDF-writing helper in the fire test suite
writes a coordinate variable's values as a literal `1..6` list, from a time when the
number of fuel classes was fixed at six. It is now a runtime value that can be eight, and
the dimension it writes into is sized from that runtime value — so under the larger
configuration the coordinate is short, silently, with the tail left at netCDF's fill
value. This task fixes it. It comes first because a later task in this plan reads from the
same helper.

1. Step 0 verified the short write and disproved the consequence originally claimed for
   it: the existing figures do not read the coordinate's values and so are not
   mislabelled by it. Do not go looking for a different bug to restore the stakes; the
   wrong coordinate is reason enough, and no figure should change.

**Files:**
- Modify: `src/fates/testing/tests/functional/fire/shr/FatesTestFireMod.F90`
  (`WriteFireData`, the `litter_class` write, around line 268)

**Interfaces:**
- Consumes: `FatesInterfaceTypesMod::num_fuel_classes` (already used elsewhere in this
  module).
- Produces: nothing later tasks depend on; the fix is contained.

- [x] **Step 0 (orchestrator):** Confirm the defect is live before dispatching anything.
  Run the existing fuel functional test under `parameter_files/fates_params_moss.json` and
  read the `litter_class` coordinate out of `fuel_out.nc` — the question is whether netCDF
  short-writes it with two fill values, errors, or something else, and whether the fuel
  test's bar charts are in fact mislabelled by it. Then decide the fix's shape: a
  constructed index array is the obvious one, and this module already builds `time_index`
  that way, so reuse that idiom rather than inventing a second one. Decide whether the
  6-class figures change at all — if they do, that is worth knowing before the commit,
  not after.

  **Step 0 findings and rulings** (verified 2026-09-04 by running the fuel functional test
  on the current tree, both parameter files):

  - **The short write is real.** Under `parameter_files/fates_params_moss.json`
    (`num_fuel_classes == 8`), `fuel_out.nc` carries
    `litter_class = 1, 2, 3, 4, 5, 6, _, _`. netCDF raises nothing:
    `FatesUnitTestIOMod::WriteVar1DInt` calls `nf90_put_var(ncid, varID, data(:))`, which
    takes its element count from the six-element array constructor and leaves elements 7-8
    at the default integer fill. No `_FillValue` attribute is registered, so xarray reads
    the coordinate as int32 `[1 2 3 4 5 6 -2147483647 -2147483647]` — an index coordinate
    carrying two sentinels, not NaN.
  - **Ruling: the bar charts are not mislabelled. Cut that half of the claim.**
    `fuel_test.py` sizes its label list from `fuel_dat.sizes["litter_class"]` and slices
    with `isel(litter_class=i)`, positionally; it never reads the coordinate's values.
    Confirmed on the 8-class `Fuel loading` figure — `live_moss`/`dead_moss` are labelled
    on fuel models 1080/1081 and zero on 108, matching `FatesFuelClassesMod`'s documented
    1-8 ordering. `WriteFireData` has exactly one caller (`FatesTestFuel.F90`), and
    nothing else in the tree, Fortran or Python, reads `litter_class` values. The fix is
    warranted by the wrong coordinate alone; no figure changes under either file.
  - **Ruling: fix shape.** An allocatable `litter_index(num_fuel_classes)` filled by a
    `do` loop, matching the `time_index` block immediately above it, passed to `WriteVar`.
    Not an inline `[(i, i = 1, num_fuel_classes)]` constructor — reuse the module's one
    existing idiom. Size it from `num_fuel_classes`, matching the `RegisterNCDims` call
    two lines up, not from `size(loading, dim=1)`.
  - **Ruling: fix the stale comment above `time_index`.** It reads `! create pft indices`
    over a loop that fills time indices. The new block lands beside it, so a wrong comment
    on the line the new code imitates is worth one line of diff. This is a comment
    correctness fix, not whitespace churn.
  - **Ruling: the 6-class output must be unchanged**, since the fix reproduces `1..6`
    exactly there. Step 2 demonstrates that against the pre-fix baselines rather than
    asserting it.
  - **Deferred to Task 5** (a finding, not Task 0's scope): `FatesTestFuel.F90:79`
    branches on a literal `num_fuel_classes == 8` where
    `fuel_classes%moss_classes_present()` exists — the same thing Task 4 Step 2 forbids in
    new code. Left alone because Task 0's Files list is one file.
- [x] **Step 1: fix the write** so the coordinate is generated from `num_fuel_classes`.
- [x] **Step 2: verify under both parameter files.** Run the fuel test with the default
  file and with `fates_params_moss.json`; confirm the coordinate now reads 1–6 and 1–8
  respectively, and inspect the loading bar charts under `src/fates/_run/plots/fuel/` for
  correct class labels. Note whether the 6-class figures are unchanged.
- [x] **Step 3: reviews, then commit.**

---

### Task 1: pFUnit coverage for the proxy and its pure-function consumers

**Summary for another engineer.** A model has a diagnostic "how wet is the moss" number,
computed as the larger of two normalized wetness measures, plus two pure functions of it
that scale photosynthesis. None of it has unit tests. This task writes them. The work is
almost entirely test design rather than implementation: the code already exists and
already works, so the difficulty is choosing input values that would actually catch a
mistake, and proving each assertion catches one.

1. Because the implementation predates the tests, a green first run is not evidence.
   Every assertion has to be seen failing under a deliberate mutation of the code it
   covers before it counts. Each mutation is committed and then reverted by a commit, so
   the red-green record survives in the history and nothing uncommitted is ever at risk.
2. One routine under test is `private` and must be made public to be callable. There is
   existing precedent in this file's neighbourhood for doing that with an explanatory
   comment; follow it rather than duplicating the routine's arithmetic in the test.
3. Adding a `.pf` file to an *existing* pFUnit directory silently disables it — the suite
   compiles, links, and is never called, and the run is green. Use a new directory.

**Files:**
- Create: `src/fates/testing/tests/unit/moss_fwet_test/` (directory, `CMakeLists.txt`, and
  `test_MossFwet.pf`) — generate with
  `./generate_empty_test.py unit --test-name moss_fwet`, which performs all four
  registration steps
- Modify: `src/fates/testing/CMakeLists.txt` and `src/fates/testing/config/unit.cfg`
  (both written by the generator; verify rather than hand-edit)
- Modify: `src/fates/biogeophys/LeafBiophysicsMod.F90` — add `public :: MossCO2FilmFactor`

**Interfaces:**
- Consumes: `fates_patch_type::UpdateMossFwet(fwet_veg, h2o_vol_top, watsat_top)` and
  `::UpdateMossWetnessScaler()` (`biogeochem/FatesPatchMod.F90`);
  `LeafBiophysicsMod::MossCO2FilmFactor(fwet_moss)`; the host scalars
  `hlm_moss_vcmax_fwet_thresh` (`main/FatesInterfaceTypesMod.F90`) and
  `lb_params%moss_co2_film_min`, both of which the test sets itself because no parameter
  file reaches a pFUnit test.
- Produces: `public :: MossCO2FilmFactor` in `LeafBiophysicsMod`, which Task 3 also uses.

- [x] **Step 0 (orchestrator):** Settle the case table — the `(fwet_veg, h2o_vol,
  watsat)` triples and the threshold values — against `designing-unit-test-cases`, so no
  two inputs coincide and no expected value can be produced by the wrong branch. At
  minimum the table must separate: soil ingredient larger, canopy ingredient larger, the
  upper clamp at and past saturation, the lower clamp, and the `watsat_top > nearzero`
  guard exercised with the `-999` sentinel `wrap_btran` actually writes into `watsat_sl`
  (not a bare zero). For the scaler, pick proxy values below, at and above
  `hlm_moss_vcmax_fwet_thresh` whose results are mutually distinct. For
  `MossCO2FilmFactor`, decide which of the two clamps the test pins: the routine's header
  comment claims the outer floor binds from `fwet ≈ 0.684` upward and the inner one never
  binds at the default — confirm that from the code before writing an assertion that
  depends on it, and if it is wrong, that is a finding about the code, not a reason to
  weaken the test. Confirm the patch object can be declared and used without `Init()` (the
  routines touch four scalar members) and that no globals init is needed. Decide whether
  `nearzero` and the sentinel belong in the test as named constants.

  **Step 0 findings and rulings** (2026-09-04). These are binding on the implementer;
  where one conflicts with the implementer's own judgement, it raises the conflict rather
  than quietly doing something else.

  **Confirmations.**

  - The header comment on `MossCO2FilmFactor` is **correct**, so assertions may depend on
    it. `(1-fwet)**12 = 1e-6` at `1-fwet = 10**(-0.5) = 0.316228`, i.e. `fwet = 0.68377`;
    and `co2_film_dryfrac_min**12 = 0.1**12 = 1e-12`, four orders below the default outer
    floor, so the inner clamp cannot change the result at any default-ish setting. No
    finding against the code.
  - The patch needs no `Init()` and no `InitializeGlobals`. `validate_cohorts_test` already
    declares a bare `type(fates_patch_type) :: patch` and calls a type-bound procedure on
    it; `fates_patch_type` is `type, public`, its `contains` block has no `private`, so
    both `UpdateMossFwet` and `UpdateMossWetnessScaler` are callable. The only module state
    either routine reads is `hlm_moss_vcmax_fwet_thresh` and `nearzero`.
  - `lb_params` is a public module variable, so `lb_params%moss_co2_film_min` is settable
    directly. Nothing else in `LeafBiophysicsMod` needs initialising for this one function.

  **Fixture.** Follow `test_FireFuel.pf`: the patch is a component of the `@TestCase` type,
  seeded in `setUp`, with no `tearDown` (nothing to undo — the host scalars are module
  variables that `setUp` rewrites on every test, which is the reason `test_FireFuel.pf`
  gives for doing it there).

  `setUp` seeds all four patch members with **distinct negative markers** —
  `marker_fwet = -1`, `marker_soil = -2`, `marker_canopy = -3`, `marker_scaler = -4` — so
  that "never written" and "written from the wrong source" are both visible, and so that no
  marker can be confused with an expected value (every expected value is in `[0,1]`).
  Uninitialized-variable checking is off in this build, so an unseeded scalar reads as
  whatever the stack held; the markers are not optional.

  **Host scalars are deliberately not the namelist defaults**, and the file says so in the
  wording `test_FireFuel.pf` already uses for its own coefficients — the tests must not
  depend on values the host may retune. Two different thresholds are used on purpose, so
  that replacing `hlm_moss_vcmax_fwet_thresh` with a literal fails somewhere:

  | Constant | Value | Used by | Note |
  |---|---|---|---|
  | `test_vcmax_thresh` | `0.5` | the `UpdateMossFwet` cases | namelist default is 0.6 |
  | `test_vcmax_thresh_scaler` | `0.25` | the scaler trio | second value kills a hardcoded threshold |
  | `test_co2_film_min` | `4.0e-6` | the film cases | namelist default is 1.0e-6 |
  | `test_co2_film_min_tiny` | `1.0e-15` | the inner-clamp case only | below `0.1**12`, the only regime the inner clamp acts in |

  **`nearzero` is not imported.** The guard's threshold is pinned from outside by a fixed
  pair that brackets it, `watsat_below_nearzero = 2.5e-31_r8` and
  `watsat_above_nearzero = 2.0e-30_r8` — a quarter of `nearzero` and twice it — each with a
  comment saying where it sits relative to `FatesConstantsMod`'s `nearzero` and that the
  tightness is the point.
  Importing `nearzero` and deriving a value from it would make the test follow the constant
  wherever it moved, which is the opposite of pinning it.
  The sentinel **is** a named constant, `watsat_sentinel = -999.0_r8`, with a comment naming
  `wrap_btran` in `src/utils/clmfates_interfaceMod.F90` as its writer.

  **Case table for `UpdateMossFwet`** — `hlm_moss_vcmax_fwet_thresh = test_vcmax_thresh`
  (0.5) throughout. Every value is dyadic, so every expected result is exact; the
  `tolerance=tol` on each assert is slack, not a fudge. Each case asserts all four members.

  | Test name | `fwet_veg` | `h2o_vol_top` | `watsat_top` | → soil | canopy | proxy | scaler |
  |---|---|---|---|---|---|---|---|
  | `UpdateMossFwet_SoilWetterThanCanopy_ProxyTakesSoil` | 0.125 | 0.1875 | 0.5 | 0.375 | 0.125 | 0.375 | 0.75 |
  | `UpdateMossFwet_CanopyWetterThanSoil_ProxyTakesCanopy` | 0.3125 | 0.0625 | 0.5 | 0.125 | 0.3125 | 0.3125 | 0.625 |
  | `UpdateMossFwet_WaterAtPorosity_SoilSaturationIsOne` | 0.0625 | 0.375 | 0.375 | 1.0 | 0.0625 | 1.0 | 1.0 |
  | `UpdateMossFwet_WaterAbovePorosity_SoilSaturationClampedToOne` | 0.0625 | 0.375 | 0.25 | 1.0 | 0.0625 | 1.0 | 1.0 |
  | `UpdateMossFwet_NegativeSoilWater_SoilSaturationClampedToZero` | 0.1875 | -0.125 | 0.5 | 0.0 | 0.1875 | 0.1875 | 0.375 |
  | `UpdateMossFwet_SentinelPorosity_GuardZeroesSoilIngredient` | 0.4375 | -999.0 | -999.0 | 0.0 | 0.4375 | 0.4375 | 0.875 |
  | `UpdateMossFwet_PorosityBelowNearzero_GuardZeroesSoilIngredient` | 0.4375 | 0.75 | 2.5e-31 | 0.0 | 0.4375 | 0.4375 | 0.875 |
  | `UpdateMossFwet_PorosityAboveNearzero_GuardAdmitsSoilIngredient` | 0.0625 | 5.0e-31 | 2.0e-30 | 0.25 | 0.0625 | 0.25 | 0.5 |

  Four things about that table are load-bearing and belong in the tests' detailed
  descriptions:

  1. **The sentinel case carries the sentinel in `h2o_vol_top` as well**, which is what
     `wrap_btran` writes into both fields in its else branch. This is not decoration. With a
     valid positive `h2o_vol_top` beside a sentinel `watsat_top`, deleting the guard yields
     a negative ratio that the lower clamp returns to zero — the same answer the guard
     gives — and the case passes with the guard gone. Both fields sentinel makes the ratio
     exactly 1, so a deleted or inverted guard shows up as `1.0` against an expected `0.0`.
  2. **The sub-`nearzero` case is the only one that pins the threshold as positive.**
     Changing `nearzero` to a bare `0.0` leaves the sentinel case unmoved (`-999` fails
     either test) and is caught here alone. It is beyond the minimum this step asked for and
     is included for that reason.
  3. **`WaterAtPorosity` cannot pin the upper clamp**, because a setup already at the limit
     behaves the same whether the limit is enforced or absent; it pins that saturation reads
     as exactly 1. `WaterAbovePorosity` is its twin and is the one that catches a dropped
     clamp. The two differ in `watsat_top` and nothing else. Say so in both, and note that
     soil, proxy and scaler all read `1.0` in both, so a swapped-member write is caught in
     those two cases only by `fwet_moss_canopy` and the markers. Note also that this case
     holds `h2o_vol_top` and `watsat_top` equal, which is what puts it at the limit but also
     makes it blind to a transposition of the two arguments; the other cases catch that.
  4. **The two `Nearzero` cases are a pair, and the above case is the one that has to grow
     into acceptance.** The five ordinary cases sit 28 or more orders of magnitude above
     `nearzero`, so on their own they leave the guard's threshold pinned only to lie
     somewhere below the smallest of them: replacing `nearzero` with `1.0e-3` passes all of
     them. `watsat_above_nearzero` is twice `nearzero`, so it is the case that constrains
     the threshold from above, and its expected soil saturation is exactly `0.25` because
     `5.0e-31` and `2.0e-30` differ by a power of two. Its twin below is the case that
     constrains the threshold from below, and it alone catches `nearzero` replaced by a bare
     `0.0`. Name the twin in both descriptions, and say that the bracket is deliberately
     tight: at a quarter of `nearzero` below and twice it above, the two together pin the
     threshold to within a factor of eight, where a merely "far below" rejection case would
     leave ten orders of magnitude of it free.

  **Case table for `UpdateMossWetnessScaler`** — `hlm_moss_vcmax_fwet_thresh =
  test_vcmax_thresh_scaler` (0.25). Each test sets `patch%fwet_moss` directly and calls the
  routine, which is how restart and patch fusion call it.

  | Test name | `fwet_moss` | → scaler |
  |---|---|---|
  | `UpdateMossWetnessScaler_ProxyBelowThreshold_ScalesLinearly` | 0.125 | 0.5 |
  | `UpdateMossWetnessScaler_ProxyAtThreshold_ReachesFullCapacity` | 0.25 | 1.0 |
  | `UpdateMossWetnessScaler_ProxyAboveThreshold_ClampedToFullCapacity` | 0.625 | 1.0 |

  This step asked for three results that are mutually distinct. **They cannot be**: at and
  above the threshold both give exactly 1, which is what the clamp is for. Ruling: keep all
  three, and have each detailed description say what its case pins — the below case is the
  only one whose result is not 1, and the above case is the only one that catches a dropped
  `min`. The at case pins nothing the other two do not: `min` encodes no boundary that could
  be inclusive or exclusive, so at a ratio of exactly 1 it returns the same value whether it
  is there or not. Its description must say that it documents the design intent at the
  threshold — the namelist describes it as the value "at and above which" moss performs
  fully — and must not claim it pins an inclusive boundary.

  Each of the three also asserts that `fwet_moss_soil` and `fwet_moss_canopy` still hold
  their `setUp` markers: the routine must leave the two ingredients alone, and the restart
  and fusion callers depend on that. It does **not** assert that `fwet_moss` is unchanged,
  and the descriptions must not claim the trio shows the routine "writes the scaler and
  nothing else" — a clobber of `fwet_moss` itself is caught instead by the proxy assertion
  in every `UpdateMossFwet` case, which is read after the refresh call. Say that, and name
  where the coverage lives, rather than adding a fourth assertion here that would owe its
  own mutation.

  **Case table for `MossCO2FilmFactor`** — `lb_params%moss_co2_film_min = test_co2_film_min`
  (4.0e-6) except where noted. At that floor the outer crossover sits at `fwet = 0.6450`.

  | Test name | `fwet_moss` | floor | → expected |
  |---|---|---|---|
  | `MossCO2FilmFactor_DryMoss_NoAttenuation` | 0.0 | 4.0e-6 | 1.0 |
  | `MossCO2FilmFactor_BelowOuterFloorCrossover_PowerLawSets` | 0.375 | 4.0e-6 | 3.5527136788005009e-3 |
  | `MossCO2FilmFactor_AboveOuterFloorCrossover_OuterFloorSets` | 0.75 | 4.0e-6 | 4.0e-6 |
  | `MossCO2FilmFactor_FloorBelowInnerClamp_InnerClampSets` | 0.9375 | 1.0e-15 | 1.0e-12 |

  Ruling on which clamp is pinned: **both**. The outer one is pinned by the second and third
  cases, which bracket the crossover; the third asserts the floor's actual value, so a
  hardcoded `1.0e-6` in the source fails it. The inner one cannot be pinned at any floor the
  host would really set — that is the header's own claim — so the fourth case drops the
  floor below `0.1**12` deliberately, which the header names as the sole regime in which the
  inner clamp has any effect. Without it the inner `max` is dead code as far as this suite
  knows, and its removal would pass everything.

  Two notes for the implementer on that table: `0.375` rather than `0.5` in the second case,
  because `0.5` is symmetric under `1-fwet` and would not catch that flip; and the fourth
  case needs its own tolerance, `tol_film_inner = 1.0e-24_r8`, because the file's
  `tol = 1.e-13_r8` is only a tenth of its expected value of `1.0e-12` — an absolute
  tolerance that is generous slack everywhere else in the file is a relative bound of 0.1
  here, where `1.0e-24` restores a relative bound comparable to the rest. (An earlier
  version of this ruling said `tol` was a hundred times the expected value and would let the
  case pass against zero; both halves were wrong — the hundredfold ratio is between `tol`
  and the *floor* the case sets, `1.0e-15`, which the inner clamp overrides. The tolerance
  value was right for the wrong reason.) `3.5527136788005009e-3` is
  `0.625**12` and is exact in binary; give it as a literal with that provenance in the
  comment rather than recomputing the power in the test.

  **Naming.** Follow the local convention in `test_FireFuel.pf` —
  `<Routine>_<Condition>_<Branch>`, CamelCase, no `test_` prefix — which already carries the
  condition and the branch that `designing-unit-test-cases` requires.

  **The binding limit is 63 characters, not 90.** The `pfunit-tests` skill documents a
  90-character budget on the mangled global symbol `<module>_mp_<PROCEDURE>`, overflow of
  which is only `warning #5462`. What stops the build first is Fortran's 63-character limit
  on the bare subroutine name — `ifx error #6439`, a hard error — which bites 27 characters
  earlier. So the budget is 63 on the test name alone. Under it,
  `UpdateMossWetnessScaler_ProxyAboveThreshold_ClampedToFullCapacity` (65) does not compile
  and is named `UpdateMossWetnessScaler_ProxyAboveThreshold_HeldAtFullCapacity` (62)
  instead; every other name in both tables fits. Carry the skill correction to Task 5.
- [x] **Step 0b (orchestrator):** This task's review round adds a **third reviewer**,
  because `writing-tests-before-the-implementer` requires it and this task's Step 7 does
  not satisfy it on its own. All of this task's coverage is retrofitted to code that
  already landed, so there is no red-first evidence anywhere in it, and for that case the
  skill splits the mutation duty: the test author mutates every assertion it lands, **and
  a reviewer independently mutates, choosing its own mutations rather than re-running the
  author's**. A test that catches only the mutation its author had in mind reads as
  coverage without being coverage — and this Step 0 block prescribes most of the author's
  mutations, which makes the point sharper here, not softer.

  Mechanics, so this costs no commits and risks nothing: the mutation reviewer edits the
  source in place and **restores by editing back** — never `git checkout`, `git restore`,
  `git stash` or `git clean`, per the Global Constraints — and finishes by showing
  `git status` clean and `git diff` empty in `src/fates`. The orchestrator re-checks that
  before proceeding. It runs **alone**, after the spec-compliance and code reviewers have
  returned, so that no other agent is reading a tree it is transiently mutating. Sam's
  budget of seven FATES commits for this task is therefore unaffected.
- [x] **Step 1: make `MossCO2FilmFactor` public**, with a short comment saying a unit test
  needs it and that restating its arithmetic in the test would let the two drift — the
  same justification `FatesFuelMod` already carries for `MoistureOfExtinction` and
  `max_grass_frac`. Match that wording rather than inventing a new one.
- [x] **Step 2: generate the test directory** and confirm all four registration points
  landed: the directory, its `CMakeLists.txt`, the `add_subdirectory` line under
  `## Unit tests` in `testing/CMakeLists.txt`, and the `[moss_fwet]` section in
  `config/unit.cfg` with `test_dir = fates_moss_fwet_utest`.
- [x] **Step 3: write the tests** per the Step 0 table. Set the host scalars in `setUp`,
  and reset them there too — they are module variables that persist across tests, which is
  why `test_FireFuel.pf` resets its own. Write asserts in pFUnit's `assertEqual(expected,
  actual)` order even though most existing FATES tests do the reverse.
- [x] **Step 4: run and prove they ran.** `./run_unit_tests.py -t moss_fwet`. The runner's
  `out of 1` summary is not evidence; run
  `src/fates/_build/testing/fates_moss_fwet_utest/MossFwet -v` and read its `(N tests)`
  line and the test names.
- [x] **Step 5: build check.** This task edits a non-test FATES source file, so run the
  CTSM build in `test-bld-adrianna-moss-grass-pft/`. Do not pipe `qcmd -- ./case.build`
  into `tail`/`head` — the exit status becomes the pager's. Redirect to a file, echo `$?`,
  and grep for `MODEL BUILD HAS FINISHED SUCCESSFULLY`. If it fails for a git-related
  reason, do not touch git state: stop and ask Sam.
- [x] **Step 6: reviews, then commit the tests in `src/fates/` only.** Hold the CTSM
  pointer bump until Step 9 — the mutation round below adds more FATES commits, and the
  pointer should land on the last of them.
- [x] **Step 7: mutation-check every assertion, one commit per routine.** The
  implementation predates these tests, so a green first run is not evidence: an assertion
  counts only once it has been seen failing. Do one mutation/revert pair per routine under
  test — `UpdateMossFwet`, `UpdateMossWetnessScaler`, `MossCO2FilmFactor` — so three pairs.
  Each pair: **commit** that routine's full set of perturbations together (for
  `UpdateMossFwet`: swap the `max` for a `min`, drop each clamp, invert the `watsat`
  guard), run the suite, then **`git revert` that commit** — never `git checkout` or
  `git restore`. The red-green record therefore lives in the FATES history as three
  mutation/revert pairs, and no uncommitted work is ever at risk.

  Read the run two ways: every assertion covering that routine must fail, and no assertion
  outside it may. Where a combined mutation makes attribution ambiguous — an assertion that
  could be failing for a perturbation other than the one it targets, or one whose expected
  value a second perturbation could coincidentally restore — split that single assertion
  into its own pair rather than leaving it unproven. Record which perturbation each
  assertion caught.

  **Step 0 ruling — one split is known in advance.** Every `UpdateMossFwet` case asserts
  `moss_wetness_scaler`, which pins that `UpdateMossFwet` refreshes the scaler at all. In
  the combined mutation that assertion is unattributable: a broken `soil_saturation` and a
  deleted `call this%UpdateMossWetnessScaler()` both redden it. So budget a **fourth**
  pair whose only perturbation is deleting that call. Its proof is two-sided — the scaler
  assertions must fail while the soil, canopy and proxy assertions in the same tests all
  still pass. That is the "one more pair" the Git choreography already allows for, taking
  this task to nine FATES commits rather than seven.

  Add to the perturbation lists the plan sketches: for `UpdateMossWetnessScaler`, drop the
  `min` and separately replace `hlm_moss_vcmax_fwet_thresh` with a literal `0.5` (the
  second is why the scaler trio runs at a different threshold from the `UpdateMossFwet`
  cases); for `MossCO2FilmFactor`, drop each `max` in turn, flip `1.0_r8 - fwet_moss` to
  `fwet_moss`, and change the exponent.

  Finish with the anti-retrofit check from `writing-tests-before-the-implementer`, run
  from the `src/fates` root so the pathspec is not silently scoped to a subdirectory:
  `git diff <test-commit>..HEAD -- ':(top)testing/tests/unit/moss_fwet_test/'` must come
  back empty. If Step 8 forces a test to change, that is a finding: its own commit, and
  the reason in the hand-off.
- [x] **Step 8: close any gap the mutation round exposed.** An assertion that no mutation
  reaches is not a test — replace it, and re-run its mutation. If a mutation the tests
  *should* catch passes even after that, stop and report: per the Process section that is
  a capability that does not work, not a note to file.
- [x] **Step 9: bump the CTSM submodule pointer and `.gitmodules` fxtag** in one CTSM
  commit, then present.

---

### Task 2: functional-test scaffolding and the designed scenario ladder

**Summary for another engineer.** Stand up a new standalone Fortran driver in an existing
test harness — a program that links the model library, runs a handful of routines outside
any host model, writes netCDF, and hands off to a Python class that draws it. The physics
content is deliberately trivial at this stage: a short table of hand-chosen input triples
run through one routine. The point of the task is that the plumbing works end to end and
that a reviewer can reject the scaffolding independently of the science that lands on top
of it next.

1. The harness has a generator that does the registration; use it rather than copying an
   existing test directory, and then check the registration by hand, because a test that
   is built but not registered runs silently never.
2. This is a new top-level group in the test tree, and Python package discovery walks it —
   an empty `__init__.py` is needed one level above what the generator creates, or the
   plotter is never imported and the run warns rather than fails.

**Files:**
- Create: `src/fates/testing/tests/functional/moss/fwet/` — generate with
  `./generate_empty_test.py functional --test-name fwet --test-sub-dir moss`, giving
  `test_Fwet.F90`, `fwet_test.py`, `CMakeLists.txt`, `__init__.py`
- Create: `src/fates/testing/tests/functional/moss/__init__.py` (empty — the generator
  does not make this one, and `pkgutil.walk_packages` needs it)
- Modify: `src/fates/testing/CMakeLists.txt`, `src/fates/testing/config/functional.cfg`
  (generator-written; verify)

**Interfaces:**
- Consumes: `FatesUnitTestParamReaderMod::ReadParameters`,
  `FatesArgumentUtils::command_line_arg`, `FatesUnitTestIOMod` (`OpenNCFile`,
  `RegisterNCDims`, `RegisterVar`, `EndNCDef`, `WriteVar`, `CloseNCFile`);
  `fates_patch_type::UpdateMossFwet`.
- Produces: the driver executable and its netCDF output file, whose name and scenario
  dimension Task 3 extends rather than replaces.

- [ ] **Step 0 (orchestrator):** Fix the names and the layout, because Tasks 3 and 4 build
  on them: the config section name, the `out_file` name, the netCDF dimension and variable
  names, and the scenario table itself. Decide whether the scenario table is shared with
  Task 1's case table or deliberately different (they answer different questions — one
  asserts, one illustrates — so identical values may be the wrong call). Confirm the
  generator's naming (`test_Fwet.F90`, `Fwet_exe`, class `Fwet`) against the older
  hand-written convention (`FatesTestFuel.F90`, `FATES_fuel_exe`) and rule on which this
  test follows. Confirm `use_param_file = True` and that no `datm_file` entry is needed
  yet. Decide how the host scalars the driver must set by hand are grouped and commented —
  `FatesTestFuel.F90` has a block comment for exactly this, and its reasoning should be
  reused, not restated differently.
- [ ] **Step 1: generate the test** and add `moss/__init__.py`. Verify all four
  registration points plus the package file.
- [ ] **Step 2: write the driver.** Read the parameter file from `argv(1)`; set the host
  scalars that would otherwise come from the CTSM namelist; run the scenario table through
  `UpdateMossFwet` and `UpdateMossWetnessScaler`; capture the proxy, both ingredients and
  the scaler per scenario.
- [ ] **Step 3: write the netCDF output**, including the scenario names as a character
  variable and the host scalars the run used, so a figure can be traced back to its
  settings.
- [ ] **Step 4: write the plotter.** One figure: proxy, both ingredients and the scaler per
  scenario, with the scenario names as labels. Index with named dimensions
  (`arr.isel(...)`), never positionally — output arrays come back with dimensions reversed
  relative to the Fortran declaration, and getting it wrong produces plausible wrong
  numbers that mimic a physics bug.
- [ ] **Step 5: run it.**
  `MPLBACKEND=Agg python run_functional_tests.py --save-figs -t <name>` from
  `src/fates/testing`, then inspect the PNG under `src/fates/_run/plots/<name>/`. Use
  `-c/--clean` after the `CMakeLists.txt` changes. Confirm the other four functional tests
  still build — `-t` selects what runs, not what builds, so a compile error anywhere fails
  the run.
- [ ] **Step 6: reviews, then commit.**

---

### Task 3: the year-long surrogate-driven trajectory

**Summary for another engineer.** Extend the driver from the previous task with a
365-day time series: read an existing daily weather file, push it through a small
made-up canopy-and-soil water model, and plot what the diagnostic does with the result.
The made-up model is the delicate part. It exists only to generate inputs with a realistic
shape — spiky after rain, smooth underneath, frozen in winter — and it is not the thing
under test. Everything about it, in the code, in the file metadata and on the figure, has
to say so, because the figure it produces looks exactly like a model-validation plot and
will be read as one otherwise.

1. The diagnostic consumes *total* soil water, liquid plus ice, on purpose: frozen ground
   means frozen moss, which suppresses fire. The winter behaviour of the surrogate should
   exercise that rather than paper over it.
2. The canopy half of the diagnostic is capped by a host parameter at 0.05, so it almost
   never wins against the soil half. That is a known limitation of the design, not a bug
   to tune away, and the figure should make the ceiling visible.

**Files:**
- Modify: `src/fates/testing/tests/functional/moss/fwet/` driver and plotter (both from
  Task 2)
- Modify: `src/fates/testing/config/functional.cfg` — add the `datm_file` entry

**Interfaces:**
- Consumes: `FatesTestFireMod::ReadDatmData(nc_file, temp_degC, precip, rh, wind)` from
  `tests/functional/fire/shr/`, already compiled into the `fates` library for every test
  (`src/fates/CMakeLists.txt` adds `fire/shr` as `fire_share`), so no CMake change is
  needed to call it; `tests/data/BONA_datm.nc`;
  `LeafBiophysicsMod::MossCO2FilmFactor` (made public in Task 1).
- Produces: the time-series half of the netCDF output, which Task 4 adds two variables to.

- [ ] **Step 0 (orchestrator):** Fix the surrogate's *requirements*, not its equations —
  the implementer chooses the functional forms and coefficients, and the extra reviewer
  named below checks them. The requirements to settle here: that it is one canopy store
  and one soil bucket and nothing more elaborate; that `fwet_veg` cannot exceed CTSM's
  `maximum_leaf_wetted_fraction` of 0.05, because the real ceiling is what makes the soil
  ingredient dominate; that a freeze period holds total soil water rather than draining it,
  since the proxy consumes liquid plus ice; that the year contains at least one visible
  dry-down; and how the surrogate is labelled in the driver, in the netCDF metadata and on
  the figure. Also confirm `ReadDatmData` is reachable from a driver outside `fire/` and
  that adding `datm_file` to the config is all the harness needs, and confirm the BONA
  record's length and that it actually contains a freeze period and a dry-down — if it
  does not, those claims are not demonstrable from this file, and that is a finding to
  report, not something to work around by inventing weather.
- [ ] **Step 0b (orchestrator):** This task's review round adds a **third reviewer**,
  scoped to the surrogate alone: is it as simple as the requirements allow, is it
  unmistakably labelled as not-CTSM everywhere it surfaces, and does any part of the driver
  or the figure invite a reader to treat it as a model result? Dispatch it alongside the
  spec-compliance and code reviewers at step 3 of the loop.
- [ ] **Step 1: read the DATM record** and confirm the series lengths and units.
- [ ] **Step 2: implement the surrogate** as its own clearly-named, clearly-commented
  routine, kept separate from the FATES calls so no reader can mistake one for the other.
- [ ] **Step 3: run the trajectory** through `UpdateMossFwet`, `UpdateMossWetnessScaler`
  and `MossCO2FilmFactor`, one step per day, and record all of it.
- [ ] **Step 4: extend the netCDF output** with the time-series variables and the
  surrogate's parameters and provenance.
- [ ] **Step 5: extend the plotter** with the trajectory figure: precipitation, the proxy
  and both ingredients, the scaler, and the CO₂ film factor on a shared time axis, with
  the canopy ceiling drawn.
- [ ] **Step 6: run it and read the figure.** Confirm what the figure actually shows
  against the Task 8 Step 4 language — the canopy ingredient spiking and decaying, the
  soil ingredient smooth, the proxy tracking the larger. If the surrogate does not produce
  that shape, fix the surrogate; if the *proxy* does not follow it, that is a finding about
  FATES and a stop.
- [ ] **Step 7: reviews, then commit.**

---

### Task 4: the moss fuel-moisture panel, and the two-parameter-file check

**Summary for another engineer.** Add the last consumer to the plot: two fire fuel classes
whose moisture is a linear function of the same diagnostic. They exist only when the run
is given a parameter file that declares them, and the whole test must still work — and
still be readable — when it is not. So this task is really about conditional behaviour:
one code path where the classes are present, one where they are absent, and an output that
says which one ran rather than silently dropping a panel.

1. The moisture routine zeroes everything unless the fuel object carries some load, so
   this needs a populated synthetic fuel stand, not an empty one; the fire tests already
   have such stands and a helper that builds them.
2. Verification here means running the whole functional suite twice under two different
   parameter files, because the runner passes one file to every test in an invocation.

**Files:**
- Modify: `src/fates/testing/tests/functional/moss/fwet/` driver and plotter

**Interfaces:**
- Consumes: `FatesFuelMod::fuel_type` (`Init`, `UpdateLoading`, `SumLoading`,
  `CalculateFractionalLoading`, `UpdateFuelMoisture`, `effective_moisture`);
  `FatesTestFireMod::SetUpFuel`; `SyntheticFuelModels::fuel_models_array_class`;
  `FatesFuelClassesMod::fuel_classes` (`moss_classes_present`, `live_moss`, `dead_moss`);
  `SFNesterovMod::nesterov_index`; `SFParamsMod::SF_val_SAV`, `SF_val_drying_ratio`;
  the four `hlm_moss_fuel_moisture_*` host scalars.
- Produces: nothing later tasks consume.

- [ ] **Step 0 (orchestrator):** Choose the synthetic fuel model to load the stand from —
  `FatesTestFuel` uses 1080/1081 for the moss-enabled case, and reusing one keeps the two
  tests comparable. Decide the fuel-moisture coefficient values and whether they match
  `FatesTestFuel`'s or the CTSM namelist defaults, and say why. Decide how the absent-panel
  case is communicated: an integer `num_fuel_classes` in the output plus an explicit note
  on the figure is the intent, but confirm the plotter can render that cleanly.
  `UpdateFuelMoisture` needs a `fire_weather` object even though the moss classes ignore
  it — decide whether the Nesterov index is driven from the same DATM record (which also
  lets the figure show moss moisture against the NI-driven classes) or held fixed.
  Confirm the effective-moisture normalization by moisture of extinction is what the panel
  should plot, since that is what determines whether a class burns.
- [ ] **Step 1: build the fuel stand** and update its moisture per day from the Task 3
  trajectory's proxy.
- [ ] **Step 2: branch on `fuel_classes%moss_classes_present()`**, recording
  `num_fuel_classes` in the output either way. Use the named predicate, not a literal
  `== 8`.
- [ ] **Step 3: extend the netCDF output and the plotter** with the live and dead moss
  effective moisture, and with the extinction line at 1 so the burn/no-burn crossing is
  visible.
- [ ] **Step 4: run under both parameter files.** Once with the default
  (`parameter_files/fates_params_default.json`, 6 litter classes — panel absent, note
  shown) and once with `parameter_files/fates_params_moss.json` (8 — panel present). In
  both runs confirm the other four functional tests still pass, since they receive the
  same file.
- [ ] **Step 5: reviews, then commit.**

---

### Task 5: record what these tests do and do not establish

**Summary for another engineer.** Close the loop on the documents. A verification step in
the parent plan was skipped for want of a machine; this work covers part of what it was
meant to establish and none of the rest. Write down which is which, so that nobody later
reads a green test suite as the skipped step having been done. Also file the incidental
findings the work turned up.

1. The temptation this task exists to resist is marking the parent step complete. It is
   not complete, and the reasons are specific.

**Files:**
- Modify: `docs/superpowers/plans/2026-08-19-moss-grass-pft.md` (Task 8 Step 4; the
  upstream-observations section)
- Modify: `docs/superpowers/plans/2026-09-04-moss-fwet-tests.md` (this file — tick the
  boxes)
- Modify (possibly): `.claude/skills/fates-functional-tests/SKILL.md` — its reuse
  inventory and its "all four" registration list

**Interfaces:** none.

- [ ] **Step 0 (orchestrator):** Collect the findings the earlier tasks produced and decide
  where each belongs. Known candidates, to be confirmed rather than assumed: the
  functional-test skill's registration list says "all four", but a *shared* module
  directory needs a fifth entry in `src/fates/CMakeLists.txt` (this plan avoids one, but
  the next test may not); the generator's naming diverges from the older hand-written fire
  tests; and Task 0's litter-class fix is a candidate for the parent plan's
  upstream-observations section, since it is a defect in code this branch inherited rather
  than one it introduced. Decide which of these Sam should see as a question rather than a
  note.
- [ ] **Step 1: amend the parent plan's Task 8 Step 4** to say what these tests cover and
  what still requires an ALP2 run — the `bc_in` fill, the daily-vs-subdaily meaning of
  `h2o_liqvol_sl`, restart of the three patch members, and the area-weighted history fill
  over bareground. **Leave Step 4 unticked.**
- [ ] **Step 2: file the confirmed findings** in the parent plan's upstream-observations
  section, and update the `fates-functional-tests` skill if Step 0 confirmed a gap in it.
- [ ] **Step 3: tick this plan's checkboxes** and record each task's commit.
- [ ] **Step 4: reviews, then commit.**
