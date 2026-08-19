# NVP Stub Implementation Plan (executes `this-is-the-community-velvety-harp.md`)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Spec:** `.claude/plans/this-is-the-community-velvety-harp.md` (the "design plan"; §-references below point there). This file is the task decomposition of that spec — the spec governs on any conflict.

**Goal:** A stub NVP (moss) layer at index 0 on istsoil/istcrop columns, on a new branch from the `ctsm5.4.028` tag, bit-for-bit with stock when `use_nvp=.false.`, conservation-exact when on, engineered to merge into `ctsm5.4.028_nvp`.

**Architecture:** Static per-column `jbot_sno` (0 or −1) + honest `snl`; NVP occupies matrix row −1 in the heat solve; centralized 4-way endmember fractions; constant namelist thickness/coverage/transmissivity; zero-thickness (`dz_nvp=0`) is first-class via the skip invariant. Code is harvested from the `ctsm5.4.028_nvp` worktree where the audit marked it sound, reimplemented where marked [fix].

**Tech Stack:** CTSM Fortran (F2003), CTSM build-namelist (Perl/XML), pFUnit unit tests, git worktrees.

## Global Constraints

- Work happens in the **user's dedicated checkout with a pre-made working branch** (path and branch name confirmed with the user at execution start; based on `ctsm5.4.028`). Do NOT create a new branch or worktree for the implementation.
- Harvest source (read-only): a git worktree of branch `ctsm5.4.028_nvp` at **`.worktrees/ctsm5.4.028_nvp`**, in the top level of the dedicated checkout, detached at **`103082a17`** — the commit the spec audited, so every "theirs `:NNNN`" line reference in this plan holds verbatim. The branch is not local; it lives on remote `huitang-earth` (`git@github.com:huitang-earth/CTSM.git`). Created once in Task 0:

```bash
git fetch huitang-earth ctsm5.4.028_nvp
git worktree add --detach .worktrees/ctsm5.4.028_nvp 103082a17
```

  Add `.worktrees` to the `.gitignore` "DELETE THESE BEFORE MERGING" block (which already lists `test-bld`) so it never enters a commit. Referred to below as `<worktree>`. Submodules are deliberately not initialized — the stub harvests only CLM source (`src/main`, `src/biogeophys`, `bld/`) and has no FATES dependency.

  The branch has moved on since the harvest commit, in `clm_varctl.F90`, `controlMod.F90`, both namelist XMLs, and `CLMBuildNamelist.pm` — **exactly Task 1's files**. So Task 1's "place `use_nvp` where their branch places it" anchors must be checked against the branch head as well as `<worktree>`, and Task 18's merge rehearsal targets the branch head at that time.
- `use_nvp = .false.` must remain **bit-for-bit** with stock: every new conditional must reduce algebraically to stock when `col%jbot_sno(c) == 0` (which is everywhere when `use_nvp=.false.`).
- Match `ctsm5.4.028_nvp` names exactly wherever a counterpart exists (spec §1.7): `col%jbot_sno`, `col%nvp_layer_active`, `col%dz_nvp`, `col%frac_nvp`, `NVPParamsMod`, `NVPLayerDynamicsMod`, `qflx_nvp_*`, `qflx_ev_nvp*`, `eflx_sh_nvp`, `H2ONVP`/`T_NVP`/… history names, restart names `DZ_NVP`/`FRAC_NVP`/`JBOT_SNO`.
- Never assume `frac_nvp = 1` (spec §1.4). Never let snow loops touch index 0 on NVP columns (spec §2). All moss physics gates on `nvp_is_present(c)` (spec §2).
- **The five NVP index queries are type-bound, not module procedures** (settled in Task 2). Call them on the column object — `col%get_jtop_snow(c)`, `col%get_jbot_snow(c)`, `col%nvp_layer_exists(c)`, `col%nvp_is_present(c)`, `col%nvp_is_empty(c)` — so the spec §2 idiom table reads `do j = col%get_jtop_snow(c), col%get_jbot_snow(c)`. **In a routine that takes `col` as a dummy argument, this matters for correctness, not style:** referencing the module `col` through host association while it is argument-associated is not conforming (F2018 15.5.2.13) and lets a compiler assume the read cannot alias writes through the dummy. `SnowHydrologyMod`'s `ZeroEmptySnowLayers` is exactly such a routine, and five other files use the same pattern. Prefer `col%get_jbot_snow(c)` over the raw `col%jbot_sno(c)` component at call sites.
  - **The five index queries differ in what they read, and that decides which routines can safely call them.** `get_jtop_snow`, `get_jbot_snow` and `nvp_layer_exists` read only `snl` and `jbot_sno`; `nvp_is_present` and `nvp_is_empty` additionally read **`dz(c,0)`**. So in a routine that receives `col%dz` as a definable dummy — `BulkDiag_NewSnowDiagnostics` and `PostPercolation_AdjustLayerThicknesses` both do, and Task 5c added `get_jtop_snow` calls to each — the first three are conforming (`col%dz` is never referenced by another means, F2018 15.5.2.13) but `nvp_is_present`/`nvp_is_empty` **are not**. If a later task needs a presence test in such a routine, pass the answer in or take `col` as a dummy; do not reach for the module `col`.
- All `BalanceCheckMod` `endrun`s stay armed (spec §1.11).
- **Debug traces are allowed during development and are removed in Task 17.** Spec §1.11 permits `if (use_nvp)`-guarded, rate-limited diagnostics; this relaxes that further for the duration of the build-out, because the call-order questions this plan keeps raising are only answerable from a real run. Rules that make the removal mechanical and keep `use_nvp=.false.` honest:
  - Every trace line is prefixed **`NVP_TRACE:`** and is the only thing on its line. Task 17 removes them by that marker, so a trace without it will survive and ship.
  - Guard with `if (masterproc)` — 128 ranks otherwise.
  - **Traces go AROUND call sites, not inside `use_nvp`-guarded routines.** A trace inside `NVPLayerInit` never fires with the flag off, which tells you nothing; a trace at the call site tells you the call was reached and whether it did anything. Trace the skipped case too.
  - Trace the non-NVP routines whose firing order NVP depends on, not just NVP's own — the orderings that have actually mattered are `control_init` → `WaterType%ReadNamelist`, `NVPLayerInit` → `InitSnowLayers`, `subgridRestRead` → `clm_instRest`, and `InitAllocate` → `InitHistory` → `InitCold`. The last of these was got wrong in Task 4 despite being knowable by reading.
  - Init-time only, or otherwise one-shot. Nothing inside a timestep loop.
- Every code comment states a constraint, not a narration. New/changed comments in harvested code must be re-checked against OUR conventions (their stale comments caused bugs — spec §3).
- Fortran style: match surrounding code (2-space indent, `_r8` literals, `associate` blocks, `SHR_ASSERT_ALL_FL` for bounds).
- **pFUnit authoring limits, both found the hard way.** The preprocessor cannot parse a **trailing comment** on an `@assert` line (Task 5a), and cannot parse an **`&` continuation** of one either (Task 5d) — it passes the fragment through verbatim and the compile dies on "Unrecognized token '@'". Keep every assertion on one physical line and hoist long actual arguments into local scalars first; put any comment on its own line above.
- **The user runs the system test suites — never run them yourself.** `run_sys_tests`, `clm_short`, and `aux_clm` are the user's to launch, foreground or background. Your verification stops at the build check and unit tests; then hand off and wait. Never report or characterize a suite result the user has not given you.
- **Never change a line only for whitespace.** No re-aligning an existing declaration or `use` block to accommodate a longer new name, no stripping trailing whitespace on lines you did not otherwise need to touch, no reindenting untouched code. Let a new line be wider than its neighbors rather than moving them. Whitespace-only edits inflate the diff, land in `git blame`, and manufacture merge conflicts against `ctsm5.4.028_nvp` for no benefit. Check before finishing: `git diff --numstat` and `git diff -w --numstat` must report the same counts for every file.

## Execution Process (user-mandated — applies to every task)

1. Work happens in the user's dedicated checkout on its working branch (confirmed in Task 0).
2. **Every task opens with Step 0: plan review — performed by the orchestrating session, NOT by a subagent** (subagents cannot ask the user anything). Read this task's text against the spec and the actual code it will touch, then **STOP and put to the user**: clarifying questions, problems foreseen, cleanup the task text needs, and anything the task depends on that isn't true yet. Proceed to Step 1 only after the user answers. If Step 0 turns up nothing, say so in one line and ask to proceed anyway — the stop is unconditional.
3. Step 0's resolutions are **written into this plan file** before the implementer is dispatched (amend the task's step text so the subagent actually sees them — it receives only its own task text, never this list, never the Self-Review section).
4. **Fresh implementer subagent per task.** The subagent receives: this plan's task text as amended in Step 0 (only its own task), the spec path, the harvest-worktree path, the dedicated-checkout path, and the Global Constraints above.
5. Each task ends with: verification passes (below) → **one commit** for the task.
6. After the commit, run **two-stage review** (superpowers:requesting-code-review pattern): first a **spec-compliance** reviewer (does the diff implement this task's requirements and only them? cite spec §), then a **code-quality** reviewer (correctness, style, conservation hazards). Reviewers are fresh subagents that see the task text + the commit diff.
7. Issues found → fix → **amend the task's commit** (`git commit --amend --no-edit`) → re-run the failed review stage.
8. **Before presenting, run two mechanical sweeps.** Both close failures that have already recurred in this plan; neither is a judgment call, so do them by inspection rather than from memory.
   - **Plan consistency.** For every decision made in this task's Step 0 or during its reviews, ask what *else* in the plan it contradicts — not whether the plan reads consistently. A decision usually needs edits somewhere other than where it was made: Task 2's type-bound choice belonged in Global Constraints, because implementers never see another task's text; Task 4's zero-init decision left a justification in its own Interfaces block that later turned out to be wrong. Correct stale text in place; do not merely append the new decision beside it.
   - **MERGE_NOTES completeness.** List every `[fix]`, every deliberate divergence from `ctsm5.4.028_nvp`, and every file this task touched that their branch also touches. Each needs a row. Task 18's merge rehearsal compares the real conflict set against that table, so an unlogged divergence surfaces there as an unexplained conflict. This was missed in Tasks 3 and 4.

9. **STOP. Present the task's diff + review outcomes to the user. Do not start the next task until the user approves.** User feedback → fix → amend → re-present.

**Verification before every commit:**
- **Build check**: from the dedicated checkout, `cd test-bld && qcmd -- ./case.build` (a dedicated case at the top level of the checkout). Expected: build completes with no errors. `test-bld/` is write-protected — run the build from it, never edit anything under it.
  - **When the task adds a new `.F90`**, the build cache will not notice it: CIME derives `Srcfiles` from `Filepath`, and adding a file to an existing source directory does not touch `Filepath`, so the build fails with `error #7002: Error in opening the compiled module file`. Force the refresh first — `touch /glade/derecho/scratch/samrabin/test-bld/bld/intel/mpich/debug/nothreads/clm/obj/Filepath` — or `./case.build --clean lnd`. Confirmed empirically in Task 1.
- **Unit tests** (required for any commit that touches Fortran): from the checkout's `src/` directory, `qcmd -- ../cime/scripts/fortran_unit_testing/run_tests.py --build-dir unit_tests.temp`. Expected: all tests pass.
  - **When the task adds a `.pf` file**, `rm -rf src/unit_tests.temp` first. `run_tests.py` does not regenerate a directory's pFUnit driver when its `CMakeLists.txt` test-source list changes, so an incremental run reports "100% tests passed" while still executing the *old* set of cases. Confirmed empirically in Task 5d, where the first run silently reported the pre-task count. Never trust an incremental run's case count after adding a test file.
- Namelist-touching tasks additionally run `bld/unit_testers/build-namelist_test.pl`.

---

### Task 0: Checkout confirmation, verification harness, MERGE_NOTES

**Files:**
- Create: `MERGE_NOTES.md` (top level of the dedicated checkout)

**Interfaces:**
- Produces: confirmed dedicated-checkout path + working branch (recorded in MERGE_NOTES.md), verified build-check and unit-test commands, harvest-checkout path.

- [x] **Step 0: Plan review (orchestrator; do not delegate).** Read this task's text against the spec and the code it touches. **STOP** and put to the user: clarifying questions, problems foreseen, cleanup the task text needs, unmet dependencies. Write the resolutions into this plan file before dispatching the implementer. Scope is Task 0 only — questions about a later task belong to that task's own Step 0, not here. Already settled before this task began: the checkout path and working branch, and the harvest worktree's commit (Global Constraints).

- [x] **Step 1: Confirm the workspace with the user.** Ask for: the dedicated checkout's path and the working branch name. Verify: `git -C <checkout> status` shows that branch, based on `ctsm5.4.028` (`git merge-base HEAD ctsm5.4.028` = the tag commit).

- [x] **Step 2: Harvest worktree of `ctsm5.4.028_nvp`.** Create it at `.worktrees/ctsm5.4.028_nvp` per the Global Constraints (fetch from `huitang-earth`, `git worktree add`), at the commit settled in Step 0. Add `.worktrees` to `.gitignore`'s "DELETE THESE BEFORE MERGING" block. Verify: `git -C .worktrees/ctsm5.4.028_nvp log -1` shows the expected commit, and `git -C .worktrees/ctsm5.4.028_nvp diff --stat ctsm5.4.028..HEAD` lists the ~40 NVP files (the diff command every later task uses to read their code).

- [x] **Step 3: Verify the build check works before any changes**

```bash
cd <checkout>/test-bld && qcmd -- ./case.build
```
Expected: clean build of unmodified code. If `test-bld/` does not exist, stop and ask the user to set it up.

- [x] **Step 4: Verify the unit-test harness works before any changes**

```bash
cd <checkout>/src && qcmd -- ../cime/scripts/fortran_unit_testing/run_tests.py --build-dir unit_tests.temp
```
Expected: all existing tests pass on the unmodified branch (this is the baseline).

- [x] **Step 5: Write `MERGE_NOTES.md`** with sections: "Workspace" (checkout path, branch, harvest path), "Verification commands" (the two commands above, verbatim), "Verification results" (empty; Task 18 fills it), "Intentional merge conflicts" (empty table: | file | why ours differs | resolution |), "Deferred items" (copy the spec §8 table titles). This file accumulates one row per [fix] as tasks land.

- [x] **Step 6: Commit**

```bash
git add MERGE_NOTES.md && git commit -m "Add MERGE_NOTES scaffold for NVP stub work"
```

---

### Task 1: `use_nvp` namelist + `NVPParamsMod`

**Files:**
- Create: `src/biogeophys/NVPParamsMod.F90`
- Modify: `src/main/clm_varctl.F90` (**place `use_nvp` where the `ctsm5.4.028_nvp` branch has it: immediately after `use_fates_bgc`** — check their diff for the exact spot), `src/main/controlMod.F90` (namelist decl / broadcast / log at their branch's positions)
- Modify: `bld/namelist_files/namelist_definition_ctsm.xml`, `bld/namelist_files/namelist_defaults_ctsm.xml`, `bld/CLMBuildNamelist.pm`
- Modify: `src/biogeophys/WaterType.F90` (water-tracer guard — see Step 3)

**Interfaces:**
- Produces: `use_nvp` (logical, `clm_varctl`); module `NVPParamsMod` holding the parameters listed in Step 1. **No read routine in the module** — `nvp_inparm` is read in `controlMod`, mirroring their structure (Step 0 decision 4).
- Consumes: nothing.

- [x] **Step 0: Plan review — DONE.** Resolutions, all confirmed by the user, are folded into Steps 1–4 below: (1) the four Mualem–van Genuchten parameters are added, since Task 3's harvested retention-curve and conductivity functions need them; (2) `nvp_frac_min` is deliberately omitted — it is an activation threshold and the stub never activates; (3) the water-tracer guard moves to `WaterType%ReadNamelist`, the only scope where the flags exist; (4) `nvp_inparm` is read in `controlMod`, mirroring their structure, so `NVPParamsMod` is declarations only. Their `<their value>` literals were read off the harvest worktree and are now inline below.

- [x] **Step 1: Write `NVPParamsMod`.** Mirror the structure of `<worktree>/src/biogeophys/NVPParamsMod.F90` (blanket `public`, declarations only, no read routine). All values below were read from that file except the stub-only block. Keep their comments' unit annotations; drop their `[PORTED by Hui Tang: ...]` markers.

```fortran
module NVPParamsMod
  ! Parameters for the non-vascular plant (NVP) layer, read via the nvp_inparm
  ! namelist group in controlMod. Stub configuration: thickness/coverage/optics
  ! are namelist constants (FATES-prognostic in the ctsm5.4.028_nvp merge).
  use shr_kind_mod, only : r8 => shr_kind_r8
  implicit none
  public

  ! Evaporation resistance: rnvp = rnvp_min + rnvp_amp*(1 - satfrac)**rnvp_exp
  real(r8) :: rnvp_min      = 10.0_r8     ! resistance when saturated       [s m-1]
  real(r8) :: rnvp_amp      = 1000.0_r8   ! amplitude of increase when dry  [s m-1]
  real(r8) :: rnvp_exp      = 3.0_r8      ! exponent of dryness function    [-]
  real(r8) :: rnvp_ice      = 1500.0_r8   ! resistance when frozen          [s m-1]

  ! Hydraulic properties (Mualem-van Genuchten); consumed by Task 3's
  ! NVPWaterRetentionCurve / NVPHydraulicConductivity
  real(r8) :: ksat_nvp      = 1.0e-4_r8   ! saturated hydraulic conductivity [m s-1]
  real(r8) :: n_van_nvp     = 1.5_r8      ! van Genuchten shape parameter n  [-]
  real(r8) :: alpha_van_nvp = 0.01_r8     ! van Genuchten alpha              [cm-1]
  real(r8) :: watsat_nvp    = 0.85_r8     ! porosity                         [m3 m-3]
  real(r8) :: watres_nvp    = 0.05_r8     ! residual water content           [m3 m-3]

  ! Thermal properties of the dry NVP matrix (Farouki-style mixing)
  real(r8) :: thk_dry_nvp   = 0.05_r8     ! dry NVP thermal conductivity     [W m-1 K-1]
  real(r8) :: csol_nvp      = 0.58e6_r8   ! dry NVP volumetric heat capacity [J m-3 K-1]

  ! Stub-only (intentional merge conflict: theirs are FATES-driven)
  real(r8) :: dz_nvp                    = 0._r8    ! prescribed thickness (m); 0 = moss absent
  real(r8) :: frac_nvp                  = 0._r8    ! prescribed areal coverage        [0-1]
  real(r8) :: nvp_transmissivity        = 1._r8    ! SW fraction transmitted to soil  [0-1]
  real(r8) :: alb_nvp_vis               = 0.10_r8  ! NVP albedo, visible              [-]
  real(r8) :: alb_nvp_nir               = 0.25_r8  ! NVP albedo, near-infrared        [-]
  real(r8) :: nvp_coldstart_saturation  = 0.5_r8   ! cold-start pore saturation       [0-1]
end module
```
Deliberately **not** ported: their `nvp_frac_min` (activation threshold — the stub assigns `jbot_sno` statically and never activates). Add a MERGE_NOTES row. Note their `rnvp_ice` is declared but absent from their `nvp_inparm` group, i.e. unsettable on their branch; ours goes in the group (spec §7 treats registration as a fix).

- [x] **Step 2: Read `nvp_inparm` in `controlMod`**, mirroring their structure (`<worktree>/src/main/controlMod.F90`: `use NVPParamsMod` at :55, `namelist /nvp_inparm/` at :276, `shr_nl_find_group_name`/read/`endrun` at :406-410, broadcasts near :890). Ours declares every parameter from Step 1 in the group — including `rnvp_ice`, which theirs omits — and broadcasts each. Validity checks (spec §7), placed after the broadcasts and **wrapped in `if (use_nvp)`** so a stock run is untouched by parameters it never uses: `endrun` unless `dz_nvp >= 0._r8`; `endrun` if `dz_nvp == 0 .and. frac_nvp > 0`; `endrun` unless `0 <= frac_nvp <= 1`, `0 <= nvp_transmissivity <= 1`, `0 <= nvp_coldstart_saturation <= 1`. Plus a degeneracy check: `dz_nvp` must be **exactly** `0._r8` or `>= dz_nvp_min` (`1.e-6_r8`, a local parameter). Exact zero is the spec's first-class "no moss" value and downstream code reads `dz(c,0) > 0` as "moss present" and divides by it, so a denormal thickness must be rejected outright rather than admitted as a very thin layer.

- [x] **Step 3: `use_nvp` in clm_varctl + controlMod**, mirroring `use_excess_ice` exactly (declaration default `.false.`, namelist entry in `clm_inparm`, mpi_bcast, log print). **Water-tracer guard (spec §5) goes in `WaterType%ReadNamelist`, NOT `controlMod`.** The two flags are local variables of that subroutine ([WaterType.F90:441-442](src/biogeophys/WaterType.F90#L441)), never module state, so `controlMod` cannot see them; `SetupTracerInfo` gives `num_tracers > 0` iff either is true. Immediately after the existing `shr_mpi_bcast` calls (~:475), add:

```fortran
if (use_nvp .and. (enable_water_isotopes .or. enable_water_tracer_consistency_checks)) then
   call endrun(msg='use_nvp does not support water tracers'//errMsg(sourcefile, __LINE__))
end if
```
`use_nvp` comes from `clm_varctl` (a leaf module — no circular dependency).

- [x] **Step 4: XML registration.** `namelist_definition_ctsm.xml`: an entry for `use_nvp` (group `clm_inparm`, logical) **at their branch's position** (theirs is at `<worktree>/bld/namelist_files/namelist_definition_ctsm.xml:951`; port only `use_nvp`, not their `use_nvp_undersnow` / `nvp_rad_model_ground` / `use_nvp_temp_for_patch_gas_params`), plus an entry for **every** `nvp_inparm` real from Step 1 (group `nvp_inparm`; descriptions from the Step 1 declarations). Note their branch never registered `nvp_inparm` at all — zero occurrences in their definition XML — so for the reals there is no their-branch position to mirror; registering them is our fix (spec §7). `namelist_defaults_ctsm.xml`: `use_nvp = .false.` at their position (theirs :643) and a default for each real, **identical to the Fortran defaults** (spec §7). `CLMBuildNamelist.pm`: `add_default` for `use_nvp` and for each `nvp_inparm` real (follow `setup_logic_water_tracers` at :3394 as the pattern for a small group); do NOT add a FATES restriction (spec §1.10 — intentional conflict; MERGE_NOTES row).

  Also add the **build-namelist-side twin of the Step 3 runtime guard**, so the incompatibility is caught before the run starts rather than at initialization: after the `use_nvp` and water-tracer defaults are set, `fatal_error` if `use_nvp` is true and either `enable_water_isotopes` or `enable_water_tracer_consistency_checks` is. Both are already handled in `setup_logic_water_tracers` (:3394-3402), so their values are available via `$nl->get_value`. The Fortran `endrun` stays as the backstop — a user can set the namelist by hand.

- [x] **Step 5: Verify.** Build check (`cd test-bld && qcmd -- ./case.build`), unit tests (`cd src && qcmd -- ../cime/scripts/fortran_unit_testing/run_tests.py --build-dir unit_tests.temp`; baseline is 59/59 passing), and — because this task touches the namelist — `bld/unit_testers/build-namelist_test.pl`, which is present. Expected: all pass; a run with `use_nvp` unset produces `lnd_in` identical to stock except the new `nvp_inparm` group at its default values.

- [x] **Step 6: Commit** `git add -A && git commit -m "Add use_nvp namelist infrastructure and NVPParamsMod"` — then the review/approval gate (Execution Process).

---

### Task 2: ColumnType members and query functions

**Files:**
- Modify: `src/main/ColumnType.F90` (members ~line 60-80 to match their layout; alloc/dealloc in `Init`/`Clean` ~line 137/…)

**Interfaces:**
- Produces (used by every later task):
  - `col%jbot_sno(begc:endc)` integer, init `0`
  - `col%nvp_layer_active(begc:endc)` logical, init `.false.`
  - `col%dz_nvp(begc:endc)` real(r8), init `0._r8`
  - `col%frac_nvp(begc:endc)` real(r8), init `0._r8`
  - Five `pure` **type-bound** functions on `column_type`, each taking `(this, c)` — called as `col%<name>(c)`, see Global Constraints for why type-bound:
    - `col%get_jtop_snow(c)` — `snl(c) + 1 + jbot_sno(c)`
    - `col%get_jbot_snow(c)` — `jbot_sno(c)`; pairs with the above so snow loops never touch the raw component
    - `col%nvp_layer_exists(c)` — `jbot_sno(c) == -1`
    - `col%nvp_is_present(c)` — slot exists **and** `dz(c,0) > 0._r8`, via a nested `if` so `dz(c,0)` is never read off an NVP column
    - `col%nvp_is_empty(c)` — `nvp_layer_exists(c) .and. .not. nvp_is_present(c)`

- [x] **Step 0: Plan review — DONE.** Resolutions, confirmed by the user, folded into Steps 1-2: (1) `nvp_is_present` is written as a nested `if` on `jbot_sno`, never as `.and.`, so the `col%dz(c,0)` read is structurally unreachable on non-NVP columns — Fortran does not guarantee `.and.` short-circuits and `dz` is NaN-initialized until `ZeroEmptySnowLayers` has run, so the naive form compares against NaN during init and trips Intel floating-invalid in DEBUG builds; (2) the four functions stay `pure`, which rules out `SHR_ASSERT_ALL_FL` inside them — accepted, since DEBUG builds already bounds-check the underlying array accesses. Context: our `ColumnType` is `save`/`private` with `col` a public module target (:108) and `contains` at :111, so the functions are public module procedures reading the global `col` and need explicit `public ::` declarations.

- [x] **Step 1:** Read their `<worktree>/src/main/ColumnType.F90` diff (`git diff ctsm5.4.028..HEAD -- src/main/ColumnType.F90` in the worktree) and add the four members with identical names, at their position (immediately after `snl`, before `dz`), and the matching `allocate`/`deallocate` lines in `Init`/`Clean` at their positions, with the allocation defaults above. Keep concrete defaults — a consistency check catches failure-to-set at init (Task 3). **Write our own declaration comments; do not port theirs.** Theirs carry `[PORTED by Hui Tang: ...]` markers and assert FATES semantics that are false here ("aggregated from FATES bc_out", "Updated each FATES dynamics timestep in ... wrap_update_hlmfates_dyn", "Consumed by NVPLayerDynamicsMod%UpdateNVPLayer") — our stub assigns these statically at init and has no `UpdateNVPLayer`. That guarantees a conflict on those comment lines; add a MERGE_NOTES row. Note `nvp_layer_active` is redundant with `jbot_sno == -1` and is write-only in our stub, carried solely so their code merges (spec §1.1) — do not make anything read it.

- [x] **Step 2:** Add the four functions as `pure` public module procedures (after `contains`, reading the global `col`; the module defaults to `private`, so each needs an explicit `public ::`). `get_jtop_snow`'s comment must state (spec §2): "When snl==0 on an NVP column this returns 0 (the NVP index) — callers wanting a surface layer with actual mass must fall back to soil layer 1 when .not. nvp_is_present(c)."

  **`nvp_is_present` must not read `col%dz(c,0)` on non-NVP columns.** Fortran does not guarantee `.and.` short-circuits, and `col%dz` is NaN-initialized at allocation and only zeroed once `ZeroEmptySnowLayers` runs, so the naive `nvp_layer_exists(c) .and. col%dz(c,0) > 0._r8` can compare against NaN during initialization — the Intel floating-invalid class the spec blames for their expected-fails. Write it so the `dz` read is structurally unreachable unless the slot exists:

```fortran
pure function nvp_is_present(c) result(present)
  ! Moss physically present: the slot exists AND holds a layer of nonzero
  ! thickness. dz(c,0) is only read where the slot exists -- elsewhere it is
  ! snow storage and may be NaN before the first ZeroEmptySnowLayers call.
  integer, intent(in) :: c
  logical :: present
  present = .false.
  if (nvp_layer_exists(c)) then
     present = (col%dz(c,0) > 0._r8)
  end if
end function nvp_is_present
```
  `nvp_is_empty` derives from these two and so inherits the same protection.

- [x] **Step 3: Run build check.** Expected: compiles; nothing consumes the members yet.

- [x] **Step 4: Commit** `git commit -am "Add NVP column members and index/presence query functions"` → review/approval gate.

---

### Task 3: `NVPLayerDynamicsMod` — static init, restart, cold start

**Files:**
- Create: `src/biogeophys/NVPLayerDynamicsMod.F90`
- Modify: `src/main/clm_instMod.F90` — call `NVPLayerInit` in `clm_instInit` **immediately before the `InitSnowLayers` call at :293** (the plan previously named `clm_initializeMod.F90`; that is wrong, `InitSnowLayers` is called from here), and call `NVPLayerRestart` from `clm_instRest` (:515) alongside the other biogeophys restarts
- Modify: `src/main/clm_initializeMod.F90` — call `NVPColdStart` under `if (is_cold_start)` after the restart-read block; `is_cold_start` is not resolved until :515, well after `clm_instInit`, so this is a different phase from `NVPLayerInit`, not adjacent to it
- Modify: `src/biogeophys/SnowHydrologyMod.F90` — minimal guard only (see Step 2a); the full reindex is Task 5

**Interfaces:**
- Consumes: Task 1 params, Task 2 members/functions.
- Produces:
  - `subroutine NVPLayerInit(bounds)` — for each istsoil/istcrop column: `jbot_sno=-1`, `nvp_layer_active=.true.`, `col%dz_nvp = dz_nvp` (namelist), `col%frac_nvp = frac_nvp` (namelist), `col%dz(c,0)=dz_nvp`, `col%z(c,0)=-0.5_r8*dz_nvp`, `col%zi(c,-1)=-dz_nvp`; `endrun` if called on any other landunit type (spec §6 assertion). All other columns untouched (defaults stand).
  - `subroutine NVPLayerRestart(bounds, ncid, flag)` — restartvars `DZ_NVP` (`interp`), `FRAC_NVP` (`interp`), `JBOT_SNO` (**`skip`** — spec §1.6); on read, derive `nvp_layer_active = (jbot_sno == -1)`; cross-flag guards (spec §7): on `flag=='read'`, if `use_nvp` and `JBOT_SNO` absent → `endrun("restart predates use_nvp; cold-start or interpolate")`; add the reverse guard where restart vars are probed with `use_nvp=.false.` — implement by always *probing* for `JBOT_SNO` presence (readvar pattern of `restUtilMod`) even when `use_nvp=.false.`, and `endrun("restart was written with use_nvp on; enable use_nvp or use a different initial file")` if found. Consistency check: after read with `use_nvp=T`, `endrun` if `abs(col%dz(c,0) - dz_nvp) > 1.e-12_r8` on any NVP column (namelist changed since restart write).
  - `subroutine NVPColdStart(bounds)` — for `nvp_is_present` columns only: fill layer-0 pore water at saturation `nvp_coldstart_saturation` (namelist, Task 1 — parameterized to facilitate testing), partitioned by the column's initial `t_soisno(c,1)`: liquid if `>= tfrz`, ice otherwise (spec §7 — climate-agnostic, unlike their frozen-only `NVPColdStartIce`); zero for `nvp_is_empty`.
- **Deferred out of this task (Step 0 decision): every routine with no caller yet.** Each lands in the task that first consumes it, so nothing commits as dead code. All still live in `NVPLayerDynamicsMod`:
  - `NVPWaterRetentionCurve`, `NVPHydraulicConductivity` (harvest verbatim from their :223-305) → **Task 13**
  - `NVPEvapResistance(fwet_nvp, frozen)` — extracted from their `NVPEvaporation` (:306-388), which has no standalone resistance function; this extraction is ours → **Task 11**
  - `elemental subroutine NVPEffectiveFractions(...)` — the single 4-way derivation (spec §4b) → **Task 8**, its first consumer

- [x] **Step 0: Plan review — DONE.** Resolutions folded into the Files list and Steps 1-3 above: the `NVPLayerInit` call site was named wrongly (it is `clm_instMod`, not `clm_initializeMod`); the restart guard becomes `if (use_nvp .or. flag == 'read')` to make the reverse probe work without a `use_nvp=.false.` run writing NVP variables into its own restart file; `NVPColdStart` sits in a different phase from `NVPLayerInit`, not adjacent to it; a minimal `InitSnowLayers` guard lands here (Step 2a) so `use_nvp=T` is not left silently wrong between Tasks 3 and 5; and every routine with no caller yet is deferred to the task that first consumes it. Original notes retained below. Known going in: (a) this task sets `jbot_sno=-1` while `InitSnowLayers` is not reindexed until Task 5, so `use_nvp=T` is not meaningfully runnable between Tasks 3 and 5 — intermediate commits are only expected to hold for `use_nvp=.false.` (already recorded in MERGE_NOTES by Task 0); (b) `src/biogeophys/CMakeLists.txt` does not list `NVPParamsMod.F90`. That was correct through Task 1 because nothing in the pFUnit build referenced it, but this task's `NVPWaterRetentionCurve`/`NVPHydraulicConductivity` pull `NVPParamsMod` into code the unit tests link, so the file must be added there or the unit-test build breaks. Check whether `NVPLayerDynamicsMod.F90` needs the same. (c) Task 2's nested-`if` in `nvp_is_present` protects **non-NVP** columns only. On a column where `jbot_sno == -1`, the function reads `col%dz(c,0)` — which is still the allocation-time NaN until `NVPLayerInit` assigns it. So `NVPLayerInit` must set `dz(c,0)` before *any* presence query can run on that column, or DEBUG builds trip Intel floating-invalid. This reinforces the spec §7 ordering requirement (geometry before `InitSnowLayers`); verify the ordering rather than assuming it.

- [x] **Step 1:** Write the module: `NVPLayerInit` and `NVPColdStart` fresh, `NVPLayerRestart` adapted from theirs (:665-732) with the guards below. Nothing else — the physics functions are deferred (above). NO `UpdateNVPLayer` dynamic transitions (spec §2), but keep the file name and subroutine granularity so their FATES-driven version merges alongside cleanly. Use `restUtilMod`'s `restartvar`, **not** `restFileMod` — `restFileMod` uses `clm_instMod`, which would create a build-dependency cycle (their comment at :682 records this the hard way).

- [x] **Step 2:** Wire calls: `NVPLayerInit` in `clm_instInit` immediately before `InitSnowLayers` (:293); `NVPColdStart` under `if (is_cold_start)` in `clm_initializeMod` after the restart-read block; `NVPLayerRestart` from `clm_instRest` (:515) with the other biogeophys restarts.

  **The restart call site is `if (use_nvp .or. flag == 'read')`, not `if (use_nvp)`.** `clm_instRest` runs with `flag` = `define`, `write`, and `read`. Guarding on `use_nvp` alone defeats the spec §7 reverse probe; removing the guard entirely is worse, because then a `use_nvp=.false.` run writes `DZ_NVP`/`FRAC_NVP`/`JBOT_SNO` into its own restart file, and a later `use_nvp=.false.` read of that file trips the "written with use_nvp on" guard against a file written with it off. Define and write only under `use_nvp`; probe always.

- [x] **Step 2a — minimal `InitSnowLayers` guard (Step 0 decision).** `NVPLayerInit` sets `dz(c,0) = dz_nvp`, and `InitSnowLayers` then overwrites `dz(c,-nlevsno+1:0) = spval` (`SnowHydrologyMod.F90:3046`). Since `spval = 1.e36 > 0`, `col%nvp_is_present(c)` would return `.true.` on every NVP column off a garbage thickness — a silently wrong state, not an obviously broken one. Add the narrowest possible guard so that assignment (and the companions on `z`/`zi`) skips index 0 where `col%nvp_layer_exists(c)`. **Nothing else in `SnowHydrologyMod` changes here** — the full reindex is Task 5, which supersedes this guard.

- [x] **Step 3: Verify.** Build check and unit tests (baseline 59/59). Expected: compiles; `use_nvp=F` runs enter no new code except the read-only restart probe, and `col%jbot_sno` stays 0 everywhere, so every Task 2 predicate is `.false.` and behavior is bit-for-bit stock.
- [x] **Step 4: Commit** `git commit -am "Add NVPLayerDynamicsMod: static NVP layer init, restart, cold start"` → review/approval gate. Add MERGE_NOTES rows (static init vs their UpdateNVPLayer; restart guards).

---

### Task 4: NVP state/flux/diagnostic variables + history fields

**Files:**
- Modify: `src/biogeophys/TemperatureType.F90` (`t_nvp_col` + restart `T_NVP` + history `T_NVP`), `src/biogeophys/WaterStateType.F90` (`h2onvp_col` + restart/history `H2ONVP`), `src/biogeophys/WaterDiagnosticBulkType.F90` (`fwet_nvp_col` + restart/history `FWET_NVP`; `vwc_nvp_col` + history `VWC_NVP`), `src/biogeophys/WaterDiagnosticType.F90` (`qg_nvp_col` — generic, alongside `qg_col`), `src/biogeophys/WaterFluxBulkType.F90` (`qflx_ev_nvp_patch/_col/_eff_col`, `qflx_nvp_infl_col`, `qflx_nvp_drain_col` + their history fields, all `inactive`), **`src/biogeophys/WaterFluxType.F90` (`qflx_nvp_to_snow_col` — the GENERIC type, not bulk)**, `src/biogeophys/EnergyFluxType.F90` (`eflx_sh_nvp_patch` + history `EFLX_SH_NVP`), `src/biogeophys/SolarAbsorbedType.F90` (`sabg_nvp_patch`)

**Interfaces:**
- Consumes: `use_nvp`.
- Produces: the variables above. History/restart registration guarded `if (use_nvp)` — that guard is sufficient on its own, because Task 3's `JBOT_SNO` probe already `endrun`s when `use_nvp=T` meets a file lacking the NVP variables, so `T_NVP`/`H2ONVP`/`FWET_NVP` can never be read from a file without them. Do not add redundant probes.
- **Placement is load-bearing, verified against the code (Step 0):**
  - `qflx_nvp_to_snow_col` → **generic `WaterFluxType`**. `BalanceCheck` takes `class(waterflux_type), intent(in)` (`BalanceCheckMod.F90:445`), and `qflx_snow_drain_col` — its sibling in the same `snow_sources` sum — lives in the generic type. In the bulk type it is invisible to the generic check, forcing Task 14 into the `select type` downcast spec §5 forbids.
  - `qflx_ev_nvp_*` → **bulk**, alongside `qflx_ev_snow`/`_soil`/`_h2osfc`.
  - `qflx_nvp_infl_col`, `qflx_nvp_drain_col` → **bulk**; both Task 13 consumers (`Infiltration`, `SetQflxInputs`) take concrete `type(waterfluxbulk_type)`.
  - `qg_nvp_col` → **generic `WaterDiagnosticType`**, alongside `qg_col`.
- **Zero-init, expressed as the CTSM idiom.** New flux variables initialize to `0._r8`, not `nan` — but write it as `AllocateVar1d(..., ival = 0.0_r8)` where that helper is used, which is exactly how CTSM already initializes conditionally-set fluxes (`qflx_solidevap_from_top_layer_patch`/`_col`, `WaterFluxType.F90:185,208`). This is the house convention for fluxes not written every timestep on every element, not a departure from it.

  **Zeroing must also happen in `InitCold`, or the zero-init is decorative.** The sequence is `InitAllocate → InitHistory → InitCold`, and `InitHistory` fills each registered variable with `spval`. `qflx_snow_drain_col` shows the required three-part pattern: `spval` in `InitHistory` (`WaterFluxType.F90:646`), `0._r8` in `InitCold` (`:910`), `0._r8` again on `.not. readvar` (`:976`). Consumers sum these over every column or patch, not only NVP ones, so a surviving `spval` puts `1.e36` into the first `snow_sources` sum. (An earlier draft of this bullet claimed zero-init was needed to keep the `use_nvp=.false.`-with-tracers configuration consistent. That was wrong: `CompareBulkToTracer` treats nan-vs-nan as equal and short-circuits `0 == 0`, so tracers were never the reason.)

- [x] **Step 0: Plan review — DONE.** Two resolutions, folded into Files and Interfaces above. (1) `qflx_nvp_to_snow_col` moves from the bulk type to the generic `WaterFluxType`, because `BalanceCheck` takes `class(waterflux_type)` — leaving it in bulk would force Task 14 into the `select type` downcast spec §5 forbids. The other placements were checked against the code and are correct as written. (2) Zero-init is kept, and the earlier characterization of it as a departure from CTSM convention was wrong: `AllocateVar1d` accepts `ival`, and CTSM already passes `ival = 0.0_r8` for conditionally-set fluxes, which is exactly what these are. It also keeps the legal `use_nvp=.false.` + tracers-on configuration consistent, since `AllocateVar1d` enrolls every variable in the water-tracer container.

- [x] **Step 1:** For each file, read their diff (`git diff ctsm5.4.028..HEAD -- <file>` in the worktree) and port the member/alloc/history/restart additions with the placement and init rules above. Skip anything referencing FATES or `UpdateNVPLayer`.
- [x] **Step 2: Run build check.**
- [x] **Step 3: Commit** `git commit -am "Add NVP state, flux, and diagnostic variables with history/restart"` → review/approval gate.

---

### Task 5: Snow layer lifecycle reindex (SnowHydrologyMod part 1)

Split into 5a-5c at Step 0 (originally 5a-5d; that 5d was merged into 5c once 5b's review showed every routine it covered writes a snow slot and so cannot stay stock past the last stopgap). A **new** 5d was added afterwards, at the user's request, for pFUnit coverage of the 5c reindex — it is test code, not a fifth slice of the reindex: the original single task was ~1,392 lines across eight
routines, and unlike every task before it, it **rewrites live arithmetic** rather than
adding guarded code. `CombineSnowLayers` (424 lines) and `DivideSnowLayers` (385) are
each larger than all of Task 4. Each sub-task below builds, tests, and commits on its
own, and gets its own two-stage review.

**Shared interfaces (all sub-tasks):**
- Consumes: `col%get_jtop_snow(c)`, `col%get_jbot_snow(c)`, `col%nvp_is_present(c)`, `col%nvp_is_empty(c)` (Task 2). `snl` keeps stock semantics — −(number of snow layers) — on every column.
- Produces: snow occupies `col%get_jtop_snow(c) : col%get_jbot_snow(c)` on all columns; geometry recursions anchored at `zi(c, col%get_jbot_snow(c))`; max snow layers `nlevsno-1` where the NVP slot exists.
- Apply the spec §2 idiom table. Every transformation must reduce to the stock expression when `jbot_sno == 0`, which is the whole bit-for-bit argument.

**Verification for sub-tasks 5a-5c**, in addition to the standard build check and unit tests: the **`clm_short`** suite against the `ctsm5.4.028` baseline, and for 5c the full **aux_clm** suite. Task 5d is test code and needs neither. This is the first task that can break bit-for-bit, and neither the build nor the unit tests can detect an answer change — aux_clm at Task 4 was the first thing that ever tested it.

> **The user runs the test suites. Never run `run_sys_tests`, `clm_short`, or `aux_clm` yourself, and never launch a suite in the background.** Finish the build check and unit tests, then **STOP** and hand the sub-task to the user for the suite run. Report the results only after the user provides them; do not predict, assume, or characterize a suite outcome that has not been reported.

---

#### Task 5a: Snow pack creation and cold-start placement

**Files:** `src/biogeophys/SnowHydrologyMod.F90` — `InitSnowLayers`, `Bulk_InitializeSnowPack`, `UpdateState_InitializeSnowPack`

- [x] **Step 0: Plan review — DONE.** Resolutions folded into the steps below. Facts established against the code, so the implementer does not have to rediscover them:
  - **`InitSnowLayers`' geometry loop is inside the column loop** (`do j = 0, snl(c)+1, -1`), so unlike `CombineSnowLayers` in 5b it **can** take a per-column bound: `do j = jbot, snl(c)+1+jbot, -1`. The two routines need opposite treatments; do not generalize one to the other.
  - The `zi(c,0) = 0._r8` in the too-little-snow branch **stays**. The slice above it stops at `jbot-1`, correctly leaving `zi(-1)` as the moss top (which must not be zeroed) and `zi(0)` as the soil-surface datum.
  - Neither `InitializeSnowPack` routine takes `col` as a dummy argument, so the module `col` is in scope and the type-bound queries are unproblematic here.
  - Capping at `nlevsno-1` gives a deep-snow NVP column a **thicker bottom layer** than stock, since the same depth spreads over one fewer layer. Inherent to reserving the slot (spec §1.1) — expected, not a defect.

- [x] **Step 0a: Move the Task 3 stopgap, do not just delete it (user decision).** Task 3 added an `endrun` in `InitSnowLayers` on `jbot < 0 .and. snow_depth(c) >= dzmin(1)`. That exists only because placement was not yet reindexed — **delete it**. **Keep** the `jbot = col%get_jbot_snow(c)` line and the `jbot`-bounded `spval` and zeroing slices Task 3 also added: those are not a stopgap, they are the start of this reindex and Step 1 extends them. Deleting them would put `spval` back into the moss slot. But after this sub-task `CombineSnowLayers` and `DivideSnowLayers` still assume snow ends at slot 0, so `use_nvp=.true.` would stop refusing to run and instead run wrong at the first combine or divide. Add an entry `endrun` to **both** routines firing on `col%nvp_layer_exists(c) .and. col%snl(c) < 0`, each removed by the sub-task that reindexes it (5b, 5c). No test sets `use_nvp=.true.`, so `clm_short` and `aux_clm` are unaffected.

- [x] **Step 1 — `InitSnowLayers` (stock :2955-3145; [fix], their branch left it unmodified).** Every snow slot index gains `jbot`, which is 0 off NVP columns so each expression is the stock expression there:
  - single-layer case: `dz(c,0) = snow_depth(c)` → `dz(c,jbot)`
  - the all-but-bottom-two loop: `dz(c,j+snl(c)) = dzmax_u(j)` → `dz(c,j+snl(c)+jbot)`
  - the hardcoded bottom pair: `dz(c,-1)`/`dz(c,0)` → `dz(c,jbot-1)`/`dz(c,jbot)`
  - layer-count search: cap at `nlevsno - merge(1, 0, col%nvp_layer_exists(c))` instead of `nlevsno`
  - geometry loop: `do j = 0, snl(c)+1, -1` → `do j = jbot, snl(c)+1+jbot, -1`, anchored at `zi(c,jbot)`, which `NVPLayerInit` already set to `-dz_nvp` — **do not reset it here**

  The lake short-circuit and no-snow branches zero only slots `<= jbot`, never slot 0 on an NVP column, because that is moss geometry.

- [x] **Step 2 — `Bulk_InitializeSnowPack` / `UpdateState_InitializeSnowPack` (stock :955-1012, :919-952; theirs :944-1029, [harvest, adapt]).** First layer is created at index `jbot` with `snl = -1` (honest `snl`, not their `-2`); `zi(c,jbot-1) = zi(c,jbot) - dz(c,jbot)`; the `t_soisno` / `h2osoi_*` / `frac_iceold` writes land at `(c,jbot)`. In `UpdateState_InitializeSnowPack` that is the pair `h2osoi_ice(c,0) = h2osno_no_layers(c)` and `h2osoi_liq(c,0) = 0._r8` (:947-948) — both move to `(c,jbot)`. Its `h2osoi_*` dummies are declared `(bounds%begc:, -nlevsno+1:)`, so index `jbot = -1` is in bounds.

- [ ] **Step 3: Verify.** Build check and unit tests (baseline 59/59). Then **STOP**: the user runs `clm_short` against the `ctsm5.4.028` baseline and reports the result. Do not run it.
- [ ] **Step 4: Commit** `git commit -am "Reindex snow pack creation and cold-start placement for the NVP slot"` → review/approval gate.

---

#### Task 5b: `CombineSnowLayers`

**Files:** `src/biogeophys/SnowHydrologyMod.F90` — `CombineSnowLayers` (stock :2083-2507; theirs :2171-2634, [harvest+fix])

- [x] **Step 0: Plan review — DONE.** Established against the code; no blocking questions. (a) **There are TWO `j`-outer, column-inner loops in this routine**, not one: the whole-pack accumulation at `:2326` (`do j = -nlevsno+1,0` / `do fc` / `if (j >= snl(c)+1)`) as well as the geometry recursion in Step 5. Neither can take a per-column bound — change the **guard** in both, to `j >= col%get_jtop_snow(c) .and. j <= col%get_jbot_snow(c)`. Step 4 below is worded as a bound change; it is a guard change. (b) **`[fix] (c)` requires no new code**: the aerosol merge already sits inside `if (j < 0)` alongside the `dz` merge, so changing that one guard to `j < jbot` excludes slot 0 structurally — there is no separate disposal path to write. (c) **`[fix] (b)` is provably correct, not a judgement call**: `qflx_sl_top_soil_col` has exactly one consumer in the whole tree, `snow_sinks` in `BalanceCheckMod:770,779,792`. It is bookkeeping for *snow lost this water at the bottom*, not a routing statement, so it must be booked whether the receiver is moss or soil — `h2osno_total` excludes the moss slot either way. (d) the receiver index is `j+1` in every case except `nvp_is_empty(c) .and. j == jbot`, where it must be soil layer 1: `j+1` would be the zero-thickness slot 0. Original notes: this is the `[fix]`-heaviest routine in the plan — four separate corrections to their branch — and the one where their single-layer combination bug lived; (b) **this sub-task removes the entry `endrun` that 5a placed here** (`col%nvp_layer_exists(c) .and. col%snl(c) < 0`). It exists only while this routine still assumes snow ends at slot 0.

- [ ] **Step 1 — loop bounds and the landunit guard.** The vanishing-thin-layer loop becomes `do j = msn_old(c)+1+jbot, jbot` (equivalently `col%get_jtop_snow(c), col%get_jbot_snow(c)`, since `msn_old(c) = snl(c)`). The landunit guard `if (j < 0 .or. (ltype(l) == istsoil .or. urbpoi(l) .or. ltype(l) == istcrop))` becomes `j < jbot`: it means "not the bottom layer, or the landunit has something beneath to receive the water".

- [ ] **Step 2 — the hand-off receiver, and the two `[fix]`es.** The stock receiver is `j+1`, which at `j == jbot` lands on soil layer 1 when `jbot == 0` and on the **moss slot** when `jbot == -1`. That is correct where `col%nvp_is_present(c)`. **[fix] (a):** where `col%nvp_is_empty(c)`, the water must pass through to soil layer 1 rather than into a zero-thickness layer — the spec §2 skip invariant. **[fix] (b):** `qflx_sl_top_soil_col` must be booked for the `j == jbot` dissolution in **all** cases; their branch never sets it under NVP, leaving a systematic `errh2osno` residual (audit §1b). It is zeroed at the top of the routine, so the booking is a pure addition.

- [ ] **Step 3 — aerosols and the dz-merge guard. [fix] (c):** do not merge aerosol masses into slot 0; drop them, matching the disposal the whole-pack path already uses (spec §4d — their guard covers `dz` only, so aerosol mass strands in the moss slot). The dz-merge guard becomes `if (j < jbot)` and the bottom-neighbour test `else if (i == jbot)`.

- [ ] **Step 4 — whole-pack disappearance.** The accumulation at `:2326` is `j`-outer and column-inner, so **change its guard**, not its bounds: `if (j >= col%get_jtop_snow(c) .and. j <= col%get_jbot_snow(c))`. That covers `zwice`/`zwliq`, `snow_depth`, and the inline `h2osno_total` sum together. Liquid goes to moss where `col%nvp_is_present(c)`, else to the stock target `h2osoi_liq(c,1)` for soil/crop/urban.

- [ ] **Step 5 — geometry recursion.** **The loop bounds do not change.** The recursion is `j`-outer and column-inner:
```fortran
do j = 0, -nlevsno+1, -1
   do fc = 1, num_snowc
      c = filter_snowc(fc)
      if (j >= snl(c) + 1) then
```
so it cannot take a per-column bound, and with the `nlevsno-1` cap an NVP column's snow occupies `-nlevsno+1 .. -1`, already inside the existing range. Change only the **guard**, to `j >= col%get_jtop_snow(c) .and. j <= col%get_jbot_snow(c)`. The `zi(c,jbot)` anchor is already correct from `NVPLayerInit`. (An earlier draft of this plan proposed `do j = jbot, -nlevsno+1+jbot, -1`; that is unimplementable here.)

- [ ] **Step 6 — do NOT port their `snl` fixups.** The stock entry guard `snl(c) < -1` and the `EXIT` at `snl(c) >= -1` are **already correct** under honest `snl`: `snl == -1` is a legal one-layer state. Their `snl == -1 → 0` fixups exist only to patch their `snl = −(N_snow+1)` convention and would be a bug here (spec §1.2).

- [ ] **Step 7: Verify.** Build check and unit tests. Then **STOP**: the user runs `clm_short` and reports the result. Do not run it.
- [ ] **Step 8: Commit** `git commit -am "Reindex CombineSnowLayers for the NVP slot"` → review/approval gate.

---

#### Task 5c: `DivideSnowLayers` and the rest of the snow lifecycle

Absorbs what was originally Task 5d, the sweep-routine group (the Task 5d that now follows is a later, unrelated addition: pFUnit coverage). **Every routine in this sub-task's scope writes a snow slot and so must be reindexed together**: `ZeroEmptySnowLayers` zeroes `dz(c,0)`/`z(c,0)`/`zi(c,-1)` whenever `snl(c) == 0`, `SnowCompaction` writes `dz(c,j)` at `SnowHydrologyMod:2076`, and `PostPercolation_AdjustLayerThicknesses` at `:1760` — all looping `-nlevsno+1, 0`. Left stock, they would not merely mis-account the moss layer, they would change its thickness or erase it.

**Files:** `src/biogeophys/SnowHydrologyMod.F90` — `DivideSnowLayers`, `ZeroEmptySnowLayers`, `SnowCompaction`, `PostPercolation_AdjustLayerThicknesses`, the `swe_old` fill; `src/biogeophys/WaterStateType.F90` — `CalculateTotalH2osno`, `CheckSnowConsistency`; `src/biogeophys/TotalWaterAndHeatMod.F90` — two loop lower bounds; `src/biogeochem/ch4Mod.F90` — comment only.

- [x] **Step 0: Plan review — DONE.** Resolutions folded into the steps below. Facts established against the code, so the implementer does not have to rediscover them:
  - **`j`-outer vs `j`-inner, settled for every loop in scope.** `j`-outer/column-inner, so they take **guard** changes and their bounds stay literal: `DivideSnowLayers`' un-staging (`:2874`) and geometry recursion (`:2948`), `SnowCompaction` (`:1969`), `PostPercolation` (`:1756`), `ZeroEmptySnowLayers` (`:2997`). `j`-inner inside a `do fc`, so they take real **bound** changes: both `swe_old` loops (`:500`, `:503`), `CalculateTotalH2osno` (`WaterStateType:913`), `CheckSnowConsistency` (`:958`), and the two `TotalWaterAndHeatMod` loops in Step 6.
  - **`ZeroEmptySnowLayers` carries the complement guard**, `j <= snl(c) .and. snl(c) > -nlevsno`, not the `j >= snl(c)+1` form the other routines use. It transforms to `j < col%get_jtop_snow(c) .and. col%get_jtop_snow(c) > -nlevsno+1`. (Both halves reduce to stock at `jbot == 0`. The second half is dead code in stock too — at a full pack the first half is already false — but preserve it rather than change behaviour gratuitously.)
  - **`use_nvp=.true.` will produce wrong answers until Task 14 (user decision).** Removing the stopgap at Step 7 does not make the configuration correct: Task 6 still owns stock `-nlevsno+1, 0` loops in `SnowWater`, the three percolation routines (`:1351`, `:1440`, `:1495`), `CalcAndApplyAerosolFluxes` (`:1591`) and `SnowCapping`; Tasks 7-12 own the thermal and radiation loops; Task 15 owns the `SNO_*` history fill. The user weighed a relocated tripwire (preserves only snow-free runs — too few tests are snow-free to be worth it) and a namelist-level refusal (blocks everything) and chose to accept wrong answers instead. What Step 6 buys is that the run does not *abort*: without it `errh2o` exceeds `error_thresh = 1.e-5` mm on the first snowy timestep and `BalanceCheckMod` calls `endrun`, which would have been option 1b with a worse diagnostic. Do not describe `use_nvp=.true.` as correct anywhere in code comments or MERGE_NOTES.

- [x] **Step 1 — `DivideSnowLayers` (stock :2510-2895; theirs :2637-3068, [harvest, adapt]).** Staging map `dzsno(c,k) = frac_sno * dz(c, k + snl(c) + jbot)` — the stock map shifted by `jbot`; `msno = abs(snl(c))`, honest, with no `-1` adjustment. Subdivision cap `k < nlevsno - merge(1, 0, col%nvp_layer_exists(c))` (theirs :2815, keep): this is what enforces the `nlevsno-1` invariant. **Corrected by Task 5d's mutation testing:** the invariant is load-bearing for bounds safety, but *not* within this routine's own call — its loops carry literal `-nlevsno+1, 0` bounds, so removing the cap silently drops the top staging slot instead of writing out of range. The out-of-bounds access appears (a) immediately in `InitSnowLayers`, whose geometry loop takes *per-column* bounds and so reads `dz(c,-nlevsno)` and writes `zi(c,-nlevsno-1)`, and (b) on the **next** `DivideSnowLayers` call, whose staging read `dz(c, j+snl(c)+jbot)` goes below `dz`'s lower bound once `snl == -nlevsno` has been recorded. Earlier plan text said the write happened here, in this call; that was wrong. `snl = -msno`, stock.
  **The un-staging loop (`:2874`) needs work; the shifted staging map alone does not spare it.** It is `j`-outer over `-nlevsno+1, 0` guarded `j >= snl(c)+1`, so it would still write slot 0. Change the **guard** to `j >= col%get_jtop_snow(c) .and. j <= col%get_jbot_snow(c)` and add `- jbot` to the inverse map (`dzsno(c, j-snl(c)-jbot)` and likewise for `swice`/`swliq`/`tsno`/the eight aerosol arrays/`rds`). Index range stays `1 .. msno`, within `dzsno`'s `nlevsno` extent.
  **The geometry recursion (`:2948`) is `j`-outer**, like `CombineSnowLayers`': change the guard to the same `jtop`/`jbot` pair, not the bounds. The `zi(c,jbot)` anchor is already correct from `NVPLayerInit`.
  **The two `is_lake` blocks (`:2661` and the post-un-staging consistency check) stay stock (user decision).** NVP columns are istsoil/istcrop only, so `nvp_layer_exists` is false on every lake column and `jbot` is 0 there. Add one comment saying exactly that; do not transform them.

- [x] **Step 2 — the guard sweep.** In `SnowCompaction` (`:1969`), `ZeroEmptySnowLayers` (`:2997`) and `PostPercolation_AdjustLayerThicknesses` (`:1756`): all three are `j`-outer, so the literal `-nlevsno+1, 0` bounds stay and only the guards change — `j >= snl(c)+1` becomes `j >= col%get_jtop_snow(c) .and. j <= col%get_jbot_snow(c)`, and `ZeroEmptySnowLayers` takes the complement form given in Step 0. Their `cycle`-at-`j==0` guards are then unnecessary — the guards already exclude slot 0 on an NVP column. Structural exclusion beats per-site opt-out: a missed site then fails loudly with a wrong range rather than silently treating moss as snow (spec §1.2).
  **`SnowCompaction` also carries a whole-pack slice at `:2032`** — `wsum = sum(h2osoi_liq(c,snl(c)+1:0)+h2osoi_ice(c,snl(c)+1:0))`, feeding `FracSnowDuringMelt` and thence `ddz3`. It is not a loop and the guard change does not reach it. Reindex it to `col%get_jtop_snow(c):col%get_jbot_snow(c)` on both terms.
  **`ZeroEmptySnowLayers` is the one routine here that takes `col` as a dummy argument** (`:2964`), which is why Task 2 made the queries type-bound — `col%get_jbot_snow(c)` binds to the dummy, and a module-level function reading the global `col` would not be conforming (F2018 15.5.2.13). Its guard fires at `j = 0` when `snl(c) == 0`; that is the geometry destroyer, and it is reachable because `filter_snowc` is built at `HydrologyNoDrainageMod:279`, before combining, so a column whose last layer just vanished still enters at `:404` with `snl == 0`.
  **Added after review:** two `snl(c)+1`-as-top-layer writes in the same file were reindexed to `col%get_jtop_snow(c)` — `dz(c,snl(c)+1)` in `BulkDiag_NewSnowDiagnostics` (the routine holding this task's `swe_old` fill, so in scope) and `h2osoi_ice(c,snl(c)+1)` in `UpdateState_AddNewSnow` (its partner one call later, and the site that would otherwise have made Step 7's "runs to completion" false: new snowfall booked into the moss slot gives `errh2osno = -qflx_snow_grnd*dtime` and aborts). Neither was owned by any task's file list — see "Snow-index sites found by sweep, not by audit" in MERGE_NOTES for the rest of that category, now folded into Tasks 6-10.

- [x] **Step 3 — `swe_old` ([fix]).** Their branch left this bare loop including the moss slot while `AerosolMod` excludes it — an inconsistency feeding SNICAR/aerosol scaling (spec §5). **There are two loops, not one**, both `j`-inner so both take real bounds: `:500` zeroes above the pack (`-nlevsno+1, snl(c)` → `-nlevsno+1, col%get_jtop_snow(c)-1`) and `:503` fills the pack (`snl(c)+1, 0` → `col%get_jtop_snow(c), col%get_jbot_snow(c)`).
  **`swe_old(c,0)` is then never written on an NVP column and stays at its allocation-time `nan` (user decision).** Do not add a defensive zero. `swe_old_col` has no history or restart field and its only reader is `SnowCompaction` inside the reindexed guard, so nothing consumes it; if something downstream ever trips over it, that is the signal to write code that handles the situation rather than to mask it now.

- [x] **Step 4 — pull two loop bounds forward from Task 14.** `CalculateTotalH2osno` (`WaterStateType.F90:913`) still runs `do j = col%snl(c)+1, 0`, which on an NVP column with `snl = -3` sums `-2..0`: it includes the moss slot **and misses a real snow layer**. `CheckSnowConsistency` (`:958`) scans `-nlevsno+1 : snl(c)`, which likewise covers real snow layers and would abort debug builds — including on a *snow-free* NVP column, where it reaches slot 0 and finds cold-start moss water that is neither `0` nor `spval`. Reindex both to the `get_jtop_snow`/`get_jbot_snow` range. Without this, `errh2osno` cannot close once the stopgap is gone — 5b books `qflx_sl_top_soil` correctly, but the other side of the balance would be wrong — and the armed `endrun` in `BalanceCheckMod` would abort every `use_nvp=.true.` run, including the golden zero-thickness case. Task 14 keeps the rest of its scope.

- [x] **Step 5 — the ch4Mod comments (spec §2). CORRECTED after review.** This step originally listed four `j == 0` sites (`:3653`, `:3749`, `:3815`, `:3940`) as all being the atmosphere pseudo-layer. **That list was wrong**: it came from a raw grep without checking each site's enclosing loop, and `:3815` is the terminating iteration of a *genuine* snow loop — `do j = -nlevsno+1,0` with a `j >= snl(c)+1` guard, which divides by `dz(c,j)`. The implementer faithfully turned the wrong list into a comment asserting the §2 transformation "must not be applied anywhere in this file", directly above the loop where it must be applied. Two comments now: one scoping the exemption to the `j = 0,nlevsoi` loops only, and one at the snow-resistance loop recording that it is a real snow loop still owed the transformation. The loop itself is left stock, logged in MERGE_NOTES under "Snow-index sites found by sweep, not by audit", and assigned to Task 6.

- [x] **Step 6 — pull two more loop bounds forward from Task 14, so the run does not abort.** `ComputeLiqIceMassNonLake` (`TotalWaterAndHeatMod.F90:282`) and `ComputeHeatNonLake` (`:691`) run `do j = snl(c)+1,0`, the column water and heat totals behind `errh2o` and `errsoi`. On an NVP column that sums the moss slot **and drops the top snow layer** — the same defect as `CalculateTotalH2osno`, and it bites even in the golden zero-thickness case, because `jbot_sno` is static and does not depend on `dz(c,0)`. Change the **lower** bound only, `snl(c)+1` → `col%get_jtop_snow(c)`; leave the upper bound at `0` so the moss slot lands inside the column total and 5b's snow-to-moss routing stays an internal transfer (`qflx_sl_top_soil` is *not* a term in the `errh2o` expression at `BalanceCheckMod:592-605` — it is snow-sink bookkeeping only). Both reduce to stock at `jbot == 0`, and in the golden case they sum the same values in the same order plus a trailing zero, so bit-for-bit holds.
  The lake counterparts (`:485`, `:1015`) stay stock — NVP columns are never lake. Task 14 Step 1 supersedes this with the fuller restructuring (`jtop..jbot` plus explicit moss water, ice and **solid** heat terms); this is the minimal intermediate that keeps the balance checks from firing spuriously. The moss solid-heat term omitted here is harmless for now only because nothing updates `t_soisno(c,0)` before Task 7.

- [x] **Step 7 — remove the last stopgap.** Delete the entry `endrun` 5a placed in `DivideSnowLayers`, and the `use_nvp` import at `SnowHydrologyMod:26` that exists solely for it. After this `use_nvp=.true.` runs to completion instead of aborting — it is **not** correct until Task 14, per Step 0.

- [ ] **Step 8: Verify.** Build check and unit tests (baseline 59/59; the `SnowHydrology` binary must report 17 tests, two of which cover the NVP path). Then **STOP**: the user runs `clm_short` **and the full `aux_clm` suite** — Task 5 as a whole is the first rewrite of live snow arithmetic, so it gets the same gate that validated Task 4 — and reports the results. Do not run either. No suite test sets `use_nvp=.true.`, so these gate the `use_nvp=.false.` bit-for-bit requirement only.
- [ ] **Step 9: Commit** `git commit -am "Reindex the remaining snow lifecycle for the NVP slot"` → review/approval gate. MERGE_NOTES rows across 5a-5c for every divergence from their guards, especially the honest-`snl` sites.

---

#### Task 5d: pFUnit coverage for the Task 5c reindex

Tests only, plus **one** line of model code the user has explicitly approved (see Step 1) — so
this sub-task cannot change answers and does not need a suite run. It exists because
`DivideSnowLayers` is the second-largest rewrite in the plan and had **zero** coverage, and
because Tasks 6-15 will keep editing every routine 5c touched.

**Files:** `src/biogeophys/SnowHydrologyMod.F90` (one `public ::` line); new
`src/biogeophys/test/SnowHydrology_test/test_SnowHydrology_{divideSnowLayers,zeroEmptySnowLayers,postPercolation}.pf`
plus their three lines in that directory's `CMakeLists.txt`; new
`src/biogeophys/test/WaterState_test/` (test file + `CMakeLists.txt` + one
`add_subdirectory` line in `src/biogeophys/test/CMakeLists.txt`); and additions to the
existing `src/biogeophys/test/TotalWaterAndHeat_test/test_total_water_and_heat.pf`.

**What the harness already gives you — do not rebuild any of it:**
- `col%jbot_sno` is a plain array; assign it directly in the `.pf` after the subgrid setup, exactly as `test_initSnowLayers_depth1_nvp` does. **Task 16 Step 1's premise that `unittestSubgridMod` needs parameterizing is wrong** — no unit-test infrastructure change is required, and Task 16 should be corrected when it is reached.
- `unittestWaterTypeFactory` (`src/unit_test_shr/`) builds a real `water_type`: `init` → `setup_before_subgrid(my_nlevsoi, nlevgrnd_additional, my_nlevsno)` → subgrid setup → `setup_after_subgrid(snl=, dz=)` → `create_water_type(water_inst, ...)` → `teardown`. Worked examples: `test_irrigation.pf:371`, `test_water_type.pf:53`.
- `temperature_type` and `aerosol_type` have **no** factory, and do not need one: hand-allocate only the components the routine under test touches, following `src/dyn_subgrid/test/dynConsBiogeophys_test/test_dyn_cons_biogeophys.pf:178-190`, and deallocate in `tearDown`. `ZeroEmptySnowLayers` needs only `temperature_inst%t_soisno_col`; `DivideSnowLayers` needs that plus the eight `aerosol_inst%mss_*_col` arrays and `snw_rds_col` / `frac_sno_eff_col`.
- `unittestFilterBuilderMod::filter_from_range` builds `num_snowc` / `filter_snowc`.
- **Ordering trap:** the water factory's `setup_before_subgrid` sets `nlevsno` itself, so a test using the factory must not also assign `nlevsno` directly the way the current `SnowHydrology` tests do. `SnowHydrologySetControlForTesting()` is still required for anything reading `dzmin`/`dzmax_u`/`dzmax_l`, and `SnowHydrologyClean()` in `tearDown`.
- The pFUnit preprocessor cannot parse a trailing comment on an `@assert` line. Put the comment on its own line above.

- [x] **Step 0: Plan review — DONE.** Both open items closed, and two setup traps established empirically so the implementer does not lose a cycle to each:
  - **(a) The type reachability holds.** `waterstatebulk_type` extends `waterstate_type` (`WaterStateBulkType.F90:26`) and `waterdiagnosticbulk_type` extends `waterdiagnostic_type` (`WaterDiagnosticBulkType.F90:37`), and both are `public` pointer members of `water_type` (`WaterType.F90:142-143`). So `water_inst%waterstatebulk_inst%CalculateTotalH2osno(...)` binds, and `waterdiagnosticbulk_inst` satisfies the `class(waterdiagnostic_type)` dummy.
  - **(b) `ComputeHeatNonLake` stays out** — the user scoped this task to the five assessed candidates, and it was not among them.
  - **The unit-test build does NOT define `NDEBUG`.** `run_tests.py:219-231` passes `CMAKE_BUILD_TYPE=CESM_DEBUG`, and the generated `flags.make` carries `-O0 -g -check uninit -check bounds -check pointers -fpe0` with no `-DNDEBUG`. So `CheckSnowConsistency` **does** run from inside `CalculateTotalH2osno` in unit tests, and Step 2's third case really is a `CheckSnowConsistency` test. Assert it rather than merely relying on the absence of an abort.
  - **`-fpe0` traps floating-point exceptions, so zero denominators abort the test binary rather than producing `nan`.** `DivideSnowLayers`' un-staging divides by `frac_sno(c)` when `.not. is_lake`, so `waterdiagnosticbulk_inst%frac_sno_eff_col` must be set **nonzero** in every Step 4 test. This is the most likely first failure and it will look like a crash, not an assertion.
  - **`-check bounds` is on**, which changes what mutation-testing the cap looks like: reverting the `nlevsno-1` cap in Step 7 will likely abort with a bounds error rather than fail an assertion. That still counts as the test catching it — record which form each reversion produced.
  - **Factory ordering, from the one worked example** (`test_irrigation.pf:237-259, 370-371`): `water_factory%init()` → `water_factory%setup_before_subgrid(...)` → `setup_single_veg_patch(...)` → `water_factory%setup_after_subgrid(snl=, dz=)` → `water_factory%create_water_type(water_inst)`, with `water_factory%teardown(water_inst)` in `tearDown`. Set `col%jbot_sno` after the subgrid setup and before calling the routine under test.

- [x] **Step 1 — the one model-code line ([user-approved]).** `PostPercolation_AdjustLayerThicknesses` is private and takes nothing but plain arrays, which makes it the cheapest routine in Task 5c to test and the only one blocked from being tested at all. Add it to the existing block in `SnowHydrologyMod.F90` headed `! The following are public just for the sake of unit testing:`, alongside `SnowCappingExcess` and `SnowHydrologySetControlForTesting`. **This is the entire model-code footprint of Task 5d** — the user approved it explicitly; it is not scope creep, and it has no runtime effect.

- [x] **Step 2 — `CalculateTotalH2osno` (new `WaterState_test` directory).** Cases, each with the moss slot and the true top snow layer holding *distinctive* values so an off-by-one cannot pass:
  - `jbot_sno = 0`, `snl = -3`: total is `h2osno_no_layers` plus slots `-2..0`. Locks stock.
  - `jbot_sno = -1`, `snl = -3`: total must **include** slot `-3` and **exclude** slot 0. This is the assertion the whole reindex exists for.
  - `jbot_sno = -1`, `snl = 0` (snow-free NVP column with cold-start moss water): total is `h2osno_no_layers` alone.
  - **The third case doubles as the `CheckSnowConsistency` test.** `CalculateTotalH2osno` calls it under `#ifndef NDEBUG`, and before Task 5c Step 4 it scanned to slot 0 and would `endrun` on exactly this column. Its *passing* is the evidence — but that only holds if the unit-test build is a debug build. **Verify that, do not assume it**; if `NDEBUG` is defined, say so and drop the claim rather than leaving a comment asserting coverage that does not exist.

- [x] **Step 3 — `ZeroEmptySnowLayers` (new `.pf`).** The routine 5c's Step 0 called the geometry destroyer:
  - `snl == 0`, `jbot == -1`, moss geometry and water set: `dz(c,0)`, `z(c,0)`, `zi(c,-1)`, `h2osoi_liq/ice(c,0)` and `t_soisno(c,0)` must all **survive**, while `-nlevsno+1 .. -1` are zeroed.
  - `snl == 0`, `jbot == 0`: everything `-nlevsno+1 .. 0` zeroed. Locks stock.
  - `snl = -2`, `jbot = -1`: slots above the pack zeroed; snow slots and moss untouched.
  - Full pack, `snl = -(nlevsno-1)`, `jbot = -1`: nothing zeroed, and `zi(c,-nlevsno)` specifically untouched.

- [x] **Step 4 — `DivideSnowLayers` (new `.pf`).** Highest-value test in this sub-task:
  - **Round trip, no subdivision:** `snl = -3`, `jbot = -1`, all layers below `dzmax_u`/`dzmax_l`. Every `dz`, `h2osoi_ice/liq`, `t_soisno`, aerosol mass and `snw_rds` must come back **unchanged**, and `snl` must still be `-3`. This is the sharpest test of the staging/un-staging map pair, and it is the cheapest — the plan text for Step 1 of 5c was itself wrong about the un-staging map, so this is the site with a demonstrated authoring hazard.
  - **Subdivision:** `snl = -1`, `jbot = -1`, bottom layer over `dzmax_l(1)`. Assert `snl == -2`, mass conserved (ice and liquid summed over the pack), `dz(c,0)` untouched, `zi(c,-1)` still `-dz_nvp`, and the recursion closing: `zi(c,j) - dz(c,j) == zi(c,j-1)` across the pack.
  - **The cap:** `snl = -(nlevsno-1)`, `jbot = -1`, bottom layer over threshold. `snl` must **not** grow past `-(nlevsno-1)`. This is the bounds-safety invariant — without it the geometry recursion writes below the start of `zi` — so it is the single most important assertion here.
  - A `jbot = 0` mirror of the round-trip and cap cases, locking stock.

- [x] **Step 5 — `PostPercolation_AdjustLayerThicknesses` (new `.pf`).** All-array dummies, so no factory needed at all — build the arrays directly. `snl = -3`, `jbot = -1`: a snow layer whose water exceeds its `dz` grows; **`dz(c,0)` does not change even when the moss slot's water would imply a larger thickness**. Plus a `jbot = 0` mirror.

- [x] **Step 6 — `ComputeLiqIceMassNonLake` (append to `test_total_water_and_heat.pf`).** Orientation, for you and not for the file: that file currently tests only the pure helpers (`LiquidWaterHeat`, `AdjustDeltaHeatForDeltaLiq`), so no `Compute*` routine there has a setup you can copy — expect to write the `water_type` scaffolding from the factory yourself. **Do not put any of that in the test file**; a comment about what the file does not cover is narration, and it goes stale the moment someone adds coverage. `snl = -3`, `jbot = -1`: the total must include **both** the top snow layer at `-3` and the moss slot at 0 (5c deliberately left the upper bound at 0 — see its Step 6). Plus a `jbot = 0` mirror.

- [x] **Step 7 — mutation-test every new assertion.** A test written against code that already works proves nothing until you have seen it fail. For each new test: revert the corresponding Task 5c change in the working tree, confirm **that specific assertion** fails and that the `jbot = 0` cases still pass, then restore. Report which assertion caught which reversion. This is how `test_initSnowLayers_depth1_nvp` was validated in Task 5a, and it is not optional — a test that passes against both the fixed and the broken code is worse than no test, because it reads as coverage.

- [x] **Step 8: Verify.** Build check and unit tests. The `SnowHydrology` binary grows from 17 tests; the new `WaterState` binary appears; total rises above 59. **No suite run is needed** — everything here is test code except one `public ::` declaration, which cannot affect answers. Say so when handing off rather than leaving the user to decide whether to re-run `aux_clm`.
- [x] **Step 9: Commit** `git commit -am "Unit tests for the NVP snow lifecycle reindex"` → review/approval gate. No MERGE_NOTES row is needed for the test files (their branch has no counterpart), but the `public ::` line needs one.

**Findings from the implementation, recorded because they correct earlier text or cost a debugging cycle:**
- **Step 1 was not literally one line.** `PostPercolation_AdjustLayerThicknesses` was already named in the module's `private ::` block, and declaring it `public` while that stood is a duplicate-attribute compile error. Net footprint is +1 `public` / −1 `private`, which is still the whole model-code change.
- **The cap mutation does not abort on bounds**, contrary to this task's Step 0 note and to Task 5c Step 1's earlier wording. Both are corrected in place; see Task 5c Step 1 for where the out-of-bounds access actually lives.
- **`dzmin` / `dzmax_u` / `dzmax_l` are allocated inside `InitSnowLayers`, not by `SnowHydrologySetControlForTesting`**, which only sets the scalar namelist values. Tests needing them call `InitSnowLayers` with zero snow depth as the allocator and free them with `SnowHydrologyClean()` in `tearDown`.
- **Two cap tests could not fail, and Step 7 did not catch it.** `divide_capsAtNlevsno_stock` started from an already-full stock pack, so the `do while` cap gated nothing and `dzmax_l(nlevsno)` is `huge` — `msno` came out 5 for every cap value from `k<1` to `k<6`. The NVP cap test had the mirror-image hole: starting at capacity, it was identical for caps `k<1`..`k<4`, so an over-strict `merge(2,0,...)` was invisible. Both are now **growth** cases, and each was mutation-tested against the mutation it exists to detect (unconditional cap for the stock mirror, `merge(2,0,...)` for the NVP one). The lesson — mutate what the *mirror* is blind to, and prefer growth cases over saturation cases when the property is a limit — is carried into Task 16 Step 0.
- **`PostPercolation_AdjustLayerThicknesses`'s `snl` dummy is dead** after Task 5c — the body reads `col%get_jtop_snow(c)`/`col%get_jbot_snow(c)` and never touches it. Left in place here (out of scope); worth deleting when a later task next edits that routine, together with the now-unused `associate` entries Task 5c's reviews noted.

---

### Task 6: Percolation, drain, capping, aerosols (SnowHydrologyMod part 2 + AerosolMod)

**Files:**
- Modify: `src/biogeophys/SnowHydrologyMod.F90` — `SnowWater`, `BulkFlux_SnowPercolation`, `UpdateState_SnowPercolation`, `TracerFlux_SnowPercolation`, `SumFlux_AddSnowPercolation`, `CalcAndApplyAerosolFluxes`, `SnowCapping` + 5 helpers (stock ~3121-3693)
- Modify: `src/biogeophys/AerosolMod.F90` (`AerosolMasses` guard, theirs :570-580)
- **Folded in from the Task 5c unassigned-sites sweep** — all snow-domain, all still stock, none previously owned by any task. Line numbers are ours at Task 5c:
  - `src/biogeophys/SnowHydrologyMod.F90:1237` — `lev_top(c) = snl(c)+1` in `UpdateState_TopLayerFluxes`, called from `SnowWater` at `:1080`. Top-layer sublimation/condensation lands on the moss slot at `snl == -1`.
  - `src/biogeophys/AerosolMod.F90:621-624` — `h2osno_top`/`mss_*_top` read from `snl(c)+1`, inside `AerosolMasses` but outside the `:570-580` guard this task already cites.
  - `src/biogeophys/AerosolMod.F90:788-796` — the eight `mss_*(c,snl(c)+1)` deposition writes in `AerosolFluxes`, a routine this task did not name at all.
  - `src/biogeophys/HydrologyNoDrainageMod.F90:704` — `h2osno_top(c)` from `snl(c)+1`. **Assigned here by domain, not by file:** Task 10 owns this file, but this is the same SNICAR input as `AerosolMod:621` and belongs with the aerosol work. Task 10's entry cross-references it so the two do not both edit it.
  - `src/biogeophys/WaterDiagnosticBulkType.F90:789-790` — `snw_rds_col(c,snl(c)+1:0)` and `(c,-nlevsno+1:snl(c))` in `InitBulkCold`. **Array slices, not loops** — the sweep found these are the easiest kind of site to miss. Cold-start grain radius written across the moss slot.
  - `src/main/clm_driver.F90:1637-1638` — `frac_iceold(c,j)` over `j >= snl(c)+1` in `clm_drv_init`. **Fix this one first: it is a divide by zero in the golden `dz_nvp = 0` case**, `h2osoi_ice(c,0)/(h2osoi_liq(c,0)+h2osoi_ice(c,0))` with both terms zero, on every timestep the column carries resolved snow.
  - `src/biogeochem/ch4Mod.F90:3793-3841` — the `do j = -nlevsno+1,0` snow-resistance loop in `ch4_tran`, its `j >= snl(c)+1` guard, and its `j == 0` terminating test. **Also a divide by zero in the golden case** (`icefrac = h2osoi_ice(c,j)/denice/dz(c,j)`), reached whenever `use_lch4`, so in every BGC compset. Task 5c left a comment at the loop saying exactly this; delete the "Left stock for now" sentence when you fix it. Do **not** touch the `j = 0,nlevsoi` loops in the same routine — index 0 there is the atmosphere pseudo-layer, per the other comment.

**Interfaces:**
- Consumes: Task 2 functions; Task 4 fluxes (`qflx_nvp_*` not yet — Task 13 wires the moss water budget; this task only routes snow-side water).
- Produces: `qflx_snow_percolation(c, col%jbot_sno(c))` = flux out of the snowpack bottom; when `nvp_is_present`, it is deposited in `h2osoi_liq(c,0)` and `qflx_snow_drain` books it; when `nvp_is_empty` or `jbot_sno==0`, stock routing (drain hand-off, nothing stored at 0).

- [ ] **Step 0: Plan review (orchestrator; do not delegate).** Read this task's text against the spec and the code it touches. **STOP** and put to the user: clarifying questions, problems foreseen, cleanup the task text needs, unmet dependencies. Write the resolutions into this plan file before dispatching the implementer. Known going in: Step 4 leaves the `SnowCapping` refactor shape ("gather-and-scatter vs. indexed dummies — whichever produces the smaller diff") to the implementer; decide it here so the two-stage reviewers have a fixed target.

- [ ] **Step 1 — `BulkFlux_SnowPercolation` (theirs :1342-1451, [harvest]):** three-way structure on `jbot_sno`; keep their zero-denominator guard; loop `do j = get_jtop_snow(c), col%jbot_sno(c)` so slot 0 never enters (their version entered j=0 and zeroed it — ours is structural; simpler, note in MERGE_NOTES).
- [ ] **Step 2 — `UpdateState_SnowPercolation` ([harvest+fix]):** deposit `perc(c,j-1)` into layer `j` for `j = get_jtop_snow(c)+1 .. jbot`; then the bottom outflow: `if (nvp_is_present(c)) h2osoi_liq(c,0) += perc(c,jbot)*dtime` else leave for the drain hand-off (**zero-dz [fix]**, spec §4a).
- [ ] **Step 3 — `SumFlux_AddSnowPercolation` (theirs :1890-1953, [harvest]):** `qflx_snow_drain += perc(c,jbot)`; when moss received it, exclude from `qflx_rain_plus_snomelt` (their logic keyed on `nvp_layer_active` → ours keys on `nvp_is_present`).
- [ ] **Step 4 — `SnowCapping` + helpers ([fix], theirs unmodified):** every `(begc:endc, 0)` slice argument becomes a per-column gather at `col%jbot_sno(c)`. Mechanically: change the helper dummies from slices to indexed access, or build local gathered arrays `x_bottom(c) = x(c, col%jbot_sno(c))` before the calls and scatter back after — choose whichever produces the smaller diff (read the six routines first; they are slice-plumbing, ~3181-3244, 3288-3694 stock). Moss is never capped (bottom = bottom SNOW layer).
- [ ] **Step 5 — Aerosols:** `AerosolMasses` guard `j <= col%jbot_sno(c)` ([harvest], their 6-liner); `CalcAndApplyAerosolFluxes` cascade loop ends at `jbot_sno` (structural exclusion of slot 0 — their version leaked `qin` into `mss_*(c,0)`; ours doesn't: MERGE_NOTES row, spec §4g).
- [ ] **Step 6: Run build check.**
- [ ] **Step 7: Commit** `git commit -am "Route snow percolation, capping, and aerosols around the NVP slot"` → review/approval gate.

---

### Task 7: Thermal properties + heat-diffusion factors (SoilTemperatureMod part 1)

**Files:**
- Modify: `src/biogeophys/SoilTemperatureMod.F90` — `SoilThermProp` (stock 602-901), `ComputeHeatDiffFluxAndFactor` (stock 1799-1910)
- **Folded in from the Task 5c unassigned-sites sweep:** `src/biogeophys/TemperatureType.F90:736` — the `do j = snl(c)+1, 0` snow-temperature fill in `InitCold`, which follows a blanket `spval` assignment at `:732`. On an NVP column at cold start with `snow_depth > 0` it writes 250 K into the moss slot and **leaves the top snow layer holding `spval = 1e36`**, which then reaches `SoilThermProp` — this task's own routine — on the first timestep. **`TemperatureType%InitCold` is shared with Task 10**, which owns `:837` in the same routine; coordinate so the second task to arrive does not undo the first.

**Interfaces:**
- Consumes: `NVPParamsMod` (`thk_dry_nvp`, `csol_nvp`, `watsat_nvp`), Task 2 functions.
- Produces: `thk(c,0)`/`cv(c,0)` for present moss; `tk(c,0)` = moss↔soil interface conductivity, `tk(c,-1)` = snow↔moss; `fact(c,0)`/`fn(c,0)` **always defined** on NVP columns (their critical gap).

- [ ] **Step 0: Plan review (orchestrator; do not delegate).** Read this task's text against the spec and the code it touches. **STOP** and put to the user: clarifying questions, problems foreseen, cleanup the task text needs, unmet dependencies. Write the resolutions into this plan file before dispatching the implementer. Known going in: Step 3 opens with a rhetorical self-question ("generic loop skips `j==0` and `j==-1`? No —") — rewrite as a direct instruction; and it hands the implementer the zero-thickness half-thickness conductances that Task 8 Step 3 then consumes, so pin the exact expressions here, once, for both tasks.

- [ ] **Step 1 — snow branches:** snow-conductivity loop bound and `bw` guard: `snl(c)+1 <= j <= 0` becomes `get_jtop_snow(c) <= j <= col%jbot_sno(c)` (structural exclusion; do not port their `.NOT.(...j==0)` guard).
- [ ] **Step 2 — NVP `thk(c,0)`/`cv(c,0)` ([harvest] theirs :885-907, :1038-1061):** their Farouki-style `thk` (guards: `dz>0`, `satw>1e-6`) and per-moss-area `cv` with `thin_sfclayer` floor, `if (nvp_is_present(c))`. For `nvp_is_empty(c)`: `thk(c,0)=0`, `cv(c,0)=thin_sfclayer` and they are never consumed (Task 8's continuity row).
- [ ] **Step 3 — interface conductivities:** generic loop skips `j==0` and `j==-1`? No — keep the generic loop over `get_jtop_snow(c) <= j <= nlevgrnd-1` INCLUDING j=0 and j=−1 for `nvp_is_present` columns (their :947-968 shows both degenerate gracefully); add the explicit presence-predicate collapse for `nvp_is_empty`: `tk(c,0) = <direct snow-or-surface↔soil conductance>` and `tk(c,-1)` per §3 zero-dz (half-thickness node-to-interface conductances). Write a comment stating the constraint: "zero-thickness NVP: interface conductances measured to the coincident interface; the layer contributes no resistance."
- [ ] **Step 4 — `h2osno_no_layers` heat ([fix], spec §6 orphan):** `cv(c,1) += cpice*h2osno_no_layers` becomes `cv(c,0) += …` when `nvp_is_present(c)` (layerless snow sits on the moss), else stock.
- [ ] **Step 5 — `ComputeHeatDiffFluxAndFactor` ([fix], their critical gap):** guard `if (j >= col%snl(c)+1)` becomes `if (j >= get_jtop_snow(c))` — on an NVP column with `snl==0` this includes `j=0`, so `fact(c,0)`/`fn(c,0)` are always computed. For `nvp_is_empty`, `fact(c,0)` computes to 0 (dz factor) — acceptable because no Task-8/9 consumer touches it on empty columns (verified by the golden test).
- [ ] **Step 6: Run build check.**
- [ ] **Step 7: Commit** `git commit -am "NVP thermal properties and always-defined heat-diffusion factors"` → review/approval gate.

---

### Task 8: Banded matrix, RHS, assembly, jtop (SoilTemperatureMod part 2)

**Files:**
- Modify: `src/biogeophys/SoilTemperatureMod.F90` — `SoilTemperature` (jtop ~273, load/unload 396-434), `SetRHSVec*` (1913-2353), `SetMatrix*` (2356-2926), `AssembleMatrixFromSubmatrices` (2474-2588 incl. sparsity diagram)
- **Folded in from the Task 5c unassigned-sites sweep:** `src/biogeophys/SoilTemperatureMod.F90:474` — the `if (j >= snl(c)+1)` guard in `SoilTemperature`'s non-urban `fn1` branch. Inside the routine this task names, but outside the `396-434` range it cites; the cited ranges are not exhaustive, so sweep the whole routine rather than working from them.

**Interfaces:**
- Consumes: Task 7 `tk`/`cv`/`fact`/`fn`; `NVPEffectiveFractions` (Task 3); `hs_nvp`/`dhsdT` come from `ComputeGroundHeatFluxAndDeriv` (extended in Task 11 — until then `hs_nvp` is a new local computed as 0; see Step 4).
- Produces: NVP at matrix row −1 (`tvector(c,-1) = t_soisno(c,0)` on NVP columns); `jtop(c) = snl(c) + col%jbot_sno(c)`; conservation-closed moss↔soil coupling weights; flux-continuity row for `nvp_is_empty`.

- [ ] **Step 0: Plan review (orchestrator; do not delegate).** Read this task's text against the spec and the code it touches. **STOP** and put to the user: clarifying questions, problems foreseen, cleanup the task text needs, unmet dependencies. Write the resolutions into this plan file before dispatching the implementer. **Known going in — this is the most important Step 0 in the plan:** Step 2(a) is a half-retracted sentence ("…soil row's coupling weight = `frac_nvp_eff + frac_sno_eff`… NO — the fixed rule:") covering the moss↔soil conduction closure, which spec §3 requires to balance identically for **all** admissible fractions including `frac_sno_eff > frac_nvp` (the regime where their branch creates energy). Derive `w_iface` explicitly, write the algebra into this task's text, and only then dispatch. Also confirm Step 3's band spans stay inside `nband=5`. **This task also lands `NVPEffectiveFractions` in `NVPLayerDynamicsMod`** — deferred out of Task 3 so nothing commits uncalled; this is its first consumer. It is THE single 4-way derivation (spec §4b), so write it once here and have Tasks 10-13 call it:

```fortran
! Centralized 4-way endmember fractions. dz0 = col%dz(c,0).
! Where the moss slot is empty, moss contributes nothing (skip invariant).
if (dz0 > 0._r8) then
   frac_nvp_eff = min(1._r8 - frac_h2osfc - frac_sno_eff, &
                      max(0._r8, frac_nvp_col - frac_sno_eff))
else
   frac_nvp_eff = 0._r8
end if
frac_soil = max(0._r8, 1._r8 - frac_sno_eff - frac_h2osfc - frac_nvp_eff)
```

- [ ] **Step 1 — row mapping:** load/unload loops: snow `do j = get_jtop_snow(c), col%jbot_sno(c); tvector(c,j-1)=t_soisno(c,j)`; NVP: `if (nvp_layer_exists(c)) tvector(c,-1) = t_soisno(c,0)`; `jtop(c) = snl(c) + col%jbot_sno(c)` (uniform, no special case — spec §3). Post-solve unload mirrors, plus for `nvp_is_empty(c)`: `t_soisno(c,0) = t_soisno(c,1)` tie-value (spec §3, with the documented rationale comment).
- [ ] **Step 2 — harvest their block structure** (`SetRHSVec_Snow` :2726-2770, `SetMatrix_Snow` :3363-3414, `SetRHSVec_Soil` :2963-3037, `SetMatrix_Soil` :3541-3619 in their numbering) with these **[fix]** deltas (spec §3): (a) ONE weight derivation — moss equation is per-moss-area (divide by `frac_nvp`), so the column-level moss↔soil flux weight is `frac_nvp` on BOTH sides: soil row's coupling weight = `frac_nvp_eff + frac_sno_eff`… NO — the fixed rule: derive the per-column interface flux once, `F = w_iface * tk(c,0)/dzm * ΔT` with `w_iface = frac_nvp_col_weight` chosen so moss loss = soil gain identically; implement by computing `w_iface` in one place (local function or block) used by all four sub-blocks; document the algebra in the code comment. (b) no `frac_h2osfc` double-subtraction: NVP soil branches use the stock convention (`frac_soil` from `NVPEffectiveFractions` replaces `1-frac_sno_eff` exactly once; the trailing h2osfc block stays stock). (c) delete their ad-hoc `frac_nvp_eff*sabg_soil_col` RHS term (spec §9b) — Task 12 provides the consistent partition.
- [ ] **Step 3 — flux-continuity row for `nvp_is_empty`:** in `SetMatrix_Snow`/`SetRHSVec_Snow`'s NVP branch: if empty, row −1 gets `g_a*T_snowbot_or_zero - (g_a+g_b)*T_0 + g_b*T_1 = 0` with `g_a` = conductance snow-node→interface (or 0 when `snl==0`, then the row is `T_0 - T_1 = 0`), `g_b` = conductance interface→soil-1-node; both from half-thicknesses (Task 7 Step 3 values). RHS = 0. Off-diagonal spans: snow row −2 (span 1… wait, snow bottom is row −2, moss row −1: span 1) and soil row 1 (span 2) — inside nband=5.
- [ ] **Step 4 — `hs_nvp`:** declare the local + zero-fill in `ComputeGroundHeatFluxAndDeriv`'s outputs now (so this task builds); Task 11 fills it. Mark with a comment: "filled by surface-flux task".
- [ ] **Step 5 — assembly + docs:** extend `AssembleMatrixFromSubmatrices` band placements for the new row-−1 couplings (read their :3246-3275) and **redraw the ASCII sparsity diagram** labeling row −1 as "NVP layer (moss) on NVP columns / bottom snow otherwise" (spec §3 doc fix).
- [ ] **Step 6: Run build check.**
- [ ] **Step 7: Commit** `git commit -am "NVP row in the heat solve with conservation-closed coupling and zero-dz continuity"` → review/approval gate.

---

### Task 9: Phase change (SoilTemperatureMod part 3)

**Files:**
- Modify: `src/biogeophys/SoilTemperatureMod.F90` — `Phasechange` (stock 1133-1540), `PhaseChangeH2osfc` (stock 904-1130)

**Interfaces:**
- Consumes: `fact(c,0)` (Task 7), `NVPEffectiveFractions`, `nvp_is_present`.
- Produces: NVP melt/freeze with plain-`tfrz` criterion, per-moss-area weighting consistent with Task 8; NVP excluded from `qflx_snomelt/snofrz` but in `xmf`; `t_nvp_col` sync; moss ice capped at pore capacity (`watsat_nvp*denice*dz(c,0)`) with excess pushed per spec §4a.

- [ ] **Step 0: Plan review (orchestrator; do not delegate).** Read this task's text against the spec and the code it touches. **STOP** and put to the user: clarifying questions, problems foreseen, cleanup the task text needs, unmet dependencies. Write the resolutions into this plan file before dispatching the implementer. Known going in: Step 1's weighting must be re-derived against whatever Task 8 Step 0 settled as the single weight rule — carry that derivation in verbatim rather than restating it. Step 3 trails off mid-reasoning ("else stock `(c,0)`-as-snow… careful:"); resolve it against the spec §6 orphan table first.

- [ ] **Step 1 — `Phasechange` [harvest]** their buried (`snl<0`, :1490-1505) and exposed (`snl==0`, :1526-1550) NVP blocks, their `hm(c,0)`/T-correction weighting (:1658-1677, 1783-1893) re-derived against Task 8's single weight rule, their melt-flux exclusions (:1829-1843) and `t_nvp_col` re-sync (:1907-1913). All guarded `nvp_is_present` (empty moss: no mass, block skipped — [fix] explicit guard rather than relying on zero mass).
- [ ] **Step 2 — snow/soil boundary tests:** every `j < 1`/`j <= 0` snow-vs-soil discriminator in `Phasechange` becomes `j <= col%jbot_sno(c)` EXCEPT the new NVP-specific `j == 0` blocks (spec §2 idiom table).
- [ ] **Step 3 — `PhaseChangeH2osfc` [harvest+fix]:** their `snl<0` reroutes to `(c,jbot)` = bottom snow ([harvest], re-expressed via `jbot_sno`); the `snl==0` branches ([fix], their gap): frozen-h2osfc ice deposits into moss when `nvp_is_present` (with the pore-capacity cap) else stock `(c,0)`-as-snow… careful: stock `snl==0` writes `h2osoi_ice(c,0)`/`t_soisno(c,0)` as the *newly created* snow slot — on NVP columns that must become `(c,jbot_sno)` creation or moss deposit per the spec §6 orphan table (moss when present). Do not overwrite moss temperature with `t_h2osfc` (spec §3 fix).
- [ ] **Step 4: Run build check.**
- [ ] **Step 5: Commit** `git commit -am "NVP phase change with consistent weighting and h2osfc rerouting"` → review/approval gate.

---

### Task 10: Ground temperature blends + surface humidity

**Files:**
- Modify: `src/biogeophys/SoilTemperatureMod.F90` (t_grnd, stock 548-568), `src/biogeophys/BiogeophysPreFluxCalcsMod.F90` (:334-341 + `tssbef` loop bounds :302-312), `src/biogeophys/SoilFluxesMod.F90` (t_grnd0 :175-181 — blend only; energy check is Task 11), `src/biogeophys/HydrologyNoDrainageMod.F90` (:555-570 blend; SNOWICE/SNOWLIQ loop bounds :442-499), `src/biogeophys/SurfaceHumidityMod.F90` (qg blend, their :~165-290)
- **Folded in from the Task 5c unassigned-sites sweep:**
  - `src/biogeophys/TemperatureType.F90:837` — `t_grnd_col(c) = t_soisno_col(c,snl(c)+1)` in `InitCold`, the cold-start counterpart of this task's `t_grnd` blends. Decide it consistently with them: whatever this task makes `t_grnd` mean on an NVP column, cold start must produce. **The routine is shared with Task 7**, which owns `:736` in it.
  - `src/biogeophys/BiogeophysPreFluxCalcsMod.F90:354` — the `h2osoi_liq(c,snl(c)+1) <= 0 .and. h2osoi_ice(c,snl(c)+1) > 0` test, just below the `:334-341` block this task already cites. Sweep the routine rather than the cited range.
  - **Not yours:** `src/biogeophys/HydrologyNoDrainageMod.F90:704` (`h2osno_top` from `snl(c)+1`) is in a file this task owns but is assigned to **Task 6** by domain — it is SNICAR input, the twin of `AerosolMod:621`. Leave it alone.

**Interfaces:**
- Consumes: `NVPEffectiveFractions`, `t_soisno(c,0)`, `NVPWaterRetentionCurve` (for `hr_nvp`), Task 4 `qg_nvp_col`.
- Produces: all four t_grnd-family blends as `frac_sno_eff*T(get_jtop_snow) + frac_nvp_eff*T(c,0) + frac_soil*T(c,1) + frac_h2osfc*t_h2osfc` — same fraction call, all sites; `qg`/`dqgdT` 4-way blend with `hr_nvp` (frozen guard `hr_nvp=1`).

- [ ] **Step 0: Plan review (orchestrator; do not delegate).** Read this task's text against the spec and the code it touches. **STOP** and put to the user: clarifying questions, problems foreseen, cleanup the task text needs, unmet dependencies. Write the resolutions into this plan file before dispatching the implementer.

- [ ] **Step 1:** Update the three t_grnd/t_grnd0 sites + surface-T uses of `t_soisno(c,snl(c)+1)` in these files → `t_soisno(c, get_jtop_snow(c))` with the documented fallback: when `snl==0 .and. .not. nvp_is_present(c)`, the blend's moss term is zero (fractions handle it) and `get_jtop_snow` is never used as a mass-bearing index.
- [ ] **Step 2:** `SurfaceHumidityMod` [harvest] their `qg_nvp` (retention-curve humidity, frozen branch) with the **[fix]**: gate on `nvp_is_present(c)` (their gap: `frac_nvp>0` with no layer → bone-dry fraction).
- [ ] **Step 3:** Loop-bound sweeps in these files per the §2 idiom table (`tssbef`, SNOWICE/SNOWLIQ, `t_sno_mul_mss`).
- [ ] **Step 4: Run build check. Step 5: Commit** `git commit -am "4-way ground temperature and humidity blends"` → review/approval gate.

---

### Task 11: Surface fluxes + ground heat flux + energy check

**Files:**
- Modify: `src/biogeophys/SoilTemperatureMod.F90` (`ComputeGroundHeatFluxAndDeriv` stock 1543-1796: `lwrad_emit_nvp`, `hs_nvp` fill, `eflx_gnet_nvp`), `src/biogeophys/BareGroundFluxesMod.F90` (their +184 diff), `src/biogeophys/CanopyFluxesMod.F90` (their +162 diff), `src/biogeophys/SoilFluxesMod.F90` (their +358 diff: `qflx_evap_grnd_eff`, lw_grnd both places, `eflx_soil_grnd`, errsoi)

**Interfaces:**
- Consumes: Task 10 blends, Task 4 fluxes, `NVPEvapResistance`, `NVPEffectiveFractions`, `fwet_nvp_col`.
- Produces: `hs_nvp(c)` (fills Task 8's zero local), `eflx_sh_nvp_patch`, `qflx_ev_nvp_patch`, 4-way `qflx_evap_grnd_eff`, errsoi with moss storage term weighted `frac_nvp` ([fix], spec §3) and skipped when `nvp_is_empty` ([fix], spec §3 zero-dz).

- [ ] **Step 0: Plan review (orchestrator; do not delegate).** Read this task's text against the spec and the code it touches. **STOP** and put to the user: clarifying questions, problems foreseen, cleanup the task text needs, unmet dependencies. Write the resolutions into this plan file before dispatching the implementer. Known going in: (a) Step 2 references `sabg_nvp`, which Task 12 produces — confirm the forward dependency is a zero-valued placeholder here (as `hs_nvp` was in Task 8 Step 4) and not a build break; (b) **this task lands `NVPEvapResistance` in `NVPLayerDynamicsMod`**, deferred out of Task 3 so nothing committed uncalled. Their branch has no such function — the formula is inline in their `NVPEvaporation` (`<worktree>/src/biogeophys/NVPLayerDynamicsMod.F90:306-388`), and they duplicate it in three files. Extract it once here, using the Task 1 `rnvp_min`/`rnvp_amp`/`rnvp_exp`/`rnvp_ice` parameters, and have both BareGroundFluxes and CanopyFluxes call it.

- [ ] **Step 1 [harvest]:** their per-surface resistances (`raiw_nvp`, dew branch, `wtgq_*` 4-way) — `rnvp` via `NVPEvapResistance` (single source, Task 3). **[fix]** one gate everywhere: `frac_nvp_eff > 0` (from the centralized call) in BOTH modules.
- [ ] **Step 2 [harvest]:** `lw_grnd` 4-way in BOTH SoilFluxes places and BOTH CanopyFluxes places (their two-places lesson, spec §4b); `eflx_soil_grnd` solar/latent terms per their :472-486 with Task 12's partition names (`sabg_nvp`); `qflx_evap_grnd_eff` (:433-446) and its uses (:553-571).
- [ ] **Step 3 [harvest+fix]:** `ComputeGroundHeatFluxAndDeriv`: `lwrad_emit_nvp = emg*sb*t_soisno(c,0)**4`; `hs_nvp` accumulation over patches — **[fix]** the accumulation must use the same patch gate as the flux definitions so atmosphere-seen flux == moss-lost flux for any patch structure (audit's non-veg-patch inconsistency).
- [ ] **Step 4 [fix]:** errsoi: moss term `- frac_nvp * (t_soisno(c,0)-tssbef(c,0))/fact(c,0)` when `nvp_is_present`; nothing when empty; snow terms' `j<1` discriminator → `j <= col%jbot_sno(c)`.
- [ ] **Step 5: Run build check. Step 6: Commit** `git commit -am "NVP surface energy/moisture fluxes and energy-balance accounting"` → review/approval gate.

---

### Task 12: Radiation (constant transmissivity)

**Files:**
- Modify: `src/biogeophys/SurfaceRadiationMod.F90` (stock 745-852), `src/biogeophys/SurfaceAlbedoMod.F90` (ground-albedo blend, their :868-879 region), `src/biogeophys/SolarAbsorbedType.F90` (`sabg_nvp_patch` exists from Task 4)

**Interfaces:**
- Consumes: `nvp_transmissivity`, `alb_nvp_vis/nir`, `NVPEffectiveFractions`, `sabg_lyr`.
- Produces: `sabg_nvp(p)` = `(1-nvp_transmissivity) * <flux reaching NVP surface>`; slot 1 keeps the transmitted remainder; `sabg_lyr` sums conserve with the `endrun` **armed** (no bypass — spec §4f); ground albedo blend uses `alb_nvp_vis/nir` over the exposed-moss fraction.

- [ ] **Step 0: Plan review (orchestrator; do not delegate).** Read this task's text against the spec and the code it touches. **STOP** and put to the user: clarifying questions, problems foreseen, cleanup the task text needs, unmet dependencies. Write the resolutions into this plan file before dispatching the implementer. Known going in: **Step 1 contains unretracted thinking-out-loud** ("`sabg_nvp(p) = (1-nvp_transmissivity)*sabg_lyr(p,1)` … NO — slot semantics:") — settle what "the flux reaching the NVP surface" is in each `snl` regime and rewrite the step before dispatch. Spec §4f requires transmissivity ≡ 1 to reproduce stock exactly and the `sabg_lyr` `endrun` to stay armed.

- [ ] **Step 1:** In `SurfaceRadiation`, after the existing snl-dependent `sabg_lyr` fill: on `nvp_is_present` columns, `sabg_nvp(p) = (1-nvp_transmissivity)*sabg_lyr(p,1)` … NO — slot semantics: the flux reaching the NVP surface is `sabg_lyr(p,1)` (SNICAR's through-snow output) for `snl<0`, or `sabg(p)`'s ground share for `snl==0`; set `sabg_lyr(p,0) = sabg_nvp(p)` and `sabg_lyr(p,1) = <reaching> - sabg_nvp(p)`. Transmissivity forced to 1 when `nvp_is_empty` (fraction rule makes `sabg_nvp=0`). Hardcoded stock splits (`snl==-1` 0.6/0.4) keep their slot arithmetic but slot indices via `jbot_sno` (spec §4f "slot numbers become jbot_sno-relative").
- [ ] **Step 2:** `sabg_pen`, `sabg_snl_sum`, and the conservation check updated for the new slot-0 meaning; the `endrun` tolerance unchanged and armed.
- [ ] **Step 3:** `SurfaceAlbedoMod`: exposed-moss fraction of the ground albedo uses `alb_nvp_vis/nir` (simplified from their Beer-effective form; note MERGE_NOTES row: theirs supersedes at merge). `albsfc` (under-snow) stays soil albedo (their SNICAR handles under-snow moss at merge; our slot-0 assignment covers the stub).
- [ ] **Step 4:** `SoilFluxesMod` `sabg_chk` consistency (Task 11's `eflx_soil_grnd` used the same partition — verify with a grep that `sabg_nvp` appears in exactly: SurfaceRadiation (producer), eflx_soil_grnd, sabg_chk, hs_nvp).
- [ ] **Step 5: Run build check. Step 6: Commit** `git commit -am "Constant-transmissivity NVP radiation partition"` → review/approval gate.

---

### Task 13: NVP water balance + soil-side plumbing

**Files:**
- Modify: `src/biogeophys/NVPLayerDynamicsMod.F90` (add `NVPWaterBalance_Column`), `src/biogeophys/HydrologyNoDrainageMod.F90` (call site after `SnowWater`, before `SetQflxInputs` — their :324-330), `src/biogeophys/SoilHydrologyMod.F90` (`SetQflxInputs` :302-412 their numbering; `Infiltration` :492-510; `RenewCondensation` :2637-2746), `src/biogeophys/SurfaceWaterMod.F90` (:331), `src/main/clm_driver.F90` (`p2c` of `qflx_ev_nvp_patch`, their :1726-1743, guarded `if (use_nvp)`)

**Interfaces:**
- Consumes: Task 4 fluxes, Task 3 physics functions, `NVPEffectiveFractions`.
- Produces: closed moss water budget: in = `frac_nvp_eff`-share of `qflx_rain_plus_snomelt` + snow percolation deposit (Task 6) + dew share; out = `qflx_ev_nvp_eff_col` + `qflx_nvp_drain_col` (Darcy + saturation excess) + `qflx_nvp_to_snow_col` (ice push, only when snow exists); `qflx_infl += qflx_nvp_drain_col`.

- [ ] **Step 0: Plan review (orchestrator; do not delegate).** Read this task's text against the spec and the code it touches. **STOP** and put to the user: clarifying questions, problems foreseen, cleanup the task text needs, unmet dependencies. Write the resolutions into this plan file before dispatching the implementer. Known going in: (a) Step 1(b) replaces their water-creating `max(0, h2osoi_net)` clamp with "limit evaporation to available water and pass any residual demand to the soil-evap pathway" — confirm where that residual lands and that Task 11's `qflx_evap_grnd_eff` decomposition can absorb it without double-counting; (b) **this task lands `NVPWaterRetentionCurve` and `NVPHydraulicConductivity` in `NVPLayerDynamicsMod`** (harvest verbatim from `<worktree>/src/biogeophys/NVPLayerDynamicsMod.F90:223-305`), deferred out of Task 3 so nothing committed uncalled. They consume the Task 1 Mualem-van Genuchten parameters `ksat_nvp`, `n_van_nvp`, `alpha_van_nvp`, `watsat_nvp`, `watres_nvp`. Adding them to code the pFUnit build links may require listing `NVPLayerDynamicsMod.F90` and `NVPParamsMod.F90` in `src/biogeophys/CMakeLists.txt` — check before assuming.

- [ ] **Step 1 [harvest+fix] `NVPWaterBalance_Column`** from theirs (:394-661): keep Darcy exchange (upstream-weighted K, caps both directions), saturation excess, `fwet_nvp`/`vwc_nvp`/`h2onvp` diagnostics. **Fixes:** (a) the infiltration credit uses THE SAME `frac_nvp_eff` and the same withheld amount as `SetQflxInputs` (close the rain-through-snow leak: whatever `SetQflxInputs` withholds is exactly what the moss is credited, same timestep, all `snl`); (b) no `max(0, h2osoi_net)` clamp — instead limit evaporation to available water and pass any residual demand to the soil-evap pathway (read their clamp at :591 and the surrounding budget to place the limiter on the demand side); (c) ice cap: excess ice → snow (`qflx_nvp_to_snow_col`, only when `snl<0`); when no snow, cap is enforced in Phasechange (Task 9) so this path never triggers — add an `endrun` if it would (defensive, cites the invariant).
- [ ] **Step 2 [fix] `SetQflxInputs`:** ONE fraction (`NVPEffectiveFractions`), withheld amount `frac_nvp_eff*(qflx_top_soil - qflx_sat_excess_surf)` recorded into `qflx_nvp_infl_col` (consumed by Step 1 the same timestep); evap partition uses the same call. Zero-dz: fraction rule → stock.
- [ ] **Step 3 [harvest] `Infiltration`:** `qflx_infl += qflx_nvp_drain_col` (guarded `use_nvp`; the flux is zero-init so the guard is belt-and-braces).
- [ ] **Step 4 [fix] `RenewCondensation`:** no-snow dew/frost target: moss (`h2osoi_liq/ice(c,0)`) scaled by the exposed-moss share when `nvp_is_present`, soil layer 1 for the rest — using the same fractions; sublimation debit excludes what `qflx_ev_nvp` already took (read Task 11's `qflx_evap_grnd_eff` decomposition to identify the double-debit and remove exactly it).
- [ ] **Step 5 [fix] `SurfaceWaterMod`:** too-small-h2osfc → `h2osoi_liq(c,0)` when `nvp_is_present`, else stock.
- [ ] **Step 6: Run build check. Step 7: Commit** `git commit -am "NVP water balance and soil-side routing"` → review/approval gate.

---

### Task 14: Conservation accounting

**Files:**
- Modify: `src/biogeophys/TotalWaterAndHeatMod.F90` (:282, :485, :688-757, :1015 stock), `src/biogeophys/WaterStateType.F90` (`CalculateTotalH2osno` :891, `CheckSnowConsistency` :936), `src/biogeophys/BalanceCheckMod.F90` (snow sources :813-840 their numbering)

**Interfaces:**
- Consumes: everything prior.
- Produces: moss water+heat in column totals exactly once (both `snl` states); moss excluded from `h2osno_total`; `qflx_nvp_to_snow_col` as a snow source; NO `select type` downcast.

- [ ] **Step 0: Plan review (orchestrator; do not delegate).** Read this task's text against the spec and the code it touches. **STOP** and put to the user: clarifying questions, problems foreseen, cleanup the task text needs, unmet dependencies. Write the resolutions into this plan file before dispatching the implementer. Known going in: Step 3 offers two ways to avoid the `select type` downcast (move the flux to the generic `waterflux_type`, or correct in a bulk-only wrapper) — pick one here.

- [ ] **Step 1:** snow loops in `TotalWaterAndHeatMod` → `get_jtop_snow..jbot_sno` bounds; add the moss terms unconditionally on `nvp_layer_exists` columns (zero when empty): water mass `h2osoi_liq/ice(c,0)`; heat: `AccumulateLiquidWaterHeat(t_soisno(c,0), h2osoi_liq(c,0))` + ice `TempToHeat(cv=h2osoi_ice(c,0)*cpice)` + solid `TempToHeat(cv=csol_nvp*(1-watsat_nvp)*dz(c,0))` — **both** mass and heat, **both** with the same single predicate (their §2b bug: heat side missing when `snl==0`). **Task 5c Step 6 already moved the *lower* bound of the two non-lake loops (`:282`, `:691`) to `get_jtop_snow`, leaving the upper bound at `0`** so the balance checks would not fire spuriously with the stopgap gone; this step supersedes that intermediate with the full `jtop..jbot`-plus-explicit-moss-terms form. The lake loops (`:485`, `:1015`) are still stock and stay that way — NVP columns are never lake.
- [ ] **Step 2:** ~~`CalculateTotalH2osno` excludes slot 0 via the loop bound; `CheckSnowConsistency` range shifts likewise.~~ **Both were pulled forward into Task 5c Step 4** — without them `errh2osno` cannot close once Task 5's stopgap is removed, so `use_nvp=.true.` would abort in the armed balance check on every run. Verify here that they are present and correct rather than re-doing them. Layerless-snow heat temperature source: `t_soisno(c, merge(0, 1, nvp_is_present(c)))` at their :688 counterpart (consistent with Task 7 Step 4).
- [ ] **Step 3 [fix]:** `BalanceCheckMod`: add `qflx_nvp_to_snow_col` to `snow_sources` WITHOUT `select type` — route it via the generic `waterflux_type` (add the member there rather than the bulk type; check how `qflx_snow_drain` is declared — same home) or compute the correction in a bulk-only wrapper before the generic check. `qflx_sl_top_soil` now set correctly by Task 5, so no other snow-balance change. All `endrun`s untouched (armed).
- [ ] **Step 4: Run build check. Step 5: Commit** `git commit -am "NVP conservation accounting in totals and balance checks"` → review/approval gate.

---

### Task 15: History snow-field fill + SNO_* slices

**Files:**
- Modify: `src/main/histFileMod.F90` (`hist_set_snow_field_2d` :2209-2300), plus the 19 `SNO_*` field registrations if their slices need bound changes (they are `(:, -nlevsno+1:0)` literals — with the moss in slot 0, the fill routine's exclusion is the fix; slices can stay if the fill never reads slot 0 on NVP columns — decide by reading the fill)

- [ ] **Step 0: Plan review (orchestrator; do not delegate).** Read this task's text against the spec and the code it touches. **STOP** and put to the user: clarifying questions, problems foreseen, cleanup the task text needs, unmet dependencies. Write the resolutions into this plan file before dispatching the implementer.

- [ ] **Step 1:** `hist_set_snow_field_2d`: bottom-justification ends at `col%jbot_sno(c)` instead of 0; `num_snow_layers = abs(snl(c))` is already honest. Verify no `SNO_*` field can expose slot 0 on NVP columns; adjust slices only if the fill alone is insufficient.
- [ ] **Step 2: Run build check. Step 3: Commit** `git commit -am "Exclude NVP slot from snow history fields"` → review/approval gate.

---

### Task 16: Unit tests

**Files:**
- Modify: `src/unit_test_shr/unittestSubgridMod.F90` (:471-493 `init_nlevsno` area — add optional `jbot_sno` setup), `src/biogeophys/test/SnowHydrology_test/*`, `src/biogeophys/test/TotalWaterAndHeat_test/*`, `src/biogeophys/test/Balance_test/*` (run existing suites both ways; add NVP-specific cases)

- [ ] **Step 0: Plan review (orchestrator; do not delegate).** Read this task's text against the spec and the code it touches. **STOP** and put to the user: clarifying questions, problems foreseen, cleanup the task text needs, unmet dependencies. Write the resolutions into this plan file before dispatching the implementer. Known going in: (a) these tests arrive after the code they cover — confirm whether that ordering stands, or whether the remaining case should instead be written alongside Task 14 (superpowers:test-driven-development would put it first); (b) **mutation-test each new assertion, and mutate the right thing.** Task 5d shipped a stock-column mirror test that could not fail: the implementer mutated the NVP-only term it was testing, and the stock mirror is blind to that mutation *by design*. A mirror whose job is to prove an NVP-only term does not leak onto stock columns has to be mutated the other way — make the term unconditional — and a test that starts from an already-saturated state cannot detect a cap at all. Prefer growth cases over saturation cases when the property under test is a limit.

- [ ] **Step 1:** ~~Parameterize the test-subgrid snow setup over `jbot_sno`~~ — **not needed**: `col%jbot_sno` is a plain array, assignable directly in a `.pf`, as Tasks 5a and 5d both do. Cases (a) and (c) below were **superseded by Task 5d**, which also covers `DivideSnowLayers`, `ZeroEmptySnowLayers` and `PostPercolation_AdjustLayerThicknesses`; only (b) remains for this task. Add cases: (a) `CalculateTotalH2osno` excludes slot 0 when `jbot_sno=-1`; (b) CombineSnowLayers vanishing bottom layer on an NVP column deposits into slot 0 when `dz(c,0)>0` and passes through when `dz(c,0)=0` with `qflx_sl_top_soil` booked; (c) TotalWaterAndHeat counts moss water+heat exactly once for `snl==0` and `snl<0`.
- [ ] **Step 2:** Run the pFUnit suites (the standard per-commit unit-test command from the Execution Process — from `src/`, `qcmd -- ../cime/scripts/fortran_unit_testing/run_tests.py --build-dir unit_tests.temp`) with the new cases included.
- [ ] **Step 3: Commit** `git commit -am "Unit tests for NVP snow indexing and conservation"` → review/approval gate.

---

### Task 17: Remove the NVP debug traces

Runs **before** Task 18 so the final verification gates and the merge rehearsal see the code that actually ships. Every trace added under the Global Constraints debug-trace rule is removed here.

**Files:** whichever carry `NVP_TRACE:` when this task starts — do not work from a list written earlier, it will be stale.

- [ ] **Step 0: Plan review (orchestrator; do not delegate).** Read this task's text against the spec and the code it touches. **STOP** and put to the user: clarifying questions, problems foreseen, cleanup the task text needs, unmet dependencies. Write the resolutions into this plan file before dispatching the implementer. Known going in: decide whether any trace has proven useful enough to keep as a permanent `if (use_nvp)`-guarded diagnostic, which spec §1.11 does allow — if so it stops being a trace, loses the marker, and gets a comment saying what invariant it reports.

- [ ] **Step 1: Remove them.** `grep -rn 'NVP_TRACE:' src/ bld/` is the complete work list. Delete each line, and any `if (masterproc)` wrapper, `use` statement, or local variable that existed only to support it. Removing a trace must not change indentation or spacing of surviving lines.

- [ ] **Step 2: Prove none survive.** `grep -rn 'NVP_TRACE:' src/ bld/` returns nothing. Also confirm no orphaned `use shr_sys_mod, only : ...`/`masterproc` imports remain that nothing else uses — a dangling import compiles fine and ships as noise.

- [ ] **Step 3: Verify.** Build check and unit tests (baseline 59/59). Then the check that matters: `git diff ctsm5.4.028 -- src/ bld/` must contain **zero** `write(iulog` additions outside `if (use_nvp)` guards. Spec §9c.2 lists their branch's ~128 debug writes, many unguarded, as the blocking defect that makes `use_nvp=.false.` non-bit-for-bit. This step is what keeps us from shipping the same defect.

- [ ] **Step 4: Commit** `git commit -am "Remove NVP development debug traces"` → review/approval gate.

---

### Task 18: Verification & merge rehearsal (spec §10)

No new source files. Run and record results in MERGE_NOTES.md § "Verification results":

- [ ] **Step 0: Plan review (orchestrator; do not delegate).** Read this task's text against the spec and the code it touches. **STOP** and put to the user: clarifying questions, problems foreseen, cleanup the task text needs, unmet dependencies. Write the resolutions into this plan file before dispatching the implementer. Known going in: Steps 1–4 need real cases on Derecho (compsets, resolutions, run lengths, baselines) that this plan never names — settle them here. Step 5's merge rehearsal must target whichever `ctsm5.4.028_nvp` commit is the actual merge destination, which may not be the commit harvested from.

- [ ] **Step 1:** `use_nvp=.false.` bit-for-bit vs `ctsm5.4.028` — strongest available: full case SMS comparison on the user's machine; locally: assert `git diff ctsm5.4.028 -- src/ | grep -v <new files>` touches only guarded lines, and unit suites pass with `jbot_sno=0`.
- [ ] **Step 2:** Golden zero-thickness: `use_nvp=T, dz_nvp=0, frac_nvp=0` vs `use_nvp=F` (case-level, user's machine; unit-level analogs from Task 16 locally).
- [ ] **Step 3:** Partial-cover closure: `frac_nvp=0.3` and `0.7`, winter-crossing run, all balance checks armed — zero balance failures.
- [ ] **Step 4:** ERS exact-restart with `use_nvp=T, dz_nvp>0`.
- [ ] **Step 5:** Merge rehearsal: `git worktree add /tmp/nvp_merge_rehearsal ctsm5.4.028_nvp && cd /tmp/nvp_merge_rehearsal && git merge --no-commit --no-ff <working branch from Task 0>`; diff the conflict list against MERGE_NOTES "Intentional merge conflicts"; record; `git merge --abort`, remove the rehearsal worktree.
- [ ] **Step 6: Commit MERGE_NOTES updates** → final review/approval gate.

---

## Self-Review (performed per writing-plans skill)

- **Spec coverage:** §1 decisions → Tasks 1-3 (1,2,7,8), §2 → Tasks 2,5; §3 → Tasks 7-9; §4a → 6,13; §4b → 10,11; §4c → 9; §4d → 5; §4e → 6; §4f → 12; §4g → 6; §5 → 14; §6 → 3; §7 → 1,3,15,16; §10 → 17. Gap check: spec §7 cold-start ordering → Task 3 Step 2 + Task 5 Step 1; `ch4Mod` clarifying comment (spec §2) → **added to Task 5 Step 5's sweep scope** (one comment at ch4Mod's `j==0` pseudo-layer sites; include in that commit).
- **Type consistency:** `get_jtop_snow`/`nvp_layer_exists`/`nvp_is_present`/`nvp_is_empty` (Task 2) used with those exact names throughout; `NVPEffectiveFractions` (Task 3) is the only fraction source in Tasks 8-13; `NVPParamsMod` names match Task 1 declarations.
- **Placeholders:** `<their value>` items in Task 1 are read-from-disk data, not deferred design; Task 8 Step 2's weight rule states the governing constraint (moss loss = soil gain identically) with implementation latitude — resolved in **Task 8 Step 0** (the derivation is written into the task text before dispatch), then re-checked by the spec-compliance reviewer to confirm the algebra note landed in code comments.
- **Note on this section:** implementer subagents never see it — they receive only their own task's text (Execution Process 4). Anything recorded here that an implementer must act on has to be written into the task's steps, which is what each task's Step 0 is for. The `ch4Mod` item above is exactly this failure mode: it is claimed as "added to Task 5 Step 5" but Task 5 Step 5's text never mentions it, so Task 5 Step 0 must land it there or drop it deliberately.
