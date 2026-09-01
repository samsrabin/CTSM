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
the submodule pointer bump and the matching `.gitmodules` `fxtag` — see below; the first
FATES-touching task also updates the `url` to `samsrabin/fates`). One logical task = one
CTSM commit (which may carry a FATES pointer bump) + at most one FATES commit.

**The `.gitmodules` `fxtag` must never lag the submodule pointer (Sam, 2026-08-25).**
CTSM records the FATES hash in two independent places — the `src/fates` gitlink and
`[submodule "fates"] fxtag` in `.gitmodules` — and `git commit` updates only the gitlink.
So: every CTSM commit that moves the FATES pointer must edit that `fxtag` in the **same**
commit, and, conversely, every commit that edits that `fxtag` must move the pointer to
match. The same applies to any other submodule whose pointer a commit moves. Verify
before committing — these two must print the same hash:

```
git ls-tree HEAD src/fates
git config -f .gitmodules submodule.fates.fxtag
```

**CTSM history was rewritten on 2026-08-25** to repair exactly that drift: an interactive
rebase replaced every CTSM commit after `5a350acf4`, and the pre-rewrite branch is
preserved as `adrianna-moss-grass-pft-badgitmodules`. Commits at or before `5a350acf4` are
unchanged and shared by both branches; the later SHAs recorded in this plan were updated to
the rewritten ones. **FATES was not rebased** — every FATES SHA in this plan and the spec is
still valid, as are the NVP-branch and fork SHAs.

### Test-naming constraint: `ERS`/`ERP` need `STOP_N` >= 3

**`ERS` and `ERP` tests have a minimum `STOP_N` of 3, whatever the `STOP_OPTION` is**
(Sam, 2026-08-25). CIME rejects anything shorter during test setup. So a two-unit restart
test has to be respelled in a finer unit: `ERS_Ly2` becomes `ERS_Ld731` (what Task 5 uses
after Sam's fix in `ac7f14249`; `Ld730` would do as well). Applies whenever a task adds a
restart test. `SMS` is unaffected — `SMS_Ly2` is fine.

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
- **The two `*_NoTrunks` fallback branches include trunks.** `AverageBulkDensity_NoTrunks`
  and `AverageSAV_NoTrunks` (`fire/FatesFuelMod.F90:349,381`) exclude the trunk class in
  their normal branch, exactly as their names promise, but their near-zero-loading fallback
  is `sum(x(1:num_fuel_classes))/num_fuel_classes` — an unweighted mean over *every* class
  including trunks, whose `fates_fire_FBD` is 999.0. Latent today because the branch only
  fires on patches with essentially no fuel, where nothing downstream burns. Relevant to us
  because the value moves when the class count grows: see Task 4 Step 3b.
- **`fates_maxElementsPerPatch` does not account for the fuel-class count.**
  `main/FatesInterfaceMod.F90:945` takes a `max()` over the cohort and CWD-by-soil-layer
  terms but omits both `num_fuel_classes` and `numpft`, even though the patch-level restart
  variable `fates_litter_moisture_pa_nfsc` packs `num_fuel_classes` values into that utility
  dimension (`main/FatesRestartInterfaceMod.F90:2828-2832,3872-3876`). It fits only because
  `ncwd*hlm_maxlevsoil` dominates. True at 6 and still true at 8, so this is a documentation
  gap rather than a bug — but the assumption is unstated and would break silently.
- **The soil-water boundary condition disagrees with itself between its two host fills.**
  `bc_in%h2o_liqvol_sl` declares itself "Liquid volume in soil layer (m3/m3)"
  (`main/FatesInterfaceTypesMod.F90:572`), and CTSM's `wrap_btran` fills it from
  `h2osoi_liqvol_col` — liquid only — as it has since that routine was introduced (CTSM
  `85b9d5b83`, clm4_5_12_r192, Aug 2016). Nine months later `dynamics_driv` gained a *second*
  fill of the same field from `h2osoi_vol_col`, which is total water, liquid plus ice (CTSM
  `2c68a254f`, clm4_5_16_r238, May 2017). Neither commit mentions the other, no comment marks
  the difference, and the tech note never states the field's phase — though it does describe
  btran as handling the ice fraction separately via effective porosity over total porosity,
  which is only coherent if the water term is liquid. So the phase FATES sees depends on which
  host routine wrote last: total water during the daily dynamics call, liquid-only during the
  sub-daily canopy flux steps. Two of the three daily-path consumers are protected by accident,
  because `check_layer_water` (`biogeophys/EDBtranMod.F90:42-57`) tests `tempk` independently of
  the water value, so `get_active_suction_layers` and the `smp_memory` accumulation
  (`biogeochem/EDPhysiologyMod.F90:1228`) drop frozen layers either way. The unguarded consumer
  is `liqvol_memory` (`biogeochem/EDPhysiologyMod.F90:1223`), a raw root-weighted mean feeding
  drought-deciduous phenology. It is latent only because all 14 default PFTs set
  `fates_phen_drought_threshold` negative (-152957.4), selecting the matric-potential branch at
  `:1250-1253`; a PFT switching to a positive volumetric threshold would silently compare
  ice+liquid against a liquid-water threshold. What is *not* latent is the diagnostic:
  `FATES_MEANLIQVOL_DROUGHTPHEN_PF`, long name "PFT-level mean liquid water volume for drought
  phenolgy", reports total water today. The fix is a choice between making the daily fill use
  liquid volumetric water (an answer change for any PFT on the volumetric threshold, and for
  that history variable) and documenting the field as total-at-daily/liquid-at-sub-daily, which
  is hard to defend for a field named `liqvol`. Noticed because Task 8's moss wetness proxy
  reads this field in the daily path: total water is the behaviour that task wants — a frozen
  top layer means frozen moss, which damps fire — but that is a coincidence of where the proxy
  is computed, not a contract the field offers.

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
- New moss history variables register **unconditionally** in
  `main/FatesHistoryInterfaceMod.F90` (`use_default='active'`, `hlms='CLM:ALM'`; patch→site
  averaging per existing helpers), each carrying a
  `! TODO: Before merge, change these to default 'inactive'` comment. This means a moss-off
  run's history file gains these fields too (populated with 0, since the underlying patch
  members are only ever written when `hlm_use_moss==itrue`) — Sam confirmed on 2026-09-01 that
  this is the right call for new fields, and that the `TODO` comments mark a required pre-merge
  sweep: every one of them must be revisited (flip the default, or reconsider the guard) before
  this branch merges. The first task to add one (Task 6, FATES `8bdc97783`) establishes the
  pattern; later tasks follow it. **Every task that adds a moss-specific history variable also
  adds it to the output list (`hist_fincl`) in the `FatesNvp` testmod's `user_nl_clm`, in that
  same task — using the append form `hist_fincl1 += 'VAR'`, never a plain assignment.** CIME
  applies testmods in order and later ones win (`cime/CIME/user_mod_support.py`), and the
  nocomp test composes `FatesNvp` after `clm/Fates`, which sets `hist_empty_htapes` plus the
  ~23-variable FATES list. A plain assignment would silently wipe `FATES_FUEL_AMOUNT`,
  `FATES_BURNFRAC` and the rest — on the only test that runs SPITFIRE, while looking harmless
  on the SP tests.
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
    ~~the `*_nonvp` categories hold the `FatesNvpOff` tests, which arrive in Task 5.~~
    **Superseded 2026-08-24 (Sam):** there is no `FatesNvpOff` — moss-off simply means "no
    moss testmod", so the `*_nonvp` categories hold plain `FatesALP2*` entries. See Task 5
    Step 0(e).
  - **Testmod names.** Keep the NVP branch's names verbatim (`FatesNvp`, `FatesALP2*`); do
    **not** rename to `FatesMoss*`. (`FatesNvpOff` was in this list; dropped 2026-08-24.)
  - **Testdata.** Verified present on derecho's `$DIN_LOC_ROOT`
    (`/glade/campaign/cesm/cesmdata/cseg/inputdata`): all `fsurdat`
    `surfdata_ALP2_hist_2000_16pfts_c260427*.nc` variants and the default/moss paramfile
    JSONs under `lnd/clm2/testdata/moss/`.
  - **Machines/compilers.** As the NVP entries do: derecho intel, derecho gnu, and izumi
    nag. ~~(Note the NVP branch omits izumi from the `*_nonvp` categories — mirror that.)~~
    **Superseded 2026-08-24 (Sam):** izumi nag carries the same categories as derecho on
    every entry, including the `*_nonvp` suites. Task 5 Step 2's entries follow the new rule;
    Task 0's two existing entries still follow the old one — see Task 5 Step 2.
  - **`use_bedrock`.** Set `use_bedrock = .true.` in **all** `FatesALP2*` testmods — it
    matters for running at this site — and **not** in `FatesNvp`. Task 5 must drop the
    `use_bedrock` line when it ports `FatesNvp`.
  - **`.gitignore`.** Add `.worktrees/` (done, under "REMOVE BEFORE MERGE").
  - **Finding for later tasks.** CIME keys baselines by full test name *including
    testmods*, so none of Task 5's new entries can compare against Task 0's baselines —
    they need baselines of their own, which Sam generates at Task 5 (see Task 5 Step 4(D)).
    Task 0's two plain tests carry no `FatesNvp*` testmod, so `use_fates_moss` takes its
    `.false.` default: those are the b4b sentinel for Tasks 1–4. (This bullet said
    "`FatesNvpOff` tests" until 2026-08-24; that testmod was dropped.)
  - Forward check: `FatesNvp` does not exist on this branch yet — it arrives (adapted) in
    Task 5 along with the remaining NVP-branch tests, without the `FatesNvpOff` that NVP
    pairs it with. Task 0's two
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
  `FatesNvpOff` (a testmod we do not port), so there is no no-moss ALP2 test there to copy. Model the `<machines>`
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
- **Thirteen moss PFT parameters are deferred to Tasks 10/11** (Sam, 2026-08-24). The file
  was regenerated with them held at their `arctic_c3_grass` values; the generator keeps
  the moss values and the reason. Full list and rationale: Task 5 Step 4(C).
- **This file was NOT usable by a model run until Task 4 landed** (resolved 2026-08-24).
  Before that, `num_fuel_classes = 6` was a compile-time `parameter` and the `SF_val_*`
  arrays were fixed length-6, filled by `SF_val_SAV(:) = param_p%r_data_1d(:)` — a
  non-conforming array assignment for an 8-entry file, which traps in a bounds-checked build
  and is silently wrong otherwise. So Tasks 2 and 3 pointed no test at it. Its first consumer
  is Task 4's own Step 3b, not Task 5 as originally planned: making the count runtime is what
  makes the file readable, so the earliest CLM-level test of it belongs in that same task.

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
  **Note (2026-08-24):** thirteen of the values below are present in the generator but
  **not applied** — see the deferral pointer in Interfaces above and Task 5 Step 4(C). The
  bullets record what the moss column will hold once Tasks 10/11 restore them.
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

### Task 4: Runtime fuel-class count (6 ↔ 8)

**Status: COMPLETE (2026-08-24).** FATES `21ae02ab`; CTSM pointer bump in `f749bce7b`.
Two review rounds (code + spec); the as-built design diverges from this plan's original
Steps 1–3 in ways recorded inline below, because the planned mechanism turned out to be
impossible. **Verification runs are deferred to Task 5** — see Step 4. The moss fuel-class
indices moved to Task 6.

The moss fuel-class indices and their accessors moved to Task 6 (Sam's call, 2026-08-24).
Nothing this task lands names class 7 or 8: every consumer of the fuel-class dimension
either loops `1..num_fuel_classes` (history `FatesHistoryInterfaceMod.F90:4224,4902`,
restart `FatesRestartInterfaceMod.F90:2829,3873`, the history dim maps
`FatesInterfaceMod.F90:1299,1444`, and all the arithmetic in `FatesFuelMod`) or names a
class ≤ 6 (`trunks`, `dead_leaves` at `EDPatchDynamicsMod.F90:2086` and
`EDPhysiologyMod.F90:3298,3302`, `live_grass` at `EDPatchDynamicsMod.F90:1102`). In this
task the accessors would be dead code with an unexercised guard; they land in Task 6 with
their first consumer.

**Files:**
- Modify (FATES): `fire/FatesFuelClassesMod.F90` (drop the compile-time `parameter`),
  `main/FatesInterfaceTypesMod.F90` (declare `num_fuel_classes`), `fire/FatesFuelMod.F90`
  (fuel type arrays → allocatable, plus a `Deallocate` method), `fire/SFParamsMod.F90`
  (`SF_val_*` → allocatable; set the count from the paramfile dimension; moss/count
  agreement check)
- Modify (FATES, `use`-swaps only): `fire/SFMainMod.F90`,
  `main/FatesHistoryInterfaceMod.F90`, `main/FatesRestartInterfaceMod.F90`,
  `main/FatesInterfaceMod.F90`
- Modify (FATES tests): `testing/tests/functional/fire/fuel/FatesTestFuel.F90`,
  `testing/tests/functional/fire/shr/FatesTestFireMod.F90`,
  `testing/tests/fortran_shr/FatesUnitTestParamReaderMod.F90`,
  `testing/tests/unit/fire_fuel_test/test_FireFuel.pf`
- Modify (CTSM, `use`-swaps only): `src/main/histFileMod.F90` (which defines
  `fates_levfuel` from this symbol), `src/utils/clmfates_interfaceMod.F90`
- Create (CTSM): a testmod that turns moss on and points `fates_paramfile` at the in-repo
  moss JSON (provisional name `FatesMossParamfile`; confirm at Step 3b)
- Modify (CTSM): `cime_config/testdefs/testlist_clm.xml` (one short test, see Step 3b)

**Interfaces:**
- Consumes: `hlm_use_moss` (Task 1); 8-entry parameter file (Task 2).
- Produces: `num_fuel_classes` as a plain public module **variable** in
  `main/FatesInterfaceTypesMod.F90`, read from the size of the parameter file's
  `fates_litterclass` dimension. Deliberately **not** `protected`, and with **no**
  initializer — it matches its siblings `numpft`/`nlevage`/`nlevcoage`/`nlevdamage`, which
  are declared the same way and set from the parameter file in the same phase (Sam's call,
  2026-08-24). There is no `SetNumFuelClasses`.
- Produces: `fuel_type` arrays (`loading`, `frac_loading`, `frac_burnt`,
  `effective_moisture`) allocatable, allocated to `num_fuel_classes` in `Init` and freed by
  a new `Deallocate` method. Tasks 6, 7, 9 depend on these names.
- Produces: the moss/count agreement abort, in `SpitFireCheckParams` — see Step 2 for why
  it cannot live in the parameter read.

- [x] **Step 0 (orchestrator) — COMPLETE (2026-08-24).** Enumerated every use of
  `num_fuel_classes`. Findings:
  - **No type-definition component was missed.** After Step 3 the only remaining
    `num_fuel_classes`-dimensioned declarations are dummy arguments and local automatic
    arrays (`fire/SFMainMod.F90:370`; `fire/FatesFuelMod.F90:202,206,207,253,256,335,367,400`),
    all legal specification expressions over a use-associated module variable.
  - **Restart and history do register the dimension from this symbol at runtime**
    (`main/FatesInterfaceMod.F90:1245,1268-1269,1299,1444`;
    `main/FatesRestartInterfaceMod.F90:2829,3873`; `main/FatesHistoryInterfaceMod.F90:4224,4902`),
    reaching CTSM as `fates_levfuel` via `src/main/histFileMod.F90:2567`.
  - **The CWD-index aliasing needs no change**, as predicted: every burnt-litter loop in
    `EDPatchDynamicsMod` is `do c = 1,ncwd` (4), so a longer fuel array never reaches them.
  - The Step 3b testmod-mechanics question is **not** settled; it moved into Step 3b itself,
    which is where it is needed.
- [x] **Step 1: declare the count. COMPLETE.** `fire/FatesFuelClassesMod.F90` loses
  `integer, parameter, public :: num_fuel_classes = 6`; the symbol is redeclared as
  `integer, public :: num_fuel_classes` in `main/FatesInterfaceTypesMod.F90`, beside the
  other parameter-file-derived runtime dimensions. No `protected`, no initializer, no
  `SetNumFuelClasses` — see Interfaces. The moss indices and their accessors moved to
  Task 6.
- [x] **Step 2: set the count. COMPLETE, and not where this plan said.** The planned call
  site — "in `FatesInterfaceMod`, immediately after ctrlparms are verified (before parameter
  read)" — **does not exist.** CTSM verifies ctrlparms in `CLMFatesGlobals2`
  (`clmfates_interfaceMod.F90:673` passes `use_moss`, `:693` `check_allset`) but reads the
  parameter file in `CLMFatesGlobals1` (`:390` → `SetFatesGlobalElements1`), an earlier call
  from `clm_initializeMod.F90:109` vs `:274`. So at parameter-read time `hlm_use_moss` is
  still the `-999` unset sentinel (`main/FatesInterfaceMod.F90:1577`), and the count cannot
  be derived from it. Instead:
  - The count is read from the file itself, in `SpitFireParamsInit`:
    `num_fuel_classes = pstruct%GetDimSizeFromName('fates_litterclass')`. This is strictly
    better than the planned form, because it makes every `SF_val_x(:) = param_p%r_data_1d(:)`
    assignment conforming *by construction* rather than checking after the fact.
  - The moss/count **agreement** check moved to `SpitFireCheckParams`, reached from
    `FatesCheckParameters` in `SetFatesGlobalElements2`, whose own comment states the
    rationale: "performed after the parameter AND after all namelist settings because they
    are cross referenced." Both operands are valid there, and it is master-only, like every
    other check in that routine. This is the same placement Task 3 used for the
    `fates_vascular` biconditional, for the same reason.
- [x] **Step 3: allocatable conversions. COMPLETE.** `fuel_type` members and the nine
  `SFParamsMod` `SF_val_*` litterclass arrays became allocatable, allocated in
  `fuel_type%Init` and `SpitFireParamsInit` respectively. `SF_val_CWD_frac` correctly stays
  fixed at `ncwd` — its JSON dimension is `fates_NCWD`, not `fates_litterclass`.
  - **No per-array size check was added**, contrary to the original Step 3 text. It would be
    redundant: `main/JSONParameterUtilsMod.F90:678-687` already aborts if any 1-D parameter's
    data length disagrees with its declared dimension. The only check worth having is the
    moss-switch/count agreement one, which is why it is the only one, and why it can safely
    be late (Step 2).
  - Making the arrays allocatable broke two test drivers that had relied on the members
    being static, both fixed here: `FatesTestFuel.F90` never called `fuel%Init()` at all
    (and allocated its own `num_fuel_classes`-sized arrays before `ReadParameters`, so they
    were size 0); `test_FireFuel.pf` gained a `num_fuel_classes` assignment in `setUp` plus a
    `tearDown` calling the new `fuel_type%Deallocate`. The hard-coded 6 in the pFUnit test is
    deliberate: the count is now an *input* to the unit under test, and no unit test has a
    parameter file to read (`testing/framework/unit_test.py` runs them under `ctest` with no
    arguments).
- [x] **Step 3b: first CLM-level test of the 8-class parameter file. COMPLETE (2026-08-24).**
  Testmod `FatesMossParams` sets both `use_fates_moss = .true.` and `fates_paramfile` (and,
  from Task 5, a comment explaining why it and `FatesNvp` are identical), and two
  `SMS_Ld5_D_Mmpi-serial` tests at `1x1_ALP2`/`I2000Clm60FatesSpRsGs` compose it with
  `FatesColdSatPhen` and `FatesALP2Bare`/`FatesALP2BareGrass`. A case built from it completes
  successfully; the formal suite runs are Task 5's (Step 4). Their category rows were
  corrected in Task 5 Step 2: they had inherited `*_nonvp` rows from the Task 0 machine
  block, which is wrong for a moss-on test.
  **The switch is not optional in this testmod**, and a first pass omitted it: with the 8-class
  file and `use_fates_moss` at its `.false.` default, the run aborts twice over — on this
  task's own agreement check (8 ≠ 6) and on Task 3's `fates_vascular` biconditional. The switch
  and the moss paramfile must always travel together, which is why they live in one testmod
  rather than two composable ones. This task is where
  the moss JSON becomes readable at all, so it is the earliest point a CLM test can use it —
  Task 5 is merely where the plan had concentrated the testlist work. Add one now, because
  this task's highest risk is an accidental history or restart shape change from making the
  fuel-class count runtime, and no FATES functional test can see CLM's history/restart files.
  - Create a testmod setting `use_fates_moss = .true.` and pointing `fates_paramfile` at
    `src/fates/parameter_files/fates_params_moss.json`.
  - **`fates_paramfile` mechanics — RESOLVED (2026-08-24). A one-line `user_nl_clm` entry
    using `$SRCROOT` works; no `shell_commands` and no inputdata copy are needed.** The
    testmod is `FatesMossParams`, whose entire content is:

    ```
    fates_paramfile = '$SRCROOT/src/fates/parameter_files/fates_params_moss.json'
    ```

    Verified by `preview_namelists`: `CaseDocs/lnd_in` carries the fully expanded path. Why
    this works, and the two traps it avoids:
    - **XML variables are expanded in `user_nl_clm`.** `read_envxml_case_files`
      (`bld/CLMBuildNamelist.pm:494-520`) builds an id→value hash from every `env_*xml` in the
      case, and `process_namelist_infile` runs `expand_xml_variables_in_namelist` over every
      user_nl value (`:1533`). `SRCROOT` is an entry in `env_case.xml`, so it resolves. This is
      the same mechanism the `$DIN_LOC_ROOT` paths in `FatesALP2Bare`/`FatesALP2BareGrass` use.
    - **A bare CTSM-root-relative path would NOT have worked**, even though that is exactly the
      form in `namelist_defaults_ctsm.xml:617`. The `landroot` relative→absolute conversion
      (`:5582-5584`) sits inside `add_default`'s `if (! defined $val)` guard (`:5537`), and
      user_nl is merged into the namelist object at `:627`, long before the FATES block at
      `:4883`. So for a user-supplied value `add_default` returns immediately and never
      absolutizes; the path would reach `lnd_in` verbatim and be opened relative to the run
      directory. The relative form works only as a *default*, never as an override.
    - **Nothing involves inputdata.** `check_input_files` writes only `abs`- and `rel:`-typed
      variables into `ctsm.input_data_list` (`:5668,5684`); `landroot` falls through both
      branches, so `fates_paramfile` never enters that list and `check_input_data` never looks
      for it. Note the flip side: unlike the `abs` branch there is no existence test at
      build-namelist time, so a mistyped path fails at model init, not at case setup.
    - The `shell_commands` + `xmlquery SRCROOT` pattern (`FatesColdSeedDisp`, `FatesColdPRT2`)
      remains the fallback, but those testmods need it only because they *generate* a modified
      paramfile with `modify_fates_paramfile.py` — which is also why they pull in
      `FatesSetupParamBuild`, a conda/`ctsm_pylib`/`ncgen` availability checker. Our moss JSON
      is committed, so none of that applies. **This also settles the same open question for
      Task 5.**
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
  - **One thing does change numerically at 8 classes even with zero moss area**, and this
    test can reach it: the near-zero-loading fallback branches in `AverageBulkDensity_NoTrunks`
    and `AverageSAV_NoTrunks` (`fire/FatesFuelMod.F90:349,381`) take an unweighted mean over
    *all* classes and divide by `num_fuel_classes`, so they now include the two moss entries.
    Reached only on patches with essentially no fuel, where there is no fire to be affected —
    but do not be surprised by it, and see the upstream-observations note on those two lines.
- [x] **Step 4: verify — RUNS DEFERRED TO TASK 5 (Sam's call, 2026-08-24).** Closed as a
  Task 4 obligation by transferring the runs into Task 5's test sweep rather than by having
  run them; the list below is what Task 5 must therefore check. The code and tests are in
  place; only their execution moves.
  (a) FATES fuel functional test with a standard 6-class file
  (`MPLBACKEND=Agg python run_functional_tests.py --save-figs -t fuel`) — identical results to
  pre-change; (b) the FATES unit tests, which is where the `hlm_use_moss` integer-as-logical
  slip found in review would have surfaced (gfortran rejects it, Intel accepts it as a DEC
  extension, so an Intel-only build proves nothing here); (c) the two Step 3b tests;
  (d) standing rule: ALP2 baseline
  tests compare b4b (this task is the highest-risk one for accidental shape changes — check
  history and restart dimensions in the baseline-compare output explicitly).
  - Note what is **not** verifiable from the FATES harness: the moss/count agreement abort.
    It lives in `SpitFireCheckParams`, whose only caller is `FatesCheckParameters`
    (`main/FatesInterfaceMod.F90:2812`), which no test driver reaches. So pointing the fuel
    functional test at the 8-class moss file does not abort — it runs with 8 classes. That is
    fine, and deliberate: it means the harness no longer reads `hlm_use_moss` at all, so no
    test driver has to fake ctrlparms. The abort is CLM-level behaviour, and Step 3b is what
    exercises it.
- [x] **Step 5: reviews, then commit. COMPLETE (2026-08-24).** Code review and spec review
  both run; all findings either fixed or explicitly declined (the bare `num_fuel_classes`
  declaration and the unguarded `SF_val_*` allocates, both left to match FATES convention).
  FATES commit + CTSM pointer bump in `f749bce7b` (rebased 2026-08-25 from `41043800a`,
  itself `eb3e4131f` before two amends).

### Task 5: First moss run — moss testmods and system tests

**Status: COMPLETE (2026-08-25).** Sam ran the CTSM system-test suite at commit `fba615ab1`
on 2026-08-25 and **all tests pass as expected**. That tip includes the moss testmods and
14 ALP2 testlist entries (`01e1d847d`, with the FATES parameter-deferral pointer bump in
`c6c131bdd`) plus the extra infrastructure that made the `derecho_intel` + `mpi-serial` ALP2
runs pass — the intel/mpi-serial namelist guard and its `ch4finundatedmapalgo='nn'`
exception, the `FatesALP2` base-testmod refactor, and the bedrock indexing fix — recorded in
Step 4 below.

**Files:**
- Create: `cime_config/testdefs/testmods_dirs/clm/FatesNvp/user_nl_clm` (adapted from
  the NVP branch's dir of the same name). **The first-class moss testmod** (Sam, 2026-08-24):
  it exists independently of Task 4's `FatesMossParams`, which stays a special case and is
  eventually deleted. This is also where Tasks 6–10 append their history variables.
- Create: `cime_config/testdefs/testmods_dirs/clm/FatesALP2BareMoss/user_nl_clm` (ditto)
- Create: `cime_config/testdefs/testmods_dirs/clm/FatesALP2BareGrassMoss/user_nl_clm`
  (ditto)
- Modify: `cime_config/testdefs/testlist_clm.xml`
- Modify (FATES): `tools/make_moss_params.py` and `parameter_files/fates_params_moss.json`
  — the parameter deferral of Step 4(C). Implies a FATES commit and a CTSM submodule
  pointer bump.
- **No `FatesNvpOff`** — see Step 0(e).

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
- **Also inherits Task 4's Step 4 verification runs** (Sam's call, 2026-08-24): the FATES fuel
  functional test, the FATES unit tests, the two `FatesMossParams` tests added in Task 4
  Step 3b, and the ALP2 baseline b4b compare. Task 4 landed the code and the tests but ran
  neither, so Task 5's sweep is the first execution of any of it — including the first check
  that the runtime fuel-class count did not change history or restart shapes, which Task 4
  flagged as its highest risk.

NVP-branch source material (adapt, keeping the testmod names): `FatesNvp` (sets
`use_nvp=.true.`, `use_nvp_undersnow`, `nvp_rad_model_ground`, `use_bedrock=.true.`),
`FatesNvpOff` (includes `FatesNvp`, overrides `use_nvp=.false.` — **not ported**, see
Step 0(e)), `FatesALP2BareMoss` and `FatesALP2BareGrassMoss` (moss fsurdat variants
`_moss`/`_grassmoss` + NVP-branch moss param JSONs). Note NVP paired each fsurdat with its *own* paramfile —
`fates_params_default_moss...json` (moss on HLM 12) for `_moss`, and
`fates_params_default_mossMapsBrEvTrTree...json` (moss on HLM 4) for `_grassmoss`. We cover
both fsurdats with our single paramfile, so both of our testmods point `fates_paramfile` at
`fates_params_moss.json` — the same one-line `$SRCROOT` form Task 4's `FatesMossParams`
established. Do not port NVP's two-paramfile split.

**Blocking prerequisite — TWO new fsurdats that only Sam can create (from Task 2 Step 0).**
The NVP branch shipped two ALP2 moss fsurdats, one per NVP paramfile, and because we commit
ONE moss paramfile with moss on HLM PFT 4, we regenerate both. Verified against the files in
`$DIN_LOC_ROOT/lnd/clm2/testdata/moss/fsurdat` on 2026-08-24:

| source | area layout | status under our paramfile |
|---|---|---|
| `..._moss.nc` | 5.75% bare, 94.25% on natpft **12** | index 12 is still `arctic_c3_grass` for us, so this is a **grass** run. Area must move 12 → 4. |
| `..._grassmoss.nc` | 20% bare, 50% on natpft **4**, 30% on natpft **12** | area is already right — NVP's `mossMapsBrEvTrTree` paramfile made the same HLM-4 choice we did, so this reads as bare + moss + grass unchanged. Its moss *canopy column* is malformed. |

That second row is the payoff of the HLM-4 decision: we inherit NVP's bare+grass+moss area
layout for free, and only the moss-only file needs its area relocated.

**`..._grassmoss.nc`'s moss column is malformed, and we now fix it rather than work around
it** (Sam's call, 2026-08-24). Its index 4 matches the authoritative moss column — index 12
of `..._moss.nc`, i.e. LAI 2.0 / SAI 0.5 / `HEIGHT_TOP` 0.0338 m / `HEIGHT_BOT` 1e-06 m —
*exactly* for `MONTHLY_HEIGHT_TOP`, `MONTHLY_LAI` and `MONTHLY_SAI` in all 12 months, but its
`MONTHLY_HEIGHT_BOT` is 0.8386 m, the tropical tree's, under a top of 0.0338 m. Bottom above
top, every month: three of the four columns were moved from 12 to 4, not four.
**This is inert in a FATES run** — `MONTHLY_HEIGHT_BOT` is read only at
`src/biogeochem/SatellitePhenologyMod.F90:494`, flows into `hbot_input_patch`, and is consumed
only by `SatellitePhenology`, which `endrun`s immediately if `use_fates` is true (`:199-202`);
FATES-SP ingests only `hlm_sp_htop`, there is no `hlm_sp_hbot` anywhere in the tree, and
`hbot` flows the other way (FATES → CTSM, `clmfates_interfaceMod.F90:1766`). So this is
housekeeping, not a bug fix — but it is cheap, and it stops the nonsense column waiting for
the next reader.

A tested generator for both files is written and handed to Sam:
`./make_moss_pft4_fsurdat.py` at the top of the CTSM checkout. It was originally to be left
untracked (Sam, 2026-08-21); Sam committed it instead on 2026-08-24, and it is **to be
removed before any upstream merge** — Task 12 owns that. netCDF4 + numpy + stdlib, for the
`ctsm_pylib` env. Every path is defaulted: `--fin-*` from `$INPUTDATA` (falling back to
`$DIN_LOC_ROOT`), `--fout-*` into the invoking directory with a freshly minted `cYYMMDD`
stamp. A bare invocation builds **both** outputs; there is no way to build only one.
- **moss-only output:** moves `PCT_NAT_PFT` *and* all four `MONTHLY_*` columns from index 12
  to 4, zeroing only the area at 12. Moving the area alone would give moss the stock
  tropical-tree canopy (`MONTHLY_HEIGHT_TOP` 29.35 m vs the hand-tuned 0.034 m), which matters
  because FATES-SP prescribes LAI/SAI/height from those arrays.
- **grassmoss output:** leaves `PCT_NAT_PFT` untouched and overwrites index 4's four
  `MONTHLY_*` columns with the authoritative moss column. It installs the whole column rather
  than patching the one variable we noticed, and **enforces** that exactly
  `MONTHLY_HEIGHT_BOT` needed correcting — in both directions, by exact comparison. Another
  column differing means the input is not the file the script was written for; that column
  *not* differing means the file has already been through the script. Either aborts before
  anything is written. Verified 2026-08-24: the output differs from its input in exactly
  12 values (index 4 of `MONTHLY_HEIGHT_BOT`, one per month) plus the `history` attribute.
- **Single-gridcell only.** Both inputs are checked and a multi-gridcell file is refused
  (Sam, 2026-08-24). Supporting more was judged not worth it for a script that only ever
  sees the 1×1 ALP2 files and that Task 12 deletes. An earlier draft reported a per-gridcell
  sum range instead; review found it silently produced `nan` whenever any gridcell carried
  the `_FillValue = NaN` these files declare, which would have hidden exactly the bad
  gridcell it was added to expose.

**Claude has no write access to `$DIN_LOC_ROOT`**; Sam runs the script and chooses both
filenames, their datestamps and their location. Task 5 cannot start its moss tests until both
files exist.

One further observation about the existing fsurdats, recorded but NOT acted on:
- `..._grass.nc` is also hand-tuned: its index 12 `MONTHLY_HEIGHT_TOP` is 0.043 m, not the
  stock 0.50 m the plain and `_bare` files carry. So Task 0's grass baseline is a 4 cm
  canopy — fine, but the baselines are specific to these edited files.

- [x] **Step 0 (orchestrator) — COMPLETE (2026-08-24).** Inspect the four NVP-branch testmods and the full
  NVP-branch `testlist_clm.xml` block at `1x1_ALP2` (including entries beyond the four
  Task 0 brought in — identify the ones exercising nocomp fixed-biogeography, per the
  NVP test comments). Resolved in Task 0's Step 0, do not re-ask: (a) porting `FatesNvp`
  drops three of NVP's four lines — `use_nvp_undersnow` and `nvp_rad_model_ground` do not
  exist here, and `use_bedrock = .true.` lives in the `FatesALP2*` testmods instead.
  **Superseded 2026-08-24 on one point:** this item used to say `FatesNvp` contains *only*
  `use_fates_moss = .true.` It also needs the `fates_paramfile` line — see (e). (b) *(was
  `FatesNvpOff` construction; dropped — see (e).)* (c) the two new ALP2 moss testmods carry
  `use_bedrock = .true.` and point `fsurdat` at the **regenerated** fsurdats from the blocking
  prerequisite above — *not* at the NVP paths, since both NVP files need rebuilding for our
  HLM-4 mapping. They do **not** set `fates_paramfile` — that lives in `FatesNvp` (see (e)).
  Wherever it is set, it points at the committed
  Task 2 JSON via the `$SRCROOT` form (Task 4 Step 3b), never at a `$DIN_LOC_ROOT` testdata
  JSON, which both lack the 8-entry
  litterclass dimension AND set the NVP-only `fates_allom_fnrt_prof_mode = 4` on their
  moss PFT (see Task 0 Step 1: that mode does not exist in our FATES pin and aborts any
  vegetated patch in `set_root_fraction`). Task 2's moss column must therefore use a
  rooting mode our FATES supports (1–3), consistent with spec §3's "shallow grass-style
  roots, NOT the NVP branch's no-root profile mode 4";
  (d) categories are the NVP branch's `fates_nvp*` scheme, machines derecho intel/gnu +
  izumi nag. Forward check: Tasks 6–11 hand these
  tests to Sam and Tasks 6–10 append history variables to `FatesNvp/user_nl_clm`.

  **Resolved 2026-08-24** (inspected all 10 NVP `1x1_ALP2` entries against our 4). The two
  fsurdat filenames remain pending Sam running the generator, but those are a Step 1 input,
  not a Step 0 question.
  - (e) **No `FatesNvpOff`** (Sam confirmed 2026-08-24, after first asking for it). NVP's
    version includes `FatesNvp` and flips `use_nvp = .false.` while keeping the moss
    paramfile. For us that is moss-off with the 8-class file, which aborts on *both* the
    Task 4 agreement check and the Task 3 biconditional, so ours would have to additionally
    get back to a 6-litterclass file — and relying on a later testmod's `user_nl_clm` line to
    override an earlier one may not even work. Nothing is lost by dropping it: moss-off for us
    just means "no moss testmod", and Task 0's plain `FatesALP2Bare`/`FatesALP2BareGrass`
    entries already carry the `fates_nvp_nonvp` and `fates_nvp_short_nonvp` category rows. So
    three testmods to create, not four, and (g)'s `Ly2` moss-off twins are plain compositions.

    Because nothing has to override it, **`fates_paramfile` lives in `FatesNvp`** rather than
    being duplicated into each `FatesALP2*Moss` testmod — we have one moss paramfile where NVP
    had two, one per fsurdat. That makes `FatesNvp` byte-identical to Task 4's
    `FatesMossParams` apart from comments. Deliberate: `FatesNvp` is the first-class moss
    testmod and is where Tasks 6–10 append history variables, while `FatesMossParams` stays
    the minimal paramfile-dimension case and is eventually deleted. Both files carry a comment
    saying why the other exists, so neither gets consolidated away. A corollary of them being
    identical today is (f).
  - (f) **Two of NVP's ten are already done.** Its `Nvp--ALP2BareGrass` and `Nvp--ALP2Bare`
    `Ld5` entries are "moss on, no moss area" — exactly Task 4's two `FatesMossParams` tests
    under different testmod names. Do not re-add them.
  - (g) **Entries to add** (Sam confirmed): bare+moss `Ld5`; bare+moss `Ly2`;
    bare+grass+moss `Ly2`; nocomp-fixedbiogeo bare+grass+moss `Ly2` (compset
    `I2000Clm60Fates`, *not* `…SpRsGs` — NVP's comment saying "in SP mode" is wrong);
    `Ly2` moss-off twins of Task 0's two plain tests, to populate `fates_nvp_long_nonvp`;
    plus one `ERS_D` exact-restart moss test. The `_long` categories are currently unpopulated
    because all four of our existing entries are `Ld5`.
  - (h) **Categories strictly by duration** (Sam's call): `Ld5` → `_short`, `Ly2` → `_long`.
    This overrides NVP's own inconsistency — its `Ld5` bare+moss entry carries a
    `fates_nvp_long` row and its `Ly2` nocomp entry carries a `fates_nvp_short` row.
  - (i) Comments say **GSWP3v1** climate, matching Task 0's entries, not NVP's CRU-JRA.
- [x] **Step 1: port the three testmods**, adapted per Step 0. **COMPLETE (2026-08-24).**
  `FatesNvp` = `use_fates_moss = .true.` + the `$SRCROOT` `fates_paramfile` line, i.e.
  identical to `FatesMossParams` apart from comments (see Step 0(e)); both files carry a
  comment saying why the other exists. `FatesALP2BareMoss` and `FatesALP2BareGrassMoss` are
  `fsurdat` + `use_bedrock = .true.` only, pointing at Sam's regenerated files:
  `.../moss/fsurdat/surfdata_ALP2_hist_2000_16pfts_c260824_{moss,grassmoss}Pft4.nc`.
  Verified in place under `$INPUTDATA`: `mossPft4` is 5.75% bare + 94.25% on natpft 4,
  `grassmossPft4` is 20/50/30 on natpft 0/4/12.
- [x] **Step 2: testlist. COMPLETE (2026-08-24).** **Ten** entries added, all `1x1_ALP2`,
  `Mmpi-serial`. Eight landed first; the last two came out of Step 5's review — the moss-off
  `ERS` sentinel and the nocomp `ERS`. Wallclocks: `Ld5` `00:20:00`, `Ly2` `00:30:00`,
  `ERS_Ld731_D` `01:00:00`.
  **The `Ly2` figure is not a guess** — NVP commit `997cb054a` ("Add an expected fail and
  extend one test's walltime") bumped the direct analogue of our moss-off `Ly2` bare twin
  from `00:20:00` to `00:30:00`, so 20 minutes is known to be short. An earlier draft of this
  step cited NVP's `00:20:00`, which was the pre-bump value. `ERS_Ld731_D` gets `01:00:00`
  because exact-restart runs the model about 1.5×.
  The entries:
  - `SMS_Ld5_D` bare+moss (`FatesColdSatPhen--FatesNvp--FatesALP2BareMoss`) — short
  - `SMS_Ly2_D` bare+moss — long
  - `SMS_Ly2_D` bare+grass+moss (`…--FatesALP2BareGrassMoss`) — long
  - `SMS_Ly2_D` nocomp fixed-biogeography bare+grass+moss
    (`FatesColdNoCompFixedBioGeo--FatesNvp--FatesALP2BareGrassMoss`), compset
    `I2000Clm60Fates` — long. Comment says explicitly that this is *not* SP mode, correcting
    NVP's.
  - `SMS_Ly2_D` moss-off twins of Task 0's two plain tests — long, and the only entries
    carrying `fates_nvp_long_nonvp`
  - `ERS_Ld5_D` and `ERS_Ld731_D` exact-restart, bare+moss (Sam's call: one short, one
    long; the long one was `ERS_Ly2_D` until `ac7f14249` — see the `STOP_N` >= 3
    constraint above)
  - `ERS_Ld5_D` moss-off, `FatesColdSatPhen--FatesALP2BareGrass` — restart-integrity
    sentinel for the 6-litterclass path, which the moss-on `ERS` tests cannot cover. Carries
    `fates_nvp_nonvp` and `fates_nvp_short_nonvp` like Task 0's entries.
  - `ERS_Ld731_D` nocomp fixed-biogeography bare+grass+moss, compset `I2000Clm60Fates` —
    added in Step 5 after review found that spec §10's exact-restart-in-nocomp requirement
    was unmet. **This is the only exact-restart test that exercises fuel, fire, litter
    turnover and allocation**: SP mode skips all of them (`EDMainMod.F90` gates
    `DailyFireModel`, disturbance, state integration and recruitment on non-SP), so the
    SP `ERS` tests restart a configuration in which `moss_fines` is identically zero. Task 7
    Step 5(c) depends on this entry existing.

  Categories per Sam's calls (h) and 2026-08-24: strictly by duration, so short entries take
  `fates`/`fates_nvp`/`fates_nvp_short` and long ones `fates`/`fates_nvp`/`fates_nvp_long`,
  with the moss-off twins adding `fates_nvp_long_nonvp`. **Izumi nag carries the same
  categories as derecho intel/gnu on every entry** — this supersedes the note at the Task 0
  Step 0 "Categories" bullet that izumi should be omitted from the `*_nonvp` suites.

  Two pre-existing inconsistencies in already-committed entries surfaced here:
  - **Fixed:** Task 4's two `FatesMossParams` entries carried `fates_nvp_nonvp` and
    `fates_nvp_short_nonvp`, but those are moss-*on* tests and `_nonvp` means moss-off — the
    rows were a copy-paste from the Task 0 machine block. Removed (Sam, 2026-08-24).
  - **Deliberately left:** Task 0's two plain entries still omit izumi from their `*_nonvp`
    rows, i.e. they follow the superseded rule while everything added here follows the new
    one. Sam's call (2026-08-24) — not worth churning the b4b baseline entries for.
- [x] **Step 3: build check — SKIPPED (Sam, 2026-08-24).** The case built at the end of
  Task 4 and nothing build-relevant has changed since: this task added only testmods,
  testlist entries, and two fsurdats. No Fortran, no build files.
- [x] **Step 4: expected outcomes for Sam's review.** Drafted 2026-08-24; **executed and
  COMPLETE (2026-08-25)** — Sam ran the suite and every test passed as expected. This was the
  first execution of anything in Tasks 4-5: Task 4 landed code and tests but ran neither.

  **A. FATES harness (inherited from Task 4 Step 4).**
  1. Fuel functional test, standard 6-class paramfile (`run_functional_tests.py -t fuel`) —
     results **identical to pre-change**. This is the b4b check on making the fuel-class count
     runtime.
  2. FATES unit tests — **PASS**. Note this is the first *gfortran* compile of the Task 4
     code; the `hlm_use_moss` integer-as-logical slip that review caught would have surfaced
     only here, since Intel accepts it as a DEC extension.

  **B. CLM system tests — 14 `1x1_ALP2` entries, in six groups.**
  - *Moss off, pre-existing (2, Task 0, `Ld5`).* Unchanged and **b4b against their
    baselines**. These remain the b4b instrument for the whole project.
  - *Moss on, zero moss area (2, Task 4, `FatesMossParams`, `Ld5`).* **PASS.** Exercises the
    8-litterclass read, the runtime fuel-class sizing, and Task 3's `vascular`/switch
    agreement check. Be precise about the history/restart claim: these are `SMS` with **no
    baseline**, so they show only that the 8-class path runs end to end and writes history and
    restart files without aborting — the dimensions are self-consistent and registerable, not
    verified correct. The b4b guarantee for the *unchanged 6-class* path comes from Task 0's
    two entries comparing against their baselines, and restart integrity comes from the `ERS`
    entries. No moss science (zero moss area).
  - *Moss on, with moss area, SP mode (5 new: `SMS_Ld5_D` and `SMS_Ly2_D` bare+moss,
    `SMS_Ly2_D` bare+grass+moss, `ERS_Ld5_D` and `ERS_Ld731_D` bare+moss).* **PASS**, and both
    `ERS` entries restart bit-for-bit. Note these restart a configuration with no fire, no
    litter turnover and no allocation — SP mode skips all of it.
  - *Moss on, with moss area, nocomp full FATES (2 new: `SMS_Ly2_D` and `ERS_Ld731_D`, both
    `FatesColdNoCompFixedBioGeo--FatesNvp--FatesALP2BareGrassMoss`, compset
    `I2000Clm60Fates`).* **PASS.** The only entries that exercise moss through fuel, fire,
    litter and allocation, and the only exact-restart coverage of any of it.
  - *Moss off, long (2 new `SMS_Ly2_D` twins of Task 0's plain tests).* **PASS.**
  - *Moss off, exact restart (1 new `ERS_Ld5_D` on `FatesALP2BareGrass`).* **PASS.** Restart
    sentinel for the 6-litterclass path.
  - None of the 10 new entries has a baseline — all are new names.

  **C. What these prove — and the thirteen deferred parameters.** Moss runs as a grass-like
  PFT with a moss identity. Thirteen parameters that would otherwise change its carbon or
  radiation behaviour are **deferred** (Sam's calls, 2026-08-24). This is the canonical
  record; Task 2 carries only a pointer here, and Tasks 10/11 the restore instructions.

  - Deferred to **Task 10**, physiology: `fates_leaf_vcmax25top`,
    `fates_leaf_stomatal_intercept`, `fates_leaf_stomatal_slope_ballberry`,
    `fates_leaf_stomatal_slope_medlyn`, `fates_leaf_agross_btran_model`,
    `fates_phen_leaf_habit`.
  - Deferred to **Task 10** as well, the radiation group restored together:
    `fates_rad_leaf_clumping_index`, `fates_rad_leaf_taunir`, `fates_rad_leaf_tauvis`,
    `fates_rad_stem_taunir`, `fates_rad_stem_tauvis`, `fates_rad_leaf_xl`.
  - Deferred to **Task 11**: `fates_recruit_seed_dbh_repro_threshold`.
  - **Mechanism:** they stay in `MOSS_PFT_OVERRIDES` in `tools/make_moss_params.py` with
    their rationale comments intact, but are named in a `DEFERRED_PFT_OVERRIDES` set that the
    apply loop skips, so moss keeps the `arctic_c3_grass` value it was seeded from. The script
    prints what it deferred and hard-errors on a key that is not a real override. Restoration
    is a one-line delete per key plus a regeneration.
  - **Why the physiology six:** until Task 10 replaces the stomatal solve, moss still goes
    through it, and with intercept and both slopes at 0 the conductance collapses to the
    `gsmin0` floor (`biogeophys/LeafBiophysicsMod.F90:2001-2005`) — GPP ~0, a carbon sink with
    no source. Evergreen leaf habit deepens the drain. Harmless in SP mode where structure is
    prescribed, but the nocomp full-FATES 2-year test has moss on 50% of the gridcell living
    off its own carbon balance for two years, where starvation or a conservation-check failure
    would be an artefact of task ordering *and* would mask real bugs.
  - **Why the radiation six:** added after review corrected an earlier claim here that
    radiation does not affect carbon balance. It does — `fates_rad_leaf_clumping_index`
    multiplies the light-extinction coefficient directly
    (`radiation/TwoStreamMLPEMod.F90:689,966`), so it changes absorbed PAR and therefore GPP,
    in the very test the deferral exists to protect. Moss carries 10.0 against a parameter
    documented as "clumping index 0-1" with no range check anywhere in FATES. The tau/xl
    overrides go with it because they are one coherent radiative description of a dark,
    near-opaque thallus; applying half would be worse than applying none. **This does not
    revisit the 10.0 value**, which is Sam's settled decision — only when it takes effect.
  - **Not deferred:** the two moss-scale structural overrides, `fates_recruit_height_min` and
    `fates_allom_fnrt_prof_a`. Neither enters the carbon or radiation budget, so the spec §3
    corrections stand.
  - **Net effect:** moss differs from `arctic_c3_grass` in **five** parameters —
    `fates_pftname`, `fates_vascular`, `fates_hlm_pft_map`, `fates_recruit_height_min`,
    `fates_allom_fnrt_prof_a`. Moss is grass with an identity flag.
  - **On reproduction.** Review flagged that reverting the dbh threshold to grass's 3.0 leaves
    moss on the immature branch at `seed_alloc = 0.0`, i.e. producing no seed — spec §3's
    stated extinction mechanism. Checked against the regenerated file: of ~70
    reproduction/recruitment/allometry parameters, moss and grass now differ in exactly two,
    and only `fates_recruit_height_min` is reproduction-adjacent — it sets recruit size, not
    whether reproduction happens. Every governing parameter (`seed_alloc`,
    `seed_alloc_mature`, `germination_rate`, `init_density`, `prescribed_rate`, and every
    allometry coefficient and mode including `dbh_maxheight`) is now identical to grass. So
    moss's dbh grows the way grass's does and crossing 3.0 cm is the same question as for
    arctic grass in the same gridcell. The spec's "never crosses 3 cm" described moss carrying
    its *own* parameters, which it no longer does. Residual: moss recruits smaller, so it
    takes marginally longer. Static-parameter reasoning, not a run.
  - Checked before deferring `fates_phen_leaf_habit`: reverting to grass's deciduous value is
    safe because moss already inherits `fates_phen_flush_fraction = 0.5` from the grass copy,
    satisfying the deciduous requirement in `EDPftvarcon.F90`.

  So these tests exercise **plumbing, not moss physiology or radiation**, and deliberately so.
  The corollary is that they cannot detect a regression in either; Task 10 is the first task
  whose tests can.

  **D. Baselines.** None of the 10 new entries has one — CIME keys baselines by full test
  name, and all 10 names are new, including the moss-off `Ly2` twins, which differ from
  Task 0's `Ld5` entries only in duration. **Sam generates moss baselines at this task**
  (decided 2026-08-24), so Tasks 6-11 can see exactly what each change does to moss
  behaviour. That also satisfies Task 6 Step 5(b), which compares `FATES_LIVEMOSS_FUEL`
  against what previously appeared in the live-grass fuel class — a comparison that needs a
  prior moss run to exist.

  **E. Two abort cases no test covers.** A CIME test that aborts is a FAIL, so these stay
  manual: (i) `use_fates_moss = .true.` with the default 6-class JSON, and (ii) the moss JSON
  with `use_fates_moss = .false.` Both should abort cleanly at initialization with the Task 4
  size message and/or Task 3's `fates_vascular` biconditional message. (The E cases are
  manual and separate from the automated suite; "all tests pass" above refers to the suite.)

  **F. Infrastructure added 2026-08-25 to make the `derecho_intel` + `mpi-serial` ALP2 runs
  pass.** These runs first died with an ESMF floating divide-by-zero deep in the
  `ch4finundated` stream regrid — a known intel + mpi-serial issue, **ESCOMP/CTSM #3798**
  (gnu builds of the same tests passed; SP-mode ALP2 tests passed on both compilers). Landed:
  - `2d62c1ef0` — a CLMBuildNamelist guard that fails the namelist build when
    `COMPILER=intel` and `MPILIB=mpi-serial`, so the combination errors clearly at build-nml
    time instead of crashing at runtime. Added via subagent-driven development
    (implement → review), plus a `%failtest` unit test.
  - `90ef1c642` — an exception to that guard: it does **not** fire when
    `ch4finundatedmapalgo='nn'` (nearest-neighbor mapping avoids the crash). Required moving
    the guard call after `process_namelist_user_input` so the namelist value is available;
    two new unit tests (`nn` passes, `bilinear` still fails).
  - `f249440ab` + `fba615ab1` — a `FatesALP2` base testmod that sets `use_bedrock=.true.`
    and `ch4finundatedmapalgo='nn'`, inherited via `include_user_mods` by all four
    `FatesALP2{Bare,BareGrass,BareGrassMoss,BareMoss}` leaf testmods, so every ALP2 test now
    carries `nn` and the guard is satisfied.
  - `44a424d03` — bedrock indexing fix in the FATES interface (ESCOMP/CTSM #4159), needed
    because the ALP2 testmods run with `use_bedrock=.true.`
  **Scope caveat:** the guard is a blanket intel × mpi-serial block (Sam's call — to be
  removed before any upstream merge). Its blast radius is *every* intel + `_Mmpi-serial`
  entry in `testlist_clm.xml` (~38, mostly non-ALP2), all of which would now fail the
  namelist build on `derecho_intel` unless they also set `nn`.
- [x] **Step 5: reviews, then commit. COMPLETE (2026-08-24).** Code review and spec review
  both run over the uncommitted work, plus a third focused review of
  `make_moss_pft4_fsurdat.py`. Substantive changes that came out of them: the `Ly2`
  wallclocks (NVP's own bump commit proved `00:20:00` short), the nocomp `ERS` entry (spec
  §10's exact-restart-in-nocomp requirement was unmet — every other `ERS` is SP-mode, where
  FATES skips fire, litter and allocation entirely), the `hist_fincl1 +=` requirement (a
  plain assignment would have wiped the FATES history list on the only SPITFIRE test), the
  radiation group joining the deferral (an earlier note wrongly claimed radiation does not
  affect carbon balance), and the fsurdat script's drift check becoming a real two-directional
  assertion over an exact comparison. Findings deliberately not acted on: no
  `ExpectedTestFails` entries, since we expect these to pass on this branch — NVP carries
  changes we do not. Sam's post-commit review optionally runs the
  hand-off.

### Task 6: Moss fuel-class indices, live-moss fuel routing, cohort burn keying, and live-moss history

**Files:**
- Modify (FATES): `fire/FatesFuelClassesMod.F90` (the moss indices and accessors, moved
  here from Task 4 on 2026-08-24 — see that task's preamble)
- Modify (FATES): `biogeochem/FatesPatchMod.F90` (`UpdateLiveGrass`, ~lines 814–842;
  add `livemoss` patch member beside `livegrass`)
- Modify (FATES): `fire/SFMainMod.F90` (`UpdateFuelCharacteristics`, ~lines 164–186)
- Modify (FATES): `biogeochem/EDPatchDynamicsMod.F90` (cohort burn keying, ~lines
  1096–1103)
- Modify (FATES): `main/FatesHistoryInterfaceMod.F90` (`FATES_LIVEMOSS_FUEL`)
- Modify: `cime_config/testdefs/testmods_dirs/clm/FatesNvp/user_nl_clm` (add the new
  history variable to the output list)

**Interfaces:**
- Consumes: `prt_params%vascular` (Task 3), `num_fuel_classes` as a runtime value (Task 4).
- Produces: `fuel_classes%live_moss()` → 7 and `fuel_classes%dead_moss()` → 8, from private
  indices `live_moss_i = 7`/`dead_moss_i = 8`, both accessors `endrun`ing if
  `num_fuel_classes < 8`. Tasks 7 and 9 consume `dead_moss()` from here, not from Task 4.
  The guard is exercised for the first time by this task, which is why the accessors live
  here rather than in Task 4.
- Produces: `currentPatch%livemoss` (r8, kgC m-2), filled alongside `livegrass`;
  `loading(fuel_classes%live_moss()) = currentPatch%livemoss`; history variable
  `FATES_LIVEMOSS_FUEL` (site-level kgC m-2, registered only when `hlm_use_moss` —
  this task establishes the conditional-registration pattern later tasks follow).

- [x] **Step 0 (orchestrator):** Re-read `UpdateLiveGrass` and the burn-keying block;
  confirm `UpdateTreeGrassArea` (accepted: moss stays lumped as "grass" for wind
  attenuation, spec §12) needs no change. Identify the conditional-registration
  precedent in `FatesHistoryInterfaceMod` (e.g., hydro-only variables) for the history
  step. Forward check: Task 7 must NOT double-count moss in `livegrass`; the history
  pattern here is reused by Tasks 7, 8, 10.
- [x] **Step 0b: moss fuel-class indices.** In `fire/FatesFuelClassesMod.F90`, add private
  indices `live_moss_i = 7` and `dead_moss_i = 8` with public accessor functions
  `live_moss()`/`dead_moss()` that `endrun` if `num_fuel_classes < 8`. Also fix that module's
  header comment, which still says "There are six fuel classes". Do this first — Steps 2 and 3
  below both call the accessors.
- [x] **Step 1: split live pools.** In `UpdateLiveGrass`, for non-woody cohorts branch
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
- [x] **Step 2: loading.** In `UpdateFuelCharacteristics`, where
  `loading(live_grass)` is set from `livegrass`, add (guarded by
  `hlm_use_moss == itrue`): `loading(fuel_classes%live_moss()) = currentPatch%livemoss`.
- [x] **Step 3: cohort burn keying.** In `EDPatchDynamicsMod` where non-woody cohorts
  take `leaf_burn_frac = frac_burnt(fuel_classes%live_grass())`, moss cohorts
  (`vascular==ifalse`) instead take `frac_burnt(fuel_classes%live_moss())`.
- [x] **Step 4: history.** Register and fill `FATES_LIVEMOSS_FUEL` (patch `livemoss`
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
- Consumes: `prt_params%vascular` (Task 3), `fuel_classes%dead_moss()` (Task 6).
- Produces: on `litter_type`: `moss_fines(ndcmpy)`, `moss_fines_in(ndcmpy)`,
  `moss_fines_frag(ndcmpy)` (all r8, kg m-2 and kg m-2 day-1), behaving exactly as the
  `leaf_fines` triplet; `loading(dead_moss)` populated; history `FATES_MOSS_FINES`
  (site-level kg m-2). Task 9 needs `dead_moss` loading populated.

- [x] **Step 0 (orchestrator):** Enumerate ALL touch points of `leaf_fines` (`grep -rn
  leaf_fines src/fates --include=*.F90`) — every site must be evaluated for a
  `moss_fines` twin: init/allocate/zero, fuse, copy, turnover input, fragmentation,
  burn, disturbance-driven litter transfer between patches, seed/litter mass checks,
  restart, history, and the CTSM-BGC flux export (`FatesSoilBGCFluxMod` /
  `flux_diags`). Missing any conservation-accounting site is a mass-balance error —
  this enumeration is the core of the task. Confirm with Sam: moss fine-ROOT litter
  stays in ordinary `root_fines` (roots are a plumbing fiction; suggested: yes).
  Forward check: Task 9 moisture for `dead_moss`; the moss ALP2 ERS test is the
  conservation proof.
- [x] **Step 1: type + threading.** Add the three members mirroring the `leaf_fines`
  triplet at every site enumerated in Step 0 (allocation `ndcmpy`, zeroing, fuse with
  the same weighting arithmetic, copy, restart registration mirroring the existing
  `leaf_fines` restart pattern).
- [x] **Step 2: routing.** In `EDPhysiologyMod` where non-woody cohorts' leaf and stem
  turnover/mortality carbon enters `leaf_fines_in`, route moss cohorts
  (`vascular==ifalse`) to `moss_fines_in` instead. Fragmentation: mirror the
  `leaf_fines_frag` computation for `moss_fines_frag` using `SF_val_max_decomp(
  fuel_classes%dead_moss())` as its decay modifier, and add `moss_fines_frag` into the
  same aggregate fragmentation flux that `leaf_fines_frag` feeds (so CTSM-BGC sees one
  combined fines flux — no CTSM-side change).
- [x] **Step 3: fuel + burn.** `loading(fuel_classes%dead_moss()) =
  sum(litt%moss_fines(:))` beside the dead-leaves loading; in the
  `EDPatchDynamicsMod` burnt-litter block, burn `moss_fines` by
  `frac_burnt(fuel_classes%dead_moss())` with the same bookkeeping
  (`burned_mass` accounting) as `leaf_fines`.
- [x] **Step 4: history.** Register and fill `FATES_MOSS_FINES` per the Task 6 pattern.
- [ ] **Step 5: verify.** (a) Fuel functional test: nonzero `moss_fines` →
  `loading(8)` matches; (b) FATES unit/patch tests (`python run_unit_tests.py`,
  `MPLBACKEND=Agg python run_functional_tests.py --save-figs -t patch`); (c) moss ALP2 SMS +
  **ERS** tests PASS —
  the exact-restart test now covers the restarted `moss_fines` pools, and fatal
  balance checks prove the routing conserves; `FATES_MOSS_FINES` accumulates over the
  run and dead-leaves fuel drops correspondingly for the moss patch; (d) ALP2
  baselines b4b.
- [x] **Step 6: reviews, then commit.**

### Task 8: fwet proxy — canopy wetted fraction `bc_in` field, patch `fwet_moss`, and fwet history

**Files:**
- Modify (FATES): `main/FatesInterfaceTypesMod.F90` (declare `fwet_veg_pa` in
  `bc_in_type`, patch-dimensioned), `main/FatesInterfaceMod.F90` (`allocate_bcin`
  with `maxpatch_total`, `zero_bcs`)
- Modify: `src/utils/clmfates_interfaceMod.F90` (fill `fwet_veg_pa` from
  `waterdiagnosticbulk_inst%fwet_patch`, ungated; fill `watsat_sl` daily from
  `soilstate_inst%watsat_col`, gated on `use_fates_moss` since `wrap_btran` is
  otherwise its only writer; wire the instance into the wrapper that runs before
  fire/photosynthesis — per Step 0)
- Modify (FATES): `biogeochem/FatesPatchMod.F90` (add `fwet_moss` patch member) and the
  site-level update loop (`EDMainMod` daily driver or `SFMainMod` entry — Step 0 picks
  the single update point)
- Modify (FATES): `main/FatesHistoryInterfaceMod.F90` (`FATES_MOSS_FWET`,
  `FATES_MOSS_FWET_SOIL`, `FATES_MOSS_FWET_CANOPY`)
- Modify (FATES): `main/FatesRestartInterfaceMod.F90` (restart `fwet_moss` and its two
  ingredients, gated on `hlm_use_moss`, following the Task 7 `moss_fines` conditional
  pattern)
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

**Step 0 resolutions (Sam, 2026-09-01):**
- The soil half uses TOTAL volumetric water (liquid + ice), not liquid only — a frozen top
  soil layer means frozen moss, which damps fire. This keeps spec §7's single new coupler
  field. `bc_in%h2o_liqvol_sl` carries total water only at the daily `dynamics_driv` fill;
  `wrap_btran` overwrites it with liquid-only water sub-daily, which is why the proxy must be
  diagnosed in the daily sequence — see the upstream-observations bullet on that field.
- `watsat_sl` is filled daily in `dynamics_driv`, gated on `use_fates_moss`, because
  `wrap_btran` sets it to -999 outside the exposed-vegetation filter and the proxy needs a
  valid porosity at the daily call.
- The single update point is `ed_ecosystem_dynamics`, outside the SP/ST3 gate and ahead of
  `DailyFireModel` — unlike grass's fuel quantities, which are computed only when SPITFIRE is
  on — because moss physiology needs the proxy too. Deliberately one writer.
- Three patch members rather than one: `update_history_dyn_sitelevel` takes no `bc_in`, so the
  two ingredients spec §9 asks for must ride on the patch. `fwet_moss_soil` stays there too,
  for uniformity, though it is site-uniform by construction.
- Bareground patches are skipped, and history is area-weighted over all patches including
  bareground, matching the existing intensive fuel diagnostics (`FATES_FUEL_EFF_MOIST`,
  `_BULKD`, `_SAV`, `_MEF`), which are likewise computed only for vegetated patches and then
  diluted by bareground area.
- The three patch members are on the FATES restart file, gated on `hlm_use_moss`. Without them
  the first post-restart history record is zero, because `restart()` calls `update_history_dyn`
  before the first daily dynamics — the moss `ERS` tests would fail. Later tasks adding
  daily-diagnosed patch state should follow this.
- **`maximum_leaf_wetted_fraction` is a candidate for eventual tuning, and will be awkward
  to tune.** The canopy ingredient of the proxy can never exceed it (0.05 on the standard
  parameter file), so it sets a hard ceiling on how much interception can move the proxy —
  the reason the soil ingredient dominates in practice. Retuning it for moss alone is not
  possible today: it is a single global scalar read from the CTSM parameter file
  (`readNcdioScalar`, `biogeophys/CanopyHydrologyMod.F90:53,162`) and applied uniformly to
  every patch at `:1171`, with no PFT dimension to key off. Any change to it therefore moves
  leaf wetting for all 14 PFTs, not just moss. Making it moss-specific would mean giving it
  a PFT dimension upstream in CTSM — out of scope here. Recorded so it is not rediscovered
  in Task 9 or Task 10.

- [x] **Step 0 (orchestrator):** Choose the fill site in `clmfates_interfaceMod`: it
  must run before `wrap_spitfire` each FATES dynamics step — inspect where
  `precip24_pa`-style fire weather inputs are filled and co-locate. Confirm
  `waterdiagnosticbulk_inst` is reachable there (otherwise add it to the call
  signature from `clm_driver.F90`). Confirm top soil layer index 1 is correct for
  `h2o_liqvol_sl`. Ask Sam: should the soil half use liquid only (suggested: yes —
  frozen layer-1 water should read as "dry" fuel-wise)? Forward check: Tasks 9, 10
  read `fwet_moss` by that exact name.
- [x] **Step 1: 4-touch `bc_in` field.** Declare, allocate (`maxpatch_total`), zero, and
  fill `fwet_veg_pa` from `fwet_patch(p)` for exposed-veg patches.
- [x] **Step 2: patch member + update.** Add `fwet_moss` to `fates_patch_type` (init
  0), compute it at the chosen daily update point, guarded by `hlm_use_moss`.
- [x] **Step 3: history.** Register and fill `FATES_MOSS_FWET` (the max),
  `FATES_MOSS_FWET_SOIL` (soil ingredient), `FATES_MOSS_FWET_CANOPY` (canopy wetted
  fraction as received) per the Task 6 pattern.
- [ ] **Step 4: verify — SKIPPED (Sam, 2026-09-01).** Every machine Sam could build or run
  on was down, so verification (build, run, FATES functional/unit tests, ALP2 b4b) is
  deferred until a machine is back. When run, expect: moss ALP2 tests PASS; in the
  history, `FATES_MOSS_FWET` tracks rain events (canopy ingredient spikes with
  precipitation and decays; soil ingredient varies smoothly; the max is always ≥ both);
  ALP2 baselines b4b.
- [x] **Step 5: reviews, then commit. COMPLETE (2026-09-01).** Spec review passed; code
  review found one Important issue (the three new patch members were missing from the FATES
  restart file, which would have failed the moss `ERS_Ld731` tests as soon as this task
  landed, because `restart()` calls `update_history_dyn` before the first daily dynamics)
  plus three minor ones. All five fixed in fix round 1 and confirmed ADDRESSED by a scoped
  re-review, with no new breakage. Three further rounds followed: round 2 applied Sam's
  change requests after he reviewed the Step 0 rulings (gate the `watsat_sl` fill on
  `use_fates_moss`; say in the code why the update sits outside the fire path; record the
  resolutions and correct the Global Constraints history-variable bullet). Rounds 3 and 4
  were comment-only, making that rationale self-contained for upstream — no task numbers,
  no plan-file pointers, no hardcoded line numbers — and restating the proxy's consumers as
  a contract rather than as a call graph that does not exist until Tasks 9 and 10.

### Task 9: Moss fuel moisture

**Files:**
- Modify (FATES): `fire/FatesFuelMod.F90` (`UpdateFuelMoisture`, lines 189–236)
- Modify (FATES): `fire/SFMainMod.F90` (pass `currentPatch%fwet_moss` down)
- Modify (FATES): `testing/tests/functional/fire/fuel/FatesTestFuel.F90` (+ its Python
  checker) — moss moisture cases

**Interfaces:**
- Consumes: `currentPatch%fwet_moss` (Task 8), `fuel_classes%live_moss()/dead_moss()`
  (Task 6), `hlm_moss_fuel_moisture_live_intercept/slope`, `hlm_moss_fuel_moisture_dead_intercept/slope`, `hlm_moss_max_burn_frac`
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

**Also restores twelve deferred moss parameters** (see Task 5 Step 4(C)): delete the six
physiology keys (`fates_leaf_vcmax25top`, `fates_leaf_stomatal_intercept`,
`fates_leaf_stomatal_slope_ballberry`, `fates_leaf_stomatal_slope_medlyn`,
`fates_leaf_agross_btran_model`, `fates_phen_leaf_habit`) **and the six radiation keys**
(`fates_rad_leaf_clumping_index`, `fates_rad_leaf_taunir`, `fates_rad_leaf_tauvis`,
`fates_rad_stem_taunir`, `fates_rad_stem_tauvis`, `fates_rad_leaf_xl`) from
`DEFERRED_PFT_OVERRIDES` in `tools/make_moss_params.py`, regenerate
`fates_params_moss.json`, and commit both. This task is exactly where the zeroed stomatal
parameters stop being a hazard, because it is what replaces the stomatal solve; the
radiation group rides along because it also acts on absorbed PAR and hence GPP, and because
splitting a single coherent radiative description across two tasks would be worse than
moving it in one piece. Expect answer changes from the radiation restore that have nothing
to do with this task's Fortran — in particular `fates_rad_leaf_clumping_index` going 0.75 →
10.0, which is out of the parameter's documented 0-1 range and unchecked by FATES.

**This task is large — consider splitting it.** See Step 0.

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

- [ ] **Step 0 (orchestrator): first, consider splitting this task.** By the time it is
  reached it carries the moss CO2 path, the wetness-limited vcmax, a new patch member, a new
  history variable, *and* the restoration of twelve deferred parameters — six physiology and
  six radiation — whose answer changes are independent of this task's Fortran. Plausible
  seams: (a) the parameter restoration as its own task, so its answer changes are isolated
  and attributable; (b) radiation separate from physiology; (c) the history variable with
  whatever it diagnoses. Decide with Sam before starting, not partway through.
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

**Also restores one deferred moss parameter** (see Task 5 Step 4(C)): delete
`fates_recruit_seed_dbh_repro_threshold` from `DEFERRED_PFT_OVERRIDES` in
`tools/make_moss_params.py`, regenerate `fates_params_moss.json`, and commit both. Assigned
here because a moss-scale dbh threshold only means something once moss dimensions are
settled — flagged as a judgement call, not an obvious home.

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
- **Delete: `cime_config/testdefs/testmods_dirs/clm/FatesMossParams/`** (Sam, 2026-08-24).
  It is identical to `FatesNvp` apart from comments and exists only as the transitional
  Task 4 case; repoint its two testlist entries at `FatesNvp` or drop them if `FatesNvp`
  coverage subsumes them.
- **Delete: `make_moss_pft4_fsurdat.py`** at the CTSM repo root (Sam, 2026-08-24) — a
  project-local helper that must not go upstream. The fsurdats it generated live in
  `$INPUTDATA` and are unaffected.

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
