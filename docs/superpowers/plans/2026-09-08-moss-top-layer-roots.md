# Moss's Soil-Water Uptake in the Top Layer — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> to implement this plan task-by-task, with the **custom orchestration loop** defined in
> "Process" below (it overrides the sub-skill's defaults where they differ). Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Get moss's soil-water uptake genuinely into soil layer 1 — exactly 1.0 there,
exactly 0.0 below — and stop FATES's non-hydro hydraulic-failure mortality from killing
moss when that layer dries.

**Architecture:** A new `fates_allom_fnrt_prof_mode` in `set_root_fraction` that puts the
entire profile in layer 1, selected for moss through `make_moss_params.py`; then one
parameter override zeroing moss's `fates_mort_scalar_hydrfailure`. No new namelist
variable, no new Fortran state, no restart field, no dormancy machinery.

**Spec:** `docs/superpowers/specs/2026-08-19-moss-grass-pft-design.md` §3 (§12 for the
accepted fictions Task 2 adds to).
**Parent plan:** `docs/superpowers/plans/2026-08-19-moss-grass-pft.md`, Task 12 Step 3f.
**Brief:** `docs/superpowers/briefs/2026-09-08-moss-top-layer-roots-and-dormancy.md` —
still the best account of the code, but **superseded on dormancy** and wrong in two places;
see Orientation.

---

## Orientation

Read this before Task 1's Step 0. It is what is true of the whole plan.

**Ordering is load-bearing: this plan runs before the parent plan's Step 3b.** 3b tunes the
moss wetness window against the distribution of `FATES_MOSS_FWET`, and Task 1 changes which
soil layer moss draws from and therefore that distribution. Run 3b first and its tuning is
against a wetness signal this plan then moves, with no way to tell afterwards which
distribution it was fitted to.

**Why the profile is not already concentrated.** Moss carries
`fates_allom_fnrt_prof_mode = 3` with `fates_allom_fnrt_prof_a` raised from grass's 11.0 to
30.0 and `fates_allom_fnrt_prof_b` left at the grass value of 2.0. Mode 3
(`exponential_2p_root_profile`, `FatesAllometryMod.F90:2860-2911`) is a half-and-half sum of
two exponentials, so the `b` limb carries exactly half the profile at a 0.5 m e-folding
depth: 24.5% of moss uptake sits in the top 2 cm, and below 0.5 m moss and grass are
numerically indistinguishable. With `b = 2.0` held, no value of `a` puts more than 52% in
the top 2 cm.

**The trap that makes the obvious approach useless.** Do **not** do this by making both
exponentials steep. `set_root_fraction` normalizes and then forces the sum to exactly 1 by
adding the residual to the largest layer (`FatesAllometryMod.F90:2849-2851`), so a profile
with large `a` *and* large `b` still leaves order 1e-14 in the deep layers. That normalizes
to a perfectly valid profile and keeps `btran_ft(moss) > 0` whenever *any* layer has liquid
water above the frozen threshold — so moss goes on drinking from a metre down whenever its
own layer is unavailable, which is the behaviour this plan exists to remove. It will look
like it worked.

**What this inherits from Step 3e.** `fates_allom_l2fr = 0`: moss builds and maintains no
fine roots, so it pays no fine-root maintenance respiration. The rooting *profile* is
independent of that carbon pool — `bc_out%rootr_pasl` is built from the profile mode and its
shape parameters, weighted by leaf-area-weighted stomatal conductance, with fine-root
biomass entering nowhere (`EDBtranMod.F90:151-214`).

### Decisions taken at the 2026-09-08 gate (Sam)

1. **The new mode is number 5, not 4.** This tree's `set_root_fraction` supports 1–3; the
   NVP branch uses 4 for its *no-roots* profile. Skipping 4 keeps the parameter-file
   encoding free of a collision if NVP's mode is ever harvested.
2. **No moss dormancy is built.** Moss's hydraulic-failure mortality is switched off by
   setting `fates_mort_scalar_hydrfailure = 0.0` in the moss column — one override, no
   Fortran, no `fates_moss_dormancy` namelist variable, no restart field, no history field.
   This supersedes the brief's entire "What dormancy therefore has to be" section, including
   its namelist switch and its restart discussion. F1-F5 below are why; F3 was
   subsequently cut as false and replaced by what Step 5 measured.
3. **A new case directory.** Do not reuse
   `/glade/derecho/scratch/samrabin/mosscull`; it holds the post-3e baseline that Task 1
   compares against. Not a clone of it either — see Step 5 for why, and for why its run is
   still a valid baseline.

### Findings behind decision 2

Recorded because they are not recoverable from the diff, and because F3 is what Step 3b
inherits.

- **F1. For moss, `btran` has no consumer other than soil-water extraction and `hmort`.**
  The moss parameter file sets `fates_leaf_agross_btran_model = 0` (`btran_on_ag_none`), so
  btran does not limit moss's gross assimilation or its capacity at all — deliberately, so
  that the fwet scaler is the only water limitation and it is not double-counted
  (`FatesPlantRespPhotosynthMod.F90:824-826`). Moss's carbon economy runs entirely on
  `moss_wetness_scaler` and the CO2 film factor. Hydraulic-failure mortality keyed on btran
  is therefore a vascular mechanism imported into a PFT that uses btran for nothing else.
- **F2. With the profile in layer 1, the `hmort` trigger and "layer 1 desiccated while
  thawed" are the same event.** `btran_ft(moss)` becomes layer 1's `rresis` alone, which is
  zero when layer 1 fails `check_layer_water` or sits at or below `fates_nonhydro_smpsc`
  (−255000 mm), and `get_thaw_layer_index` collapses `hmort`'s third condition to "layer 1
  is warmer than −2 °C" (`EDMortalityFunctionsMod.F90:412-451`). So a dormancy flag defined
  as the brief defines it is true on exactly the days `hmort` would fire and false on every
  other day: it is a rename of the exemption, with nothing to restart and nothing
  informative to report.
- **F3. CUT as a false claim, and replaced by the measurement (2026-09-08).** F3 predicted
  that at btran = 0 the top layer would still hold roughly 0.2-0.3 of saturation, so moss
  would sit at a third to a half of photosynthetic capacity — a Clapp-Hornberger estimate
  from the −2.55 MPa wilting point. **Step 5 measured 0.75-1.00 instead**, and the error was
  not in the soil physics but in the premise: zero btran here never means dry soil. It means
  *frozen* soil. `FATES_MOSS_FWET_SOIL` is total water over porosity, ice included by
  design, while btran counts only layers holding liquid water. So on the zero-btran days the
  layer is nearly saturated with ice, moss's wetness scaler is capped at 1.0, and moss is at
  **full** capacity rather than a third of it. The drought route to zero btran is never
  entered in this configuration at all: on all 335 days when the layer was drier than half
  saturation, btran was exactly 1.0, and the driest it ever got was 0.399.
- **F3a. What actually kills moss here is a threshold mismatch between two frozen-soil
  tests, and it is the only route by which `hmort` fires.** `hmort`'s frozen-soil exemption
  asks whether layer 1 is warmer than `soil_tfrz_thresh` = −2 °C
  (`EDMortalityFunctionsMod.F90:192-195`). btran asks, through `check_layer_water`, whether
  the layer holds liquid water. Between −2 °C and 0 °C both are satisfied at once: the
  exemption is open because the layer is "thawed" by its threshold, and btran is zero because
  the water is ice. Moss then takes the full `fates_mort_scalar_hydrfailure` = 0.6/yr for
  having its water frozen. That is not an edge case here — it is every one of the 37 days
  `hmort` fires, and it strengthens decision 2 rather than weakening it: the mechanism being
  switched off is not even about desiccation.
- **F4. `fates_mort_hf_sm_threshold = 0` would be broken, not merely inelegant.** The gate
  becomes `btran <= 0`, which is reached, and the magnitude then evaluates `(0 - 0)/0`
  (`EDMortalityFunctionsMod.F90:193-195`). That is a NaN mortality rate, very likely trapped
  under `DEBUG=TRUE`. A negative threshold works only by making a condition unreachable —
  correct today because btran cannot go negative and the comparison is `<=`, neither of
  which upstream owes us — and reads on the parameter file as a nonsense value that nothing
  validates. The threshold is also the response's denominator, so it does double duty as
  trigger point and steepness. The scalar is the knob; use it.
- **F5. A genuine dormant state would need a threshold on `fwet_moss`, which is Step 3b's
  knob.** A real shutdown — respiration included — has to key on moss's own
  wetness metric, and choosing that threshold here would pre-empt 3b's wetness window with a
  number picked before 3b has any evidence. If moss should have a quiescent state, it belongs
  with 3b, where the distribution of `FATES_MOSS_FWET` is in front of you.

### Two claims in the brief are false and are cut

- **"Leaf maintenance respiration is already scaled by `moss_wetness_scaler`, which is zero
  at fwet = 0."** True as written and irrelevant: F3 shows fwet is ~0.2–0.3, not ~0, in the
  state at issue. The brief's companion claim that transpiration needs no zeroing *does*
  hold, via CTSM's `btran(p) > btran0` gate.
- **"`fates_leaf_stomatal_intercept` is what sets moss's whole-canopy `rssun`/`rssha`."**
  It is not. Moss inherits grass's `fates_leaf_stomatal_btran_model = 1`
  (`btran_on_gs_gs0`), which selects `gs0 = max(gsmin0, stomatal_intercept(ft)*btran)`
  (`LeafBiophysicsMod.F90:2234`; the un-btran'd `:2237` is the other branch), and
  moss's intercept is zeroed, so the floor `gsmin0` sets it — which is exactly what
  `LeafBiophysicsMod.F90:1183-1190` says. The comment at `make_moss_params.py:186-192` is
  nonetheless imprecise: the parameter is *read* on the moss path and merely loses to the
  floor. Task 1 fixes that wording.

---

## Global Constraints

`.claude/CLAUDE.md`, `~/.claude/CLAUDE.md` and the **parent plan's Global Constraints**
(`docs/superpowers/plans/2026-08-19-moss-grass-pft.md` § Global Constraints) apply in full
and are **not** restated here. So do the skills each dispatch names. What follows is only
what those do not carry.

- **The moss parameter file is generated.** `src/fates/tools/make_moss_params.py` builds
  `src/fates/parameter_files/fates_params_moss.json` from the default file plus explicit
  per-PFT overrides. Add overrides there and regenerate; never hand-edit the JSON.
  `src/fates/_run_moss/` is an untracked scratch copy from a functional-test run — leave it
  alone.
- **The run's parameter file is read straight from the work tree** —
  `fates_paramfile = '$SRCROOT/src/fates/parameter_files/fates_params_moss.json'` in the
  `FatesNvp` testmod — so a parameter change needs no rebuild and touches no inputdata. A
  Fortran change does need a rebuild.
- **Never write under `$DIN_LOC_ROOT`.** Hand Sam a `ctsm_pylib` script instead if an input
  dataset needs changing.
- **Never modify git state to make a build succeed.** If `./case.build` fails for a
  git-related reason the invocation is wrong, not the repo — stop and ask Sam. Never pipe
  `qcmd -- ./case.build` into `tail` or `head`; redirect to a file, echo `$?`, and grep for
  `MODEL BUILD HAS FINISHED SUCCESSFULLY`.
- **Analysis runs in `ctsm_pylib`** — `/glade/work/samrabin/conda-envs/ctsm_pylib/bin/python3`.
  Never create a Python environment and never survey which ones exist; ask Sam if something
  is missing. The Step 3e scripts and their README are in
  `diagnostics/2026-09-08-moss-extinction-diagnosis/`.
- **Deliver the clean implementation, not the literal-minimum one.** Integrate into the
  shared code path, name magic numbers, rename when scope generalizes. Where this plan's
  text and a clean design conflict — especially if a premise turns out wrong — raise it at
  Step 0 rather than shipping the worse version.

### Git choreography

Both tasks are FATES-only in content. Per task: commit in `src/fates/` first, then commit in
CTSM with the submodule pointer bump **and** the matching `[submodule "fates"] fxtag` in
`.gitmodules` in that same commit. Verify before committing that these print the same hash:

```
git ls-tree HEAD src/fates
git config -f .gitmodules submodule.fates.fxtag
```

Task 1 also touches a CTSM-side testmod, which rides in that same CTSM commit. Never push;
Sam handles that.

## Process (custom orchestration loop — REQUIRED)

The main session is the **orchestrator**. For each task, in order:

1. **Step 0 (orchestrator, not a subagent):** settle what this plan deliberately left open —
   names, test values, exactly which diagnostic answers which question — recording each
   ruling in the task's Step 0 block. Verify the task's assumptions still hold. Ask Sam
   anything genuinely unresolved, and stop while a question is open.
2. **Dispatch an implementer subagent** with the task text as amended by Step 0, the spec
   path, the checkout path, and the Global Constraints — never the whole plan. **Name the
   skills it must invoke, in the dispatch itself**, as "invoke these before you start":
   Task 1's test work names `writing-tests-before-the-implementer`, `pfunit-tests` and
   `designing-unit-test-cases`; anything touching the testmod names `ctsm-system-tests`.
3. **Dispatch a spec-compliance reviewer and a code-review subagent**, plus any extra
   reviewer the task names. Address all findings before committing. The orchestrator
   adjudicates; it does not take over the implementation.
4. **Commit** per Git choreography, ticking this plan's checkboxes in the same commit.
5. **Present the commit to Sam and STOP.** A task's review gate is never delegated:
   subagents cannot ask Sam anything.

**Tasks run strictly in order.** Task 2 does not begin until Task 1 is finished and approved.
This is load-bearing, not conventional: Task 1's run is the *off* case of Task 2's
comparison, and Task 2's parameter change is exactly what that run must not already carry.

**A failed verification is a stop.** A *claim that turns out false* — a trap that no longer
reproduces, a documented behaviour that is not real — is cut, recorded, reported, and the
work continues. A *capability that does not work* is a stop: if a step exists to confirm
something, comes back negative, and the consequence is that the deliverable can no longer do
what it was scoped to do, stop and report it. Do not pick a fallback. Documenting it as a
known limitation, dropping the affected check, and working around it are the same move —
shrinking the deliverable without Sam choosing that.

---

### Task 1: put moss's soil-water uptake in soil layer 1

**Files:**
- Modify: `src/fates/biogeochem/FatesAllometryMod.F90` (new mode in `set_root_fraction`)
- Modify: `src/fates/parameter_files/fates_params_default.json` (the mode parameter's
  `long_name`), then regenerate `fates_params_moss.json`
- Modify: `src/fates/tools/make_moss_params.py` (overrides and comments)
- Create: a new pFUnit test directory under `src/fates/testing/tests/unit/`
- Modify: `cime_config/testdefs/testmods_dirs/clm/FatesNvp/user_nl_clm` (one diagnostic)
- Modify: `docs/superpowers/specs/2026-08-19-moss-grass-pft-design.md` §3

**Produces:** a rooting profile that is exactly 1.0 in layer 1 and exactly 0.0 below for
moss; a 730-day ALP2 run that is the *off* case for Task 2; and the measured
`FATES_MOSS_FWET_SOIL` at btran = 0 that F3 estimates and Step 3b needs.

- [x] **Step 0 (orchestrator) — 2026-09-08.** Rulings:

  - **The mode is `top_layer_profile_type = 5`**, implemented as a sibling subroutine
    `top_layer_root_profile(root_fraction)` beside `exponential_2p_root_profile` and its
    two siblings, because every existing mode in that file has its own routine and the unit
    test then has a target.
  - **`long_name` propagation is confirmed.** `make_moss_params.py` loads the default JSON
    (`:448`) and mutates only `["data"]` (`_set_last_element(params[key]["data"], value)`,
    `:495`), so amending the default file's `long_name` propagates on regeneration; no
    second edit.
  - **`FATES_BTRAN_PF` is modelled on `FATES_ELONG_FACTOR_PF`, not on
    `FATES_BTRAN_SZPF`.** The existing `_SZPF` field is filled from `ccohort_hydr%btran` in
    the `group_hydr_complx` upfreq group — FATES-Hydro only, and
    `use_fates_moss` + `use_fates_planthydro` is a fatal namelist error, so it is
    identically zero in every run this project can do. Use `site_pft_r8` in
    `group_dyna_complx`.
  - **How to fill it.** `btran_ft` is a *site*-level per-PFT quantity stored redundantly on
    every patch: `btran_ed` builds it from site-level `bc_in` fields and a root profile that
    depends only on `ft`, with nothing patch-specific entering (`EDBtranMod.F90:151-190`),
    and the bareground patch is skipped by `if_bare` so its copy stays at its initialized
    0.0. So area-weight over non-bareground patches and normalize by that same area, which
    reduces to `btran_ft(ft)` exactly and spares the reader a divide-by-cover. Two things
    the `long_name` or a comment must say: it is a once-daily sample taken at the dynamics
    call, which is the cadence and the moment `hmort` reads it, not a diurnal mean; and it
    is computed for every PFT whether or not that PFT is present at the site.
  - **Test cases** (values and layer geometry are the test-writer's, per
    `designing-unit-test-cases`): mode 5 gives exactly 1.0 in layer 1 and exactly 0.0
    elsewhere, over a multi-layer column, under `max_nlevroot` compression to 1 and to an
    intermediate depth, and on a single-layer column; modes 1–3 still sum to 1 and do not
    put everything in layer 1; and one anchor pinning mode 3 with moss's `a = 30`, `b = 2`
    at 0.245 of uptake above 0.02 m, so the fact that motivated this change is guarded
    against future edits to the shared path.
  - **F6, found while settling this and recorded because Task 1 makes a dead FATES branch
    live.** The drought-phenology soil-moisture memory deliberately excludes the top soil
    layer (`rootfrac_notop = sum(rootfrac_scr(2:nlevroot))`,
    `EDPhysiologyMod.F90:1198-1217`) and carries an explicit "just in case all roots are in
    the first layer" fallback that sets `rootfrac_scr(2) = 1.0`. That branch is currently
    unreachable for every PFT; after this task it fires for moss every day, so moss's
    `smp_memory` and `liqvol_memory` come entirely from layer **2**. It is behaviourally
    inert — moss is `ievergreen`, and that case sets `elong_factor = 1.0` unconditionally
    (`:1522-1524`), never consulting the memory — but two consequences carry:
    `FATES_MEANSMP_DROUGHTPHEN_PF` and `FATES_MEANLIQVOL_DROUGHTPHEN_PF` are **not** usable
    as layer-1 desiccation diagnostics for moss, and FATES having anticipated the
    all-in-layer-1 case is evidence the new mode does not break this path. Do not build
    anything for it; check in the review that nothing else in that routine reads
    `rootfrac_scr` after the fallback mutates it.
- [x] **Step 1: write the unit tests first, in a different agent than the implementer** —
  FATES `6bef63ad6`, tests only, a new `testing/tests/unit/root_profile_test/` directory
  (a new `.pf` file in an *existing* directory is compiled, linked and never called). Eight
  cases across five PFT slots and three column geometries. Red state observed: 8 run, 4
  failures, each of the four mode-5 cases throwing from `case default`, with the three
  legacy-mode cases and the anchor green in the same run. The CTSM submodule pointer bump is
  deferred to Step 8 so it lands once for the whole task.

  Four things came out of it that later steps need:

  - **`endrun` does not abort this test binary.** `fates_endrun` → `shr_sys_abort` →
    `shr_abort_abort`, and the harness links
    `share/unit_test_stubs/util/shr_abort_mod.abortthrows.F90`, which calls pFUnit's
    `throw`. So driving an error path gives a clean per-test failure, not a dead executable.
    The dispatch had assumed the opposite.
  - **An empty `case (top_layer_profile_type)` would pass all eight tests, and no assertion
    on `set_root_fraction`'s output can tell the difference.** The routine zeroes
    `root_fraction(:)` up front, and its closing block adds `correction = 1 - sum(...)` to
    `maxloc(root_fraction)` — which is 1 for an all-zero array. So *any* unhandled mode
    already emerges as exactly 1.0 in layer 1 and 0.0 below, and the mode-5 cases fail today
    only on the thrown `endrun`. **Ruling:** the behavioural assertions stand, since the
    behaviour is what matters and they pin it; but Step 2 must state the profile explicitly
    in its own routine rather than inherit it from that coincidence, and the reviewers are
    told to check exactly that. Not worth another test round for a direct call.
  - **The `sum == 1` assertion has no test-side evidence, and is kept deliberately.** The
    correction block forces the sum whatever the profile routine returns, so only a mutation
    of that block can redden it — and the test-writer was scoped out of the source file.
    Step 2 runs that one mutation as an uncommitted probe and reports the output. It must not
    edit the test file; the review checks that file is byte-identical to `6bef63ad6`.
  - **`ifx` enforces the standard 63-character Fortran name limit** (error #6439, caret on
    `end module`, name truncated in the message), not the 90 characters the `pfunit-tests`
    skill documents. Cost one build. Whether to correct the skill is a question for the
    task's gate.

  The 0.245 anchor checked out and was verified independently:
  `F(z) = (2 - e^{-az} - e^{-bz}) / (2 - e^{-a z_col} - e^{-b z_col})`, so at `a = 30`,
  `b = 2`, `z = 0.02` the numerator is 0.4903989 and an unbounded column gives 0.2451995.
  A separate observation about `fnrt_prof_mode = 2` ignoring layer thickness is filed in the
  parent plan's upstream-observations section.
- [x] **Steps 2–4 — FATES `d68bee7d1`**, plus an uncommitted CTSM-side `FatesNvp` testmod
  line that lands with the task's CTSM commit at Step 8. `OK (8 tests)` on the
  `root_profile` directory and 163 tests green across all eleven FATES unit-test
  directories; `git diff 6bef63ad6..HEAD -- ':(top)testing/'` empty, so no test file was
  touched. The sum-to-one assertion's missing evidence was supplied by mutating the
  residual-correction block (`correction = 1 - sum` → `0.5 - sum`): it reddened in all four
  tests carrying it, as the first assertion in each, and was edited back. CTSM builds.

  Three things worth keeping:

  - The mode routine writes the profile explicitly and carries a `size(root_fraction) < 1`
    `endrun` guard, which its siblings do not need — they would hit a zero divisor and trap
    under `-fpe0`, where an indexed write at `nlevroot == 0` would be an out-of-bounds
    store instead.
  - The regenerated moss JSON picked up the amended `long_name` unaided; its only three
    changed lines are that `long_name`, `fnrt_prof_a` 30.0 → 11.0 and the mode 3 → 5.
  - The Orientation's stomatal-intercept citation was wrong about which branch moss takes,
    and is corrected there.

- [x] **Step 2: add the mode.** A named constant with value 5 along
  `exponential_2p_profile_type` and a branch that puts the whole profile in layer 1. Confirm
  — do not assume — that the residual correction after the `select` (`:2849-2851`) is
  exactly zero for this profile. Amend `fates_allom_fnrt_prof_mode`'s `long_name` in the
  default parameter file to name the new mode and to say why 4 is skipped.
- [x] **Step 3: put moss on it.** In `make_moss_params.py`: add
  `fates_allom_fnrt_prof_mode: 5`; **remove** the now-unread `fates_allom_fnrt_prof_a: 30.0`
  override, so moss reverts to grass's 11.0 rather than carrying an override that does
  nothing; rewrite the NOTE at `:145-151`, whose claims that "our FATES supports modes 1-3"
  and that an all-zero profile breaks the water budget are both now wrong; and fix the
  stomatal-parameter comment at `:186-192` per Orientation. Regenerate the JSON.
- [x] **Step 4: get moss's btran onto the tape as `FATES_BTRAN_PF`** (Sam, 2026-09-08, over
  the zero-code alternative of putting the existing size-resolved `FATES_BTRAN_SZPF` on the
  testmod). Patch-level `btran_ft` per PFT, registered like its neighbours, plus its
  `hist_fincl1 +=` line in the `FatesNvp` testmod. Say in the review how it is normalized —
  `_PF` fields are per m2 land area, so a PFT-relative value needs dividing by that PFT's
  patch area, which `FATES_NOCOMP_PATCHAREA_PF` reports. It registers unconditionally, so the plain
  `FatesALP2*` tests that are the `use_fates_moss`-off b4b sentinel gain a field too;
  together with the testmod line that means every ALP2 baseline shows a field-list
  difference until Sam re-baselines. Report that; do not chase it, and do not reach for
  `inactive` to protect the field lists.
- [ ] **Review round (2026-09-08).** Two reviewers, run in parallel; both independently
  found the same blocking defect, which the orchestrator then verified from the code.

  - **R1 (blocking, and it would have killed the run about one model day in).**
    `set_root_fraction` floors nothing: `nlevroot = min(max_nlevroot, nlevroot)`. CTSM
    supplies `max_rooting_depth_index_col = min(nlevsoil, altmax_lastyear_indx_col(c))` with
    no `max(...,1)` (`clmfates_interfaceMod.F90:1270`), and `altmax_lastyear_indx_col` is 0
    from `InitCold` (`ActiveLayerMod.F90:305`), updated once a year (`:120`, `:132`) from an
    `altmax_indx` that was itself just reset to 0. So a cold start supplies **0 for its whole
    first model year**, and permanently for a column that never thaws — confirmed on disk in
    an existing ALP2 cold-start restart file. Modes 1-3 tolerate it; mode 5's
    `size(root_fraction) < 1` guard aborts. FATES clamps this same field with `max(...,1)` at
    two other consumers, so 0 is expected input, not a bug in CTSM.
    **Ruling: floor `nlevroot` at 1 inside `set_root_fraction`.** That is bit-identical for
    modes 1-3 — a single-layer profile normalizes to exactly 1.0 and the correction is then
    exactly 0, where today the correction supplies the same 1.0 — and it makes mode 5 behave
    like its siblings. Not `max(...,1)` at the twelve call sites, and not a routine that
    fills layer 1 of the full array regardless of the active column.
  - **R2.** The new guard has no `return` after `endrun`. Under the unit-test harness
    `shr_abort_abort` is stubbed to *return*
    (`share/unit_test_stubs/util/shr_abort_mod.abortthrows.F90`), so execution falls through
    to an out-of-bounds write that kills the whole executable instead of raising a catchable
    exception. Harmless in a real build, fatal to the harness.
  - **R3.** That guard's comment claims the sibling routines would trap at `nlevroot = 0`
    under `-fpe0`. False: their normalization is a zero-size array assignment, so no division
    is performed and there is nothing to trap.
  - **R4 (test side).** The negated-index marker mechanism is inert — `root_fraction(:) = 0`
    runs before the clamp and before dispatch, so a seeded marker cannot survive — and its
    comment claims otherwise; a second comment calls `max_nlevroot = 1` "the shallowest
    active column there is", which is the claim that hid R1; and the "exactly zero below"
    assertion is not independently reddenable, since pFUnit returns after the first exception
    and passing the layer-1 assertion already implies the lower layers sum to zero.
  - **R5.** Nothing anywhere validates `fnrt_prof_mode`'s range — not 0, not 4, not 99. The
    only check is `case default`, which aborts at the first dynamics call and prints neither
    the PFT index nor the offending value. `PRTCheckParams` is where the sibling mode
    parameters get theirs; add it there.
  - **R6.** The routine's header comment already numbered the modes wrongly — it calls the
    1-parameter exponential 1 and the beta profile 2, where the constants are the reverse —
    and this change extended that list rather than correcting it.
  - **R7 (small).** An all-bareground site reports `FATES_BTRAN_PF = 0` rather than the
    ignore value, so "no vegetation here" reads identically to "btran genuinely went to
    zero", which is the measurement the field exists for; match whatever the neighbouring
    `group_dyna_complx` per-PFT fields do rather than making this one a special case. And the
    fill comment's "recovers `btran_ft(ft)` itself" is exact only to a few ULP once a site
    has more than one vegetated patch.
  - **R8.** The spec still carries the water-balance claim that `make_moss_params.py` now
    says is false — §3's "mode 4 hands the HLM an all-zero profile, which is the thing that
    would actually break the water budget", reaffirmed in its own 2026-09-08 amendment. Step
    7 corrects it, so the spec is not left as the surviving copy of a cut claim.

  **F6, which changes what Step 5 can measure.** Because `max_nlevroot` is 0 for the whole
  first model year, the residual correction has *already* been collapsing every PFT's profile
  into layer 1 during year 1 of every cold-start run. Three consequences. The "24.5% of
  uptake in the top 2 cm" premise of this task describes year 2 onward, not year 1. A 730-day
  cold-start run therefore carries one year of signal, not two, and year 1 of the before/after
  comparison should be identical in profile terms. And the Step 3e diagnosis runs had the same
  collapse in their first year, which bears on how those results read. **Settled (Sam,
  2026-09-08): keep 730 days, and the year-1 collapse does not change how Step 3e's
  conclusions are read.** So Step 5 carries one post-collapse year of signal, and year 1
  becomes a control.

- [x] **Fix round (2026-09-08) — FATES `a80e32ccb`** (two tests for the defect, written
  before the fix) **and `441bf4e12`** (the fix). Whole-suite `OK (10 tests)` on
  `root_profile`, all eleven FATES unit-test directories green, CTSM rebuilds. R1–R7 are
  addressed; R8 belongs to Step 7.

  - **The floor is bit-identical for modes 1–3, established empirically rather than argued.**
    A driver linked against the built `libfates.a` printed raw IEEE-754 bit patterns for all
    four modes × three soil columns × `max_nlevroot` ∈ {−3, 0, 1, 3, 5, absent}, against
    builds with and without the floor. Every pattern matches; the only difference between the
    two runs is the six abort messages the unfloored build emitted. Visible in the output: at
    `max_nlevroot` of 0 and of 1 the legacy modes both give `3FF0000000000000` in layer 1.
  - **The fall-through past `endrun` is silent in one build and fatal in another.** In the
    driver, `root_fraction(1) = 1._r8` on a zero-size dummy wrote through to the caller's
    layer 1 with `-check bounds` not firing, where the same fall-through kills the unit-test
    executable. That is the argument for keeping both the guard and the new `return`.
  - **The floor sits inside the `present(max_nlevroot)` branch**, deliberately: hoisting it
    out would turn a caller passing a genuinely zero-length `root_fraction` with no
    `max_nlevroot` into an out-of-bounds slice. That case is already broken (`maxloc` of a
    zero-size array is 0, so the closing correction indexes element 0) and is left as it was
    rather than widened.
  - **The four mode codes moved to module scope and are now public**, so `PRTCheckParams`
    validates against the constants instead of restating `1/2/3/5`. `PRTParamsFATESMod`
    already `use`s `FatesAllometryMod`, so this adds no dependency. One consequence: a
    sentence in the byte-locked test file now describes the old arrangement.
  - **After the floor, the residual correction is no longer what makes the legacy
    zero-active-column case pass** — deleting it leaves all ten tests green, because the
    single-layer normalization already gives exactly 1.0. The mutation that reddens that case
    against the fixed code is flooring at 2 instead of 1, which fails exactly one test.
  - **`FATES_BTRAN_PF` stays at 0 for an all-bareground site**, matching every other per-PFT
    variable in its group: none is ever assigned `hlm_hio_ignore_val`, and the closest
    intensive analogues leave the zeroed 0 when their input is unavailable. The one field in
    the module that does flag a zero denominator is site-level and in a different group. The
    ambiguity is recorded in the fill comment rather than fixed by a lone exception.
  - **Not yet reviewed.** The fix round has had no reviewer pass, and `PRTCheckParams`'s new
    range check has not been exercised, because it runs at model initialization and the run
    is held. Both belong with Step 5 once its design is settled.

- [ ] **Fix-round review (2026-09-08).** The fix stands; the corrections are to comments,
  plus two missing `return`s. Held for one follow-up commit, together with the test-file
  sentences, until the run has finished so that the executable and the source stay in step.

  - **The bit-identity claim is true but for the stated reason.** It does not rest on `x/x`
    being exactly 1.0: if layer 1 came back as `1 ± d` at the ULP scale the closing
    correction restores exactly 1.0 anyway, since `1 - (1∓d)` is exact by Sterbenz and
    adding it back is exact. What it actually requires is only that layer 1's raw value be
    **finite and nonzero** — a broader guarantee than the comment claims. The "including
    denormals" half is moot: `-ftz` is in the base Intel flags for every build
    (`ccs_config/machines/cmake_macros/intel.cmake:16`), so a denormal layer-1 value is
    flushed to zero and gives NaN, not 1.0. Correct the comment to the true mechanism.
  - **One geometry does differ, and is unreachable.** A column whose first layer has zero
    thickness (`zi(1) == zi(0)`) with `max_nlevroot <= 0` gives NaN in layer 1 under modes 1
    and 3 where the unfloored code gave exactly 1.0, because both compute layer 1 as a
    difference that cancels and the floored path then divides `0/0`. Not reachable from
    CTSM: `zi_sisl` comes from `col%zi` and `col%dz(c,1) > 0` always. Recorded, not fixed.
  - **Two more `endrun`s in the same routine fall through, one of them badly.** The
    `size(zi) /= size(root_fraction)+1` guard drops into `root_fraction(1:nlevroot)`, which
    is out of bounds precisely because the sizes disagree — the same failure the new `return`
    one screen below exists to prevent. The `case default` falls through to the correction
    block and yields a well-formed layer-1 profile, so a future test asserting that an
    unknown mode aborts would see a plausible answer instead. Add `return` to both. Scope it
    to this routine: FATES has no return-after-`endrun` convention to be consistent with —
    2 of 489 call sites have one.
  - **The `FATES_BTRAN_PF` reword traded one false exactness claim for another.** "Exactly it
    where there is one vegetated patch" is also untrue: the `fl(fl(btran·area)/area)` round
    trip is not the identity, measured at 1 ULP on about 12% of random pairs. The accurate
    statement is "within a few ULP in all cases, the single-patch case included".
  - **Two comments describe things that do not exist.** The negative-`max_nlevroot` check is
    said to "only run in a debug build", but `debug` is a hardcoded
    `logical, parameter :: debug = .false.` a developer must edit — the check is dead in
    every build, which strengthens the case for the floor covering negatives. And the floor's
    placement rationale is stated in terms of `maxloc` of a zero-size array giving 0, which
    is what the standard requires and what `gfortran` does, but `ifx` returns 1. The
    placement decision stands; its justification needs to say what it actually prevents.
  - **The four new constants use an inline `public` attribute** where the module keeps a
    `public ::` block after a bare `private`. Move them into the block.
  - **Nothing exercises the hardened guard any more.** The floor routes the one test that
    reached it past it, so the guard and its `return` are reachable only from a hypothetical
    external caller. Consistent with the comment's own framing; worth knowing before treating
    the `return` as covered.
  - **Four sentences in the test file now describe the pre-fix mechanism** — the zero-size
    slice, the zero-trip loops, the correction supplying layer 1 — alongside the known-stale
    one about the constants being routine-local. Comment text only: the follow-up commit must
    leave every assertion, test name and test value untouched.

- [x] **Step 5: run 730 days — done; see the outcome block below Step 6.** The case is at
  `/glade/derecho/scratch/samrabin/mosstoplayer`. ~17 minutes of model time from cold start.

  **It is not a clone of `mosscull`, deliberately.** `mosscull`'s `SRCROOT` is the
  `.worktrees/moss-extinction` worktree, so a `create_clone` would have compiled that tree
  and resolved `FatesNvp`'s `$SRCROOT/.../fates_params_moss.json` into it, missing every
  change in this task. It was built with `create_newcase` against the main checkout instead,
  carrying `mosscull`'s configuration and `xmlchange` sequence. `mosscull` was neither
  touched nor rebuilt.

  **Its run is still a valid physics baseline, checked rather than assumed.** The worktree
  tip (`a4df3a3de`) and this branch's pre-change HEAD (`a71785632`) have no differences under
  CTSM `src/`, and their FATES pointers (`522ec26b5`, `749ac0123`) have identical trees — the
  latter is a contentless merge. The only run-relevant difference is the `FatesNvp` testmod's
  `hist_fincl1 += 'RAIN'` line, an output addition. So `mosscull`'s tape simply lacks `RAIN`
  and `FATES_BTRAN_PF`; nothing about the physics differs.

  **Year 1 is a control, not signal.** Moss's old mode-3 profile and the new mode-5 one both
  collapse to layer 1 while the active column is zero-deep, so year 1 should come back
  near-identical to `mosscull`'s archived run — a tighter sentinel for this change than the
  ALP2 b4b tests. Report anything that is not near-identical there; `mosscull`'s tape simply
  lacks `RAIN` and `FATES_BTRAN_PF`.

  Report:
  (a) whether `btran_ft(moss)` reaches zero on thawed days at all, and on how many;
  (b) `FATES_MOSS_FWET_SOIL` on those days — the F3 measurement, which Step 3b inherits;
  (c) whether `FATES_MORTALITY_HYDRAULIC_PF` becomes nonzero for moss, and how often;
  (d) whether every balance check passes.
  **A clean run is not evidence that the zero-btran path is safe** (Sam, 2026-09-08): one
  site over two years does not bound the behaviour. What it establishes is whether this
  configuration exercises the path at all.
  **Stop rules.** A balance-check failure or a build failure is a capability failure: stop
  and report, do not work around. That `FATES_MORTALITY_HYDRAULIC_PF` stays zero is a
  *finding*, not a stop — but it is the finding that decides whether Task 2 is verifiable
  here, so it goes to the gate rather than into a workaround.
  Remember: `_PF` fields are per m2 **land** area, so a moss-patch-relative value is the
  tape value divided by moss's patch area, read from `FATES_NOCOMP_PATCHAREA_PF` on the
  same tape rather than assumed. The prescribed nocomp cover fractions live in the
  `FatesALP2BareGrassMoss` testmod's `fsurdat`; do not carry copies of them around.
- [x] **Step 6: report what moved, without predicting it.** Concentrating withdrawal in the
  top 2 cm dries the layer that sets `FATES_MOSS_FWET_SOIL`. The effect on moss GPP is
  **not** predictable a priori, and the brief's claim that it must rise is only half right:
  the CO2 film factor wants low fwet, but capacity carries `min(1, fwet/0.6)`, so drying
  from above 0.6 is pure gain while drying below it sets the two against each other. Record
  what the run shows. Also expect grass to move: the two nocomp patches share a CTSM soil
  column, and Step 3e measured grass responding to a moss-column-only change from day 61
  onward, so a grass difference is not by itself evidence of a leak.
- [x] **Steps 5-6 outcome (2026-09-08).** Run completed clean: `SUCCESSFUL TERMINATION OF
  CESM`, 730 daily tapes, and **every conservation and balance check passes** — zero hits
  across all five logs for every balance string either source tree can emit, with checking
  armed, and max |`FATES_CBALANCE_ERROR`| of 2.24e-20 kg/s. The `PRTCheckParams` range check
  that had never executed did not abort, and the log confirms mode 3 for PFTs 1-14 and 5 for
  PFT 15.

  - **(a)** `btran_ft(moss)` is exactly zero on 202 of 730 days, of which `hmort`'s thaw gate
    is open on 37 (19 in year 1, 18 in year 2). On the other 165 layer 1 is at or below
    −2 °C. On the 528 non-zero days btran never gets closer to zero than 6.4e-3 and its
    median is exactly 1.0. Moss was alive every day, so none of this is a missing-cohort
    artifact.
  - **(b)** See F3 and F3a, which this measurement rewrote.
  - **(c)** Hydraulic mortality fires on 37 days at the parameter's full 0.6/yr, and **18 of
    them are new** — `mosscull` has none in year 2. So **Task 2's stop rule is not
    triggered**: the mechanism it switches off demonstrably fires here, and the on/off
    comparison is measurable at this site.
  - **(e)** Year 1 came back **bit-identical** on all 149 shared time-varying variables
    across all 365 tapes, with the two expected field-list additions and nothing missing.
    Identity in fact runs to day 436; the first difference anywhere is day 437, later than
    the calendar boundary because layer 1 stays frozen until the first thaw. F6's prediction
    holds exactly, and this is a tighter sentinel for the change than the ALP2 b4b tests.
  - **(f)** The top layer does dry, in the expected direction and by an amount too small to
    matter — mean change −3.1e-6 of saturation, largest −5.0e-4 — because moss has almost no
    leaf area to transpire through. **The GPP question this step was expected to inform is
    unanswerable from this run:** moss sits at exactly `fates_recruit_height_min` = 0.02 m
    every single day, LAI 3.8e-7, GPP 5e4× below grass, so year-2 moss GPP differs by 0.01%
    and there is no amplitude at which the film-factor-versus-capacity tradeoff could appear.
    The one thing the run says about that tradeoff's shape is within-run and
    season-confounded: moss GPP peaks in the driest bin visited and correlates −0.66 with the
    wetness proxy, so down to ~0.40 saturation the film gain still beats the capacity loss.
    Step 3b inherits that as a hint, not a result. The real year-2 signal is mortality:
    −2.92% in moss density, with matching shifts in crown area and moss fuel. Grass moved by
    ≤1e-4 relative and first differs on day 531, not day 61.
  - **What the run cannot establish.** One arctic site, two years, one cold start, and moss
    never leaving recruit size. The drought route to zero btran is not exercised at all, so
    nothing here bounds the behaviour of a productive moss stand. What it does establish is
    narrower and was the point: this configuration reaches the zero-btran path and fires
    hydraulic mortality through it, entirely via frozen soil.
  - **One thing left inferred.** Which term zeroes btran on the 37 gate-open days — no
    liquid water, or matric potential at `smpsc` — is read from fwet being 0.75-1.00, since
    the tape carries neither soil temperature nor soil liquid water. Ice is the only physical
    reading, but it is inference, and F3a rests on it.

- [x] **Step 7: amend spec §3** — done, in §3's own amendment-note style. Says the profile
  is now genuinely in layer 1 and by which mode, why it is numbered 5, and that its shape
  parameters are unread. It also cuts R8: §3 carried the claim that an all-zero profile
  would break the water budget, and the note replaces it with why it does not — CTSM's
  `btran(p) > btran0` gate with `btran0 = 0`, a moss patch's `btran_pa` being
  `btran_ft(moss)` bit-exactly under nocomp, and moss's demand being four orders below
  `error_thresh`. The older amendment note that carried the claim is left in place directly
  below, since the correction names it; the record of what was believed is worth more than a
  tidy page. The 24.5% figure is kept with the year-1 caveat attached.
- [ ] **Step 8: reviews, then commit.**

---

### Task 2: switch off moss's hydraulic-failure mortality

**Files:**
- Modify: `src/fates/tools/make_moss_params.py`, then regenerate `fates_params_moss.json`
- Modify: `docs/superpowers/specs/2026-08-19-moss-grass-pft-design.md` §12
- Modify: `docs/superpowers/plans/2026-08-19-moss-grass-pft.md` (tick Step 3f)

**Produces:** moss immune to FATES's non-hydro hydraulic-failure proxy, and the on/off
comparison against Task 1's run.

- [ ] **Step 0 (orchestrator):** confirm from Task 1's run that the mechanism actually fires,
  and settle what the comparison reports.
- [ ] **Step 1: zero it.** `fates_mort_scalar_hydrfailure: 0.0` in `MOSS_PFT_OVERRIDES`
  (from the inherited 0.6), with a comment giving the reason in two sentences — btran feeds
  only soil extraction and `hmort` for moss because `fates_leaf_agross_btran_model = 0`, so
  the proxy is a vascular mechanism with no moss counterpart — and pointing here for the
  rest. Leave `fates_mort_hf_sm_threshold` at 1e-6; F4 says why. Regenerate the JSON. No
  Fortran, no namelist entry, no restart field, no history field.
- [ ] **Step 2: rerun and compare.** Same case, no rebuild needed. Against Task 1's run:
  `FATES_MORTALITY_HYDRAULIC_PF` must be identically zero for moss, and report what the
  change does to moss `FATES_NPLANT_PF`, `FATES_LAI_PF` and `FATES_VEGC_PF` over the 730
  days, and to grass.
  **Stop rule.** If Task 1's run showed `FATES_MORTALITY_HYDRAULIC_PF` identically zero for
  moss, this change is unverifiable at this site. That is a capability failure: stop and
  report it. Do not build a contrived case, and do not record the change as verified by the
  absence of a difference.
- [ ] **Step 3: record the limitation.** Add a line to spec §12: moss carries no
  hydraulic-failure mortality at any dryness, because FATES's non-hydro proxy is keyed to
  btran, which moss otherwise ignores; if moss should be killable by drying, that mechanism
  has to be built on moss's own wetness metric, and it belongs with the wetness window in
  Step 3b.
- [ ] **Step 4: close Step 3f** in the parent plan — tick the box, record both commits, and
  carry F3's measured number forward into the Step 3b entry so 3b tunes against a number
  rather than an estimate.
- [ ] **Step 5: reviews, then commit.**
