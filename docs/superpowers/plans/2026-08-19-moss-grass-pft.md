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
5. **Present the commit to Sam for review**, including the prepared system-test
   commands and expected outcomes. **Running those CTSM-FATES tests is part of Sam's
   review** — Sam may run them or skip them. Do not start the next task until Sam
   approves.

### Standing verification rule (every task)

Testing and diagnostics land WITH the capability they verify, not at the end. **Division
of labor:**

- **Claude (required, every Fortran-touching task):** (a) verify CTSM-FATES **builds**:
  from the top of the checkout, `cd test-bld && qcmd -- ./case.build` (the `test-bld/`
  case will exist on the implementation machine; if it is missing, ask Sam rather than
  creating one); (b) run the FATES functional/unit tests covering the touched code
  (`python run_functional_tests.py fuel|allometry`, `python run_unit_tests.py`).
  Claude performs **no other testing** — nothing that runs CTSM-FATES.
- **Sam (and Sam alone; may choose to skip):** all testing that actually RUNS
  CTSM-FATES — the ALP2 baseline b4b comparisons, the moss smoke + exact-restart tests,
  and science-sanity runs. **These happen as part of Sam's post-commit review (loop
  step 5), not as a pre-commit gate.** Wherever a task's verification step names such
  a test, read it as: Claude prepares the commands and expected outcomes and presents
  them with the commit; Sam decides whether to run them during review, and approval
  proceeds on Sam's say-so either way.
- The b4b intent stands throughout: `use_moss` off must remain bit-for-bit; the ALP2
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

## Global Constraints

- **All new scalar settings — switches and science constants — go on the CTSM namelist**
  (`clm_inparm` → `set_fates_ctrlparms` `hlm_*`), never the FATES parameter file. Only
  array parameters (per-PFT, per-litterclass) go on the FATES parameter file. (Spec §8.)
- **`use_moss = .false.` must be bit-for-bit with baseline**, including unchanged restart
  and history file shapes with a standard 6-litterclass parameter file. (Spec §10.)
- **All existing CTSM/FATES conservation (balance) checks remain fatal** and must pass
  with `use_moss` on and off. (Spec §5, §10.)
- `use_moss` + `use_fates_planthydro` is a fatal namelist error. (Spec §5.)
- Target configuration: nocomp fixed-biogeography, SPITFIRE on. Choices must not
  foreclose full-competition mode. (Spec §2.)
- Fortran code follows surrounding CTSM/FATES style (naming, `_r8` literals, `endrun`
  with `fates_log()`/`iulog` messages).
- New moss history variables follow the existing conditional-registration patterns in
  `main/FatesHistoryInterfaceMod.F90` (register only when `hlm_use_moss==itrue`;
  patch→site averaging per existing helpers). The first task to add one (Task 6)
  establishes the pattern; later tasks follow it. **Every task that adds a
  moss-specific history variable also adds it to the output list (`hist_fincl`) in the
  `FatesNvp` testmod's `user_nl_clm`, in that same task.**
- Reference implementations to harvest are on `ctsm5.4.028_nvp` (worktree at
  `.worktrees/nvp`) and FATES commit `33640d372` (available in `src/fates`'s object
  store; view files with `git -C src/fates show 33640d372:<path>`).

---

### Task 0: ALP2 baseline testmods, tests, and baselines

**Files:**
- Create: `cime_config/testdefs/testmods_dirs/clm/FatesALP2Bare/user_nl_clm` (+
  `include_user_mods` if the NVP branch's version has one)
- Create: `cime_config/testdefs/testmods_dirs/clm/FatesALP2BareGrass/user_nl_clm` (+ ditto)
- Modify: `cime_config/testdefs/testlist_clm.xml`
- Modify: `.gitmodules` + submodule pointers for `ccs_config` and `cdeps`

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

- [ ] **Step 0 (orchestrator):** Diff the two testmod dirs and the relevant testlist
  entries out of the NVP worktree. Confirm with Sam: (a) point `ccs_config`/`cdeps` at
  the same fork commits as the NVP branch (needed for `1x1_ALP2`; note the standing
  caveat that fork pointers must be reverted/upstreamed before any merge to CTSM
  master); (b) which testlist categories to use on our branch (the NVP entries use
  `fates` plus NVP-specific categories — suggest a new `fates_moss` category so the
  suite is one `run_sys_tests` invocation); (c) confirm the fsurdat/paramfile testdata
  paths above are already populated on the target machine's `$DIN_LOC_ROOT`; (d) which
  machine runs the suite (the NVP entries are defined on derecho intel/gnu — confirm).
  Forward check: the `FatesNvp`/`FatesNvpOff` testmods do not exist on this branch
  yet — they arrive (adapted) in Task 5, which also brings the remaining NVP-branch
  tests. Task 0's two baseline tests reference only `FatesColdSatPhen` +
  `FatesALP2Bare{,Grass}`.
- [ ] **Step 1: copy the two testmod dirs** from the NVP worktree verbatim (they contain
  only `fsurdat` and `fates_paramfile` settings — keep the paramfile line pointing at
  the existing testdata JSON for now; Task 5 adds moss variants).
- [ ] **Step 2: update submodules.** Edit `.gitmodules` (`ccs_config`, `cdeps`: url +
  fxtag per Step 0) and check out the corresponding submodule commits.
- [ ] **Step 3: testlist entries.** Add the Bare and BareGrass tests (grid `1x1_ALP2`,
  compset `I2000Clm60FatesSpRsGs`, testmods `clm/FatesColdSatPhen--clm/FatesALP2Bare`
  and `...BareGrass`), machines/compilers/categories per Step 0.
- [ ] **Step 4: prepare the baseline-generation commands.** Claude writes out the exact
  `run_sys_tests ... --generate <baseline-tag>` invocations and expected outcomes
  (both tests PASS at base code) to present with the commit.
- [ ] **Step 5: reviews, then commit** ("Add ALP2 bare and bare+grass baseline testmods
  and tests"). During post-commit review, Sam (optionally) runs the tests and generates
  the baselines; the recorded baseline tag is what later tasks' b4b comparisons use.

### Task 1: `use_moss` and moss scalar namelist plumbing

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
- Produces (CTSM): `use_moss` (logical), `moss_height_allom` (char:
  `'grass_powerlaw'`/`'mat_thickness'`), `moss_bulk_density` (r8, kg m-3),
  `moss_fuel_moisture_live_a`, `moss_fuel_moisture_live_b`, `moss_fuel_moisture_dead_a`,
  `moss_fuel_moisture_dead_b` (r8) in `clm_varctl`.
- Produces (FATES): public module variables in `FatesInterfaceTypesMod`:
  `hlm_use_moss` (integer 0/1), `hlm_moss_height_allom` (integer: 1=grass_powerlaw,
  2=mat_thickness), `hlm_moss_bulk_density`, `hlm_moss_fm_live_a`, `hlm_moss_fm_live_b`,
  `hlm_moss_fm_dead_a`, `hlm_moss_fm_dead_b` (r8). All later FATES tasks read these.

- [ ] **Step 0 (orchestrator):** Read `setup_logic_fates` and the `use_fates_sp` +
  `fates_spitfire_mode` plumbing end to end. Confirm `set_fates_ctrlparms` real-scalar
  handling (precedent: `hlm_hio_ignore_val`, `FatesInterfaceMod.F90:2210`). Forward
  check: names above are consumed verbatim by Tasks 4, 9, 10, 11. Known open questions
  for Sam: (a) confirm the name `use_moss` over the CTSM convention `use_fates_*`
  (Sam has specified `use_moss`; re-ask only if a build-namelist constraint forces the
  prefix); (b) default values for the four fuel-moisture coefficients (suggest
  live a=0.3, b=0.7; dead a=0.05, b=0.75 as placeholder defaults pending tuning —
  confirm Sam is OK with placeholders that will be tuned in Task 12).
- [ ] **Step 1: FATES branch setup.** In `src/fates/`:
  `git checkout -b adrianna-moss-grass-pft e027a4030d2a0f09039fb337ad67ced7461dd4f0`,
  and add/verify the SSH push remote `git@github.com:samsrabin/fates.git`.
- [ ] **Step 2: XML definitions.** Add to `namelist_definition_ctsm.xml` (group
  `clm_inparm`), following the `use_fates_sp` entry format:

```xml
<entry id="use_moss" type="logical" category="physics"
       group="clm_inparm" valid_values="" value=".false.">
Toggle to turn on the moss plant functional type in FATES
(only relevant if FATES is being used).
</entry>
<entry id="moss_height_allom" type="char*32" category="physics"
       group="clm_inparm" valid_values="grass_powerlaw,mat_thickness">
Height allometry applied to moss PFTs (only relevant if use_moss is true).
</entry>
<entry id="moss_bulk_density" type="real" category="physics" group="clm_inparm">
Moss mat bulk density (kg m-3) used by the mat_thickness height allometry
(only relevant if use_moss is true).
</entry>
<entry id="moss_fuel_moisture_live_a" type="real" category="physics" group="clm_inparm">
Intercept of live-moss fuel moisture as a function of the moss wetness proxy
(only relevant if use_moss is true).
</entry>
```

  ...and analogous entries for `moss_fuel_moisture_live_b`, `moss_fuel_moisture_dead_a`,
  `moss_fuel_moisture_dead_b`. Add defaults to `namelist_defaults_ctsm.xml`:
  `moss_height_allom = 'grass_powerlaw'`, `moss_bulk_density = 10.`, and the four
  coefficients (Step 0 values).
- [ ] **Step 3: build-namelist logic.** In `setup_logic_fates`, add the seven names to
  the `add_default` list and add fatal checks: `use_moss` requires `use_fates`;
  `use_moss` + `use_fates_planthydro` is fatal (message: "use_moss is incompatible with
  use_fates_planthydro").
- [ ] **Step 4: clm_varctl + controlMod.** Declare the seven variables in the FATES
  block of `clm_varctl.F90` with the same defaults as the XML; add to the `clm_inparm`
  namelist read, the `use_fates` consistency-check block (error if `use_moss` and
  `.not. use_fates`), and the `mpi_bcast` block in `controlMod.F90`.
- [ ] **Step 5: pass to FATES.** In `clmfates_interfaceMod.F90` `CLMFatesGlobals2`,
  mirror the `use_sp` pattern:

```fortran
if(use_moss) then
   pass_use_moss = 1
else
   pass_use_moss = 0
end if
call set_fates_ctrlparms('use_moss',ival=pass_use_moss)
select case (trim(moss_height_allom))
case ('grass_powerlaw')
   call set_fates_ctrlparms('moss_height_allom',ival=1)
case ('mat_thickness')
   call set_fates_ctrlparms('moss_height_allom',ival=2)
end select
call set_fates_ctrlparms('moss_bulk_density',rval=moss_bulk_density)
call set_fates_ctrlparms('moss_fm_live_a',rval=moss_fuel_moisture_live_a)
```

  ...and the remaining three coefficients likewise.
- [ ] **Step 6: FATES side.** In `FatesInterfaceTypesMod.F90` declare the seven
  `hlm_*` variables (integer/real, public). In `FatesInterfaceMod.F90`
  `set_fates_ctrlparms`: flush each to unset in the flush block, add
  `case('use_moss')` etc. to the assignment `select case`, and add "was it set?"
  checks in the verification block (pattern: `FatesInterfaceMod.F90:1837-1840`).
- [ ] **Step 7: verify.** (a) `cd bld/unit_testers && ./build-namelist_test.pl` — no new
  failures; (b) manual build-namelist checks: `use_moss=.true.` without FATES fails
  fatally; `use_moss=.true.` + `use_fates_planthydro=.true.` fails fatally; defaults
  appear in `lnd_in` when `use_moss=.true.` with FATES; (c) standing rule: ALP2
  baseline tests compare b4b.
- [ ] **Step 8: reviews, then commit** (FATES commit "Add hlm_use_moss and moss scalar
  ctrlparms"; CTSM commit "Add use_moss and moss scalar namelist plumbing" including
  `.gitmodules` update and submodule pointer bump).

### Task 2: Moss parameter file (JSON)

**Files:**
- Create (FATES): `parameter_files/fates_params_moss.json` (committed — the default
  JSON is in-repo and read directly at runtime, so the moss file is too)
- Create (FATES): the generator — either a patch file consumed by the existing
  `tools/batch_patch_params.py` (precedent: `parameter_files/patch_default_bciopt224.json`)
  or, if the patch tool cannot add a PFT column / grow a dimension, a small
  `tools/make_moss_params.py` using only the `json` stdlib module

**Interfaces:**
- Produces: a FATES parameter **JSON** with (a) a 15th PFT column `moss`; (b) new
  per-PFT variable `fates_vascular` (1 for PFTs 1–14, 0 for moss); (c)
  `fates_litterclass` dimension grown 6 → 8, with entries 7 (live moss) and 8 (dead
  moss) added to every litterclass-dimensioned variable (`fates_fire_SAV`,
  `fates_fire_FBD`, `fates_fire_min_moisture`, `fates_fire_mid_moisture`,
  `fates_fire_low_moisture_Coeff/Slope`, `fates_fire_mid_moisture_Coeff/Slope`,
  `fates_frag_maxdecomp`). Consumed by every subsequent task's testing via the
  `fates_paramfile` namelist setting.

- [ ] **Step 0 (orchestrator):** Inspect the NVP branch's moss parameter file
  (`git -C src/fates show 8382939b9:parameter_files/fates_params_default_moss.json`)
  and the default JSON's structure (dimensions section, per-variable dim lists).
  Check whether `tools/batch_patch_params.py` supports adding a PFT column and growing
  the `fates_litterclass` dimension; pick patch-file vs. standalone-script accordingly.
  Forward check: Task 3 reads `fates_vascular`; Task 4 requires exactly 8 litterclass
  entries when `use_moss` is on; Task 5's testmods point `fates_paramfile` at this
  committed JSON.
- [ ] **Step 1: build the moss JSON.** Starting from `fates_params_default.json`:
  append a 15th PFT by copying the arctic C3 grass column; override moss values
  harvested from the NVP branch's moss column (vcmax25top=30.0, slatop=0.027,
  `fates_woody=0`, plus the spec §3 corrections: `fates_recruit_seed_alloc=0.1`,
  `fates_recruit_seed_dbh_repro_threshold=0.001`, `fates_allom_dbh_maxheight=0.1`,
  realistic `fates_recruit_height_min=0.02`, layer-1-concentrated rooting profile e.g.
  `fates_allom_fnrt_prof_a=30`); add `fates_vascular` (dims: `fates_pft`; 1 everywhere,
  0 for moss); extend `fates_litterclass` to 8, copying dead-leaves values (SAV=66.0,
  FBD=4.0, etc.) into slots 7–8 as starting values; update `fates_hlm_pft_map` so moss
  maps to the arctic C3 grass HLM index (following the NVP branch's mapping). Keep the
  generation reproducible (patch file or script committed alongside).
- [ ] **Step 2: generate and inspect.** Verify with a python check, e.g.:

```bash
python -c "
import json; p = json.load(open('parameter_files/fates_params_moss.json'))
assert p['dimensions']['fates_pft'] == 15
assert p['dimensions']['fates_litterclass'] == 8
v = p['variables']['fates_vascular']['data']; assert v[-1] == 0 and all(x==1 for x in v[:-1])
assert p['variables']['fates_woody']['data'][-1] == 0
print('OK')"
```

  (adjust key paths to the actual JSON schema found in Step 0).
- [ ] **Step 3: reviews, then commit** (FATES commit: moss JSON + generator; CTSM
  pointer bump).

### Task 3: `fates_vascular` in FATES + moss identification

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

- [ ] **Step 0 (orchestrator):** Confirm how `fates_woody` is registered
  (`PRTParamsFATESMod.F90:127-129`) and where post-parameter-read cross-checks live
  (e.g., `FatesInterfaceMod` parameter-derived checks). Check whether older parameter
  files lacking `fates_vascular` must still read (decide: no — default JSON gains the
  variable in this task; document that custom param files need it; note the Task 0
  testdata JSON on `$DIN_LOC_ROOT` must gain it too or those tests break — resolve
  with Sam). Forward check: Tasks 6, 7, 10, 11 branch on `prt_params%vascular`.
- [ ] **Step 1: add the parameter.** Declare `integer,allocatable :: vascular(:)` in
  `prt_params`; register `fates_vascular` with dimension `fates_pft` and receive it in
  `PRTParamsFATESMod` mirroring `fates_woody`.
- [ ] **Step 2: consistency checks.** Where FATES validates parameters after read, add:

```fortran
do ft = 1,numpft
   if (prt_params%vascular(ft) == ifalse .and. prt_params%woody(ft) == itrue) then
      write(fates_log(),*) 'Non-vascular PFTs must be non-woody; check PFT ',ft
      call endrun(msg=errMsg(sourcefile, __LINE__))
   end if
end do
if (hlm_use_moss == itrue .neqv. any(prt_params%vascular(1:numpft) == ifalse)) then
   write(fates_log(),*) 'use_moss and the presence of a fates_vascular==0 PFT must agree'
   call endrun(msg=errMsg(sourcefile, __LINE__))
end if
```

- [ ] **Step 3: default JSON.** Add `fates_vascular` (all 1) to
  `parameter_files/fates_params_default.json` with metadata matching `fates_woody`.
- [ ] **Step 4: verify.** FATES functional suite reads the new parameter cleanly
  (`cd src/fates/testing && python run_functional_tests.py allometry`, in the conda
  env from `testing/environment.yml`); standing rule: ALP2 baseline tests compare b4b
  (after resolving the testdata-JSON question from Step 0).
- [ ] **Step 5: reviews, then commit** (FATES commit + CTSM pointer bump).

### Task 4: Runtime fuel-class count (6 ↔ 8) and moss fuel-class indices

**Files:**
- Modify (FATES): `fire/FatesFuelClassesMod.F90` (parameter → runtime), `fire/FatesFuelMod.F90`
  (fuel type arrays → allocatable), `fire/SFParamsMod.F90` (arrays → allocatable +
  size checks), `main/FatesInterfaceMod.F90` (set count from `hlm_use_moss`),
  `main/FatesHistoryInterfaceMod.F90` + `main/FatesRestartInterfaceMod.F90` (confirm
  fuel-class dims pick up the runtime value)
- Modify (FATES): `testing/tests/functional/fire/fuel/FatesTestFuel.F90` if it assumes 6

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
  `endrun` with: "fates_litterclass dimension must be 8 when use_moss is on, 6
  otherwise".
- [ ] **Step 4: verify.** (a) FATES fuel functional test with a standard 6-class file
  (`python run_functional_tests.py fuel`) — identical results to pre-change; (b) with
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
- Consumes: `use_moss` (Task 1), moss JSON (Task 2), `fates_vascular` checks (Task 3),
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

- [ ] **Step 0 (orchestrator):** Inspect the four NVP-branch testmods and the full
  NVP-branch `testlist_clm.xml` block at `1x1_ALP2` (including entries beyond the four
  Task 0 brought in — identify the ones exercising nocomp fixed-biogeography, per the
  NVP test comments). Adaptation decisions to confirm with Sam: (a) `FatesNvp` on our
  branch sets `use_moss=.true.` (the `use_nvp*`/`nvp_rad_model_ground` settings don't
  exist here) — keep `use_bedrock=.true.`?; (b) `FatesNvpOff` correspondingly
  overrides `use_moss=.false.`; (c) the two ALP2 moss testmods keep their fsurdat
  paths but point `fates_paramfile` at the committed Task 2 JSON (the NVP-branch
  JSONs lack the 8-entry litterclass dimension); (d) which NVP-branch test entries to
  bring in, and under which categories. Forward check: Tasks 6–11 hand these tests to
  Sam and Tasks 6–10 append history variables to `FatesNvp/user_nl_clm`.
- [ ] **Step 1: port the four testmods**, adapted per Step 0.
- [ ] **Step 2: testlist.** Add the remaining NVP-branch tests (adapted testmod
  compositions), covering: SP-mode moss (`FatesColdSatPhen--FatesNvp--FatesALP2*Moss`
  patterns), the `FatesNvpOff` twins (moss code present but off — b4b sentinels), and
  the nocomp fixed-biogeography moss tests identified in Step 0; include an `ERS_D`
  exact-restart variant.
- [ ] **Step 3: build check.** `cd test-bld && qcmd -- ./case.build` passes.
- [ ] **Step 4: prepare the system-test hand-off.** Claude writes out the new tests'
  invocations and expected outcomes for Sam's review: PASS with moss as an inert
  grass-like PFT, exact restart, fatal conservation checks clean; the abort case
  (`use_moss=.true.` with the default 6-class JSON) aborts cleanly with the Task 3/4
  messages; `FatesNvpOff` tests compare b4b against the Task 0 baselines; optionally
  `--generate` moss baselines so later tasks can see exactly what each change does to
  moss behavior.
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
  `python run_functional_tests.py patch`); (c) moss ALP2 SMS + **ERS** tests PASS —
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
  (Task 4), `hlm_moss_fm_live_a/b`, `hlm_moss_fm_dead_a/b` (Task 1).
- Produces: `fuel%moisture(live_moss) = hlm_moss_fm_live_a + hlm_moss_fm_live_b*fwet`
  (floored at 0); analogous for `dead_moss`. Effective moisture and `frac_burnt` for
  the moss classes then flow through existing code untouched. Fuel-class-dimensioned
  history (moisture, loading) already extends to 8 via Task 4 — this task's run
  verifies those outputs are sensible.

- [ ] **Step 0 (orchestrator):** Re-read `UpdateFuelMoisture` + `CalculateFuelBurnt`
  (max_grass_frac cap at `FatesFuelMod.F90:400,426-429`) — decide whether the 0.8 cap
  applies to the live-moss class (spec §6 says yes, mirror grass; confirm the cap is
  keyed by class index and extend to `live_moss`). Note MEF is computed from SAV
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
        hlm_moss_fm_live_a + hlm_moss_fm_live_b*fwet_moss)
   this%moisture(fuel_classes%dead_moss()) = max(0._r8, &
        hlm_moss_fm_dead_a + hlm_moss_fm_dead_b*fwet_moss)
end if
```

  (before `effective_moisture` is computed so moss classes get MEF-normalized like the
  rest). Extend the `max_grass_frac` cap to the live-moss class.
- [ ] **Step 3: functional test.** Add moss cases to the fuel functional test: given
  fwet_moss ∈ {0, 0.5, 1}, assert `moisture(7)` and `moisture(8)` equal the linear
  form; assert grass/leaf classes unchanged vs. the 6-class baseline run. Run
  `python run_functional_tests.py fuel`.
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
  `python run_functional_tests.py allometry`.
- [ ] **Step 4: verify in-model.** Run the moss ALP2 SMS test once per
  `moss_height_allom` mode (a user_nl override run for `mat_thickness`); both PASS;
  moss height history differs between modes as expected; ALP2 baselines b4b.
- [ ] **Step 5: reviews, then commit.**

### Task 12: Final integration, science sanity, and test-suite consolidation

**Files:**
- Modify: `cime_config/testdefs/testlist_clm.xml` (fill any gaps: one test per
  `moss_height_allom` mode if not added in Task 11; the full `fates_moss` category)
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
  perturbed `moss_fuel_moisture_*` coefficients); `FATES_NOCOMP_PATCHAREA_PF` reports
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
