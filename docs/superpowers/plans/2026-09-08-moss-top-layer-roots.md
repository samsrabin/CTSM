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
   its namelist switch and its restart discussion. F1–F5 below are why.
3. **A new case directory, cloned from `mosscull`.** Do not reuse
   `/glade/derecho/scratch/samrabin/mosscull`; it holds the post-3e baseline that Task 1
   compares against.

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
- **F3. Moss is *not* quiescent in that state, contrary to the brief.** btran collapses at a
  matric potential of −2.55 MPa, while `moss_wetness_scaler` is keyed to
  `h2osoi_vol/watsat` in the top layer. A soil at −2.55 MPa still holds a substantial
  fraction of saturation — by Clapp-Hornberger, `s = (psi/psi_sat)^(-1/B)`, which for
  plausible top-layer parameters is roughly 0.2–0.3 — so `fwet_moss_soil` is ~0.2–0.3 and
  the scaler `fwet/0.6` is ~0.3–0.5. **Those numbers are an estimate, not a result**: they
  depend on ALP2's actual top-layer `watsat`, `sucsat` and `bsw`, and Task 1's run measures
  the real value. The direction is robust, though: at btran = 0 moss is still
  photosynthesizing at a third to a half of capacity and paying the matching leaf
  maintenance respiration, with transpiration zero. So the state is not "moss is dormant and
  something kills it anyway"; it is "moss is doing business on its own water metric while a
  mortality mechanism keyed to a different metric kills it at 0.6/yr".
- **F4. `fates_mort_hf_sm_threshold = 0` would be broken, not merely inelegant.** The gate
  becomes `btran <= 0`, which is reached, and the magnitude then evaluates `(0 - 0)/0`
  (`EDMortalityFunctionsMod.F90:193-195`). That is a NaN mortality rate, very likely trapped
  under `DEBUG=TRUE`. A negative threshold works only by making a condition unreachable —
  correct today because btran cannot go negative and the comparison is `<=`, neither of
  which upstream owes us — and reads on the parameter file as a nonsense value that nothing
  validates. The threshold is also the response's denominator, so it does double duty as
  trigger point and steepness. The scalar is the knob; use it.
- **F5. A genuine dormant state would need a threshold on `fwet_moss`, which is Step 3b's
  knob.** Given F3, a real shutdown — respiration included — has to key on moss's own
  wetness metric, and choosing that threshold here would pre-empt 3b's wetness window with a
  number picked before 3b has any evidence. If moss should have a quiescent state, it belongs
  with 3b, where the distribution of `FATES_MOSS_FWET` is in front of you.

### Two claims in the brief are false and are cut

- **"Leaf maintenance respiration is already scaled by `moss_wetness_scaler`, which is zero
  at fwet = 0."** True as written and irrelevant: F3 shows fwet is ~0.2–0.3, not ~0, in the
  state at issue. The brief's companion claim that transpiration needs no zeroing *does*
  hold, via CTSM's `btran(p) > btran0` gate.
- **"`fates_leaf_stomatal_intercept` is what sets moss's whole-canopy `rssun`/`rssha`."**
  It is not. `gs0 = max(gsmin0, stomatal_intercept(ft))` (`LeafBiophysicsMod.F90:2237`), and
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
- [ ] **Step 1: write the unit tests first, in a different agent than the implementer.** A
  new `.pf` file added to an *existing* pFUnit directory is compiled, linked and never
  called — the run is green and proves nothing — so create a new directory. Assert that
  mode 5 gives exactly 1.0 in layer 1 and exactly 0.0 elsewhere, including under
  `max_nlevroot` compression, and that modes 1–3 are unchanged. Known wrinkle, not solved
  here: `set_root_fraction` reads `prt_params%fnrt_prof_mode/_a/_b`, so the test must
  allocate and set those module-level arrays in `setUp`. Commit the tests before the
  implementation and confirm they fail for the right reason.
- [ ] **Step 2: add the mode.** A named constant with value 5 along
  `exponential_2p_profile_type` and a branch that puts the whole profile in layer 1. Confirm
  — do not assume — that the residual correction after the `select` (`:2849-2851`) is
  exactly zero for this profile. Amend `fates_allom_fnrt_prof_mode`'s `long_name` in the
  default parameter file to name the new mode and to say why 4 is skipped.
- [ ] **Step 3: put moss on it.** In `make_moss_params.py`: add
  `fates_allom_fnrt_prof_mode: 5`; **remove** the now-unread `fates_allom_fnrt_prof_a: 30.0`
  override, so moss reverts to grass's 11.0 rather than carrying an override that does
  nothing; rewrite the NOTE at `:145-151`, whose claims that "our FATES supports modes 1-3"
  and that an all-zero profile breaks the water budget are both now wrong; and fix the
  stomatal-parameter comment at `:186-192` per Orientation. Regenerate the JSON.
- [ ] **Step 4: get moss's btran onto the tape as `FATES_BTRAN_PF`** (Sam, 2026-09-08, over
  the zero-code alternative of putting the existing size-resolved `FATES_BTRAN_SZPF` on the
  testmod). Patch-level `btran_ft` per PFT, registered like its neighbours, plus its
  `hist_fincl1 +=` line in the `FatesNvp` testmod. Say in the review how it is normalized —
  `_PF` fields are per m2 land area, so under prescribed nocomp a moss value is the tape
  value divided by moss's 0.5 cover. It registers unconditionally, so the plain
  `FatesALP2*` tests that are the `use_fates_moss`-off b4b sentinel gain a field too;
  together with the testmod line that means every ALP2 baseline shows a field-list
  difference until Sam re-baselines. Report that; do not chase it, and do not reach for
  `inactive` to protect the field lists.
- [ ] **Step 5: build, then run 730 days.** Clone a new case from
  `/glade/derecho/scratch/samrabin/mosscull` (do not reuse it — Sam, 2026-09-08). ~17
  minutes of model time from cold start. Report:
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
  tape value divided by 0.5 (prescribed nocomp cover: moss 0.5, grass 0.3, bare 0.2).
- [ ] **Step 6: report what moved, without predicting it.** Concentrating withdrawal in the
  top 2 cm dries the layer that sets `FATES_MOSS_FWET_SOIL`. The effect on moss GPP is
  **not** predictable a priori, and the brief's claim that it must rise is only half right:
  the CO2 film factor wants low fwet, but capacity carries `min(1, fwet/0.6)`, so drying
  from above 0.6 is pure gain while drying below it sets the two against each other. Record
  what the run shows. Also expect grass to move: the two nocomp patches share a CTSM soil
  column, and Step 3e measured grass responding to a moss-column-only change from day 61
  onward, so a grass difference is not by itself evidence of a leak.
- [ ] **Step 7: amend spec §3** to say the profile is now genuinely in layer 1, by which
  mode, and that mode 4 remains deliberately unused. Keep the amendment note style §3
  already uses.
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
