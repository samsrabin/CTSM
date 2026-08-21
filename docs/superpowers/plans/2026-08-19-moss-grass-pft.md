# Moss-as-Grass-PFT Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> to implement this plan task-by-task, with the **custom orchestration loop** defined in
> "Process" below (it overrides the sub-skill's defaults where they differ). Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add moss to CTSM-FATES as a grass-like PFT that contributes prognostic,
conserving biomass to two new SPITFIRE fuel classes whose moisture is diagnosed from a
soil/canopy wetness proxy.

**Architecture:** Moss is a 15th, non-woody FATES PFT identified by a new per-PFT
`fates_vascular` flag. FATES-side changes: two new fuel classes (runtime-sized), a
`moss_fines` litter pool, moss physiology (no stomatal solve, wetness-scaled vcmax), and
an optional mat-thickness height allometry. CTSM-side changes: namelist plumbing and one
new `bc_in` field (canopy wetted fraction). Spec:
`docs/superpowers/specs/2026-08-19-moss-grass-pft-design.md`.

**Tech Stack:** Fortran (CTSM + FATES submodule), CTSM build-namelist (Perl/XML), FATES
functional tests (CMake/Python, `src/fates/testing/`). The FATES parameter file is
**JSON, read directly at runtime** (`JSONRead`, `FatesInterfaceMod.F90:118-122`; the
default `fates_paramfile` points at `src/fates/parameter_files/fates_params_default.json`)
— parameter-file work is JSON editing via FATES's patch tooling, no netCDF involved. The
CTSM parameter file is untouched.

## Process (custom orchestration loop — REQUIRED)

The main session is the **orchestrator**. For each task, in order:

1. **Step 0 (orchestrator, not a subagent):** re-read the task and the spec sections it
   cites; explore the relevant code as needed; verify the task's assumptions still hold
   against the current state of the branch; check the task's "Produces" interfaces are
   still what subsequent tasks expect (forward compatibility); ask Sam any clarifying
   questions (each task's Step 0 lists known open questions — ask only what is genuinely
   unresolved).
2. **Dispatch an implementer subagent** with the task text plus any Step 0 resolutions.
3. **Dispatch a spec-compliance reviewer subagent** (checks the diff against the spec and
   the task's requirements) and a **code-review subagent** (correctness, conventions,
   conservation). Address all reviewer findings — re-dispatching the implementer as
   needed — before committing.
4. **Commit** only after reviewer comments are accounted for (see Git choreography).
5. **Present the commit to Sam for review**, including which system tests are relevant
   and the expected outcome of each. **Running those CTSM-FATES tests is part of Sam's
   review** — Sam may run them or skip them. Do not start the next task until Sam
   approves.

### Standing verification rule (every task)

Testing and diagnostics land WITH the capability they verify, not at the end. **Division
of labor:**

- **Claude (required, every Fortran-touching task):** (a) verify CTSM-FATES **builds**:
  from the top of the checkout, `cd test-bld-adrianna-moss-grass-pft && qcmd -- ./case.build` (the `test-bld-adrianna-moss-grass-pft/`
  case will exist on the implementation machine; if it is missing, ask Sam rather than
  creating one); (b) run the FATES functional/unit tests covering the touched code.
  **Always invoke the functional tests as
  `MPLBACKEND=Agg python run_functional_tests.py --save-figs -t <suite>`.** Without
  `MPLBACKEND=Agg` the run ends at an unconditional `plt.show()`
  (`testing/run_functional_tests.py:264`, outside any `--save-figs` guard) and blocks on X
  windows, which reads as a hang; `--save-figs` then writes the figures to
  `<run-dir>/plots/<test>/` (default run-dir `_run`) where they can actually be inspected.
  `run_unit_tests.py` needs neither flag. **The `-t` is not optional either:** the suite is
  selected only by `-t/--test-list`, there is no positional argument, and its default is
  `all` — so omitting it runs every functional suite rather than the one intended.
  **Run them in the `ctsm_pylib` conda env** (Sam, 2026-08-21) —
  `/glade/work/samrabin/conda-envs/ctsm_pylib/bin/python3`. FATES's
  `testing/environment.yml` names a `fates_testing` env; ignore it. **Never create or
  modify a conda env, and if `ctsm_pylib` fails to run the tests, STOP and tell Sam rather
  than troubleshooting it** — no installing, no swapping interpreters, no working around a
  missing module.
  Claude performs **no other testing** — nothing that runs CTSM-FATES.
- **Sam (and Sam alone; may choose to skip):** all testing that actually RUNS
  CTSM-FATES — the ALP2 baseline b4b comparisons, the moss smoke + exact-restart tests,
  and science-sanity runs. **These happen as part of Sam's post-commit review (loop
  step 5), not as a pre-commit gate.** Wherever a task's verification step names such
  a test, read it as: Claude names which tests are relevant and states what outcome to
  expect from each, and presents that with the commit; Sam decides whether to run them
  during review, and approval proceeds on Sam's say-so either way. Claude does **not**
  write `run_sys_tests` invocations, `--generate`/`--compare` flags, or baseline tags —
  Sam owns how the tests are launched and how baselines are named.
- The b4b intent stands throughout: `use_fates_moss` off must remain bit-for-bit; the ALP2
  baselines (Task 0) are the instrument whenever Sam chooses to run them.

### Git choreography

Work spans two repositories:

- **CTSM branch:** `adrianna-moss-grass-pft` (already exists; spec committed there).
- **FATES branch:** create `adrianna-moss-grass-pft` in `src/fates/`, branched from
  `e027a4030` (the commit pinned by `ctsm5.4.028`). Push over **SSH** to Sam's fork:
  remote `git@github.com:samsrabin/fates.git`. (The `.gitmodules` `url` entries stay in
  their existing `https://` form for downstream consumers; only the push transport is
  SSH.)

Per task that touches FATES: commit in `src/fates/` first, then commit in CTSM (including
the submodule pointer bump and, in the first FATES-touching task, the `.gitmodules`
`url`/`fxtag` update to `samsrabin/fates`). One logical task = one CTSM commit (which may
carry a FATES pointer bump) + at most one FATES commit.

## Upstream FATES observations (report when this work goes upstream)

Not defects in our work; things noticed while implementing that upstream may want to know.

- **The Tree Recruitment Scheme's tree test misclassifies 8 of 14 default PFTs.** Every TRS
  gate (`PRTAllometricCarbonMod.F90:1069`, `PRTAllometricCNPMod.F90:1500/2354/2490`,
  `EDPhysiologyMod.F90:2175/2278/2290/2404/2657`) discriminates trees with
  `allom_dbh_maxheight > min_max_dbh_for_trees` (15 cm) rather than with `woody`, even though
  `prt_params%woody(` is used 54 times elsewhere in FATES and appears nowhere in either
  PARTEH allocation module. Against `woody` that proxy is wrong in both directions: the five
  shrubs are `woody = 1` but `dbh_maxheight` 1.9–3.0, so they are excluded; the three grasses
  are `woody = 0` but `dbh_maxheight` 20–30, so they are included. Only the six trees are
  classified correctly. Excluding shrubs may well be deliberate — a 2 cm-max-dbh shrub may
  not suit a tree recruitment scheme regardless of woodiness — but including grasses looks
  accidental, since a grass's `dbh` is a fiction derived from leaf carbon and nobody reading
  "grass reaches max height at 20 cm dbh" would infer "this makes grass a tree". Latent in
  practice: `fates_regeneration_model` defaults to `default`, and every gate is conjoined
  with a regeneration-model test, so nothing fires unless TRS is explicitly enabled.
- **`npft` is computed before the non-master early return in `FatesCheckParams`.**
  `EDPftvarcon.F90:977` does `npft = size(EDPftvarcon_inst%freezetol,1)` two lines above the
  `if(.not.is_master) return` at `:979`. With `use_fates = .false.` CTSM still calls
  `SetFatesGlobalElements2` (`clmfates_interfaceMod.F90:705-708`), so that `size()` is
  evaluated on an unallocated allocatable — undefined behaviour. Pre-existing and harmless
  today only because every use of `npft` sits below the return. Anyone moving code above that
  return, upstream or here, will trip it.
- **`fates_allom_dbh_maxheight` carries two unrelated jobs.** It is the diameter at which
  height and max-leaf-biomass saturate (entering `d2h_*` and `d2blmax_*` purely as
  `min(d, dbh_maxh)`), and it is separately the TRS tree test above. A PFT cannot tune its
  height/leaf-biomass ceiling without also moving itself across that classification, or vice
  versa. Splitting the tree test onto its own parameter (or onto `woody`) would decouple them.
  This bit us concretely: moss wants a mat-scale ceiling — a moss-specific 0.1 cm caps height
  at ~4.2 cm — but we inherit grass's 20 cm to stay aligned and to avoid asserting a TRS
  classification, which leaves moss height saturating only at ~1.23 m under `grass_powerlaw`.
  Accepted as a limitation in spec §12, with the intended fix in §11.

## Global Constraints

- **All new scalar settings — switches and science constants — go on the CTSM namelist**
  (`clm_inparm` → `set_fates_ctrlparms` `hlm_*`), never the FATES parameter file. Only
  array parameters (per-PFT, per-litterclass) go on the FATES parameter file. (Spec §8.)
- **`use_fates_moss = .false.` must be bit-for-bit with baseline**, including unchanged restart
  and history file shapes with a standard 6-litterclass parameter file. (Spec §10.)
- **All existing CTSM/FATES conservation (balance) checks remain fatal** and must pass
  with `use_fates_moss` on and off. (Spec §5, §10.)
- `use_fates_moss` + `use_fates_planthydro` is a fatal namelist error. (Spec §5.)
- Target configuration: nocomp fixed-biogeography, SPITFIRE on. Choices must not
  foreclose full-competition mode. (Spec §2.)
- Fortran code follows surrounding CTSM/FATES style (naming, `_r8` literals, `endrun`
  with `fates_log()`/`iulog` messages).
- **Commits contain no unnecessary churn.** Touch only lines the change requires: no
  whitespace-only edits, no reflowing or re-indenting untouched code, no reformatting
  neighboring lines. In particular, do **not** re-align a block's `=`, `::`, or trailing
  comments just because a new line is longer or shorter — Sam does not care about
  preserving column alignment, and a realigned block buries the real change in the diff.
  Prefer adding a line that fits the existing alignment loosely over adjusting others.
- New moss history variables follow the existing conditional-registration patterns in
  `main/FatesHistoryInterfaceMod.F90` (register only when `hlm_use_moss==itrue`;
  patch→site averaging per existing helpers). The first task to add one (Task 6)
  establishes the pattern; later tasks follow it. **Every task that adds a
  moss-specific history variable also adds it to the output list (`hist_fincl`) in the
  `FatesNvp` testmod's `user_nl_clm`, in that same task.**
- Reference implementations to harvest are on `ctsm5.4.028_nvp` — a branch on the
  **`huitang-earth`** remote (`https://github.com/huitang-earth/CTSM.git`), *not* on
  `origin`; worktree at `.worktrees/nvp`, created 2026-08-19 at branch tip `997cb054a`.
  `git fetch huitang-earth ctsm5.4.028_nvp` also brings FATES commit `33640d372` into
  `src/fates`'s object store (it is not there beforehand); view files with
  `git -C src/fates show 33640d372:<path>`.

---

### Task 0: ALP2 baseline testmods, tests, and baselines

**Status: COMPLETE (2026-08-20).** Commits `2438f5ecb` (testmods, testlist, submodule
pointers) and `dedbfdf4c` (drop `fates_paramfile` — see Step 1). Sam confirmed both ALP2
tests pass on derecho intel/gnu and izumi/nag. **The ALP2 baselines exist** (Sam
confirmed 2026-08-20; he owns the tag and Claude does not need to know it). So from Task 2
onward the `use_fates_moss`-off b4b requirement is measurable, not just an argument from
the diff: every Fortran-touching task states "ALP2 baselines compare b4b" as an expected
outcome for Sam's review, and a b4b break is a real failure signal rather than an
untested claim.

**Files:**
- Create: `cime_config/testdefs/testmods_dirs/clm/FatesALP2Bare/user_nl_clm` (+
  `include_user_mods` if the NVP branch's version has one)
- Create: `cime_config/testdefs/testmods_dirs/clm/FatesALP2BareGrass/user_nl_clm` (+ ditto)
- Modify: `cime_config/testdefs/testlist_clm.xml`
- Modify: `.gitmodules` + submodule pointers for `ccs_config` and `cdeps`
- Modify: `.gitignore` (add `.worktrees/` under "REMOVE BEFORE MERGE")

**Interfaces:**
- Consumes: nothing (pure test infrastructure at the base code).
- Produces: runnable baseline tests at the ALP2 site, e.g.
  `SMS_Ld5_D_Mmpi-serial.1x1_ALP2.I2000Clm60FatesSpRsGs.clm-FatesColdSatPhen--clm-FatesALP2Bare`
  (and the `FatesALP2BareGrass` twin), **plus generated baselines** that every later
  Fortran-touching task compares against (standing verification rule).

Source material is on the NVP branch (worktree `.worktrees/nvp`):
`cime_config/testdefs/testmods_dirs/clm/FatesALP2Bare{,Grass}/` (each sets `fsurdat` to
`$DIN_LOC_ROOT/lnd/clm2/testdata/moss/fsurdat/surfdata_ALP2_hist_2000_16pfts_c260427_{bare,grass}.nc`
and `fates_paramfile` to a JSON under `$DIN_LOC_ROOT/lnd/clm2/testdata/moss/fates_paramfile/`),
plus `testlist_clm.xml` entries at grid `1x1_ALP2`, compset `I2000Clm60FatesSpRsGs`
(~lines 4969–5030 there). The `1x1_ALP2` grid definition requires the NVP branch's
`ccs_config` (`samsrabin/ccs_config_cesm.git` @ `b6387972b`) and `cdeps`
(@ `42f9a6b06`) fork pointers.

- [x] **Step 0 (orchestrator) — COMPLETE (2026-08-19).** NVP worktree created at
  `.worktrees/nvp` (branch `ctsm5.4.028_nvp`, tip `997cb054a`); testmod dirs and the
  `1x1_ALP2` testlist block (NVP lines 4905–5090) inspected. Resolutions from Sam:
  - **Submodules.** Point `ccs_config` at
    `https://github.com/samsrabin/ccs_config_cesm.git` @
    `b6387972bba85d25b0e81ebc03035864e283823c`, matching the NVP branch. For `cdeps`,
    bump `fxtag` to `42f9a6b064ca8d1843a7849c58cc733b3994f94e` but leave **both** `url`
    and `fxDONOTUSEurl` at upstream `https://github.com/ESCOMP/CDEPS.git` — that commit
    is reachable in upstream CDEPS (verified by fetch), and the NVP branch has these two
    fields swapped (fork URL parked in `fxDONOTUSEurl`). Standing caveat: the
    `ccs_config` fork pointer must be reverted or upstreamed before any merge to master.
  - **Categories.** Use the NVP branch's scheme verbatim — `fates` plus `fates_nvp`,
    `fates_nvp_short`, `fates_nvp_long`, `fates_nvp_nonvp`, `fates_nvp_short_nonvp`,
    `fates_nvp_long_nonvp`. No new `fates_moss` category. Short = `Ld5`, long = `Ly2`;
    the `*_nonvp` categories hold the `FatesNvpOff` tests, which arrive in Task 5.
  - **Testmod names.** Keep the NVP branch's names verbatim (`FatesNvp`, `FatesNvpOff`,
    `FatesALP2*`); do **not** rename to `FatesMoss*`.
  - **Testdata.** Verified present on derecho's `$DIN_LOC_ROOT`
    (`/glade/campaign/cesm/cesmdata/cseg/inputdata`): all `fsurdat`
    `surfdata_ALP2_hist_2000_16pfts_c260427*.nc` variants and the default/moss paramfile
    JSONs under `lnd/clm2/testdata/moss/`.
  - **Machines/compilers.** As the NVP entries do: derecho intel, derecho gnu, and izumi
    nag. (Note the NVP branch omits izumi from the `*_nonvp` categories — mirror that.)
  - **`use_bedrock`.** Set `use_bedrock = .true.` in **all** `FatesALP2*` testmods — it
    matters for running at this site — and **not** in `FatesNvp`. Task 5 must drop the
    `use_bedrock` line when it ports `FatesNvp`.
  - **`.gitignore`.** Add `.worktrees/` (done, under "REMOVE BEFORE MERGE").
  - **Finding for later tasks.** CIME keys baselines by full test name *including
    testmods*, so Task 5's `FatesNvpOff` tests cannot compare against Task 0's
    baselines — they need baselines of their own, generated at Task 5. Task 0's two
    plain tests carry no `FatesNvp*` testmod, so `use_fates_moss` takes its `.false.`
    default: those are the b4b sentinel for Tasks 1–4.
  - Forward check: `FatesNvp`/`FatesNvpOff` do not exist on this branch yet — they
    arrive (adapted) in Task 5 along with the remaining NVP-branch tests. Task 0's two
    baseline tests reference only `FatesColdSatPhen` + `FatesALP2Bare{,Grass}`.
- [x] **Step 1: copy the two testmod dirs** from the NVP worktree (each is a two-line
  `user_nl_clm` with only `fsurdat` and `fates_paramfile`, no `include_user_mods`), and
  add `use_bedrock = .true.` to each per Step 0. **Do NOT carry over the
  `fates_paramfile` line.** Every `fates_params_default.c*.json` under
  `$DIN_LOC_ROOT/lnd/clm2/testdata/moss/fates_paramfile/` is, despite the name, a
  15-PFT NVP-flavoured file whose 15th PFT sets
  `fates_allom_fnrt_prof_mode = 4` ("no roots (NVP)") — a mode that exists only in
  NVP-branch FATES. Our FATES pin implements modes 1–3 only, and `btran_ed` loops
  `do ft = 1,numpft` over **every** PFT on the parameter file regardless of what the
  surface dataset contains, so any vegetated patch aborts in `set_root_fraction`
  ("An undefined root profile type was specified"). Omitting the line lets the CTSM
  namelist default apply — the in-repo `src/fates/parameter_files/fates_params_default.json`
  (14 PFTs, all mode 3), which is version-locked to the FATES pin and is what every
  other FATES test uses. This is also what a no-moss baseline test *should* use.
- [x] **Step 2: update submodules.** Edit `.gitmodules` (`ccs_config`: url + fxtag;
  `cdeps`: fxtag only — see Step 0) and check out the corresponding submodule commits.
- [x] **Step 3: testlist entries.** Add the Bare and BareGrass tests (grid `1x1_ALP2`,
  compset `I2000Clm60FatesSpRsGs`, testmods `clm/FatesColdSatPhen--clm/FatesALP2Bare`
  and `...BareGrass`), machines/compilers/categories per Step 0. These are new
  constructions, not ports: every ALP2 entry on the NVP branch composes `FatesNvp` or
  `FatesNvpOff`, so there is no no-moss ALP2 test there to copy. Model the `<machines>`
  and `<options>` blocks on the NVP branch's `FatesNvp--FatesALP2Bare{,Grass}` entries
  (NVP lines 4972, 4989), minus the `FatesNvp` testmod.
- [x] **Step 4: reviews, then commit** ("Add ALP2 bare and bare+grass baseline testmods
  and tests"). During post-commit review, Sam (optionally) runs the two tests and
  generates baselines from them; expected outcome is that both PASS at base code. Sam
  owns the baseline tag and its naming convention — Claude does not write the
  `run_sys_tests` invocations and does not need to know the tag.

### Task 0b: Fix NaN `rootr_patch` below bedrock in the FATES interface

**Status: COMPLETE (2026-08-19).** Commit `cd5783c3c`. Sam confirmed the derecho intel
`FatesALP2BareGrass` test passes.

Not in the original plan. Added 2026-08-19 after Task 0's `FatesALP2BareGrass` test
failed on derecho/intel with `forrtl (65): floating invalid` at
`SoilWaterPlantSinkMod.F90:398`. Root cause is a **pre-existing CTSM–FATES interface
bug**, not anything Task 0 introduced — the NVP branch's `wrap_btran` is byte-identical
and its `ExpectedTestFails.xml` documents the same failure ("Floating invalid, doesn't
happen with gnu") across 10 ALP2 entries. We fix it rather than copying that workaround
because Task 0's two tests are the project's b4b baseline instrument, and a baseline test
that is an expected RUN FAIL on intel generates no baseline — silently reducing b4b
coverage to gnu-only for every later task, on the very compiler that hides NaN.

**Files:**
- Modify: `src/utils/clmfates_interfaceMod.F90` (`wrap_btran`, the `rootr` fill loop
  at ~line 2586–2603)

**Interfaces:**
- Consumes: nothing new.
- Produces: `soilstate_inst%rootr_patch(p, :)` fully defined over `1:nlevgrnd` for every
  active FATES patch, instead of only `1:bc_in%nlevsoil`. All later tasks inherit this;
  no new symbols.

- [x] **Step 0 (orchestrator) — COMPLETE (2026-08-19).** Root cause established:
  - `SoilStateType.F90:163` allocates `rootr_patch(begp:endp,1:nlevgrnd)` and
    initialises it to NaN, so any element never assigned holds NaN on both compilers.
  - `wrap_btran` fills `rootr(p,j)` only over `do j = 1,nlevsoil`, where `nlevsoil` is
    FATES's **per-column** count, set from `col%nbedrock(c)`
    (`clmfates_interfaceMod.F90:959` → `FatesInterfaceMod.F90:461`).
  - `Compute_EffecRootFrac_And_VertTranSink_Default` consumes `do j = 1,nlevsoi`
    (**global**) and multiplies `rootr_patch(p,j)` at `SoilWaterPlantSinkMod.F90:397-398`.
    The divide at `:416` is already guarded by `temp(c)/=0`; the operand arrives invalid.
  - ALP2's fsurdat has `zbedrock = 0.4` m, so with `use_bedrock = .true.` (Task 0)
    `col%nbedrock` is ~layer 5 of 20 and layers ~6–20 stay NaN. Intel's debug build traps
    it; gnu does not, which is why gnu "passes" — same arithmetic, untrapped, with NaN
    propagating into `rootr_col` and `qflx_rootsoi_col`.
  - Sam's decisions: fix the root cause (not `ExpectedTestFails`), and do not investigate
    whether gnu has historically been writing NaN into history output.
- [x] **Step 1: zero the sub-bedrock layers.** In `wrap_btran`, after the
  `do j = 1,nlevsoil` fill loop, set `rootr(p, nlevsoil+1 : nlevgrnd) = 0._r8` for each
  active patch. Zero to `nlevgrnd`, not `nlevsoi`: `rootr_patch` is allocated to
  `nlevgrnd` and `ch4Mod` / `SoilMoistStressMod` also read it. Physically this states
  that there is no root water uptake below bedrock, which is what FATES already means by
  truncating its column there. Wrap the assignment in `if (nlevsoil < nlevgrnd)` as
  defensive code — but note the guard can never actually be false, since `nlevsoil` is
  `col%nbedrock ∈ [3, nlevsoi]` (`initVerticalMod.F90:469-487`) and `nlevsoi < nlevgrnd`
  is enforced (`clm_varpar.F90:265-268`). It is **not** protecting against an
  out-of-bounds slice: a Fortran array section whose lower bound exceeds its upper bound
  is zero-sized and legal. Do not repeat that incorrect rationale anywhere.
  Follow the surrounding style; no churn.
- [x] **Step 2: verify (Claude).** Fortran-touching, so the standing rule applies:
  `cd test-bld-adrianna-moss-grass-pft && qcmd -- ./case.build` must succeed. No FATES
  functional test covers this interface path, so there is nothing to add there.
- [x] **Step 3: reviews, then commit.** Expected outcomes to state for Sam: the intel
  `FatesALP2BareGrass` test now runs to completion; the gnu twin still passes. Answer
  changes are confined to values that were previously NaN, so any configuration that was
  producing valid numbers is unaffected — worth saying explicitly since this lands before
  baselines are generated. Flag the commit as a candidate for a standalone upstream CTSM
  PR, since it fixes a bug unrelated to moss.

### Task 0c: Fix unconditional `associate` of uninitialised BGC pointers (nag)

**Status: COMPLETE (2026-08-20).** Commit `8c2ab55a7`. Sam confirmed the izumi/nag ALP2
tests and the new `1x1_brazil` nag FATES-SP test pass.

Not in the original plan. Added 2026-08-20 after Task 0's izumi/nag tests failed with
`Reference to undefined POINTER` at `clmfates_interfaceMod.F90:3098` in
`wrap_update_hifrq_hist`. Pre-existing CTSM bug, unrelated to moss and to Task 0b.

**Files:**
- Modify: `src/utils/clmfates_interfaceMod.F90` (`wrap_update_hifrq_hist` `associate`
  block, ~lines 3098–3125; plus the bounded sweep below)
- Modify: `cime_config/testdefs/testlist_clm.xml` (one new izumi/nag FATES-SP test)

**Interfaces:**
- Consumes: nothing new.
- Produces: no new symbols. `wrap_update_hifrq_hist` stops binding
  `soilbiogeochem_*_inst` components when `decomp_method == no_soil_decomp`.

- [x] **Step 0 (orchestrator) — COMPLETE (2026-08-20).** Root cause established:
  - `clm_instMod.F90:404` `if_decomp: if (decomp_method /= no_soil_decomp) then` gates the
    `Init` of `soilbiogeochem_carbonstate_inst` (`:425`) and
    `soilbiogeochem_carbonflux_inst` (`:435`). Those `Init`s are where `hr_col`,
    `totsomc_col` and `totlitc_col` are allocated
    (`SoilBiogeochemCarbonFluxType.F90:175`, `SoilBiogeochemCarbonStateType.F90:171-172`),
    so under `no_soil_decomp` all three are **undefined pointers**.
  - `clmfates_interfaceMod.F90:3098-3106` binds all three in an `associate` **before** the
    `if (decomp_method /= no_soil_decomp)` guard at `:3110`. An `associate` binds at block
    entry regardless of control flow, so the binding is illegal even though the names are
    read only inside the guarded branch (`:3114-3116`); the `else` branch (`:3121-3123`)
    writes literal zeros and touches none of them. nag's runtime pointer checking traps
    it; intel and gnu do not.
  - Dormant until now because no other izumi/nag test runs FATES-SP: the nag FATES
    compsets are `I2000Clm50FatesRs`, `I2000Clm60FatesRs`, `I2000Clm60FatesCrujraRs`,
    `I2000Clm60Fates`, `I1PtClm60Fates` — all full-BGC, none with `Sp`.
  - Sam's decisions: fix it (not `ExpectedTestFails`); use **option (a)**, dropping the
    three names from the `associate` rather than nesting a second `associate`; include the
    bounded sweep; and add permanent izumi/nag FATES-SP coverage.
- [x] **Step 1: drop the three BGC bindings.** Remove `hr`, `totsomc` and `totlitc` from
  the `associate` at `:3098`, leaving the five always-initialised biophysics fields
  (`eflx_lh_tot`, `eflx_sh_tot`, `fsa_patch`, `eflx_lwrad_net`, `t_ref2m`). In the guarded
  branch, reference the components directly:

```fortran
            this%fates(nc)%bc_in(s)%tot_het_resp = soilbiogeochem_carbonflux_inst%hr_col(c)
            this%fates(nc)%bc_in(s)%tot_somc     = soilbiogeochem_carbonstate_inst%totsomc_col(c)
            this%fates(nc)%bc_in(s)%tot_litc     = soilbiogeochem_carbonstate_inst%totlitc_col(c)
```

  A component reference inside a branch that does not execute is never evaluated, so this
  is safe under `no_soil_decomp`. Zero answer changes on any compiler — this only changes
  whether a name is bound, never a computed value. Keep the `else` branch untouched.
- [x] **Step 2: bounded sweep — deliberately scoped, do not widen.** In
  `clmfates_interfaceMod.F90` **only**, inspect every other `associate` block for the same
  defect: a binding to a component of an instance that is only conditionally initialised
  (the `decomp_method /= no_soil_decomp` gate at `clm_instMod.F90:404` is the one known
  such gate; also check `use_cn`/`use_fates_bgc`-style gates if any instance is bound that
  way). Report each block checked and the verdict, even when clean. Fix any found by the
  same Step 1 pattern. This is NOT a general audit of the file and NOT a sweep of other
  files — anything outside `clmfates_interfaceMod.F90` gets reported, not changed.
- [x] **Step 3: permanent izumi/nag FATES-SP coverage.** Add ONE new short, mpi-serial
  FATES-SP test on izumi/nag, cloned from the existing derecho-only entry
  `SMS_D` / `1x1_brazil` / `I2000Clm60FatesSpCruRsGs` / `clm/FatesColdSatPhen` (whose own
  comment notes "FatesSp has the largest difference in CTSM code for any FATES mode"):
  a new `SMS_D_Mmpi-serial` entry, same grid/compset/testmods, `<machine name="izumi"
  compiler="nag" category="fates"/>`, wallclock copied from the existing entry. Add it as
  a separate `<test>` element rather than appending izumi to the existing entry's machine
  list, so the derecho tests are untouched and the new one gets mpi-serial. Both the grid
  and mpi-serial are already proven on izumi (5 existing izumi `1x1_brazil` tests, 15
  existing izumi/nag `Mmpi-serial` tests). Rationale for the comment text: this test
  exists so nag checks the FATES-SP (`no_soil_decomp`) path in the regular suite, which is
  what would have caught this bug.
- [x] **Step 4: verify (Claude).** Fortran-touching, so the standing rule applies:
  `cd test-bld-adrianna-moss-grass-pft && qcmd -- ./case.build` must succeed. Also confirm
  `testlist_clm.xml` still parses and that `./cime/scripts/query_testlists` finds the new
  test under izumi/nag. **If the build fails for any git-related reason, STOP and ask Sam
  — never modify git state to make a build work.**
- [x] **Step 5: reviews, then commit.** Expected outcomes to state for Sam: the two
  izumi/nag ALP2 tests now run instead of aborting at `wrap_update_hifrq_hist`; intel and
  gnu results are bit-for-bit unchanged (no value is altered by this fix); the new
  `1x1_brazil` nag test passes. Flag as a standalone upstream CTSM PR candidate — smaller
  and cleaner than Task 0b's, since it fixes a language-standard violation with no
  numerical effect at all.

### Task 1: `use_fates_moss` and moss scalar namelist plumbing

**Status: COMPLETE (2026-08-20).** FATES `030e41a1` + `d9b28108`; CTSM `66266d8eb`,
`13a5caed3`, `9cf3be6f9`. Nothing pushed.

**Files:**
- Modify: `bld/namelist_files/namelist_definition_ctsm.xml` (near `use_fates_sp`, ~line 771)
- Modify: `bld/namelist_files/namelist_defaults_ctsm.xml`
- Modify: `bld/CLMBuildNamelist.pm` (`setup_logic_fates`, ~line 4880)
- Modify: `src/main/clm_varctl.F90` (FATES block, ~lines 321–379)
- Modify: `src/main/controlMod.F90` (`clm_inparm` namelist, consistency checks, `mpi_bcast`)
- Modify: `src/utils/clmfates_interfaceMod.F90` (`CLMFatesGlobals1`/`2`)
- Modify (FATES): `main/FatesInterfaceTypesMod.F90`, `main/FatesInterfaceMod.F90`
  (`set_fates_ctrlparms`)
- Modify: `.gitmodules` (fates `url` → `https://github.com/samsrabin/fates`, `fxtag` →
  new FATES branch commit)

**Interfaces:**
- Produces (CTSM): `use_fates_moss` (logical), `fates_moss_height_allom` (char:
  `'grass_powerlaw'`/`'mat_thickness'`), `fates_moss_bulk_density` (r8, kg m-3),
  `fates_moss_fuel_moisture_live_intercept`, `fates_moss_fuel_moisture_live_slope`, `fates_moss_fuel_moisture_dead_intercept`,
  `fates_moss_fuel_moisture_dead_slope`, `fates_moss_max_burn_frac` (r8) in `clm_varctl`.
- Produces (FATES): public module variables in `FatesInterfaceTypesMod`:
  `hlm_use_moss` (integer 0/1), `hlm_moss_height_allom` (integer: 1=grass_powerlaw,
  2=mat_thickness), `hlm_moss_bulk_density`, `hlm_moss_fuel_moisture_live_intercept`, `hlm_moss_fuel_moisture_live_slope`,
  `hlm_moss_fuel_moisture_dead_intercept`, `hlm_moss_fuel_moisture_dead_slope`, `hlm_moss_max_burn_frac` (r8). All later
  FATES tasks read these.

- [x] **Step 0 (orchestrator):** Read `setup_logic_fates` and the `use_fates_sp` +
  `fates_spitfire_mode` plumbing end to end. Confirm `set_fates_ctrlparms` real-scalar
  handling (precedent: `hlm_hio_ignore_val`, `FatesInterfaceMod.F90:2210`). Forward
  check: names above are consumed verbatim by Tasks 4, 9, 10, 11. Known open questions
  for Sam: (a) confirm the name `use_fates_moss` over the CTSM convention `use_fates_*`
  (Sam has specified `use_fates_moss`; re-ask only if a build-namelist constraint forces the
  prefix); (b) default values for the four fuel-moisture coefficients (suggest
  live a=0.3, b=0.7; dead a=0.05, b=0.75 as placeholder defaults pending tuning —
  confirm Sam is OK with placeholders that will be tuned in Task 12).
- [x] **Step 1: FATES branch setup.** In `src/fates/`:
  `git checkout -b adrianna-moss-grass-pft e027a4030d2a0f09039fb337ad67ced7461dd4f0`,
  and add/verify the SSH push remote `git@github.com:samsrabin/fates.git`.
- [x] **Step 2: XML definitions.** Add to `namelist_definition_ctsm.xml` (group
  `clm_inparm`), following the `use_fates_sp` entry format:

```xml
<entry id="use_fates_moss" type="logical" category="physics"
       group="clm_inparm" valid_values="" value=".false.">
Toggle to turn on the moss plant functional type in FATES
(only relevant if FATES is being used).
</entry>
<entry id="fates_moss_height_allom" type="char*32" category="physics"
       group="clm_inparm" valid_values="grass_powerlaw,mat_thickness">
Height allometry applied to moss PFTs (only relevant if use_fates_moss is true).
</entry>
<entry id="fates_moss_bulk_density" type="real" category="physics" group="clm_inparm">
Moss mat bulk density (kg m-3) used by the mat_thickness height allometry
(only relevant if use_fates_moss is true).
</entry>
<entry id="fates_moss_fuel_moisture_live_intercept" type="real" category="physics" group="clm_inparm">
Intercept of live-moss fuel moisture as a function of the moss wetness proxy
(only relevant if use_fates_moss is true).
</entry>
```

  ...and analogous entries for `fates_moss_fuel_moisture_live_slope`, `fates_moss_fuel_moisture_dead_intercept`,
  `fates_moss_fuel_moisture_dead_slope`, plus:

```xml
<entry id="fates_moss_max_burn_frac" type="real" category="physics" group="clm_inparm">
Maximum fraction of live moss fuel that can burn in a fire
(only relevant if use_fates_moss is true).
</entry>
```

  Add defaults to `namelist_defaults_ctsm.xml`: `fates_moss_height_allom = 'grass_powerlaw'`,
  `fates_moss_bulk_density = 10.`, the four fuel-moisture coefficients (Step 0 values), and
  `fates_moss_max_burn_frac = 1.0` (see Task 9 Step 2 for why 1.0, not grass's 0.8).
- [x] **Step 3: build-namelist logic.** In `setup_logic_fates`, add the eight names to
  the `add_default` list and add fatal checks: `use_fates_moss` requires `use_fates`;
  `use_fates_moss` + `use_fates_planthydro` is fatal (message: "use_fates_moss is incompatible with
  use_fates_planthydro").
- [x] **Step 4: clm_varctl + controlMod.** Declare the eight variables in the FATES
  block of `clm_varctl.F90` with the same defaults as the XML; add to the `clm_inparm`
  namelist read, the `use_fates` consistency-check block (error if `use_fates_moss` and
  `.not. use_fates`), and the `mpi_bcast` block in `controlMod.F90`.
- [x] **Step 5: pass to FATES.** In `clmfates_interfaceMod.F90` `CLMFatesGlobals2`,
  mirror the `use_sp` pattern:

```fortran
if(use_fates_moss) then
   pass_use_moss = 1
else
   pass_use_moss = 0
end if
call set_fates_ctrlparms('use_moss',ival=pass_use_moss)
select case (trim(fates_moss_height_allom))
case ('grass_powerlaw')
   call set_fates_ctrlparms('moss_height_allom',ival=1)
case ('mat_thickness')
   call set_fates_ctrlparms('moss_height_allom',ival=2)
end select
call set_fates_ctrlparms('moss_bulk_density',rval=fates_moss_bulk_density)
call set_fates_ctrlparms('moss_fuel_moisture_live_intercept',rval=fates_moss_fuel_moisture_live_intercept)
```

  ...and the remaining three coefficients likewise.
- [x] **Step 6: FATES side.** In `FatesInterfaceTypesMod.F90` declare the eight
  `hlm_*` variables (integer/real, public). In `FatesInterfaceMod.F90`
  `set_fates_ctrlparms`: flush each to unset in the flush block, add
  `case('use_moss')` etc. to the assignment `select case`, and add "was it set?"
  checks in the verification block (pattern: `FatesInterfaceMod.F90:1837-1840`).
- [x] **Step 7: verify.** (a) `cd bld/unit_testers && ./build-namelist_test.pl` — no new
  failures; (b) manual build-namelist checks: `use_fates_moss=.true.` without FATES fails
  fatally; `use_fates_moss=.true.` + `use_fates_planthydro=.true.` fails fatally; defaults
  appear in `lnd_in` when `use_fates_moss=.true.` with FATES; (c) standing rule: ALP2
  baseline tests compare b4b.
- [x] **Step 8: reviews, then commit** (FATES commit "Add hlm_use_moss and moss scalar
  ctrlparms"; CTSM commit "Add use_fates_moss and moss scalar namelist plumbing" including
  `.gitmodules` update and submodule pointer bump).

### Task 2: Moss parameter file (JSON)

**Status: COMPLETE (2026-08-21).** FATES `18f22ed0`; CTSM pointer bump below.
Three fix rounds; scoped re-review returned all findings addressed. The file is NOT
readable by the model until Task 4, so there is no test to run for it — see Interfaces.

**Files:**
- Create (FATES): `parameter_files/fates_params_moss.json` (committed — the default
  JSON is in-repo and read directly at runtime, so the moss file is too)
- Create (FATES): `tools/make_moss_params.py` — a standalone generator using only the
  `json` stdlib module. **Not** a `batch_patch_params.py` patch file: see Step 0.
- Modify (FATES): `parameter_files/fates_params_default.json` — add `fates_vascular`
  (all 1). Moved here from Task 3 Step 3; see Step 0.

**Interfaces:**
- Produces: a FATES parameter **JSON** with (a) a 15th PFT column `non_vascular_phototroph`;
  (b) new per-PFT variable `fates_vascular` (1 for PFTs 1–14, 0 for moss); (c)
  `fates_litterclass` dimension grown 6 → 8, with entries 7 (live moss) and 8 (dead
  moss) added to **all ten** litterclass-dimensioned variables: `fates_litterclass_name`,
  `fates_fire_SAV`, `fates_fire_FBD`, `fates_fire_min_moisture`, `fates_fire_mid_moisture`,
  `fates_fire_low_moisture_Coeff/Slope`, `fates_fire_mid_moisture_Coeff/Slope`,
  `fates_frag_maxdecomp`.
- **This file is NOT usable by a model run until Task 4 lands.** `num_fuel_classes = 6` is
  a compile-time `parameter` and the `SF_val_*` arrays are fixed length-6, filled by
  `SF_val_SAV(:) = param_p%r_data_1d(:)` (`fire/SFParamsMod.F90:217`) — a non-conforming
  array assignment for an 8-entry file, which traps in a bounds-checked build and is
  silently wrong otherwise. So Tasks 2 and 3 must NOT point any test at it; the first
  consumer is Task 5, after Task 4 makes the count runtime.

- [x] **Step 0 (orchestrator) — COMPLETE (2026-08-20).** Inspected
  `8382939b9:parameter_files/fates_params_default_moss.json`, its
  `..._mossMapsBrEvTrTree.json` sibling, our in-repo default, all five ALP2 fsurdats, and
  `tools/batch_patch_params.py` + `pft_index_swapper.py`. Findings and Sam's resolutions:
  - **Schema.** Top level is `{attributes, dimensions, parameters}`; each entry is
    `{dtype, dims, long_name, units, data}`. The key is `parameters`, **not** `variables`
    — Step 2's original snippet was wrong and is corrected below. In 2-D parameters
    `fates_pft` is the LAST (innermost) JSON dimension.
  - **Generator: standalone script.** `batch_patch_params.py` *can* add the PFT column —
    `pft_index_swapper.py` uses numpy fancy indexing, so a duplicate index in
    `pft_trim_list` (`1..14,12`) makes column 15 a copy of `arctic_c3_grass` and resets
    `dimensions.fates_pft`. But it cannot (i) change `dimensions.fates_litterclass` 6→8,
    nor (ii) create a parameter absent from the base file. Hence a standalone script.
  - **ONE moss paramfile, moss on HLM PFT 4** (Sam's decision). Change
    `fates_hlm_pft_map` row 4 from `fates_pft 1 (broadleaf_evergreen_tropical_tree) = 1.0`
    to `fates_pft 15 = 1.0`. `arctic_c3_grass` KEEPS its HLM 12 mapping;
    `broadleaf_evergreen_tropical_tree` becomes orphaned. `fates_hlm_pftno` stays 14 —
    moss can never get its own HLM index, because the fsurdat `natpft` dim is 15
    (index 0 = bare + 14 natural), so it must displace an existing one.
    We deliberately do **not** port NVP's second, HLM-12 variant: Sam considers that
    two-file split messy.
    Why HLM 4 is also safer than NVP's HLM 12: because `arctic_c3_grass` keeps HLM 12,
    `_grass.nc` stays a *grass* run under both the default and the moss paramfile. Under
    NVP's choice it would silently have become a moss run, on top of the grass b4b baseline.
  - **`fates_vascular` moves into this task.** Task 2 needs it on the moss file, but Task 3
    Step 3 was what added it to the default — and a generator can only override what the
    base file already has. Verified safe to add before any code reads it:
    `FatesInterfaceMod:827` loads the whole file into `pstruct`, logs every entry, and
    `FatesTransferParameters` claims BY NAME; the only fatal direction is
    code-asks-for-missing (`JSONFindTagPos`, `JSONParameterUtilsMod.F90:798`). An
    unclaimed extra parameter is harmless. Task 3 Step 3 becomes a verification.
  - **NVP moss column is a near-copy of `arctic_c3_grass`** — only 14 `fates_pft` params
    differ. Exactly one must NOT be copied: `fates_allom_fnrt_prof_mode = 4` (NVP-only
    mode; spec §3 explicitly rejects it, and it is the exact value that broke Task 0's
    tests). Everything else is harvested as-is, **including
    `fates_rad_leaf_clumping_index = 10.0`** — Sam's ruling (2026-08-21), reversing an
    earlier decision of mine to keep grass's 0.75 on the grounds that a clumping index is
    normally ≤ 1: "I don't care — it's what the other in-progress NVP branch had, so it's
    what we're going to use." Staying aligned with the NVP branch outweighs the
    plausibility argument, and the value is a tuning input rather than a conservation
    constraint. Do not reintroduce that objection in code comments or commit messages.
  - **`fates_frag_maxdecomp`** is read only for indices 1–4 (CWD) and 5
    (`fuel_classes%dead_leaves()`) — `EDPhysiologyMod.F90:3281-3302`. Index 6 (live grass)
    is never read, so its `999.0` is a never-read placeholder. Therefore: slot 7 (live
    moss) `= 999.0` mirroring live grass, slot 8 (dead moss) `= 1.0` like dead leaves,
    which Task 7 WILL read. (`SpitFireCheckParams` only requires `>= 0`, so 999.0 passes.)
  - **`fates_litterclass_name`** slots 7–8 are `'live moss'` and `'dead moss'`, matching
    the existing lowercase-with-space style.
  - **Not double-booked:** the namelist `fates_moss_bulk_density` is for mat-thickness
    allometry (§4); fire SAV/FBD for the new classes are paramfile arrays (spec §8).
  - **Forward check.** Task 3 reads `fates_vascular` (now already present). Task 4 requires
    exactly 8 litterclass entries when `use_fates_moss` is on. Task 5 points
    `fates_paramfile` at this committed JSON — and needs a path CIME can resolve to an
    in-repo file, which is NOT yet resolved; see Task 5.
- [x] **Step 1: build the moss JSON.** Write `tools/make_moss_params.py`, then run it to
  produce `parameter_files/fates_params_moss.json` from `fates_params_default.json`:
  - Append a 15th PFT by copying the `arctic_c3_grass` column (index 12); name it
    `non_vascular_phototroph` (NVP's name — keep it verbatim).
  - Harvest from NVP's moss column: `fates_leaf_vcmax25top = 30.0` (dims
    `['fates_leafage_class','fates_pft']`), `fates_leaf_slatop = 0.027`, `fates_woody = 0`,
    `fates_leaf_stomatal_intercept = 0`, `fates_leaf_stomatal_slope_ballberry = 0`,
    `fates_leaf_stomatal_slope_medlyn = 0`, `fates_leaf_agross_btran_model = 0`,
    `fates_phen_leaf_habit = 1`, `fates_rad_leaf_taunir/tauvis = 0.01`,
    `fates_rad_stem_taunir/tauvis = 0.01`, `fates_rad_leaf_xl = 0.0`.
    plus `fates_rad_leaf_clumping_index = 10.0`.
    Do NOT harvest `fnrt_prof_mode = 4` — that one alone is rejected (Step 0).
  - Apply the spec §3 corrections: `fates_recruit_seed_dbh_repro_threshold = 0.001`,
    `fates_recruit_height_min = 0.02`, and a layer-1-concentrated rooting profile
    (`fates_allom_fnrt_prof_a = 30`, keeping `fnrt_prof_mode = 3`).
    **Note (now folded into spec §3):** the threshold drop is the *whole* reproduction
    fix. It puts moss on the mature branch, where the inherited `seed_alloc_mature = 0.25`
    applies. `fates_recruit_seed_alloc` stays at the grass/NVP value of 0 —
    Sam's ruling (2026-08-21), reverting an earlier 0.1 of mine that only raised
    allocation to 0.35 and had no correctness justification. Both `seed_alloc` and
    `seed_alloc_mature` are inherited and must not be removed from the moss column.
  - Add `fates_vascular` (dims `['fates_pft']`, dtype integer, metadata mirroring
    `fates_woody`): all 1, 0 for moss. Add it to `fates_params_default.json` too (all 1).
  - Grow `dimensions.fates_litterclass` 6 → 8 and extend all ten litterclass-dimensioned
    parameters. Slots 7–8 copy the dead-leaves (index 5) values as starting points —
    `SAV = 66.0`, `FBD = 4.0`, etc. — EXCEPT `fates_frag_maxdecomp` (999.0 / 1.0 per
    Step 0) and `fates_litterclass_name` (`'live moss'` / `'dead moss'`).
  - Set `fates_hlm_pft_map` row 4 to moss per Step 0.
  - Record in the file's `attributes` that this file is only sensible where HLM PFT 4
    carries no real area: at a tropical site it silently turns broadleaf evergreen
    tropical tree into moss.
- [x] **Step 2: generate and inspect.** Verify against the real schema:

```bash
python -c "
import json; p = json.load(open('parameter_files/fates_params_moss.json'))
P = p['parameters']
assert p['dimensions']['fates_pft'] == 15
assert p['dimensions']['fates_litterclass'] == 8
assert P['fates_pftname']['data'][-1] == 'non_vascular_phototroph'
v = P['fates_vascular']['data']; assert v[-1] == 0 and all(x == 1 for x in v[:-1])
assert P['fates_woody']['data'][-1] == 0
assert P['fates_allom_fnrt_prof_mode']['data'][-1] == 3   # NOT NVP mode 4
assert P['fates_litterclass_name']['data'][6:] == ['live moss', 'dead moss']
assert P['fates_frag_maxdecomp']['data'][6:] == [999.0, 1.0]
# every litterclass-dimensioned parameter grew to 8
for k, e in P.items():
    if 'fates_litterclass' in e['dims']:
        assert len(e['data']) == 8, k
# moss owns HLM row 4; arctic_c3_grass keeps row 12
m = P['fates_hlm_pft_map']['data']
assert m[3][14] == 1.0 and m[3][0] == 0.0
assert m[11][11] == 1.0
print('OK')"
```

  Also confirm `fates_params_default.json` still reads with 14 PFTs / 6 litterclasses and
  now carries `fates_vascular` (all 1).
- [x] **Step 3: reviews, then commit** (FATES commit: moss JSON + generator + the
  `fates_vascular` addition to the default file; CTSM pointer bump). No CTSM test points
  at the moss file yet — see the Interfaces note.

### Task 3: `fates_vascular` in FATES + moss identification

**Status: COMPLETE (2026-08-21).** FATES `ba14851d`; CTSM pointer bump below.
Three fix rounds; scoped re-review returned all findings addressed.

**Files:**
- Modify (FATES): `parteh/PRTParametersMod.F90` (add `vascular(:)` beside `woody`,
  ~line 121), `parteh/PRTParamsFATESMod.F90` (register/receive `fates_vascular`,
  pattern at lines 127–129)
- Modify (FATES): `main/FatesInterfaceMod.F90` (post-read consistency checks)
- Modify (FATES): `parameter_files/fates_params_default.json` (add `fates_vascular`,
  all 1, so default files remain valid)

**Interfaces:**
- Consumes: `hlm_use_moss` (Task 1); parameter file with `fates_vascular` (Task 2).
- Produces: `prt_params%vascular(ipft)` (integer 0/1), used exactly like
  `prt_params%woody`. Moss test everywhere later: `prt_params%vascular(ft) == ifalse`.
  Consistency guarantees for later tasks: `vascular==0` implies `woody==0`; when
  `hlm_use_moss==0` no `vascular==0` PFT exists (fatal otherwise) and vice versa.

- [x] **Step 0 (orchestrator) — COMPLETE (2026-08-21).** No open questions; the one item
  flagged for Sam resolved on evidence.
  - **Registration pattern.** `fates_woody` is a 3-line block at
    `parteh/PRTParamsFATESMod.F90:127-129` (`GetParamFromName` → `allocate(num_pft)` →
    `i_data_1d`), declared at `parteh/PRTParametersMod.F90:121` as
    `integer, allocatable :: woody(:)`. Mirror both exactly.
  - **Both checks go in `EDPftvarcon.F90`'s `FatesCheckParams`.** It already imports
    `itrue`/`ifalse` and the `hlm_use_*` family from `FatesInterfaceTypesMod` (:945, :950-952),
    already reads `prt_params%`, and already loops `do ipft = 1,npft`. `PRTCheckParams` owns
    `prt_params` but imports no `hlm_*`, so splitting the two checks across both routines
    would scatter related logic for no gain — ruling: keep them together in `FatesCheckParams`.
  - **Ordering is guaranteed.** CTSM calls `set_fates_ctrlparms('check_allset')`
    (`clmfates_interfaceMod.F90:693`) before `SetFatesGlobalElements2` (:708), which calls
    `FatesCheckParameters()` at `FatesInterfaceMod.F90:1112` under an explicit comment that it
    runs "after the parameter AND after all namelist settings because they are cross
    referenced". So `hlm_use_moss` is set before the check reads it.
  - **The Step 2 snippet below needs renaming before use.** It says `do ft = 1,numpft` and
    `vascular(1:numpft)`; in `FatesCheckParams` the local count is `npft` and the loop index
    convention is `ipft`. `numpft` does exist as a public global
    (`FatesInterfaceTypesMod.F90:384`) but importing it here would duplicate the local — use
    `npft`/`ipft`.
  - **All three check routines early-return on non-master** (`EDPftvarcon.F90:978`), so the
    new checks abort on the master rank only, like every existing one. Follow the convention.
  - **The `$DIN_LOC_ROOT` testdata-JSON worry is MOOT — nothing reads those files.** Task 0
    removed `fates_paramfile` from the ALP2 testmods, and the namelist default
    (`namelist_defaults_ctsm.xml:617`) is the in-repo
    `src/fates/parameter_files/fates_params_default.json`, which gained `fates_vascular` in
    Task 2. The only three testmods that set `fates_paramfile` — `FatesColdPRT2`,
    `FatesColdSeedDisp`, `FatesSetupParamBuild` — each `cp` the in-repo default first and
    then edit it, so they inherit the parameter. Repo-wide there are exactly two FULL
    parameter files (`fates_params_default.json`, `fates_params_moss.json`) and both carry it;
    `patch_default_bciopt224.json` and `patch_nocomp_noresm.json` are patch inputs with 2 and 1
    entries, not files FATES reads; `parameter_files/archive/` holds historical `.cdl`, not
    read at runtime. The FATES functional tests default to the in-repo file
    (`testing/run_functional_tests.py:42`). So no test breaks, and Sam need not touch
    `$DIN_LOC_ROOT`. Standing caveat for later: from this task on, any hand-rolled parameter
    file lacking `fates_vascular` aborts via `JSONFindTagPos`.
  - Forward check: Tasks 6, 7, 10, 11 branch on `prt_params%vascular`.
- [x] **Step 1: add the parameter.** Declare `integer,allocatable :: vascular(:)` in
  `prt_params`; register `fates_vascular` with dimension `fates_pft` and receive it in
  `PRTParamsFATESMod` mirroring `fates_woody`.
- [x] **Step 2: consistency checks.** Where FATES validates parameters after read, add:

```fortran
do ft = 1,numpft
   if (prt_params%vascular(ft) == ifalse .and. prt_params%woody(ft) == itrue) then
      write(fates_log(),*) 'Non-vascular PFTs must be non-woody; check PFT ',ft
      call endrun(msg=errMsg(sourcefile, __LINE__))
   end if
end do
if (hlm_use_moss == itrue .neqv. any(prt_params%vascular(1:numpft) == ifalse)) then
   write(fates_log(),*) 'use_fates_moss and the presence of a fates_vascular==0 PFT must agree'
   call endrun(msg=errMsg(sourcefile, __LINE__))
end if
```

- [x] **Step 3: default JSON — VERIFY ONLY.** Task 2 already added `fates_vascular`
  (all 1) to `parameter_files/fates_params_default.json`, because its generator could only
  override parameters the base file already had (Task 2 Step 0). Confirm it is present with
  metadata matching `fates_woody`, and that every other parameter file in
  `parameter_files/` also carries it — from this task on, the Fortran READS it, so a file
  missing it becomes fatal via `JSONFindTagPos`.
- [x] **Step 4: verify.** FATES functional suite reads the new parameter cleanly
  (`cd src/fates/testing && MPLBACKEND=Agg python run_functional_tests.py --save-figs -t allometry`,
  using the `ctsm_pylib` env — not the `fates_testing` env its `environment.yml` names, and
  do not create one; if `ctsm_pylib` cannot run it, stop and tell Sam); standing rule: ALP2
  baseline tests compare b4b
  (after resolving the testdata-JSON question from Step 0).
- [x] **Step 5: reviews, then commit** (FATES commit + CTSM pointer bump).

### Task 4: Runtime fuel-class count (6 ↔ 8) and moss fuel-class indices

**Files:**
- Modify (FATES): `fire/FatesFuelClassesMod.F90` (parameter → runtime), `fire/FatesFuelMod.F90`
  (fuel type arrays → allocatable), `fire/SFParamsMod.F90` (arrays → allocatable +
  size checks), `main/FatesInterfaceMod.F90` (set count from `hlm_use_moss`),
  `main/FatesHistoryInterfaceMod.F90` + `main/FatesRestartInterfaceMod.F90` (confirm
  fuel-class dims pick up the runtime value)
- Modify (FATES): `testing/tests/functional/fire/fuel/FatesTestFuel.F90` if it assumes 6
- Create (CTSM): a testmod that turns moss on and points `fates_paramfile` at the in-repo
  moss JSON (provisional name `FatesMossParamfile`; confirm at Step 0)
- Modify (CTSM): `cime_config/testdefs/testlist_clm.xml` (one short test, see Step 3b)

**Interfaces:**
- Consumes: `hlm_use_moss` (Task 1); 8-entry parameter file (Task 2).
- Produces: `num_fuel_classes` as a protected module **variable** (6 default, 8 when
  moss on) set via new `SetNumFuelClasses(n)`; new accessors
  `fuel_classes%live_moss()` → 7 and `fuel_classes%dead_moss()` → 8 (valid only when
  count is 8); `fuel_type` arrays (`loading`, `frac_loading`, `frac_burnt`,
  `effective_moisture`) allocatable, allocated to `num_fuel_classes` in `Init`. Tasks
  6, 7, 9 depend on these names.

- [ ] **Step 0 (orchestrator):** Enumerate every use of `num_fuel_classes`
  (`grep -rn num_fuel_classes src/fates --include=*.F90`) — known: SFMainMod,
  SFParamsMod, FatesFuelClassesMod, FatesFuelMod, FatesRestartInterfaceMod,
  FatesInterfaceMod, FatesHistoryInterfaceMod, EDTypesMod(?), functional fire tests.
  Confirm each compiles with a runtime variable (static declarations like
  `real(r8) :: x(num_fuel_classes)` in type definitions MUST become allocatable;
  local automatic arrays inside subroutines may stay). Confirm restart/history register
  their fuel-class dimension from this symbol at runtime. Verify the CWD-index
  aliasing in `EDPatchDynamicsMod` (burnt-litter loop assumes fuel classes 1–4 are
  CWD 1–4) survives appending classes 7–8 (it should — indices 1–6 are unchanged).
  Also settle the Step 3b testmod mechanics: whether a CTSM-root-relative `fates_paramfile`
  in `user_nl_clm` resolves (it is `input_pathname="landroot"`), or whether the
  `FatesColdPRT2` `shell_commands`/`xmlquery SRCROOT` pattern is required. The answer also
  settles the same open question for Task 5. Confirm the provisional testmod name with Sam if
  it matters to him; the NVP branch has no equivalent to copy.
  Forward check: Task 6 writes `loading(fuel_classes%live_moss())`; Task 9 writes
  `moisture(fuel_classes%live_moss())` and `(dead_moss)`.
- [ ] **Step 1: FatesFuelClassesMod.** Change to
  `integer, protected, public :: num_fuel_classes = 6`, add
  `subroutine SetNumFuelClasses(n)` (sets 6 or 8; `endrun` otherwise), add private
  indices `live_moss_i = 7`, `dead_moss_i = 8` with public accessor functions
  `live_moss()`/`dead_moss()` that `endrun` if `num_fuel_classes < 8`.
- [ ] **Step 2: call site.** In `FatesInterfaceMod`, immediately after ctrlparms are
  verified (before parameter read): `call SetNumFuelClasses(6 + 2*hlm_use_moss)`.
- [ ] **Step 3: allocatable conversions.** `fuel_type` members and `SFParamsMod`
  `SF_val_*` arrays become allocatable; allocate in `fuel_type%Init` and
  `SpitFireParamsInit` respectively. In `TransferParamsSpitFire`, after receiving each
  litterclass array, check `size(param_p%r_data_1d) == num_fuel_classes`; on mismatch,
  `endrun` with: "fates_litterclass dimension must be 8 when use_fates_moss is on, 6
  otherwise".
- [ ] **Step 3b: first CLM-level test of the 8-class parameter file.** This task is where
  the moss JSON becomes readable at all, so it is the earliest point a CLM test can use it —
  Task 5 is merely where the plan had concentrated the testlist work. Add one now, because
  this task's highest risk is an accidental history or restart shape change from making the
  fuel-class count runtime, and no FATES functional test can see CLM's history/restart files.
  - Create a testmod setting `use_fates_moss = .true.` and pointing `fates_paramfile` at
    `src/fates/parameter_files/fates_params_moss.json`. Two viable mechanics: `fates_paramfile`
    is declared `input_pathname="landroot"` (`namelist_definition_ctsm.xml:1054-1055`) and its
    default is the CTSM-root-relative `src/fates/parameter_files/fates_params_default.json`, so
    a relative path in `user_nl_clm` may just work; the proven alternative is the
    `shell_commands` pattern used by `FatesColdPRT2` — `xmlquery SRCROOT`, then append an
    absolute `fates_paramfile = '...'` to `user_nl_clm`. **Step 0 must determine which form
    works from a testmod**, since the answer also settles the same open question for Task 5.
  - Compose it with an existing ALP2 fsurdat testmod and add one short test (`SMS_Ld5_D`,
    mpi-serial if the grid allows). Expected outcome: PASS.
  - **This needs no new surface dataset, and that is the point.** Our parameter file puts moss
    on HLM PFT 4, which neither `_bare.nc` nor `_grass.nc` populates, so moss exists as a PFT
    with zero area. Orphaned FATES columns are already normal — the shipped default file
    leaves `fates_pft` 8 unmapped. So this test does not block on the moss fsurdat that Sam
    generates at Task 5, and Tasks 3-4 stop being a stretch of new Fortran with no CLM-level
    coverage.
  - Be explicit about what it does and does not prove: it exercises the runtime fuel-class
    sizing, the 8-entry litterclass read, the Task 3 `vascular`/`use_fates_moss` agreement
    check, and CLM history/restart shapes under `use_fates_moss = .true.` It exercises **no
    moss science**, because there is no moss area. It also carries no baseline — CIME keys
    baselines by full test name including testmods, so this is a new name and a PASS/FAIL
    test only; the b4b instrument remains the Task 0 tests.
- [ ] **Step 4: verify.** (a) FATES fuel functional test with a standard 6-class file
  (`MPLBACKEND=Agg python run_functional_tests.py --save-figs -t fuel`) — identical results to
  pre-change; (b) with
  the Task 2 moss file → clean abort unless the test driver sets `hlm_use_moss` (set
  it where the harness sets ctrlparms); (c) standing rule: ALP2 baseline tests compare
  b4b (this task is the highest-risk one for accidental shape changes — check history
  and restart dimensions in the baseline-compare output explicitly).
- [ ] **Step 5: reviews, then commit.**

### Task 5: First moss run — moss testmods and system tests

**Files:**
- Create: `cime_config/testdefs/testmods_dirs/clm/FatesNvp/user_nl_clm` (adapted from
  the NVP branch's dir of the same name)
- Create: `cime_config/testdefs/testmods_dirs/clm/FatesNvpOff/{user_nl_clm,include_user_mods}`
  (ditto)
- Create: `cime_config/testdefs/testmods_dirs/clm/FatesALP2BareMoss/user_nl_clm` (ditto)
- Create: `cime_config/testdefs/testmods_dirs/clm/FatesALP2BareGrassMoss/user_nl_clm`
  (ditto)
- Modify: `cime_config/testdefs/testlist_clm.xml`

**Interfaces:**
- Consumes: `use_fates_moss` (Task 1), moss JSON (Task 2), `fates_vascular` checks (Task 3),
  8-class runtime sizing (Task 4).
- Produces: the moss test set every subsequent task hands to Sam (standing
  verification rule): smoke (`SMS_Ld5_D`) and exact-restart (`ERS_D`) moss tests at
  ALP2, including tests exercising the **nocomp fixed-biogeography** configuration. At
  this point moss runs as an inert grass-like PFT (fuel classes 7–8 exist but are
  empty; no moss physiology yet) — the tests prove the configuration runs, restarts
  exactly, and conserves. `FatesNvp`'s `user_nl_clm` is also where Tasks 6–10 add
  their new history variables as outputs.

NVP-branch source material (adapt, keeping the testmod names): `FatesNvp` (sets
`use_nvp=.true.`, `use_nvp_undersnow`, `nvp_rad_model_ground`, `use_bedrock=.true.`),
`FatesNvpOff` (includes `FatesNvp`, overrides `use_nvp=.false.`), `FatesALP2BareMoss`
and `FatesALP2BareGrassMoss` (moss fsurdat variants `_moss`/`_grassmoss` +
NVP-branch moss param JSONs).

**Blocking prerequisite — a new fsurdat that only Sam can create (from Task 2 Step 0).**
Because we commit ONE moss paramfile with moss on HLM PFT 4, the existing
`..._moss.nc` fsurdat — whose 94.25% sits on natpft 12 — produces a *grass* run under it,
not a moss run. `FatesALP2BareMoss` therefore needs a moss-at-index-4 counterpart.
`FatesALP2BareGrassMoss` needs nothing: `..._grassmoss.nc` already has its moss on index 4.

A tested generator for that file is written and handed to Sam:
`./make_moss_pft4_fsurdat.py` at the top of the CTSM checkout — deliberately left
**untracked and un-run until this task** (Sam, 2026-08-21); do not commit it, gitignore
it, or run it before then. netCDF4 + numpy + stdlib, for the `ctsm_pylib` env. It moves
`PCT_NAT_PFT` *and* all four `MONTHLY_*` columns from index 12 to 4 — moving the area alone
would give moss the stock tropical-tree canopy (`MONTHLY_HEIGHT_TOP` 29.35 m vs the
hand-tuned 0.034 m at index 12), which matters because FATES-SP prescribes LAI/SAI/height
from those arrays. **Claude has no write access to `$DIN_LOC_ROOT`**; Sam runs the script
and chooses the filename, datestamp and location. Task 5 cannot start its moss tests until
that file exists.

Two observations about the existing fsurdats, recorded but NOT acted on:
- `..._grassmoss.nc` looks buggy at its moss index: `MONTHLY_HEIGHT_BOT` is 0.839 m
  (the original tropical-tree value) while its `MONTHLY_HEIGHT_TOP` is 0.034 m — bottom
  above top. Three of the four columns were moved, not four. Check before relying on it.
- `..._grass.nc` is also hand-tuned: its index 12 `MONTHLY_HEIGHT_TOP` is 0.043 m, not the
  stock 0.50 m the plain and `_bare` files carry. So Task 0's grass baseline is a 4 cm
  canopy — fine, but the baselines are specific to these edited files.

- [ ] **Step 0 (orchestrator):** Inspect the four NVP-branch testmods and the full
  NVP-branch `testlist_clm.xml` block at `1x1_ALP2` (including entries beyond the four
  Task 0 brought in — identify the ones exercising nocomp fixed-biogeography, per the
  NVP test comments). Already resolved in Task 0's Step 0, do not re-ask: (a) `FatesNvp`
  on our branch contains **only** `use_fates_moss = .true.` — the `use_nvp*` /
  `nvp_rad_model_ground` settings don't exist here, and `use_bedrock = .true.` lives in
  the `FatesALP2*` testmods instead (so drop that line when porting `FatesNvp`);
  (b) `FatesNvpOff` correspondingly includes `../FatesNvp` and overrides
  `use_fates_moss = .false.`; (c) the two new ALP2 moss testmods keep their NVP fsurdat paths
  and also carry `use_bedrock = .true.`, but point `fates_paramfile` at the committed
  Task 2 JSON — never at a `$DIN_LOC_ROOT` testdata JSON, which both lack the 8-entry
  litterclass dimension AND set the NVP-only `fates_allom_fnrt_prof_mode = 4` on their
  moss PFT (see Task 0 Step 1: that mode does not exist in our FATES pin and aborts any
  vegetated patch in `set_root_fraction`). Task 2's moss column must therefore use a
  rooting mode our FATES supports (1–3), consistent with spec §3's "shallow grass-style
  roots, NOT the NVP branch's no-root profile mode 4";
  (d) categories are the NVP branch's `fates_nvp*` scheme, machines derecho intel/gnu +
  izumi nag. Still to confirm with Sam: which NVP-branch test entries to bring in beyond
  the nocomp-fixedbiogeo and `FatesNvpOff` sets. Forward check: Tasks 6–11 hand these
  tests to Sam and Tasks 6–10 append history variables to `FatesNvp/user_nl_clm`.
- [ ] **Step 1: port the four testmods**, adapted per Step 0.
- [ ] **Step 2: testlist.** Add the remaining NVP-branch tests (adapted testmod
  compositions), covering: SP-mode moss (`FatesColdSatPhen--FatesNvp--FatesALP2*Moss`
  patterns), the `FatesNvpOff` twins (moss code present but off — b4b sentinels), and
  the nocomp fixed-biogeography moss tests identified in Step 0; include an `ERS_D`
  exact-restart variant.
- [ ] **Step 3: build check.** `cd test-bld-adrianna-moss-grass-pft && qcmd -- ./case.build` passes.
- [ ] **Step 4: state the expected outcomes** for Sam's review, naming each new test:
  PASS with moss as an inert grass-like PFT, exact restart, fatal conservation checks
  clean; the abort case (`use_fates_moss=.true.` with the default 6-class JSON) aborts cleanly
  with the Task 3/4 messages. Flag to Sam that the `FatesNvpOff` tests cannot be compared
  against the Task 0 baselines — CIME keys baselines by full test name including
  testmods, and these carry `--clm-FatesNvpOff--` — so they need baselines generated here
  if they are to serve, from Task 6 on, as the moss-off b4b sentinel alongside Task 0's
  plain tests. Moss baselines generated at this task would likewise let later tasks see
  exactly what each change does to moss behavior. Whether and how to generate any of
  these is Sam's call.
- [ ] **Step 5: reviews, then commit.** Sam's post-commit review optionally runs the
  hand-off.

### Task 6: Live-moss fuel routing, cohort burn keying, and live-moss history

**Files:**
- Modify (FATES): `biogeochem/FatesPatchMod.F90` (`UpdateLiveGrass`, ~lines 814–842;
  add `livemoss` patch member beside `livegrass`)
- Modify (FATES): `fire/SFMainMod.F90` (`UpdateFuelCharacteristics`, ~lines 164–186)
- Modify (FATES): `biogeochem/EDPatchDynamicsMod.F90` (cohort burn keying, ~lines
  1096–1103)
- Modify (FATES): `main/FatesHistoryInterfaceMod.F90` (`FATES_LIVEMOSS_FUEL`)
- Modify: `cime_config/testdefs/testmods_dirs/clm/FatesNvp/user_nl_clm` (add the new
  history variable to the output list)

**Interfaces:**
- Consumes: `prt_params%vascular` (Task 3), `fuel_classes%live_moss()` (Task 4).
- Produces: `currentPatch%livemoss` (r8, kgC m-2), filled alongside `livegrass`;
  `loading(fuel_classes%live_moss()) = currentPatch%livemoss`; history variable
  `FATES_LIVEMOSS_FUEL` (site-level kgC m-2, registered only when `hlm_use_moss` —
  this task establishes the conditional-registration pattern later tasks follow).

- [ ] **Step 0 (orchestrator):** Re-read `UpdateLiveGrass` and the burn-keying block;
  confirm `UpdateTreeGrassArea` (accepted: moss stays lumped as "grass" for wind
  attenuation, spec §12) needs no change. Identify the conditional-registration
  precedent in `FatesHistoryInterfaceMod` (e.g., hydro-only variables) for the history
  step. Forward check: Task 7 must NOT double-count moss in `livegrass`; the history
  pattern here is reused by Tasks 7, 8, 10.
- [ ] **Step 1: split live pools.** In `UpdateLiveGrass`, for non-woody cohorts branch
  on `prt_params%vascular(pft)`:

```fortran
if (prt_params%woody(pft) == ifalse) then
   biomass = (leaf_c + sapw_c + struct_c)*currentCohort%n/this%area
   if (hlm_use_moss == itrue .and. prt_params%vascular(pft) == ifalse) then
      this%livemoss = this%livemoss + biomass
   else
      this%livegrass = this%livegrass + biomass
   end if
end if
```

  (initialize/zero `livemoss` wherever `livegrass` is; add to patch init/flush.)
- [ ] **Step 2: loading.** In `UpdateFuelCharacteristics`, where
  `loading(live_grass)` is set from `livegrass`, add (guarded by
  `hlm_use_moss == itrue`): `loading(fuel_classes%live_moss()) = currentPatch%livemoss`.
- [ ] **Step 3: cohort burn keying.** In `EDPatchDynamicsMod` where non-woody cohorts
  take `leaf_burn_frac = frac_burnt(fuel_classes%live_grass())`, moss cohorts
  (`vascular==ifalse`) instead take `frac_burnt(fuel_classes%live_moss())`.
- [ ] **Step 4: history.** Register and fill `FATES_LIVEMOSS_FUEL` (patch `livemoss`
  area-weighted to site), guarded by `hlm_use_moss`.
- [ ] **Step 5: verify.** (a) Fuel functional test: with a moss live pool in the driver
  data, `loading(7)` equals the input moss biomass and `SumLoading` includes it; 6-class
  run unchanged; (b) moss ALP2 tests: PASS, and `FATES_LIVEMOSS_FUEL` in the history
  file is nonzero and equals what previously appeared in the live-grass fuel class for
  the moss patch (loading moved classes, total conserved); (c) ALP2 baselines b4b.
- [ ] **Step 6: reviews, then commit.**

### Task 7: `moss_fines` litter pool — dead-moss biomass, decomposition, burning, history

**Files:**
- Modify (FATES): `biogeochem/FatesLitterMod.F90` (type members, `InitAllocate`,
  `ZeroFlux`/init, `FuseLitter` ~lines 200–216, `CopyLitter` ~lines 242–249)
- Modify (FATES): `biogeochem/EDPhysiologyMod.F90` (leaf/stem fines routing,
  ~lines 2951–2990; fragmentation)
- Modify (FATES): `biogeochem/EDPatchDynamicsMod.F90` (litter burn ~lines 2057–2096;
  disturbance litter transfer)
- Modify (FATES): `main/FatesRestartInterfaceMod.F90` (restart the new pools)
- Modify (FATES): mass-accounting sites that sum litter (e.g. `SiteMassStock` /
  patch litter totals in `EDTypesMod.F90` / `FatesUtilsMod` — Step 0 enumerates)
- Modify (FATES): `fire/SFMainMod.F90` (`loading(dead_moss) = sum(litt%moss_fines(:))`)
- Modify (FATES): `main/FatesHistoryInterfaceMod.F90` (`FATES_MOSS_FINES`)
- Modify: `cime_config/testdefs/testmods_dirs/clm/FatesNvp/user_nl_clm` (add the new
  history variable to the output list)

**Interfaces:**
- Consumes: `prt_params%vascular` (Task 3), `fuel_classes%dead_moss()` (Task 4).
- Produces: on `litter_type`: `moss_fines(ndcmpy)`, `moss_fines_in(ndcmpy)`,
  `moss_fines_frag(ndcmpy)` (all r8, kg m-2 and kg m-2 day-1), behaving exactly as the
  `leaf_fines` triplet; `loading(dead_moss)` populated; history `FATES_MOSS_FINES`
  (site-level kg m-2). Task 9 needs `dead_moss` loading populated.

- [ ] **Step 0 (orchestrator):** Enumerate ALL touch points of `leaf_fines` (`grep -rn
  leaf_fines src/fates --include=*.F90`) — every site must be evaluated for a
  `moss_fines` twin: init/allocate/zero, fuse, copy, turnover input, fragmentation,
  burn, disturbance-driven litter transfer between patches, seed/litter mass checks,
  restart, history, and the CTSM-BGC flux export (`FatesSoilBGCFluxMod` /
  `flux_diags`). Missing any conservation-accounting site is a mass-balance error —
  this enumeration is the core of the task. Confirm with Sam: moss fine-ROOT litter
  stays in ordinary `root_fines` (roots are a plumbing fiction; suggested: yes).
  Forward check: Task 9 moisture for `dead_moss`; the moss ALP2 ERS test is the
  conservation proof.
- [ ] **Step 1: type + threading.** Add the three members mirroring the `leaf_fines`
  triplet at every site enumerated in Step 0 (allocation `ndcmpy`, zeroing, fuse with
  the same weighting arithmetic, copy, restart registration mirroring the existing
  `leaf_fines` restart pattern).
- [ ] **Step 2: routing.** In `EDPhysiologyMod` where non-woody cohorts' leaf and stem
  turnover/mortality carbon enters `leaf_fines_in`, route moss cohorts
  (`vascular==ifalse`) to `moss_fines_in` instead. Fragmentation: mirror the
  `leaf_fines_frag` computation for `moss_fines_frag` using `SF_val_max_decomp(
  fuel_classes%dead_moss())` as its decay modifier, and add `moss_fines_frag` into the
  same aggregate fragmentation flux that `leaf_fines_frag` feeds (so CTSM-BGC sees one
  combined fines flux — no CTSM-side change).
- [ ] **Step 3: fuel + burn.** `loading(fuel_classes%dead_moss()) =
  sum(litt%moss_fines(:))` beside the dead-leaves loading; in the
  `EDPatchDynamicsMod` burnt-litter block, burn `moss_fines` by
  `frac_burnt(fuel_classes%dead_moss())` with the same bookkeeping
  (`burned_mass` accounting) as `leaf_fines`.
- [ ] **Step 4: history.** Register and fill `FATES_MOSS_FINES` per the Task 6 pattern.
- [ ] **Step 5: verify.** (a) Fuel functional test: nonzero `moss_fines` →
  `loading(8)` matches; (b) FATES unit/patch tests (`python run_unit_tests.py`,
  `MPLBACKEND=Agg python run_functional_tests.py --save-figs -t patch`); (c) moss ALP2 SMS +
  **ERS** tests PASS —
  the exact-restart test now covers the restarted `moss_fines` pools, and fatal
  balance checks prove the routing conserves; `FATES_MOSS_FINES` accumulates over the
  run and dead-leaves fuel drops correspondingly for the moss patch; (d) ALP2
  baselines b4b.
- [ ] **Step 6: reviews, then commit.**

### Task 8: fwet proxy — canopy wetted fraction `bc_in` field, patch `fwet_moss`, and fwet history

**Files:**
- Modify (FATES): `main/FatesInterfaceTypesMod.F90` (declare `fwet_veg_pa` in
  `bc_in_type`, patch-dimensioned), `main/FatesInterfaceMod.F90` (`allocate_bcin`
  with `maxpatch_total`, `zero_bcs`)
- Modify: `src/utils/clmfates_interfaceMod.F90` (fill from
  `waterdiagnosticbulk_inst%fwet_patch`; wire the instance into the wrapper that
  runs before fire/photosynthesis — per Step 0)
- Modify (FATES): `biogeochem/FatesPatchMod.F90` (add `fwet_moss` patch member) and the
  site-level update loop (`EDMainMod` daily driver or `SFMainMod` entry — Step 0 picks
  the single update point)
- Modify (FATES): `main/FatesHistoryInterfaceMod.F90` (`FATES_MOSS_FWET`,
  `FATES_MOSS_FWET_SOIL`, `FATES_MOSS_FWET_CANOPY`)
- Modify: `cime_config/testdefs/testmods_dirs/clm/FatesNvp/user_nl_clm` (add the new
  history variables to the output list)

**Interfaces:**
- Consumes: `bc_in%h2o_liqvol_sl(:)`, `bc_in%watsat_sl(:)` (existing;
  `FatesInterfaceTypesMod.F90:533-548`), CTSM `fwet_patch`
  (`WaterDiagnosticBulkType.F90:78`).
- Produces: `bc_in(s)%fwet_veg_pa(ifp)` (r8, 0–1) and
  `currentPatch%fwet_moss = max(min(h2o_liqvol_sl(1)/watsat_sl(1), 1._r8),
  bc_in%fwet_veg_pa(ifp))`, updated once per day before fire; history variables for
  the proxy and both ingredients. Tasks 9 and 10 read `currentPatch%fwet_moss`.

- [ ] **Step 0 (orchestrator):** Choose the fill site in `clmfates_interfaceMod`: it
  must run before `wrap_spitfire` each FATES dynamics step — inspect where
  `precip24_pa`-style fire weather inputs are filled and co-locate. Confirm
  `waterdiagnosticbulk_inst` is reachable there (otherwise add it to the call
  signature from `clm_driver.F90`). Confirm top soil layer index 1 is correct for
  `h2o_liqvol_sl`. Ask Sam: should the soil half use liquid only (suggested: yes —
  frozen layer-1 water should read as "dry" fuel-wise)? Forward check: Tasks 9, 10
  read `fwet_moss` by that exact name.
- [ ] **Step 1: 4-touch `bc_in` field.** Declare, allocate (`maxpatch_total`), zero, and
  fill `fwet_veg_pa` from `fwet_patch(p)` for exposed-veg patches.
- [ ] **Step 2: patch member + update.** Add `fwet_moss` to `fates_patch_type` (init
  0), compute it at the chosen daily update point, guarded by `hlm_use_moss`.
- [ ] **Step 3: history.** Register and fill `FATES_MOSS_FWET` (the max),
  `FATES_MOSS_FWET_SOIL` (soil ingredient), `FATES_MOSS_FWET_CANOPY` (canopy wetted
  fraction as received) per the Task 6 pattern.
- [ ] **Step 4: verify.** Moss ALP2 tests PASS; in the history, `FATES_MOSS_FWET`
  tracks rain events (canopy ingredient spikes with precipitation and decays;
  soil ingredient varies smoothly; the max is always ≥ both); ALP2 baselines b4b.
- [ ] **Step 5: reviews, then commit.**

### Task 9: Moss fuel moisture

**Files:**
- Modify (FATES): `fire/FatesFuelMod.F90` (`UpdateFuelMoisture`, lines 189–236)
- Modify (FATES): `fire/SFMainMod.F90` (pass `currentPatch%fwet_moss` down)
- Modify (FATES): `testing/tests/functional/fire/fuel/FatesTestFuel.F90` (+ its Python
  checker) — moss moisture cases

**Interfaces:**
- Consumes: `currentPatch%fwet_moss` (Task 8), `fuel_classes%live_moss()/dead_moss()`
  (Task 4), `hlm_moss_fuel_moisture_live_intercept/slope`, `hlm_moss_fuel_moisture_dead_intercept/slope`, `hlm_moss_max_burn_frac`
  (Task 1).
- Produces: `fuel%moisture(live_moss) = hlm_moss_fuel_moisture_live_intercept + hlm_moss_fuel_moisture_live_slope*fwet`
  (floored at 0); analogous for `dead_moss`. Effective moisture and `frac_burnt` for
  the moss classes then flow through existing code untouched. Fuel-class-dimensioned
  history (moisture, loading) already extends to 8 via Task 4 — this task's run
  verifies those outputs are sensible.

- [ ] **Step 0 (orchestrator):** Re-read `UpdateFuelMoisture` + `CalculateFuelBurnt`.
  **The max-burn-fraction question is already decided — do not re-ask.** Moss does NOT
  reuse grass's cap: see Step 2. Note MEF is computed from SAV
  (`FatesFuelMod.F90:271-313`) — moss MEF therefore follows moss SAV; flag to Sam that
  tuning moss SAV (Task 2 file) is the only MEF lever, per spec's accepted design.
  Forward check: none downstream.
- [ ] **Step 1: signature.** Extend `UpdateFuelMoisture(this, sav_fuel, drying_ratio,
  fireWeatherClass)` with `fwet_moss` (r8, intent(in); always passed, ignored when
  `hlm_use_moss==ifalse` — match FATES style). Update the SFMainMod call site.
- [ ] **Step 2: moss branches.** After the existing per-class Nesterov loop:

```fortran
if (hlm_use_moss == itrue) then
   this%moisture(fuel_classes%live_moss()) = max(0._r8, &
        hlm_moss_fuel_moisture_live_intercept + hlm_moss_fuel_moisture_live_slope*fwet_moss)
   this%moisture(fuel_classes%dead_moss()) = max(0._r8, &
        hlm_moss_fuel_moisture_dead_intercept + hlm_moss_fuel_moisture_dead_slope*fwet_moss)
end if
```

  (before `effective_moisture` is computed so moss classes get MEF-normalized like the
  rest).

  **Max burn fraction: moss gets its own namelist value, NOT grass's cap.** This
  implements spec §6's moss-specific cap. The existing grass cap is a hardcoded
  `real(r8), parameter :: max_grass_frac = 0.8_r8` at `FatesFuelMod.F90:400`, applied in
  `CalculateFuelBurnt` only when `i == fuel_classes%live_grass()`
  (`FatesFuelMod.F90:426-429`, comment "we can't ever kill all of the grass"). Grass keeps
  that untouched. Add a parallel branch for the live-moss class that caps with
  `hlm_moss_max_burn_frac` (Task 1) instead:

```fortran
        ! we can't ever kill all of the grass
        if (i == fuel_classes%live_grass()) then
          this%frac_burnt(i) = min(max_grass_frac, this%frac_burnt(i))
        else if (hlm_use_moss == itrue .and. i == fuel_classes%live_moss()) then
          this%frac_burnt(i) = min(hlm_moss_max_burn_frac, this%frac_burnt(i))
        end if
```

  Rationale for the 1.0 default: grass's 0.8 encodes surviving tillers/meristems, which
  moss has no equivalent of — a moss mat can burn off completely. At the default the
  `min` is a no-op (`frac_burnt` is already ≤ 1), so the default imposes no cap at all;
  the namelist exists so the cap can be tightened during tuning (Task 12) without a code
  change. Note this is the fuel-class consumption cap; it is what Task 6's cohort burn
  keying reads through `frac_burnt(fuel_classes%live_moss())`, so moss cohort
  `leaf_burn_frac` inherits the same limit automatically — no separate change there.
- [ ] **Step 3: functional test.** Add moss cases to the fuel functional test: given
  fwet_moss ∈ {0, 0.5, 1}, assert `moisture(7)` and `moisture(8)` equal the linear
  form; assert grass/leaf classes unchanged vs. the 6-class baseline run. Run
  `MPLBACKEND=Agg python run_functional_tests.py --save-figs -t fuel`.
- [ ] **Step 4: verify in-model.** Moss ALP2 tests PASS; fuel-class-dimensioned
  moisture history for classes 7–8 tracks `FATES_MOSS_FWET` (linear map) while classes
  1–6 keep tracking the Nesterov index; ALP2 baselines b4b.
- [ ] **Step 5: reviews, then commit.**

### Task 10: Moss physiology — no stomatal solve, wetness-limited vcmax, scaler history

**Files:**
- Modify (FATES): `biogeophys/LeafBiophysicsMod.F90` (`CiFunc` ~lines 901–1079,
  `CiBisection`, `LeafLayerBiophysicalRates` ~lines 1826–2036)
- Modify (FATES): `biogeophys/FatesPlantRespPhotosynthMod.F90` (thread
  `currentPatch%fwet_moss` down; moss branch selection)
- Modify (FATES): `biogeochem/FatesPatchMod.F90` (add `moss_vcmax_scaler` patch member,
  init 0, beside `fwet_moss` from Task 8)
- Modify (FATES): `main/FatesHistoryInterfaceMod.F90` (`FATES_MOSS_VCMAX_SCALER`)
- Modify: `cime_config/testdefs/testmods_dirs/clm/FatesNvp/user_nl_clm` (add the new
  history variable to the output list)

**Interfaces:**
- Consumes: `prt_params%vascular` (Task 3), `currentPatch%fwet_moss` (Task 8).
- Produces: for moss cohorts only — (a) `vcmax_z` scaled by
  `min(1._r8, fwet_moss/0.6_r8)`; (b) Ci solved with no stomatal conductance: CO₂
  through the boundary layer with water-film factor, harvested from the NVP branch
  (`git -C src/fates show 33640d372:biogeophys/LeafBiophysicsMod.F90`, the
  `nvp_model=3` branch at ~lines 1075–1099):
  `fval = ci - (can_co2_ppress - anet*can_press*1.4/(gb_mol*max(max(1-fwet,0.1)**12, 1.e-6)))`,
  with `gs` reported as the existing minimum (`gs0`). Vascular PFTs bit-for-bit
  unchanged. History `FATES_MOSS_VCMAX_SCALER`.

- [ ] **Step 0 (orchestrator):** Read the NVP branch's `nvp_model=3` `CiFunc` branch and
  the current `CiFunc`/`CiBisection` call chain; map exactly which optional arguments
  must be threaded (`fwet` down through `LeafLayerPhotosynthesis` → `CiFunc`). Decide
  the branch key: use `prt_params%vascular(ft)==ifalse` directly rather than a global
  `stomatal_model` value (this is the per-PFT dispatch, spec §5). Confirm `btran`
  needs no override (moss uses shallow-root btran, spec §3/§5) — verify the moss
  rooting profile from Task 2 produces sane `btran_ft`. Ask Sam: apply the
  vcmax-wetness scaler to leaf maintenance respiration too, or photosynthetic capacity
  only (suggested: capacity only, matching Porada; NVP branch precedent — check)?
  Forward check: none downstream.
- [ ] **Step 1: thread fwet.** Add `fwet_moss` (r8) as an optional argument through
  `LeafLayerPhotosynthesis` and into `CiFunc`/`CiBisection`, following the NVP
  branch's threading (same routine names at `33640d372`).
- [ ] **Step 2: moss Ci branch.** Inside `CiFunc`, when the moss flag argument is
  present/true, replace the stomatal-model residual with the boundary-layer-only form
  above; set the returned `gs` to the existing floor (`gs0`) so downstream CTSM
  `rssun/rssha` stay finite.
- [ ] **Step 3: vcmax scaling + history.** In `LeafLayerBiophysicalRates` (or at its
  call site where `vcmax_z` emerges — follow NVP branch placement at
  `FatesPlantRespPhotosynthMod.F90:~806`), for moss cohorts multiply `vcmax_z` by
  `min(1._r8, fwet_moss/0.6_r8)`; store the applied scaler in
  `currentPatch%moss_vcmax_scaler` (acceptable given one moss PFT per patch in nocomp;
  note full-comp refinement in a code comment) and register/fill
  `FATES_MOSS_VCMAX_SCALER` per the Task 6 pattern.
- [ ] **Step 4: verify.** Moss ALP2 tests PASS; in history, moss-PFT GPP
  (`FATES_GPP_PF`) is nonzero and covaries with `FATES_MOSS_FWET`;
  `FATES_MOSS_VCMAX_SCALER` equals `min(1, fwet/0.6)`; vascular-PFT GPP in the
  BareGrass baseline is b4b (ALP2 baseline compare); fuel + allometry functional
  tests green.
- [ ] **Step 5: reviews, then commit.**

### Task 11: Mat-thickness height allometry (namelist-selectable)

**Files:**
- Modify (FATES): `biogeochem/FatesAllometryMod.F90` (`h_allom` ~lines 336–369,
  `h2d_allom`)
- Modify (FATES): `testing/tests/functional/allometry/` (new mode coverage)

**Interfaces:**
- Consumes: `hlm_moss_height_allom`, `hlm_moss_bulk_density` (Task 1),
  `prt_params%vascular` (Task 3).
- Produces: `h_allom` case "mat thickness": for moss PFTs when
  `hlm_moss_height_allom==2`,
  `h = (blmax(d) * c2b) / (c_area_nom(d) * hlm_moss_bulk_density)` where
  `c_area_nom(d)` is the crown area at nominal spread (the `carea_2pwr` form with
  spread-max coefficient), i.e. mat thickness = leaf dry mass per crown area / bulk
  density; `h2d_allom` inverts by bisection on d ∈ [1e-6, d(maxheight)]. `ForceDBH`
  and recruitment then work unmodified.

- [ ] **Step 0 (orchestrator):** Read `h_allom`/`h2d_allom` dispatch and `carea_2pwr`
  (`FatesAllometryMod.F90:2606-2661`) to fix the exact nominal-spread expression
  (`spreadterm` at maximum spread — the `d2ca_coefficient_max` path). Confirm mode
  selection mechanics: rather than a new `allom_hmode` value on the parameter file,
  branch inside `h_allom`: `if (vascular==ifalse .and. hlm_moss_height_allom==2)` →
  mat-thickness; else fall through to the PFT's `allom_hmode` (grass power law for
  moss when ==1). This keeps the namelist in control per spec §4/§8 — confirm with
  Sam. Check monotonicity of h(d) under the 3pwr-grass `blmax` saturation so bisection
  is safe over the full d range. Forward check: none downstream.
- [ ] **Step 1: implement `h_allom` mat-thickness branch** (with `dhdd` by the same
  analytic differentiation pattern used by neighboring cases, or centered finite
  difference if the saturation term resists closed form — match file conventions).
- [ ] **Step 2: implement `h2d_allom` bisection inverse** (tolerance 1e-9 m on h;
  `endrun` on non-convergence).
- [ ] **Step 3: functional test.** Extend the allometry functional test config to run
  the moss PFT under both modes; assert round-trip `h2d(h_allom(d)) ≈ d` to 1e-6 and
  that thickness is linear in `blmax/c_area`. Run
  `MPLBACKEND=Agg python run_functional_tests.py --save-figs -t allometry`.
- [ ] **Step 4: verify in-model.** Run the moss ALP2 SMS test once per
  `fates_moss_height_allom` mode (a user_nl override run for `mat_thickness`); both PASS;
  moss height history differs between modes as expected; ALP2 baselines b4b.
- [ ] **Step 5: reviews, then commit.**

### Task 12: Final integration, science sanity, and test-suite consolidation

**Files:**
- Modify: `cime_config/testdefs/testlist_clm.xml` (fill any gaps: one test per
  `fates_moss_height_allom` mode if not added in Task 11; the full `fates_moss` category)
- Modify: `cime_config/testdefs/ExpectedTestFails.xml` (only if genuinely needed)

**Interfaces:**
- Consumes: everything.
- Produces: the complete spec §10 test matrix, green.

- [ ] **Step 0 (orchestrator):** Review accumulated test coverage from Tasks 0, 5–11
  against spec §10; list gaps. Ask Sam: any additional history variables or tests
  wanted before calling the implementation complete?
- [ ] **Step 1: consolidate the suite.** Ensure the `fates_moss` category contains: the
  ALP2 baselines (Task 0), the moss SMS + ERS tests (Task 5), and a mat-thickness-mode
  test; run the full category on the target machine — all PASS with fatal conservation
  checks.
- [ ] **Step 2: b4b-off final sweep.** Re-run the Task 0 baseline compare and (if the
  machine has an aux_clm baseline) a broader no-moss FATES test against baseline —
  bit-for-bit.
- [ ] **Step 3: science sanity.** In the moss run's history: moss GPP > 0 and responds
  to `FATES_MOSS_FWET`; `FATES_LIVEMOSS_FUEL` and `FATES_MOSS_FINES` nonzero and
  seasonal; fire behavior responds to moss moisture (compare two short runs with
  perturbed `fates_moss_fuel_moisture_*` coefficients); `FATES_NOCOMP_PATCHAREA_PF` reports
  the prescribed moss cover.
- [ ] **Step 4: reviews, then commit** (including any ExpectedTestFails hygiene, with
  each entry justified).

---

## Self-review checklist (run after writing; completed 2026-08-19)

1. **Spec coverage:** §3→Tasks 2–3; §4→Task 11; §5→Tasks 8, 10; §6→Tasks 4, 6, 7, 9;
   §7→Task 8; §8→Task 1; §9→history distributed into Tasks 6–10 (variables land with
   their quantities) plus Task 12 review; §10→Tasks 0, 5, and the standing
   verification rule, consolidated in Task 12. §11/§12 are non-goals/limitations — no
   tasks required.
2. **Placeholder scan:** none of the banned patterns; open decisions are assigned to a
   specific Step 0 with a suggested answer.
3. **Type consistency:** `prt_params%vascular`, `fuel_classes%live_moss()/dead_moss()`,
   `currentPatch%livemoss/fwet_moss/moss_vcmax_scaler`, `litt%moss_fines*`,
   `bc_in%fwet_veg_pa`, `hlm_*` names — spelled identically at every producing and
   consuming site above.
