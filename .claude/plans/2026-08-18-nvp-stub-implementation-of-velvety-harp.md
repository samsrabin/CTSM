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
- **When unit tests get written, and how they are reviewed** (settled 2026-08-27; supersedes the earlier plan to batch them all at Task 16).
  - **Each task adds the unit tests for the code it lands**, at the earliest task where the test can actually be written. A test that genuinely needs code from a later task belongs to that later task — that is a dependency, not a deferral.
  - **Every new test ships with mutation evidence, stated in the task's hand-off.** Name the mutation, and report the binary counts with it applied and with it reverted: "revert this guard to the pre-NVP form and the count drops from 60 to 58; restore it and it returns to 60." The reviewer checks that claim, not the pFUnit. This exists because `.pf` files are long and hard to read for anyone not versed in the framework, and reading a *passing* test tells you nothing about whether it would ever fail.
  - **If no mutation can be constructed, the test is not pinning anything — cut it.** That also keeps the volume down.
  - **Why not batch at the end:** the defects these tests catch are the ones the suites structurally cannot see. `BalanceCheckMod.F90:764` gates the whole snow balance on `snl < 0` and forces `errh2osno = 0` otherwise, and `BalanceCheck` runs after `HydrologyNoDrainage` — so on the timestep the last snow layer dissolves into the moss, the check is skipped entirely. Both NVP interface-recursion guards passed 60/60 binaries while mutated. And for Tasks 6-10 there is no `use_nvp = .true.` system-test signal at all, because nothing completes a run until Task 11 at the earliest, so "wait for a suite failure to tell us we need a unit test" has nothing to trigger on across the hardest stretch of index rewriting.
- **Writing unit tests and fixtures.** Applies to any task that adds or edits a `.pf` file, not only the ones whose subject is testing.
  - **The harness already provides all of the following — do not rebuild any of it.** `col%jbot_sno` is a plain array: assign it directly in the `.pf` after the subgrid setup, as `test_initSnowLayers_overfillPack_nvp` does; no `unittestSubgridMod` change is ever needed for an NVP test. `unittestWaterTypeFactory` (`src/unit_test_shr/`) builds a real `water_type` — `init` → `setup_before_subgrid(my_nlevsoi, nlevgrnd_additional, my_nlevsno)` → subgrid setup → `setup_after_subgrid(snl=, dz=)` → `create_water_type(water_inst, ...)` → `teardown`, with worked examples at `test_irrigation.pf:371` and `test_water_type.pf:53`. `unittestFilterBuilderMod::filter_from_range` builds the `num_*c`/`filter_*c` pair.
  - **`temperature_type` and `aerosol_type` have no factory and need none:** hand-allocate only the components the routine under test touches, following `src/dyn_subgrid/test/dynConsBiogeophys_test/test_dyn_cons_biogeophys.pf:178-190`. They are pointers with no default initialization, so `nullify` them in `setUp` — an `associated()` guard in `tearDown` means nothing until you do — and deallocate there.
  - **Two setup traps.** The water factory's `setup_before_subgrid` sets `nlevsno` itself, so a test using the factory must not also assign `nlevsno` directly. And `SnowHydrologySetControlForTesting()` sets only scalar namelist values: `dzmin`/`dzmax_u`/`dzmax_l` are allocated inside `InitSnowLayers`, so a test that reads them must call it first (a zero snow depth serves as a bare allocator) and call `SnowHydrologyClean()` in `tearDown`.
  - **pFUnit authoring limits, both found the hard way.** The preprocessor cannot parse a **trailing comment** on an `@assert` line (Task 5a), and cannot parse an **`&` continuation** of one either (Task 5d) — it passes the fragment through verbatim and the compile dies on "Unrecognized token '@'". Keep every assertion on one physical line, hoist long actual arguments into local scalars, and put comments on their own line above.
  - **Every test opens with a one-sentence topline summary**, alone on its own comment line or lines, then a blank `!` line, then the detailed description. Four rules, all of them things the user has corrected:
    - **One sentence.** It may wrap and may use a colon or semicolon, but it may not become two.
    - **No numbers** — no thicknesses, thresholds, layer indices or array bounds. Say "thicker than a bottom layer is allowed to be", not the value and the threshold it exceeds. Numbers belong in the detailed description below.
    - **It must stand alone.** No reference to another test, including implicit ones: not "the same setup as above", "the complement of the previous test", or "the stock counterpart of". A reader jumping straight to one test must get the whole point from its first sentence. The *detailed description* below may cross-reference other tests freely; only the summary may not.
    - **Say what the routine under test must do, and what makes this case worth pinning** — not what the test code does. "DivideSnowLayers must be the identity" is right; "sets up three layers and calls DivideSnowLayers" is wrong. Name the configuration the case exercises (for the NVP work, whether the column carries a moss slot), since that is usually the axis a test file is organised around and it is not a number.
    Worked examples: the six tests in `src/biogeophys/test/SnowHydrology_test/test_SnowHydrology_divideSnowLayers.pf`.
  - **Give the quantities a test depends on names, not literals.** A bare `-4`, `-(my_nlevsno-1)` or `dz_layers(j+5)` forces the reader to re-derive what the number means at every appearance, and the same value often means two different things in one test. Declare `integer, parameter` constants near the top of the test and use them throughout: the layer count the column starts and ends with (`snl_before` / `snl_after`, and only the pair where it changes), the pack's top slot (`jtop`), and any capacity the case turns on (`snl_full`). Then write derived indices in terms of them — `dz_layers(j-jtop+1)` rather than three different magic offsets across three tests, which is the same expression once you know `jtop`. Two payoffs beyond legibility: the declaration is a natural place to state *why* the value is what it is, and the differences between related tests collapse into the one line where the names are defined — on an NVP column `jtop = snl_before`, on a stock column `jtop = snl_before + 1`, which is the whole reindex in miniature. Where one value legitimately plays two roles, declare both names and let the second define the first (`jtop = snl_full`); that documents the identity instead of hiding it. Worked example: the same file.
  - **Name a test for the condition it exercises, not for an input value.** `test_initSnowLayers_depth1_geometry` was two mistakes at once, both corrected by the user. `depth1` names the number that was typed in, which means nothing to a reader who has not memorised the threshold it is meant to exceed, and goes stale if that threshold moves; `overfillPack` names the condition the number produces. And `_geometry` failed to distinguish the test from its NVP twin, which also asserts geometry: where two tests differ along one axis, name *that axis* in both, so the suffixes read `_stock` / `_nvp` rather than one naming the subject and the other the configuration. Renaming a test subroutine needs `rm -rf src/unit_tests.temp`; the check that the rename did not break pFUnit's discovery is that the binary's reported test count is unchanged.
  - **Say what an array's dimensions are.** Every `allocatable`, `pointer` or assumed-shape declaration in a test gets a trailing comment naming its intended bounds, in CTSM's bracket form: `real(r8), allocatable :: snow_depth(:)  ! [begc:endc]`, `integer, allocatable :: filter_snowc(:)  ! [1:num_snowc]`. A bare `(:)` tells the reader nothing about which index space the test is working in, and in this work the index space *is* the subject.
  - **Complementary tests announce each other and differ in as few lines as possible.** Where a pair exists to isolate one axis — the same fixture on a stock column and on an NVP one — each *detailed description* names its twin and states what is held fixed ("the same snow depth and the same nlevsno, differing only in whether the moss slot is claimed"). Never in the topline, which must stand alone. Then hold the pair to it: a difference in setup order, in whether an assignment is written `col%zi(c,0)` or `col%zi(bounds%begc:bounds%endc,0)`, or in the order of assertions is noise the reader must rule out before finding the real difference. Diff the two tests against each other before committing them.
  - **"stock" means a column with no moss slot; the code baseline is "pre-NVP".** Both senses are live in this work — a stock *column* is one with `jbot_sno == 0`, and the plan uses "stock" throughout for `ctsm5.4.028` itself ("bit-for-bit with stock", "reduces to the stock expression"). They coexist harmlessly until "the stock X" appears inside an NVP test, where the reader takes it as "the X used on stock columns" rather than "the X the code used before this work". Write **pre-NVP** for the code baseline whenever the noun after it is also a per-column property: bound, literal, sum loop, staging map. Leave "reduces to the stock one" alone inside a `*_stock` test, where the two senses coincide and the sentence really is about the stock-column bound.
  - **Mutation-test every new assertion, and mutate the right thing.** A test written against working code proves nothing until you have seen it fail: revert the change under test, confirm *that specific assertion* fails, restore, and report which assertion caught which reversion. Three refinements, each learned by getting it wrong. A **mirror** test — the stock-column twin of an NVP case — is blind *by design* to a mutation of the NVP-only term, so it must be mutated the other way, by making that term unconditional. If a mutation trips an *earlier* assertion, pFUnit stops the test there and the one you meant to exercise never runs, so narrow the mutation until it reaches your assertion. And when the claim is that a change *adds* coverage, run the **control**: the mutation must fail with the new test present and pass with it absent.
  - **Watch for degenerate fixtures.** Ask which dimension a fixture holds constant, equal, or symmetric, and what class of bug that blinds it to. Three instances in Task 5d alone: identical per-slot values would have hidden any indexing error; aerosol markers built as a *product* collided across (slot, species), so a transposition was invisible; and `frac_sno_eff = 1` made both legs of a scale-and-unscale the identity, so dropping either leg was invisible. Prefer growth cases to saturation cases when the property under test is a limit — a pack already at capacity cannot demonstrate a cap. A fourth kind, and the hardest to see: a fixture that is a **fixed point of the transformation under test**. The moss geometry both NVP snow fixtures wrote satisfied the interface recursion exactly, so running that recursion one slot too far reproduced it and two guards had zero coverage (Task 16 Step 2a). Where the property under test is that a transformation *stops* somewhere, ask what applying it one step further would change; if the answer is nothing, no physically realistic fixture can test it and the fixture has to be made deliberately inconsistent with the transformation, with the unphysicality explained at the value.
  - **The unit-test build is `CESM_DEBUG` and does not define `NDEBUG`.** `run_tests.py` passes `CMAKE_BUILD_TYPE=CESM_DEBUG`, and the generated `flags.make` carries `-O0 -g -check uninit -check bounds -check pointers -fpe0`. **But do not count on `-check uninit`:** the same `Fortran_FLAGS` line appends `-check nouninit` further along, and the last flag wins, so uninitialised checking is in fact **off** — verified by reading `flags.make` directly. Intel's uninit diagnostic would in any case cover only local scalars of intrinsic type, never derived-type components, which is where the unit tests actually risk it. An uninitialised read will therefore produce garbage silently rather than aborting; a test that must not read an undefined value has to be built so it cannot, not left to the compiler. Three consequences worth planning around: `#ifndef NDEBUG` blocks **do** run, so a routine's internal consistency checks are live and can be counted as coverage; `-fpe0` traps floating-point exceptions, so a zero denominator **aborts the binary** rather than producing `nan` — give every divisor a fixture feeds a nonzero value; and `-check bounds` means a mutation that breaks an index may abort with a bounds error rather than fail an assertion, which still counts as the test catching it, but record which form you saw.
  - **Never justify a fixture by what the code does today.** These tests exist to constrain changes that have not been written yet; "no current code path does that" is a reason to expect the blind spot to matter later, not a reason to accept it.
- **The user runs the system test suites — never run them yourself.** `run_sys_tests`, `clm_short`, and `aux_clm` are the user's to launch, foreground or background. Your verification stops at the build check and unit tests; then hand off and wait. Never report or characterize a suite result the user has not given you.
- **Adding and changing system tests.** Every task states its expectations in a "Testing changes and expectations" block at the bottom. Beyond that:
  - **A suite entry must be assessable as PASS or FAIL from the CIME output of a standard CIME/CTSM `SystemTests` type.** Writing a new type is possible — CTSM already has seven of its own built on `SystemTestsCompareTwo` — but **prefer a unit test to a new test type wherever the requirement can be reached that way.** Be honest about what a stock entry actually assesses: an `SMS` or `ER*` reports that the run completed and that every armed balance check stayed closed while it did, and nothing finer. Which layer received what, whether a weight was applied identically on both sides, whether a guard fired — those are unit tests' work. A coverage row must say which of the two it leans on; "the run exercises it" is not an assessment.
  - **A test lands in the task that first makes it runnable**, not in a testing task at the end. Where a test is wanted before its capability exists, add it early with an `ExpectedTestFails.xml` entry naming the CIME **phase** it fails in, and give the task that makes it pass an explicit step removing the entry. Naming the phase matters: a namelist-build guard aborts at SETUP, and a RUN entry would not cover it.
  - **Never put an `ExpectedTestFails` entry on a test used as a baseline instrument.** A test recorded as an expected RUN fail generates no baseline, silently removing b4b coverage for every later task.
  - **A CIME test that aborts is a FAIL**, so "this configuration must abort cleanly" requirements cannot be suite entries. They stay manual checks, named as such.
  - **Suite categories need no registration** — a category exists because a `<machine ... category="..."/>` line names it. Confirm a new one took with `./cime/scripts/query_testlists --list categories`. Ours are `nvp` (anything with NVP on), `bigleaf_nvp` (NVP on, FATES off) and `fates_nvp` (NVP and FATES on); every NVP entry also carries `aux_clm`, and `fates` where FATES is on.
  - **The NVP test set is required to contain all of the following** (Sam, 2026-08-26). This is a floor, not a target: site-level tests at ALP2 with NVP on, **plus at least two global tests, one with FATES on and one with FATES off**, and at least one exact-restart test (`ERS`, or `ERP` where a PE-layout change adds something). No `ER*` test may exactly duplicate an `SMS` test. The global pair is not an extra — some requirements can only ever be met there, because ALP2 carries no lake, glacier, urban or wetland landunit at all (its fsurdat is `PCT_LAKE = 0`, `PCT_GLACIER = 0`, `PCT_URBAN = 0, 0, 0`, `PCT_WETLAND = 0`), so anything about those landunits under `use_nvp = .true.` is invisible to every site test.
  - **The full test name is the key** for both baselines and `ExpectedTestFails.xml`: `TESTNAME.GRID.COMPSET.machine_compiler.testmods`, with `/` becoming `-` inside each testmod name and `--` joining them. Duration is part of it, so a `Ly2` twin of an `Ld5` test is a different test with no baseline until one is generated. Do **not** append a testid suffix to an `ExpectedTestFails` name — that narrows the entry to a single run.
  - **`ERS` and `ERP` need `STOP_N >= 3`** whatever the `STOP_OPTION`: `REST_N` is computed as roughly half of `STOP_N` plus one and then asserted strictly less than `STOP_N` (`cime/CIME/SystemTests/system_tests_common.py:212-231`). So `ERS_Ly2` is invalid and must be respelled `ERS_Ld731`. `SMS` is unaffected. `ERP` fails at SETUP; `ERS` fails in the RUN phase, after a full build has been paid for.
  - **Do not duplicate an `SMS` test exactly with an `ER*` test** — vary the duration or the configuration.
  - **In a testmod, extend history output, never assign it**: `hist_fincl1 += 'VAR'`. Testmods apply in order and later ones win, so a plain assignment wipes an earlier testmod's list — invisibly on every test that does not compose the testmod that set it.
  - **In a testmod, point at an in-repo file with `$SRCROOT/...`.** XML variables expand in `user_nl_clm`, but the relative-to-absolute conversion applies only to namelist *defaults*, never to a user override, so a relative path reaches `lnd_in` verbatim.
  - **A `landroot`-typed override never enters `ctsm.input_data_list`**, so CIME will not fetch it and will not check it exists at case-setup time. The file must already be present on every machine the test runs on.
  - **Every `use_nvp = .true.` test must cold-start.** `NVPLayerRestart` aborts if `JBOT_SNO` is absent from `finidat`, and `finidat_interp_source` is refused outright at `controlMod.F90:682-686`. Set `finidat = ' '` in the NVP testmod.
  - **Machine and compiler coverage** for new entries: derecho intel, derecho gnu, izumi nag. They catch different things — intel debug traps NaN where gnu does not, nag's runtime pointer checking catches illegal associations neither of the others sees, and gfortran rejects integer-as-logical that Intel accepts as a DEC extension.
  - **Testmod composition order is feature-then-site**, applied consistently, since later testmods win.
  - **`<option name="comment">` says what the test is and why it exists**: type and duration, site and climate, configuration, then the reason this entry earns its place — especially if it is a sentinel for something no other test covers.
  - **Wallclock. Round up, and scale by resolution — not by whether the test is "global".** The cost is asymmetric: a generous wallclock costs some queue priority, an underestimate kills a test after it has already burned the time. The driver is the land-gridcell count, and the grids in `testlist_clm.xml` span orders of magnitude — single point, then `f10_f10_mg37` at 10°x15° (the coarsest global grid), `f45_f45_mg37` at 4°x5°, `f19_g17` at ~1.9°x2.5°, `f09_g17` at ~0.9°x1.25°, `ne30pg3_t232` at ~1°. "Global" is not the axis; `f10_f10` is cheap and `f09_g17` is not.
    - `Ld5` gets `00:20:00`, and that holds everywhere — single-point through `ne30pg3_t232` all use it today.
    - **Long durations are where resolution starts to bite, and a single-point figure must not be carried across.** A single-point `Ly2` runs in `00:30:00`. At `f10_f10_mg37`, `Ld1096`/`Ld1097` — about three years — use `01:40:00`/`01:20:00`, so a two-year run there wants something in that neighbourhood rather than 30 minutes. At `f19_g17`, thirty-odd times the gridcells, the one existing `Ly2` carries `02:00:00`.
    - **Derive the value, do not guess it:** copy the wallclock from an existing entry at the same grid and a comparable duration, and round up when there is no close match. Say in the task where the figure came from, so a reviewer can check the comparison rather than the number.
    - Exact-restart runs the model about 1.5 times over, so scale the matched value accordingly — a single-point `ERS_Ld731` gets `01:00:00`.
  - **Baselines.** Whenever any test is added or changed, a **complete** new baseline is generated, including tests this branch did not touch. `--generate` name is `<branch-basename>.<shorthash>`, e.g. `permanent-nvp-layer.890b60170`; `--compare` is the previous baseline. The human is prompted for this at the post-task review gate.
  - **Amend freely until the human says a system test has been run against a commit; never after.** From that point a fix is a new commit. If it is ambiguous whether anything has been run, ask.
- **Never change a line only for whitespace.** No re-aligning an existing declaration or `use` block to accommodate a longer new name, no stripping trailing whitespace on lines you did not otherwise need to touch, no reindenting untouched code. Let a new line be wider than its neighbors rather than moving them. Whitespace-only edits inflate the diff, land in `git blame`, and manufacture merge conflicts against `ctsm5.4.028_nvp` for no benefit. Check before finishing: `git diff --numstat` and `git diff -w --numstat` must report the same counts for every file.

## Execution Process (user-mandated — applies to every task)

1. Work happens in the user's dedicated checkout on its working branch (confirmed in Task 0).
2. **Every task opens with Step 0: plan review — performed by the orchestrating session, NOT by a subagent** (subagents cannot ask the user anything). Read this task's text against the spec and the actual code it will touch, then **STOP and put to the user**: clarifying questions, problems foreseen, cleanup the task text needs, and anything the task depends on that isn't true yet. Proceed to Step 1 only after the user answers. If Step 0 turns up nothing, say so in one line and ask to proceed anyway — the stop is unconditional.
3. Step 0's resolutions are **written into this plan file** before the implementer is dispatched (amend the task's step text so the subagent actually sees them — it receives only its own task text, never this list, never the Self-Review section).
4. **Fresh implementer subagent per task.** The subagent receives: this plan's task text as amended in Step 0 (only its own task), the spec path, the harvest-worktree path, the dedicated-checkout path, and the Global Constraints above.
5. Each task ends with: verification passes (below) → **one commit** for the task.
   - **Read `git status` before every commit, and make the message describe everything that will be swept in.** `git commit -am` is fine as long as the message actually covers the whole diff. The hazard is not the flag, it is a message written for one change while the tree holds another. A subagent's work often sits uncommitted while the orchestrator writes a plan note; `-a` then sweeps it into that note's commit, under a message describing something else entirely. When that happens, reword the message to cover both, or stage explicitly with `git add <paths>` and split them. This happened at Task 5b: the whole `CombineSnowLayers` reindex landed in a commit titled "Record the ZeroEmptySnowLayers sequencing hazard in Task 5c", and the commit that claimed to do the reindex held only the review fixes. Both were reworded afterwards, but the defect survived two reviews and was caught only by the user reading the log — so the guard has to be at commit time, not at review time.
   - The commit message must describe **everything in the diff**. If the message would need an "also, unrelated:" clause, it is two commits.
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

- [x] **Step 4 — pull two loop bounds forward from Task 14.** `CalculateTotalH2osno` (`WaterStateType.F90:913`) still runs `do j = col%snl(c)+1, 0`, which on an NVP column with `snl = -3` sums `-2..0`: it includes the moss slot **and misses a real snow layer**. `CheckSnowConsistency` (`:958`) scans `-nlevsno+1 : snl(c)`, which likewise covers real snow layers and would abort debug builds — including on a *snow-free* NVP column, where it reaches slot 0 and finds cold-start moss water that is neither `0` nor `spval`. Reindex both to the `get_jtop_snow`/`get_jbot_snow` range. Without this, `errh2osno` cannot close once the stopgap is gone — 5b books `qflx_sl_top_soil` correctly, but the other side of the balance would be wrong — and the armed `endrun` in `BalanceCheckMod` would abort every `use_nvp=.true.` run, including the zero-thickness case. Task 14 keeps the rest of its scope.

- [x] **Step 5 — the ch4Mod comments (spec §2). CORRECTED after review.** This step originally listed four `j == 0` sites (`:3653`, `:3749`, `:3815`, `:3940`) as all being the atmosphere pseudo-layer. **That list was wrong**: it came from a raw grep without checking each site's enclosing loop, and `:3815` is the terminating iteration of a *genuine* snow loop — `do j = -nlevsno+1,0` with a `j >= snl(c)+1` guard, which divides by `dz(c,j)`. The implementer faithfully turned the wrong list into a comment asserting the §2 transformation "must not be applied anywhere in this file", directly above the loop where it must be applied. Two comments now: one scoping the exemption to the `j = 0,nlevsoi` loops only, and one at the snow-resistance loop recording that it is a real snow loop still owed the transformation. The loop itself is left stock, logged in MERGE_NOTES under "Snow-index sites found by sweep, not by audit", and assigned to Task 6.

- [x] **Step 6 — pull two more loop bounds forward from Task 14, so the run does not abort.** `ComputeLiqIceMassNonLake` (`TotalWaterAndHeatMod.F90:282`) and `ComputeHeatNonLake` (`:691`) run `do j = snl(c)+1,0`, the column water and heat totals behind `errh2o` and `errsoi`. On an NVP column that sums the moss slot **and drops the top snow layer** — the same defect as `CalculateTotalH2osno`, and it bites even in the zero-thickness case, because `jbot_sno` is static and does not depend on `dz(c,0)`. Change the **lower** bound only, `snl(c)+1` → `col%get_jtop_snow(c)`; leave the upper bound at `0` so the moss slot lands inside the column total and 5b's snow-to-moss routing stays an internal transfer (`qflx_sl_top_soil` is *not* a term in the `errh2o` expression at `BalanceCheckMod:592-605` — it is snow-sink bookkeeping only). Both reduce to stock at `jbot == 0`, and in the zero-thickness case they sum the same values in the same order plus a trailing zero, so bit-for-bit holds.
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

**The harness facts this task established** — the water-type factory ordering, hand-allocating `temperature_type`/`aerosol_type`, the `nlevsno` and `dzmin`/`dzmax` setup traps, and the pFUnit authoring limits — **were moved into Global Constraints** once they proved to be general, so every task sees them.

- [x] **Step 0: Plan review — DONE.** Both open items closed, and two setup traps established empirically so the implementer does not lose a cycle to each:
  - **(a) The type reachability holds.** `waterstatebulk_type` extends `waterstate_type` (`WaterStateBulkType.F90:26`) and `waterdiagnosticbulk_type` extends `waterdiagnostic_type` (`WaterDiagnosticBulkType.F90:37`), and both are `public` pointer members of `water_type` (`WaterType.F90:142-143`). So `water_inst%waterstatebulk_inst%CalculateTotalH2osno(...)` binds, and `waterdiagnosticbulk_inst` satisfies the `class(waterdiagnostic_type)` dummy.
  - **(b) `ComputeHeatNonLake` stays out** — the user scoped this task to the five assessed candidates, and it was not among them.
  - **The build-environment facts this review established** — no `NDEBUG`, `-fpe0` trapping zero denominators, `-check bounds` changing what a failed mutation looks like — **and the water-factory call ordering are now in Global Constraints.** The consequence that matters here: `CheckSnowConsistency` really does run from inside `CalculateTotalH2osno` under test, so Step 2's third case is genuine coverage of it rather than a hopeful claim.

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

- [x] **Step 7 — mutation-test every new assertion.** A test written against code that already works proves nothing until you have seen it fail. For each new test: revert the corresponding Task 5c change in the working tree, confirm **that specific assertion** fails and that the `jbot = 0` cases still pass, then restore. Report which assertion caught which reversion. This is how `test_initSnowLayers_overfillPack_nvp` was validated in Task 5a, and it is not optional — a test that passes against both the fixed and the broken code is worse than no test, because it reads as coverage.

- [x] **Step 8: Verify.** Build check and unit tests. The `SnowHydrology` binary grows from 17 tests; the new `WaterState` binary appears; total rises above 59. **No suite run is needed** — everything here is test code except one `public ::` declaration, which cannot affect answers. Say so when handing off rather than leaving the user to decide whether to re-run `aux_clm`.
- [x] **Step 9: Commit** `git commit -am "Unit tests for the NVP snow lifecycle reindex"` → review/approval gate. No MERGE_NOTES row is needed for the test files (their branch has no counterpart), but the `public ::` line needs one.

**Findings from the implementation, recorded because they correct earlier text or cost a debugging cycle:**
- **Step 1 was not literally one line.** `PostPercolation_AdjustLayerThicknesses` was already named in the module's `private ::` block, and declaring it `public` while that stood is a duplicate-attribute compile error. Net footprint is +1 `public` / −1 `private`, which is still the whole model-code change.
- **The cap mutation does not abort on bounds**, contrary to this task's Step 0 note and to Task 5c Step 1's earlier wording. Both are corrected in place; see Task 5c Step 1 for where the out-of-bounds access actually lives.
- **`dzmin` / `dzmax_u` / `dzmax_l` are allocated inside `InitSnowLayers`, not by `SnowHydrologySetControlForTesting`**, which only sets the scalar namelist values. Tests needing them call `InitSnowLayers` with zero snow depth as the allocator and free them with `SnowHydrologyClean()` in `tearDown`.
- **Two cap tests could not fail, and Step 7 did not catch it.** `divide_packLimit_stock` (then named `divide_capsAtNlevsno_stock`) started from an already-full stock pack, so the `do while` cap gated nothing and `dzmax_l(nlevsno)` is `huge` — `msno` came out 5 for every cap value from `k<1` to `k<6`. The NVP cap test had the mirror-image hole: starting at capacity, it was identical for caps `k<1`..`k<4`, so an over-strict `merge(2,0,...)` was invisible. Both are now **growth** cases, and each was mutation-tested against the mutation it exists to detect (unconditional cap for the stock mirror, `merge(2,0,...)` for the NVP one). The lesson — mutate what the *mirror* is blind to, and prefer growth cases over saturation cases when the property is a limit — is carried into Task 16 Step 0.
- **`PostPercolation_AdjustLayerThicknesses`'s `snl` dummy is dead** after Task 5c — the body reads `col%get_jtop_snow(c)`/`col%get_jbot_snow(c)` and never touches it. Left in place here (out of scope); worth deleting when a later task next edits that routine, together with the now-unused `associate` entries Task 5c's reviews noted.

---

### Task 5e: Bedrock indexing fix from `adrianna-moss-grass-pft`

**In brief.** Task 5e is a catch-up commit, not development work. It cherry-picks one already-tested fix from the `adrianna-moss-grass-pft` branch — `44a424d03`, "Fix bedrock error (indexing FATES bc \"nlevdecomp\" variables)", resolving ESCOMP/CTSM#4159 — because `use_bedrock = .true.` is required at the ALP2 site and the FATES interface mis-indexes its `nlevdecomp` boundary-condition variables without it. Nothing on this branch depends on the fix until the ALP2 tests arrive at Task 7, which is why it lands here.

**This task is an explicit exception to the Execution Process.** No Step 0, no implementer subagent, no two-stage review. The change is already reviewed and tested on the branch it comes from, and re-reviewing a cherry-pick invites gratuitous divergence from it. The standing build check and unit-test run still apply.

**Files:** `src/utils/clmfates_interfaceMod.F90` (40 insertions, 34 deletions).

- [ ] **Step 1: cherry-pick.** `git cherry-pick 44a424d03`. It applies cleanly to this branch with only line-offset shifts (verified 2026-08-27). Preserve the original authorship and the original message, including its `(cherry picked from commit ...)` trailer — do not reword it to this project's conventions.
- [ ] **Step 2: build check and unit tests**, per the standing rule.

**Testing changes and expectations.**

- **Suites.** `aux_clm` and `fates` pass, every test bit-for-bit against the previous baseline. The `nvp` suites do not exist yet.
- **Answer changes.** None. The fix corrects indexing of the FATES `nlevdecomp` boundary-condition variables, reachable only with `use_bedrock = .true.` at a site whose bedrock depth truncates the decomposition column. No test in `ctsm5.4.028` exercises that combination, so the b4b result is itself the evidence for that claim — if any test moves, the premise was wrong.
- **Tests added or changed.** None.
- **Expected fails.** None.
- **Baselines.** No new baseline: no test added or changed.

**Two commits deliberately NOT brought in** (decided 2026-08-27). `2d62c1ef0` ("Guard against COMPILER=intel + MPILIB=mpi-serial at namelist-build time") and `90ef1c642` ("ch4nn-exception") stay off this branch. The guard aborts `CLMBuildNamelist` whenever `COMPILER=intel` and `MPILIB=mpi-serial` unless `ch4finundatedmapalgo = 'nn'`; in this checkout that variable has no namelist default and `CLMBuildNamelist.pm` never sets it, so the exception never applies by accident and the guard fires on every intel + mpi-serial case, CH4 on or off. That is 58 testlist rows across 22 distinct tests — 18 in `aux_clm`, all 18 of `aux_clm_mpi_serial`, plus `ctsm_sci`, `prealpha`, `matrixcn`, `fates`, `clm_pymods`, `subset_data`, `decomp_init` and `aux_cime_baselines` — failing at **SETUP**, since `case.setup` generates namelists in test mode (`cime/CIME/case/case_setup.py:501-506`). Seven of the 18 already carry expected-fail entries, but every one is a RUN entry and would not cover a SETUP failure. Nothing this branch tests needs the guard: the ALP2 testmod sets `ch4finundatedmapalgo = 'nn'` directly, which is what makes those tests work on intel with mpi-serial. The guard is a usability improvement for whoever else hits ESCOMP/CTSM#3798 and belongs upstream on its own schedule.

---

### Task 5f: `ccs_config` and `cdeps` pointers for the ALP2 grid

**In brief.** Task 5f moves two submodule pointers to match `ctsm5.4.028_nvp`: `ccs_config` to `b6387972b`, which is what defines the `1x1_ALP2` grid, and `cdeps` to `42f9a6b06`. No Fortran, no testmods, no testlist entries — those land at Task 7, which is where the cold-start fix makes NVP actually runnable at that site.

**Both pointers match the merge target, deliberately.** `ctsm5.4.028_nvp` pins exactly these two commits in both `.gitmodules` and its gitlinks (verified 2026-08-27), and matching them is what keeps the eventual merge clean. That is the governing reason, and it outranks the CTSM-side objections below — which are recorded so that a later failure is diagnosable rather than mysterious:

- `ccs_config` `b6387972b` is one commit and a clean fast-forward from `ccs_config_cesm1.0.77`, the tag pinned today. It adds 11 lines across two files: a lat/lon point (60.8231 N, 7.27596 E) and a grid alias, in the same shape as every other `1x1_*` site. Low risk. It is on no upstream branch, which is why the `url` moves to the `samsrabin` fork.
- `cdeps` `42f9a6b06` is one commit ahead of `cdeps1.0.93`. It rewrites the **shared** `CLM_USRDAT.$CLM_USRDAT_NAME` datm stream into three split streams (`.Solar`, `.Precip`, `.TPQW`), changes the forcing-file pattern from `%ym.nc` to `clm1pt_${CLM_USRDAT_NAME}_%ym.nc`, swaps `FSDS Faxa_swdn` for split `SWDIFDS_RAD`/`SWDIRS_RAD`, and drops `ZBOT Sa_z`. The ALP2 compset is `DATM%GSWP3v1` and uses none of it. Existing `CLM_USRDAT` forcing on disk is named `1999-01.nc`, which the new pattern would not match. Its one behaviourally safe piece is the Fortran change, a pure `associated()` guard that leaves GSWP3 untouched.

**Mirror `ctsm5.4.028_nvp`'s `.gitmodules` fields exactly**, including that its `cdeps` entry parks the fork URL in `fxDONOTUSEurl` while `url` stays upstream. That arrangement means a fresh clone cannot fetch `42f9a6b06` from `url`; this checkout already has the object, so it bites only a new clone. Record it in MERGE_NOTES rather than "fixing" it — correcting it would be a divergence from the merge target for no gain.

**The `.gitmodules` `fxtag` and the gitlink must move in the same commit.** `git commit` updates only the gitlink. Verify before committing that these print the same hash, for each submodule:

```
git ls-tree HEAD ccs_config          # and: components/cdeps
git config -f .gitmodules submodule.ccs_config.fxtag
```

**Files:** `.gitmodules`; the gitlinks for `ccs_config` and `components/cdeps`; MERGE_NOTES.

- [ ] **Step 1:** Move both pointers and both `fxtag`s, and set `submodule.ccs_config.url` to the fork. One commit.
- [ ] **Step 2:** Verify `fxtag` and gitlink agree for both submodules, then confirm `./cime/scripts/query_testlists` still parses `testlist_clm.xml`.
- [ ] **Step 3: build check**, per the standing rule.

**Testing changes and expectations.**

- **Suites.** `aux_clm` and `fates` pass, every test bit-for-bit against the previous baseline. The `nvp` suites do not exist yet.
- **Answer changes.** None expected. **If any test does move, the `cdeps` bump is the first thing to check**, and the 18 intel + mpi-serial `CLM_USRDAT`/1PT tests are where to look first — the stream rewrite above is the mechanism. Deliberately **no `ExpectedTestFails.xml` entries in advance**: a speculative entry would mask exactly the signal we want from this run.
- **Tests added or changed.** None.
- **Expected fails.** None.
- **Baselines.** No new baseline: no test added or changed.

---

### Task 6: Percolation, drain, capping, aerosols (SnowHydrologyMod part 2 + AerosolMod)

**In brief.** Task 6 covers the second half of `SnowHydrologyMod` plus `AerosolMod` — everything that moves water and aerosols through the snow pack and out of its bottom — now that index 0 may hold a moss layer rather than the bottom snow layer. Most of it is mechanical reindexing from `snl+1 .. 0` to `get_jtop_snow(c) .. get_jbot_snow(c)`, and must reduce exactly to current behaviour on columns without the moss slot. Two things beyond that:

1. **One real behavioural change.** Where the moss layer has thickness, water percolating out of the bottom snow layer lands in its liquid rather than going straight to soil layer 1, with `qflx_snow_drain` booking it so the snow balance still closes. Where the slot exists but is empty — the stub's default — it passes through to soil as now.
2. **Two divide-by-zero fixes go first** — `frac_iceold` in `clm_driver` and the snow-resistance loop in `ch4Mod`. Both blow up on a zero-thickness moss slot: the first on every timestep with resolved snow, the second in every BGC compset.

**Files:**
- Modify: `src/biogeophys/SnowHydrologyMod.F90` — `SnowWater`, `BulkFlux_SnowPercolation`, `UpdateState_SnowPercolation`, `TracerFlux_SnowPercolation`, `SumFlux_AddSnowPercolation`, `CalcAndApplyAerosolFluxes`, `SnowCapping` + 5 helpers (stock ~3121-3693)
- Modify: `src/biogeophys/AerosolMod.F90` (`AerosolMasses` guard, theirs :570-580)
- **Folded in from the Task 5c unassigned-sites sweep** — all snow-domain, all still stock, none previously owned by any task. Line numbers are ours at Task 5c:
  - `src/biogeophys/SnowHydrologyMod.F90:1237` — `lev_top(c) = snl(c)+1` in `UpdateState_TopLayerFluxes`, called from `SnowWater` at `:1080`. Top-layer sublimation/condensation lands on the moss slot at `snl == -1`.
  - `src/biogeophys/AerosolMod.F90:621-624` — `h2osno_top`/`mss_*_top` read from `snl(c)+1`, inside `AerosolMasses` but outside the `:570-580` guard this task already cites.
  - `src/biogeophys/AerosolMod.F90:788-796` — the eight `mss_*(c,snl(c)+1)` deposition writes in `AerosolFluxes`, a routine this task did not name at all.
  - `src/biogeophys/HydrologyNoDrainageMod.F90:704` — `h2osno_top(c)` from `snl(c)+1`. **Assigned here by domain, not by file:** Task 10 owns this file, but this is the same SNICAR input as `AerosolMod:621` and belongs with the aerosol work. Task 10's entry cross-references it so the two do not both edit it.
  - `src/biogeophys/WaterDiagnosticBulkType.F90:789-790` — `snw_rds_col(c,snl(c)+1:0)` and `(c,-nlevsno+1:snl(c))` in `InitBulkCold`. **Array slices, not loops** — the sweep found these are the easiest kind of site to miss. Cold-start grain radius written across the moss slot.
  - `src/main/clm_driver.F90:1637-1638` — `frac_iceold(c,j)` over `j >= snl(c)+1` in `clm_drv_init`. **Fix this one first: it is a divide by zero in the `dz_nvp = 0` case**, `h2osoi_ice(c,0)/(h2osoi_liq(c,0)+h2osoi_ice(c,0))` with both terms zero, on every timestep the column carries resolved snow.
  - `src/biogeochem/ch4Mod.F90:3793-3841` — the `do j = -nlevsno+1,0` snow-resistance loop in `ch4_tran`, its `j >= snl(c)+1` guard, and its `j == 0` terminating test. **Also a divide by zero in the zero-thickness case** (`icefrac = h2osoi_ice(c,j)/denice/dz(c,j)`), reached whenever `use_lch4`, so in every BGC compset. Task 5c left a comment at the loop saying exactly this; delete the "Left stock for now" sentence when you fix it. Do **not** touch the `j = 0,nlevsoi` loops in the same routine — index 0 there is the atmosphere pseudo-layer, per the other comment.
- **Folded in 2026-08-27 from the per-task run/abort analysis — assigned to no task before now:**
  - `src/biogeophys/SoilFluxesMod.F90:213` and `:280` — both set `j = col%snl(c)+1`, and that `j` is used to split evaporation into liquid and solid by the top layer's liquid:ice ratio (`:237-239`, `:257-259`) and to compute `evaporation_limit` from that layer's contents (`:287`, `:292-293`). These are consistent with stock today, which is why nothing has broken. **This task's own change to `lev_top(c)` at `:1241` desynchronizes them**: the debit moves to `get_jtop_snow(c)` while the split and the limit stay at `snl+1`, one slot away — and with a single snow layer `snl+1` *is* the moss slot. The removal is then no longer bounded by the receiving layer's contents, so the armed negative-mass `endrun`s at `SnowHydrologyMod.F90:1283-1292`/`:1296-1306` can fire. **Change these in the same commit as `:1241`.** Note their branch is not harvestable here: `ctsm5.4.028_nvp` leaves both as `col%snl(c)+1` because under their `snl = -(N_snow+1)` convention `snl+1` *is* the top snow layer. Under our honest `snl` it is not. MERGE_NOTES row required.
  - `src/biogeophys/SnowSnicarMod.F90` — **the plan never opened this file**; it appears nowhere in the plan, the spec, or MERGE_NOTES. Take the two sites that belong to this task's domain: `SnowAge_grain`'s `snl_top`/`snl_btm` window and `cdz` (`:1576-1579`), where `cdz(0) = frac_sno*dz(c,0)` is a **fifth** zero-thickness divide-by-zero at `:1604` and `:1607` — put it on the "fix this one first" list beside `clm_driver.F90:1637` — and the hardcoded `snw_rds(c_idx,0) = snw_rds_min` at `:1721`. Also `src/biogeophys/WaterDiagnosticBulkType.F90:1285` (`ResetBulk` writing `snw_rds_col(column,0)`, called from `SnowHydrologyMod.F90:855` for a freshly created pack — it writes the moss slot instead of the new snow layer). The `SNICAR_RT` slot mapping at `:690-691` is Task 12's, not this task's; cross-reference so the two do not both edit the file blind. **Check the ordering hazard:** once this task reindexes `AerosolMasses`, its `else` branch sets `snw_rds(c,0) = 0`, and SNICAR `endrun`s on an out-of-table grain radius at `:712-721`. That is probably masked by `SnowAge_grain`'s `snw_rds_min` clamp running first, but it depends on `filter_snowc` membership matching between the two calls — verify rather than assume.

**Interfaces:**
- Consumes: Task 2 functions; Task 4 fluxes (`qflx_nvp_*` not yet — Task 13 wires the moss water budget; this task only routes snow-side water).
- Produces: `qflx_snow_percolation(c, col%jbot_sno(c))` = flux out of the snowpack bottom; when `nvp_is_present`, it is deposited in `h2osoi_liq(c,0)` and `qflx_snow_drain` books it; when `nvp_is_empty` or `jbot_sno==0`, stock routing (drain hand-off, nothing stored at 0).

- [ ] **Step 0: Plan review (orchestrator; do not delegate).** Read this task's text against the spec and the code it touches. **STOP** and put to the user: clarifying questions, problems foreseen, cleanup the task text needs, unmet dependencies. Write the resolutions into this plan file before dispatching the implementer. Known going in: Step 4 leaves the `SnowCapping` refactor shape ("gather-and-scatter vs. indexed dummies — whichever produces the smaller diff") to the implementer; decide it here so the two-stage reviewers have a fixed target.

- [ ] **Step 1 — `BulkFlux_SnowPercolation` (theirs :1342-1451, [harvest]):** three-way structure on `jbot_sno`; keep their zero-denominator guard; loop `do j = get_jtop_snow(c), col%jbot_sno(c)` so slot 0 never enters (their version entered j=0 and zeroed it — ours is structural; simpler, note in MERGE_NOTES).
- [ ] **Step 2 — `UpdateState_SnowPercolation` ([harvest+fix]):** deposit `perc(c,j-1)` into layer `j` for `j = get_jtop_snow(c)+1 .. jbot`; then the bottom outflow: `if (nvp_is_present(c)) h2osoi_liq(c,0) += perc(c,jbot)*dtime` else leave for the drain hand-off (**zero-dz [fix]**, spec §4a).
- [ ] **Step 3 — `SumFlux_AddSnowPercolation` (theirs :1890-1953, [harvest]):** `qflx_snow_drain += perc(c,jbot)`; when moss received it, exclude from `qflx_rain_plus_snomelt` (their logic keyed on `nvp_layer_active` → ours keys on `nvp_is_present`).
- [ ] **Step 4 — `SnowCapping` + helpers ([fix], theirs unmodified):** every `(begc:endc, 0)` slice argument becomes a per-column gather at `col%jbot_sno(c)`. Mechanically: change the helper dummies from slices to indexed access, or build local gathered arrays `x_bottom(c) = x(c, col%jbot_sno(c))` before the calls and scatter back after — choose whichever produces the smaller diff (read the six routines first; they are slice-plumbing, ~3181-3244, 3288-3694 stock). Moss is never capped (bottom = bottom SNOW layer).
- [ ] **Step 5 — Aerosols:** `AerosolMasses` guard `j <= col%jbot_sno(c)` ([harvest], their 6-liner); `CalcAndApplyAerosolFluxes` cascade loop ends at `jbot_sno` (structural exclusion of slot 0 — their version leaked `qin` into `mss_*(c,0)`; ours doesn't: MERGE_NOTES row, spec §4g).
- [ ] **Step 5a — unit tests for what this task lands.** Per Global Constraints, write the pFUnit coverage for this task's code before the commit, and put the **mutation evidence** for each new test in the hand-off: name the mutation, and give the binary counts with it applied and with it reverted. A test for which no mutation can be constructed is not pinning anything — cut it rather than keep it. If this task genuinely lands nothing a unit test can reach, say so explicitly in the hand-off and say why; silence is not a considered "none". **This task owes one test specifically**, recorded in the §10 coverage table as an uncovered §10.5 skip path: the zero-`dz` percolation routing. Its design constraint is that the deposit into `h2osoi_liq(c,0)` and the removal of that water from `qflx_rain_plus_snomelt` are complementary halves — **the test must fail if either is done without the other**, because one that checks only the deposit passes on a double-count. The `dz_nvp = 0` case cannot see this at all: neither half runs there, so unit tests are the only coverage it will ever have.
- [ ] **Step 6: Run build check.**
- [ ] **Step 7: Commit** `git commit -am "Route snow percolation, capping, and aerosols around the NVP slot"` → review/approval gate.

**Testing changes and expectations.**

- **Suites.** `aux_clm` and `fates` pass, every pre-existing test bit-for-bit against the previous baseline. The `nvp`, `bigleaf_nvp` and `fates_nvp` suites do not exist yet — Task 7 creates them.
- **Answer changes.** None. Every change here is gated on `nvp_layer_exists`, and at `jbot_sno == 0` the reindexed bounds are identities: `get_jtop_snow(c)` is `snl(c)+1` and `get_jbot_snow(c)` is 0. The two divide-by-zero fixes, the `SoilFluxesMod` evaporation-limiter change and the `SnowSnicarMod` work are all unreachable on a stock column.
- **Tests added or changed.** No system tests. Unit tests only: the zero-`dz` percolation routing (§10 coverage row 10.5, skip path b), which must fail if the deposit into the moss is done without the matching `qflx_rain_plus_snomelt` exclusion or vice versa.
- **Expected fails.** None.
- **Baselines.** No new baseline: no system test was added or changed.

---

### Task 7: Thermal properties + heat-diffusion factors (SoilTemperatureMod part 1)

**In brief.** Task 7 supplies the thermal properties the heat solve consumes — conductivity `thk`, heat capacity `cv`, the interface conductivities `tk`, and the `fact`/`fn` diffusion factors — on columns where index 0 may hold moss rather than the bottom snow layer. The snow branches are reindexed; the moss gets its own `thk`/`cv` from NVP parameters. Three things beyond that:

1. **The factors must always exist.** `ComputeHeatDiffFluxAndFactor` currently skips `j = 0` when `snl == 0`, leaving `fact(c,0)`/`fn(c,0)` undefined. Tasks 8 and 9 consume them, so the guard has to include the moss slot on every NVP column regardless of snow state.
2. **Layerless snow changes owner.** `h2osno_no_layers` heat currently goes into soil layer 1; where moss is present it sits on the moss instead.
3. **A cold-start trap, in two halves, and it gates the whole branch.** `TemperatureType%InitCold` and `WaterStateType%InitCold` both fill snow with a guard that is correct for a stock column and off by one for an NVP column: they write the moss slot and leave the *top* snow layer at `spval`. The temperature half reaches this task's own `SoilThermProp` on the first timestep. The water half is worse — `1e36` enters `begwb` and `h2osno_total`, and `BalanceCheckMod` aborts around timestep 4 on any column that cold-starts with snow, which is every `istsoil` column poleward of 60°. **Until this task lands, no `use_nvp = .true.` run completes on a realistic grid**, so this is the gate on every NVP-enabled system test. `TemperatureType%InitCold` is also shared with Task 10 — whichever lands second must not undo the first.

4. **This task also brings up the ALP2 test infrastructure**, because it is the task that makes `use_nvp = .true.` runnable at all: nothing survives cold start until the two `InitCold` fills above are fixed. The testmods, the testlist entries and the three new suites land here, most of the NVP-on ones behind `ExpectedTestFails` entries that later tasks remove.

**Files:**
- Modify: `src/biogeophys/SoilTemperatureMod.F90` — `SoilThermProp` (stock 602-901), `ComputeHeatDiffFluxAndFactor` (stock 1799-1910)
- Create: `cime_config/testdefs/testmods_dirs/clm/ALP2/`, `.../clm/ALP2Default/`, `.../clm/Nvp/`, `.../clm/NvpMoss03/`, `.../clm/NvpMoss07/`
- Modify: `cime_config/testdefs/testlist_clm.xml`, `cime_config/testdefs/ExpectedTestFails.xml`
- **Folded in from the Task 5c unassigned-sites sweep:** `src/biogeophys/TemperatureType.F90:736` — the `do j = snl(c)+1, 0` snow-temperature fill in `InitCold`, which follows a blanket `spval` assignment at `:732`. On an NVP column at cold start with `snow_depth > 0` it writes 250 K into the moss slot and **leaves the top snow layer holding `spval = 1e36`**, which then reaches `SoilThermProp` — this task's own routine — on the first timestep. **`TemperatureType%InitCold` is shared with Task 10**, which owns `:837` in the same routine; coordinate so the second task to arrive does not undo the first.
- **Folded in 2026-08-27 from the per-task run/abort analysis — assigned to no task before now:** `src/biogeophys/WaterStateType.F90:471-476` — the water twin of the site above, and the more damaging one. `InitCold` blanket-assigns `h2osoi_liq/ice_col(:,-nlevsno+1:) = spval` at `:390-391`, then refills only `if (j > snl(c))`, i.e. `snl+1 .. 0`. On an NVP column snow occupies `snl .. -1`, so index `snl` keeps `spval = 1e36` for both liquid and ice while the moss slot is wrongly filled as snow (`NVPColdStart` later repairs the moss, not the snow). `ZeroEmptySnowLayers` cannot repair it either — its guard is `j < col%get_jtop_snow(c)`, which excludes index `snl` by construction. The `1e36` then enters `begwb`/`endwb` (`TotalWaterAndHeatMod.F90:286`) and `h2osno_total` (`WaterStateType.F90:913`), both reindexed by Task 5c; beginning and ending totals cancel exactly in double precision, so the residual is the whole flux term and `errh2o`/`errh2osno` abort at `BalanceCheckMod.F90:658`/`:845` once past `skip_steps`. Fix it the same way as the temperature twin. Add a MERGE_NOTES row: the Task 5c sweep caught the temperature half and missed this one.

**Interfaces:**
- Consumes: `NVPParamsMod` (`thk_dry_nvp`, `csol_nvp`, `watsat_nvp`), Task 2 functions.
- Produces: `thk(c,0)`/`cv(c,0)` for present moss; `tk(c,0)` = moss↔soil interface conductivity, `tk(c,-1)` = snow↔moss; `fact(c,0)`/`fn(c,0)` **always defined** on NVP columns (their critical gap).

- [ ] **Step 0: Plan review (orchestrator; do not delegate).** Read this task's text against the spec and the code it touches. **STOP** and put to the user: clarifying questions, problems foreseen, cleanup the task text needs, unmet dependencies. Write the resolutions into this plan file before dispatching the implementer. Known going in: Step 3 opens with a rhetorical self-question ("generic loop skips `j==0` and `j==-1`? No —") — rewrite as a direct instruction; and it hands the implementer the zero-thickness half-thickness conductances that Task 8 Step 3 then consumes, so pin the exact expressions here, once, for both tasks. **The test infrastructure below needs three things settled here, none of which the plan can decide for you:** the `dz_nvp` value the partial-cover testmods use (it must be `>= 1.e-6` and physically defensible for an alpine moss mat); the grid and mask for the global FATES-off entry, since `I2000Clm60BgcCropCrujra` is used today only at `f09_t232` and `CLM_USRDAT` — `f10_f10_mt232` is the natural coarse pairing but is not yet proven with this compset; and whether §10 coverage row 10.4e's layerless-snow state is worth a dedicated short run or is adequately crossed by the winter-crossing entries. Also confirm `finidat` for `1x1_ALP2` — the NVP testmod must force a cold start, and if the compset default supplies a `finidat` the `Nvp` testmod's blank assignment has to actually override it.

- [ ] **Step 1 — snow branches:** snow-conductivity loop bound and `bw` guard: `snl(c)+1 <= j <= 0` becomes `get_jtop_snow(c) <= j <= col%jbot_sno(c)` (structural exclusion; do not port their `.NOT.(...j==0)` guard).
- [ ] **Step 2 — NVP `thk(c,0)`/`cv(c,0)` ([harvest] theirs :885-907, :1038-1061):** their Farouki-style `thk` (guards: `dz>0`, `satw>1e-6`) and per-moss-area `cv` with `thin_sfclayer` floor, `if (nvp_is_present(c))`. For `nvp_is_empty(c)`: `thk(c,0)=0`, `cv(c,0)=thin_sfclayer` and they are never consumed (Task 8's continuity row).
- [ ] **Step 3 — interface conductivities:** generic loop skips `j==0` and `j==-1`? No — keep the generic loop over `get_jtop_snow(c) <= j <= nlevgrnd-1` INCLUDING j=0 and j=−1 for `nvp_is_present` columns (their :947-968 shows both degenerate gracefully); add the explicit presence-predicate collapse for `nvp_is_empty`: `tk(c,0) = <direct snow-or-surface↔soil conductance>` and `tk(c,-1)` per §3 zero-dz (half-thickness node-to-interface conductances). Write a comment stating the constraint: "zero-thickness NVP: interface conductances measured to the coincident interface; the layer contributes no resistance."
- [ ] **Step 4 — `h2osno_no_layers` heat ([fix], spec §6 orphan):** `cv(c,1) += cpice*h2osno_no_layers` becomes `cv(c,0) += …` when `nvp_is_present(c)` (layerless snow sits on the moss), else stock.
- [ ] **Step 5 — `ComputeHeatDiffFluxAndFactor` ([fix], their critical gap):** **two tests here, not one.** The outer guard `if (j >= col%snl(c)+1)` becomes `if (j >= get_jtop_snow(c))` — on an NVP column with `snl==0` this includes `j=0`, so `fact(c,0)`/`fn(c,0)` are always computed. The **inner** test at stock `:1892`, `if (j == col%snl(c)+1)`, selects the `capr`-adjusted top-layer `fact` form and must become `j == get_jtop_snow(c)` in the same step. Left stock it picks the second snow layer, or the moss slot when `snl == -1`; and once Task 8 moves the matrix top-row test to `get_jtop_snow(c)`, the row that receives `hs_top`/`dhsdT` and the row carrying the top-layer `fact` correction would be different rows. Both `errsoi` and the matrix divide by the same `fact`, so that mismatch trips no check — it is a silent physics change.

  **An earlier draft of this step justified leaving `fact(c,0)` at 0 for `nvp_is_empty` "because no Task-8/9 consumer touches it on empty columns (verified by the zero-thickness test)". Both halves of that were wrong and it is recorded here so the reasoning is not repeated.** The premise is wrong in the common case: only the *top* layer carries the `dz` factor, so on an NVP column with `snl <= -2` the moss is not the top layer and `fact(c,0) = dtime/thin_sfclayer`, finite. It is exactly zero only at `snl == -1`, where the inner test above selects the moss slot as the top layer — and there it makes `errsoi` divide by zero at `SoilFluxesMod.F90:424` and collapses row -1 to an identity that discards the entire snow-surface flux. The justification is also inverted: a zero-thickness run shows that nothing divides by `fact(c,0)` *today*, and can never show that a later task's consumer will not.
- [ ] **Step 5a — unit tests for what this task lands.** Per Global Constraints, write the pFUnit coverage for this task's code before the commit, and put the **mutation evidence** for each new test in the hand-off: name the mutation, and give the binary counts with it applied and with it reverted. A test for which no mutation can be constructed is not pinning anything — cut it rather than keep it. If this task genuinely lands nothing a unit test can reach, say so explicitly in the hand-off and say why; silence is not a considered "none". **This task also owes the layerless-snow test recorded in the §10 coverage table (10.4e):** with `snl == 0` and `h2osno_no_layers > 0`, Step 4's heat capacity must land on `cv(c,0)` where the moss is present and stay on `cv(c,1)` where the slot is empty or the column is stock.
- [ ] **Step 5b — ALP2 testmods.** Four levels, feature-then-site composition order, no testmod overriding another's `user_nl_clm` line (that is not reliable):
  - `clm/ALP2` — the site base, feature-agnostic: `use_bedrock = .true.` and `ch4finundatedmapalgo = 'nn'`, the latter with an inline pointer to ESCOMP/CTSM#3798. The `nn` line is what lets these run on derecho intel with mpi-serial; the namelist-build guard that would otherwise enforce it is deliberately not on this branch (Task 5e).
  - `clm/ALP2Default` — `include_user_mods: ../ALP2`; sets `fsurdat` to `$DIN_LOC_ROOT/lnd/clm2/testdata/moss/fsurdat/surfdata_ALP2_hist_2000_16pfts_c260427.nc` and nothing else. That is the **plain** ALP2 dataset, deliberately not one of the `_bare`/`_grass`/`_moss` variants: it is the only one with a crop column, so it exercises both the `istsoil` and `istcrop` moss slots, and it carries 18.7% bare soil besides. The file already exists; nothing needs generating.
  - `clm/Nvp` — the feature testmod: `use_nvp = .true.` and `finidat = ' '`, and **nothing else**. With `dz_nvp` and `frac_nvp` left at their namelist defaults of 0 this *is* the zero-thickness case. Comment why the blank `finidat` is mandatory: `NVPLayerRestart` aborts when `JBOT_SNO` is absent from the restart file, and `finidat_interp_source` is refused outright at `controlMod.F90:682-686`.
  - `clm/NvpMoss03` and `clm/NvpMoss07` — each `include_user_mods: ../Nvp`, each setting `dz_nvp` and `frac_nvp` (0.3 and 0.7) directly rather than overriding. The two fractions are what spec §10.6 requires, chosen to sit either side of typical `frac_sno_eff` so both the `frac_sno_eff < frac_nvp` and `frac_sno_eff > frac_nvp` regimes are visited.
- [ ] **Step 5c — testlist entries and the three suites.** Every entry carries `aux_clm`, the applicable `nvp` categories, and `fates` where FATES is on. The set below is the floor Global Constraints require; derive each wallclock from an existing entry at the same grid and duration and say which.
  - **Compset for every FATES-off entry, at ALP2 and global alike: `I2000Clm60BgcCropCrujra`** (`2000_DATM%CRUJRA2024b_CLM60%BGC-CROP_SICE_SOCN_MOSART_SGLC_SWAV`). `I2000` rather than `IHist` because there is no `flanduse_timeseries` for ALP2. It suits this work well beyond that: BGC leaves `use_lch4` on, so it exercises the `ch4Mod` snow-resistance path that Task 6 fixes and that SP compsets skip entirely, and the crop half gives `istcrop` columns so both moss-bearing column types are covered. Its MOSART component is not an obstacle at a single point — `rof` is `null` for every `1x1_*` grid including ALP2, and `1x1_brazil`, `1x1_numaIA` and `1x1_smallvilleIA` all run MOSART compsets that way today, as does `CLM_USRDAT` with this exact compset.
  - **ALP2, NVP off** — `SMS_Ld5_D_Mmpi-serial` and `ERS_Ld5_D_Mmpi-serial` with `clm/ALP2Default`. These are the site's b4b sentinels and the only ALP2 entries expected to pass at this task, so they must **never** carry an `ExpectedTestFails` entry — a test recorded as an expected fail generates no baseline.
  - **ALP2, zero-thickness** — `SMS_Ly2_D_Mmpi-serial` and `ERS_Ld731_D_Mmpi-serial` with `clm/Nvp--clm/ALP2Default`. Winter-crossing, so they exercise the snow transitions; the `ERS` is what satisfies §10 coverage row 10.3.
  - **ALP2, partial cover** — `SMS_Ly2_D_Mmpi-serial` with `clm/NvpMoss03--clm/ALP2Default` and again with `clm/NvpMoss07--clm/ALP2Default`. These are what satisfy row 10.6, and they are the only tests that ever exercise the Task 8 coupling-weight fix — the zero-thickness case cannot, because `frac_nvp_eff` is identically zero there.
  - **Global, NVP on, FATES off** — at `f10_f10_mg37`. This is not optional: ALP2 carries no lake, glacier, urban or wetland landunit, so this entry is the only thing that satisfies row 10.8b.
  - **Global, NVP on, FATES on** — the second required global test.
  - Comments follow the house recipe: type and duration, site and climate, configuration, then why the entry earns its place — and for the two sentinels and the global FATES-off entry, say explicitly what they are sentinels *for*.
- [ ] **Step 5d — `ExpectedTestFails.xml` entries, and the removals they imply.** Every NVP-on entry above fails at this task and must land with an entry naming the phase, keyed on the full test name with no testid suffix. Per §10 coverage: the zero-thickness and global NVP-on entries cannot complete a run before **Task 11**, and the two partial-cover entries not before **Task 14**. Write the removals into those tasks as explicit steps now, in the same commit — an entry with no scheduled removal is how expected fails become permanent.
- [ ] **Step 6: Run build check.**
- [ ] **Step 7: Commit** `git commit -am "NVP thermal properties and always-defined heat-diffusion factors"` → review/approval gate.

**Testing changes and expectations.**

- **Suites.** `aux_clm` and `fates` pass, every pre-existing test bit-for-bit against the previous baseline. **This task creates `nvp`, `bigleaf_nvp` and `fates_nvp`.** Of the entries it adds, only the two NVP-off ALP2 sentinels are expected to pass; every NVP-on entry is an expected fail until Task 11 or Task 14.
- **Answer changes.** None in pre-existing tests. Both `InitCold` fixes touch only the top snow layer of an NVP column — on a stock column the fill guard `j > snl(c)` already covers the whole pack and is unchanged.
- **Tests added or changed.** The ALP2 testmods; testlist entries for the two NVP-off site sentinels, the zero-thickness `SMS`/`ERS` pair, the two partial-cover runs and the two required global tests; and the three suites.
- **Expected fails.** Every NVP-on entry, each naming the phase it fails in. The zero-thickness and global entries retire at Task 11 (Step 4b), the partial-cover pair at Task 14 (Step 3b).
- **Baselines.** **A complete new baseline is required**, including tests this task did not touch. Generate as `<branchbasename>.<shorthash>>`; compare against the previous baseline. Note the NVP-on entries generate no baseline of their own while they are expected fails — the first baselines for them come at Tasks 11 and 14.

---

### Task 8: Banded matrix, RHS, assembly, jtop (SoilTemperatureMod part 2)

**In brief.** Task 8 puts the moss into the tridiagonal heat solve as its own matrix row, mapping the pack with `jtop(c) = snl(c) + jbot_sno(c)` so no special case is needed per snow state. Most of the work is harvesting the reference branch's block structure for the RHS and matrix assembly. Three things beyond that:

1. **The moss↔soil coupling weight is the hard part.** Moss loss must equal soil gain identically for every admissible combination of fractions — including where snow cover exceeds moss cover, the regime in which the reference branch creates energy. Derive the interface flux once and use that one weight in all four sub-blocks.
2. **Zero-thickness moss gets a different row.** With no thickness there is no heat capacity, so row −1 becomes a flux-continuity equation rather than a storage equation.
3. **This task lands `NVPEffectiveFractions`**, the single four-way endmember fraction routine (snow / moss / soil / h2osfc). Tasks 10 through 13 all call it, so it must be written once here rather than re-derived per site.

**Files:**
- Modify: `src/biogeophys/SoilTemperatureMod.F90` — `SoilTemperature` (jtop ~273, load/unload 396-434), `SetRHSVec*` (1913-2353), `SetMatrix*` (2356-2926), `AssembleMatrixFromSubmatrices` (2474-2588 incl. sparsity diagram)
- **Folded in 2026-08-27 from the per-task run/abort analysis — named in no task, no spec section and no MERGE_NOTES row before now:** `src/biogeophys/SoilTemperatureMod.F90:1765`, `lyr_top = snl(c) + 1`, used at `:1769`, `:1774`, `:1777`, `:1782` and `:1789` inside `ComputeGroundHeatFluxAndDeriv`. Stock avoids double-counting the top layer's absorbed solar only because `lyr_top` agrees with the matrix's top-row test. **This task changes that test to `get_jtop_snow(c)`, so the two disagree by one slot and `sabg_lyr(p,snl(c)+1)` is counted twice** — once inside `hs_top_snow` and again as the interior-layer body source. Energy created, up to order 100 W m⁻² in daylight, positive sign. `lwrad_emit_snow(c) = emg(c)*sb*t_soisno(c,snl(c)+1)**4` at `:1670` is the same class of site in the same routine. Change both here, in the same commit as the `jtop` change.
- **Folded in from the Task 5c unassigned-sites sweep:** `src/biogeophys/SoilTemperatureMod.F90:474` — the `if (j >= snl(c)+1)` guard in `SoilTemperature`'s non-urban `fn1` branch. Inside the routine this task names, but outside the `396-434` range it cites; the cited ranges are not exhaustive, so sweep the whole routine rather than working from them.

**Interfaces:**
- Consumes: Task 7 `tk`/`cv`/`fact`/`fn`; `NVPEffectiveFractions` (Task 3); `hs_nvp`/`dhsdT` come from `ComputeGroundHeatFluxAndDeriv` (extended in Task 11 — until then `hs_nvp` is a new local computed as 0; see Step 4).
- Produces: NVP at matrix row −1 (`tvector(c,-1) = t_soisno(c,0)` on NVP columns); `jtop(c) = snl(c) + col%jbot_sno(c)`; conservation-closed moss↔soil coupling weights; flux-continuity row for `nvp_is_empty`.

- [ ] **Step 0: Plan review (orchestrator; do not delegate).** Read this task's text against the spec and the code it touches. **STOP** and put to the user: clarifying questions, problems foreseen, cleanup the task text needs, unmet dependencies. Write the resolutions into this plan file before dispatching the implementer. **Known going in — this is the most important Step 0 in the plan:** Step 2(a) is a half-retracted sentence ("…soil row's coupling weight = `frac_nvp_eff + frac_sno_eff`… NO — the fixed rule:") covering the moss↔soil conduction closure, which spec §3 requires to balance identically for **all** admissible fractions including `frac_sno_eff > frac_nvp` (the regime where their branch creates energy). Derive `w_iface` explicitly, write the algebra into this task's text, and only then dispatch. Also confirm Step 3's band spans stay inside `nband=5`. **Three additions from the 2026-08-27 per-task energy analysis, all of which Step 0 must settle before dispatch:**
  - **Step 2(a) names only the moss↔soil weight, and that is not sufficient.** Because `nband = 5` forbids a direct snow↔soil coupling under this row map — snow bottom is row −2, soil 1 is row +1, a span of 3 — *all* of the snow's downward flux must pass through the moss node. So there is a **snow↔moss** weight as well, and Step 2(a) does not mention it. If the moss row is per-moss-area (which is what spec §3 commits to by writing the storage term as `frac_nvp·ΔT/fact`), the snow→moss term must be `(frac_sno_eff/frac_nvp)·fn_snow_bot` in per-moss-area units — unbounded as `frac_nvp → 0`, which is a legal and first-class namelist state. Two ways out, and Step 0 must pick one and write the algebra: **(i)** make the moss row a **column-area** equation — heat capacity `frac_nvp·cv_moss`, all fluxes column-area, `errsoi` term unchanged — in which case conservation is identical for every admissible fraction and the soil-side weight becomes a free physics choice; or **(ii)** keep per-moss-area `cv` and state explicitly what happens at `frac_sno_eff > frac_nvp` and as `frac_nvp → 0`.
  - **`dz_nvp > 0` with `frac_nvp = 0` is admitted and is a division by zero waiting to happen.** `controlMod.F90:645-677` rejects `dz_nvp = 0 .and. frac_nvp > 0` but never the converse. In that state `nvp_is_present(c)` is true, every `[physics]` gate fires, and the moss row carries real heat capacity — so any `1/frac_nvp` weight is `1/0`. The Global Constraints rule "never assume `frac_nvp = 1`" does not cover it. Either add the validity check in `controlMod` or make the weights `frac_nvp`-free (which option (i) above does for free).
  - **The snow-free row must be written by the `nvp_is_present` branch, not only the empty one.** With `jtop(c) = snl(c) + jbot_sno(c)`, a snow-free NVP column has `jtop = -1`, while the reindexed snow loop `do j = get_jtop_snow(c), get_jbot_snow(c)` is `do j = 0, -1` — **zero-trip**. Step 3 already covers the empty case (`T_0 - T_1 = 0` when `snl == 0`). Step 2 must cover the *present* case in the same state, or row −1 is an exact zero row inside `[jtop, jbot]`, `dgbsv` returns a nonzero info code, and `BandDiagonalMod.F90:212` `endrun`s **on every snow-free NVP column, every timestep**. **This task also lands `NVPEffectiveFractions` in `NVPLayerDynamicsMod`** — deferred out of Task 3 so nothing commits uncalled; this is its first consumer. It is THE single 4-way derivation (spec §4b), so write it once here and have Tasks 10-13 call it:

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
- [ ] **Step 5a — unit tests for what this task lands.** Per Global Constraints, write the pFUnit coverage for this task's code before the commit, and put the **mutation evidence** for each new test in the hand-off: name the mutation, and give the binary counts with it applied and with it reverted. A test for which no mutation can be constructed is not pinning anything — cut it rather than keep it. If this task genuinely lands nothing a unit test can reach, say so explicitly in the hand-off and say why; silence is not a considered "none". **This task owes two tests specifically**, both recorded in the §10 coverage table as uncovered §10.5 skip paths: the **§3 degenerate row** — the flux-continuity equation the moss row carries when `nvp_is_empty`, including its collapse to `T_0 - T_1 = 0` at `snl == 0` — and the **§4b fraction rule**, that `NVPEffectiveFractions` returns `frac_nvp_eff = 0` whenever `dz(c,0) = 0` and that the 4-way partition sums to 1 across admissible fractions. Both are first writable here, because neither the row nor the routine exists before this task. **A third test, from §10 coverage row 10.4e:** that `cv(c,0)` is actually consumed once the moss row is in the solve. Between Task 7 and this task the layerless-snow heat capacity is assigned to a row the system does not contain, because `jtop(c) = snl(c) = 0` on a snow-free NVP column — it is silently absent from the solve, and no armed check sees it.
- [ ] **Step 6: Run build check.**
- [ ] **Step 7: Commit** `git commit -am "NVP row in the heat solve with conservation-closed coupling and zero-dz continuity"` → review/approval gate.

**Testing changes and expectations.**

- **Suites.** `aux_clm` and `fates` pass, every pre-existing test bit-for-bit against the previous baseline. The two NVP-off ALP2 sentinels also compare b4b. Every NVP-on entry remains an expected fail.
- **Answer changes.** None outside NVP columns. The `jtop(c) = snl(c) + jbot_sno(c)` change reduces to stock `snl(c)` at `jbot_sno == 0`; the risk to watch is Step 2's rewrite of the `SetRHSVec_*`/`SetMatrix_*` block structure, where re-associating an existing floating-point expression would move the last bit on stock columns. Say in the hand-off which expressions were touched.
- **Tests added or changed.** No system tests. Unit tests only: the §3 degenerate row and the §4b fraction rule (§10 coverage row 10.5, skip paths c and d), plus the row-10.4e test that `cv(c,0)` is actually consumed once the moss row is in the solve.
- **Expected fails.** Unchanged; none retire here.
- **Baselines.** No new baseline: no system test was added or changed.

---

### Task 9: Phase change (SoilTemperatureMod part 3)

**In brief.** Task 9 adds melt and freeze in the moss layer and reroutes the snow-versus-soil discriminators in `Phasechange` and `PhaseChangeH2osfc` so they key off the bottom snow index rather than a literal 0. The weighting must match whatever Task 8 settled as its single coupling rule. Two things beyond that:

1. **Moss phase change is accounted separately.** It uses plain `tfrz`, stays out of `qflx_snomelt`/`qflx_snofrz` but inside `xmf`, and moss ice is capped at pore capacity with the excess pushed onward.
2. **`PhaseChangeH2osfc`'s `snl == 0` branches are a trap.** They write slot 0 as a *newly created* snow layer. On an NVP column that must instead create the layer at the bottom snow index, or deposit into the moss where one is present — and must not overwrite moss temperature with the surface-water temperature.

**Files:**
- Modify: `src/biogeophys/SoilTemperatureMod.F90` — `Phasechange` (stock 1133-1540), `PhaseChangeH2osfc` (stock 904-1130)

**Interfaces:**
- Consumes: `fact(c,0)` (Task 7), `NVPEffectiveFractions`, `nvp_is_present`.
- Produces: NVP melt/freeze with plain-`tfrz` criterion, per-moss-area weighting consistent with Task 8; NVP excluded from `qflx_snomelt/snofrz` but in `xmf`; `t_nvp_col` sync; moss ice capped at pore capacity (`watsat_nvp*denice*dz(c,0)`) with excess pushed per spec §4a.

- [ ] **Step 0: Plan review (orchestrator; do not delegate).** Read this task's text against the spec and the code it touches. **STOP** and put to the user: clarifying questions, problems foreseen, cleanup the task text needs, unmet dependencies. Write the resolutions into this plan file before dispatching the implementer. Known going in: Step 1's weighting must be re-derived against whatever Task 8 Step 0 settled as the single weight rule — carry that derivation in verbatim rather than restating it. Step 3 trails off mid-reasoning ("else stock `(c,0)`-as-snow… careful:"); resolve it against the spec §6 orphan table first.

- [ ] **Step 1 — `Phasechange` [harvest]** their buried (`snl<0`, :1490-1505) and exposed (`snl==0`, :1526-1550) NVP blocks, their `hm(c,0)`/T-correction weighting (:1658-1677, 1783-1893) re-derived against Task 8's single weight rule, their melt-flux exclusions (:1829-1843) and `t_nvp_col` re-sync (:1907-1913). All guarded `nvp_is_present` (empty moss: no mass, block skipped — [fix] explicit guard rather than relying on zero mass).
- [ ] **Step 2 — snow/soil boundary tests:** every `j < 1`/`j <= 0` snow-vs-soil discriminator in `Phasechange` becomes `j <= col%jbot_sno(c)` EXCEPT the new NVP-specific `j == 0` blocks (spec §2 idiom table). **Include the initialization guard at stock `SoilTemperatureMod.F90:1248`, `if (j >= snl(c)+1)`, which the earlier draft of this step did not name.** It is the write guard for `imelt(c,j)` at `:1251` and for `qflx_snomelt_lyr`/`qflx_snofrz_lyr` at `:1266-1267`, and on an NVP column it stops one slot short of the top snow layer. `imelt_col` has **no restart registration anywhere in the tree** and is read unconditionally by `SnowCompaction` at `SnowHydrologyMod.F90:2026`, inside the guard Task 5c reindexed — so a base run and a restarted run take different compaction branches for the top snow layer, with no crash and no balance failure. **This is the exact-restart gate: it presents only as a `COMPARE_base_rest` FAIL.** The same one-line fix also stops `qflx_snomelt_lyr`/`qflx_snofrz_lyr` reaching history as `spval` on that slot.
- [ ] **Step 3 — `PhaseChangeH2osfc` [harvest+fix]:** their `snl<0` reroutes to `(c,jbot)` = bottom snow ([harvest], re-expressed via `jbot_sno`); the `snl==0` branches ([fix], their gap): frozen-h2osfc ice deposits into moss when `nvp_is_present` (with the pore-capacity cap) else stock `(c,0)`-as-snow… careful: stock `snl==0` writes `h2osoi_ice(c,0)`/`t_soisno(c,0)` as the *newly created* snow slot — on NVP columns that must become `(c,jbot_sno)` creation or moss deposit per the spec §6 orphan table (moss when present). Do not overwrite moss temperature with `t_h2osfc` (spec §3 fix).
- [ ] **Step 3a — unit tests for what this task lands.** Per Global Constraints, write the pFUnit coverage for this task's code before the commit, and put the **mutation evidence** for each new test in the hand-off: name the mutation, and give the binary counts with it applied and with it reverted. A test for which no mutation can be constructed is not pinning anything — cut it rather than keep it. If this task genuinely lands nothing a unit test can reach, say so explicitly in the hand-off and say why; silence is not a considered "none".
- [ ] **Step 4: Run build check.**
- [ ] **Step 5: Commit** `git commit -am "NVP phase change with consistent weighting and h2osfc rerouting"` → review/approval gate.

**Testing changes and expectations.**

- **Suites.** `aux_clm` and `fates` pass, every pre-existing test bit-for-bit against the previous baseline. The NVP-off ALP2 sentinels compare b4b. Every NVP-on entry remains an expected fail — this task makes exact restart *possible* by fixing the `Phasechange` initialization guard, but the NVP-on runs still cannot complete, so the `ERS` entry stays an expected fail until Task 11.
- **Answer changes.** None outside NVP columns.
- **Tests added or changed.** No system tests. Unit tests only, for the phase-change behaviour this task lands.
- **Expected fails.** Unchanged; none retire here.
- **Baselines.** No new baseline: no system test was added or changed.

---

### Task 10: Ground temperature blends + surface humidity

**In brief.** Task 10 turns the ground temperature into a four-way blend over snow, moss, soil and surface water, using the same fraction call at every site, and does the same for surface specific humidity. Two things beyond that:

1. **Four blend sites plus cold start must agree.** `t_grnd`, `t_grnd0`, the `BiogeophysPreFluxCalcs` surface temperature, and the `HydrologyNoDrainage` blend all have to mean the same thing on an NVP column, and `TemperatureType%InitCold` must produce that same thing at cold start. That routine is shared with Task 7.
2. **Humidity must be gated on the layer existing, not on its fraction.** The moss retention curve supplies `qg`; a column with a nonzero moss fraction but no actual layer would otherwise read bone-dry.

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
- [ ] **Step 3a — unit tests for what this task lands.** Per Global Constraints, write the pFUnit coverage for this task's code before the commit, and put the **mutation evidence** for each new test in the hand-off: name the mutation, and give the binary counts with it applied and with it reverted. A test for which no mutation can be constructed is not pinning anything — cut it rather than keep it. If this task genuinely lands nothing a unit test can reach, say so explicitly in the hand-off and say why; silence is not a considered "none".
- [ ] **Step 4: Run build check. Step 5: Commit** `git commit -am "4-way ground temperature and humidity blends"` → review/approval gate.

**Testing changes and expectations.**

- **Suites.** `aux_clm` and `fates` pass, every pre-existing test bit-for-bit against the previous baseline. The NVP-off ALP2 sentinels compare b4b. Every NVP-on entry remains an expected fail.
- **Answer changes.** None outside NVP columns — but this is the task where that claim is easiest to break. `frac_soil = max(0._r8, 1 - frac_sno_eff - frac_h2osfc - frac_nvp_eff)` is **not** algebraically identical to the stock `(1 - frac_sno_eff - frac_h2osfc)` wherever the stock quantity would go negative, because of the clamp. Substitute the centralized fraction only where it is provably identical, or keep the stock expression on `jbot_sno == 0` columns, and say in the hand-off which was done at each of the four call sites.
- **Tests added or changed.** No system tests. Unit tests only, for the blends this task lands.
- **Expected fails.** Unchanged; none retire here.
- **Baselines.** No new baseline: no system test was added or changed.

---

### Task 11: Surface fluxes + ground heat flux + energy check

**In brief.** Task 11 gives the moss its own surface energy and moisture fluxes — sensible heat, evaporation, longwave emission — fills the ground heat flux `hs_nvp` that Task 8 stubbed to zero, and adds the moss storage term to the soil energy balance check. Two things beyond that:

1. **Flux seen by the atmosphere must equal flux lost by the moss.** The `hs_nvp` accumulation over patches has to use the same patch gate as the flux definitions, or the two disagree for any non-vegetated patch structure.
2. **This task lands `NVPEvapResistance`** as one shared function. The reference branch has the formula inline and duplicated in three files, which is how its two `lw_grnd` sites drifted apart.

**Files:**
- Modify: `src/biogeophys/SoilTemperatureMod.F90` (`ComputeGroundHeatFluxAndDeriv` stock 1543-1796: `lwrad_emit_nvp`, `hs_nvp` fill, `eflx_gnet_nvp`), `src/biogeophys/BareGroundFluxesMod.F90` (their +184 diff), `src/biogeophys/CanopyFluxesMod.F90` (their +162 diff), `src/biogeophys/SoilFluxesMod.F90` (their +358 diff: `qflx_evap_grnd_eff`, lw_grnd both places, `eflx_soil_grnd`, errsoi)

**Interfaces:**
- Consumes: Task 10 blends, Task 4 fluxes, `NVPEvapResistance`, `NVPEffectiveFractions`, `fwet_nvp_col`.
- Produces: `hs_nvp(c)` (fills Task 8's zero local), `eflx_sh_nvp_patch`, `qflx_ev_nvp_patch`, 4-way `qflx_evap_grnd_eff`, errsoi with moss storage term weighted `frac_nvp` ([fix], spec §3) and skipped when `nvp_is_empty` ([fix], spec §3 zero-dz).

- [ ] **Step 0: Plan review (orchestrator; do not delegate).** Read this task's text against the spec and the code it touches. **STOP** and put to the user: clarifying questions, problems foreseen, cleanup the task text needs, unmet dependencies. Write the resolutions into this plan file before dispatching the implementer. Known going in: (a) Step 2 references `sabg_nvp`, which Task 12 produces — confirm the forward dependency is a zero-valued placeholder here (as `hs_nvp` was in Task 8 Step 4) and not a build break; (b) **this task lands `NVPEvapResistance` in `NVPLayerDynamicsMod`**, deferred out of Task 3 so nothing committed uncalled. Their branch has no such function — the formula is inline in their `NVPEvaporation` (`<worktree>/src/biogeophys/NVPLayerDynamicsMod.F90:306-388`), and they duplicate it in three files. Extract it once here, using the Task 1 `rnvp_min`/`rnvp_amp`/`rnvp_exp`/`rnvp_ice` parameters, and have both BareGroundFluxes and CanopyFluxes call it.

- [ ] **Step 1 [harvest]:** their per-surface resistances (`raiw_nvp`, dew branch, `wtgq_*` 4-way) — `rnvp` via `NVPEvapResistance` (single source, Task 3). **[fix]** one gate everywhere: `frac_nvp_eff > 0` (from the centralized call) in BOTH modules.
- [ ] **Step 2 [harvest]:** `lw_grnd` 4-way in BOTH SoilFluxes places and BOTH CanopyFluxes places (their two-places lesson, spec §4b); `eflx_soil_grnd` solar/latent terms per their :472-486 with Task 12's partition names (`sabg_nvp`); `qflx_evap_grnd_eff` (:433-446) and its uses (:553-571).
- [ ] **Step 3 [harvest+fix]:** `ComputeGroundHeatFluxAndDeriv`: `lwrad_emit_nvp = emg*sb*t_soisno(c,0)**4`; `hs_nvp` accumulation over patches — **[fix]** the accumulation must use the same patch gate as the flux definitions so atmosphere-seen flux == moss-lost flux for any patch structure (audit's non-veg-patch inconsistency).
- [ ] **Step 4 [fix]:** errsoi at `SoilFluxesMod.F90:423-424`: moss term `- frac_nvp * (t_soisno(c,0)-tssbef(c,0))/fact(c,0)` when `nvp_is_present`; nothing when empty. **The snow-term window has TWO halves and both must change** — `j >= col%snl(c)+1 .and. j < 1` becomes `j >= col%get_jtop_snow(c) .and. j <= col%jbot_sno(c)`. An earlier draft named only the `j < 1` half. Fixing only the upper half leaves the window at `snl+1 .. -1`, which excludes the true top snow layer at `snl(c)` — the very layer Task 8's `jtop` change makes the solve start updating. Its unaccounted storage is `frac_sno_eff·cv·ΔT/dtime`, order 1–100 W m⁻², against a fatal threshold of `1e-4` at `BalanceCheckMod.F90:1113`. **This step is the difference between energy closing at this task and never closing at all**, so treat the two-half change as the point of the step rather than a detail of it.
- [ ] **Step 4a — unit tests for what this task lands.** Per Global Constraints, write the pFUnit coverage for this task's code before the commit, and put the **mutation evidence** for each new test in the hand-off: name the mutation, and give the binary counts with it applied and with it reverted. A test for which no mutation can be constructed is not pinning anything — cut it rather than keep it. If this task genuinely lands nothing a unit test can reach, say so explicitly in the hand-off and say why; silence is not a considered "none".
- [ ] **Step 4b — retire the `ExpectedTestFails.xml` entries this task earns.** Task 7 Step 5d added entries for every NVP-on test because none could complete a run. This task is where the zero-thickness and global NVP-on entries start passing — Step 4's `errsoi` window is the last thing keeping them from closing. **Remove those entries in this task's commit**, and if any of them still fails, say so in the hand-off rather than restoring the entry: a still-failing test after this task means a fix is missing, not that the expectation was right. The two partial-cover entries stay; they are Task 14's to retire.
- [ ] **Step 5: Run build check. Step 6: Commit** `git commit -am "NVP surface energy/moisture fluxes and energy-balance accounting"` → review/approval gate.

**Testing changes and expectations.**

- **Suites.** `aux_clm` and `fates` pass, every pre-existing test bit-for-bit against the previous baseline. **The zero-thickness and global NVP-on entries start passing here** — Step 4's `errsoi` window is the last thing keeping them from closing. The two partial-cover entries remain expected fails until Task 14.
- **Answer changes.** None in pre-existing tests. NVP-on answers are established for the first time at this task, so there is no prior baseline for them to move against.
- **Tests added or changed.** No new entries. Step 4b removes the `ExpectedTestFails.xml` entries for the zero-thickness and global NVP-on tests.
- **Expected fails.** Zero-thickness and global entries retired. The two partial-cover entries remain, and are Task 14's to retire. If a retired test still fails, that is a missing fix — report it rather than restoring the entry.
- **Baselines.** **A complete new baseline is required.** The retired entries produce comparable output for the first time, so this is where their baselines come from. Generate as `<branchbasename>.<shorthash>>`; compare against the previous baseline.

---

### Task 12: Radiation (constant transmissivity)

**In brief.** Task 12 splits absorbed shortwave between the moss and what lies beneath it using a constant transmissivity, and blends moss albedo into the ground albedo over the exposed-moss fraction. Two things beyond that:

1. **Transmissivity ≡ 1 must reproduce current behaviour exactly**, and the `sabg_lyr` conservation `endrun` stays armed — no bypass, no widened tolerance.
2. **"The flux reaching the moss surface" means different things by snow state** — SNICAR's through-snow output when snow is resolved, the ground share of `sabg` when it is not. That has to be settled before implementation; the task text currently reasons about it without concluding.

**Files:**
- Modify: `src/biogeophys/SurfaceRadiationMod.F90` (stock 745-852), `src/biogeophys/SurfaceAlbedoMod.F90` (ground-albedo blend, their :868-879 region), `src/biogeophys/SolarAbsorbedType.F90` (`sabg_nvp_patch` exists from Task 4)

**Interfaces:**
- Consumes: `nvp_transmissivity`, `alb_nvp_vis/nir`, `NVPEffectiveFractions`, `sabg_lyr`.
- Produces: `sabg_nvp(p)` = `(1-nvp_transmissivity) * <flux reaching NVP surface>`; slot 1 keeps the transmitted remainder; `sabg_lyr` sums conserve with the `endrun` **armed** (no bypass — spec §4f); ground albedo blend uses `alb_nvp_vis/nir` over the exposed-moss fraction.

- [ ] **Step 0: Plan review (orchestrator; do not delegate).** Read this task's text against the spec and the code it touches. **STOP** and put to the user: clarifying questions, problems foreseen, cleanup the task text needs, unmet dependencies. Write the resolutions into this plan file before dispatching the implementer. Known going in: **Step 1 contains unretracted thinking-out-loud** ("`sabg_nvp(p) = (1-nvp_transmissivity)*sabg_lyr(p,1)` … NO — slot semantics:") — settle what "the flux reaching the NVP surface" is in each `snl` regime and rewrite the step before dispatch. Spec §4f requires transmissivity ≡ 1 to reproduce stock exactly and the `sabg_lyr` `endrun` to stay armed. **Three things folded in 2026-08-27 from the per-task run/abort analysis:**
  - **The `sabg_lyr` `endrun` becomes load-bearing at this task and was not before.** `SurfaceRadiationMod.F90:830` compares `sum(sabg_lyr(p,:))` over the *whole allocated range* against `sabg_snow(p)`, so it verifies the sum and never the distribution — which is why it passes through Tasks 6–11 even though SNICAR's window is misaligned by a slot. The moment Step 1 redistributes between slots 0 and 1 it starts to bite. Specifically: on a column with `snl <= -1`, SNICAR has **already** written a nonzero share into slot 0, because `SNICAR_RT` hardcodes `snl_btm = 0` (`SnowSnicarMod.F90:690`). If `<reaching>` in Step 1 is read as `sabg_lyr(p,1)` alone, that pre-existing slot-0 share is destroyed and the `endrun` fires. If it is `sabg_lyr_old(p,0) + sabg_lyr_old(p,1)`, the sum is preserved. Settle which, here.
  - **`src/biogeophys/SnowSnicarMod.F90` belongs partly to this task** and was in no task's scope until now. Take the `SNICAR_RT` slot mapping: `snl_btm = 0` / `snl_top = snl_lcl+1` at `:690-691` make SNICAR read the moss slot as the bottom snow layer and drop the true top snow layer from the optics, in every configuration. Task 6 takes the `SnowAge_grain` half; cross-reference so the two do not edit the file blind.
  - **`sabg_nvp_patch` is `NaN` in every configuration and must be zeroed before it is consumed.** `SolarAbsorbedType.F90:134` allocates it `= nan` with no `spval` in `InitHistory` and no `0._r8` in `InitCold` — it is the one Task 4 variable that missed the three-part pattern, because `SolarAbsorbedType` does not use the `AllocateVar1d(ival=)` helper. If this task's or Task 11's consumer writes an ungated `- sabg_nvp(p)`, **every patch in a `use_nvp = .false.` run gets `NaN` in `eflx_soil_grnd` and `sabg_chk` and the whole baseline comparison fails.** Add the `InitCold` zeroing in whichever of Tasks 11/12 lands first.

- [ ] **Step 1:** In `SurfaceRadiation`, after the existing snl-dependent `sabg_lyr` fill: on `nvp_is_present` columns, `sabg_nvp(p) = (1-nvp_transmissivity)*sabg_lyr(p,1)` … NO — slot semantics: the flux reaching the NVP surface is `sabg_lyr(p,1)` (SNICAR's through-snow output) for `snl<0`, or `sabg(p)`'s ground share for `snl==0`; set `sabg_lyr(p,0) = sabg_nvp(p)` and `sabg_lyr(p,1) = <reaching> - sabg_nvp(p)`. Transmissivity forced to 1 when `nvp_is_empty` (fraction rule makes `sabg_nvp=0`). Hardcoded stock splits (`snl==-1` 0.6/0.4) keep their slot arithmetic but slot indices via `jbot_sno` (spec §4f "slot numbers become jbot_sno-relative").
- [ ] **Step 2:** `sabg_pen`, `sabg_snl_sum`, and the conservation check updated for the new slot-0 meaning; the `endrun` tolerance unchanged and armed.
- [ ] **Step 3:** `SurfaceAlbedoMod`: exposed-moss fraction of the ground albedo uses `alb_nvp_vis/nir` (simplified from their Beer-effective form; note MERGE_NOTES row: theirs supersedes at merge). `albsfc` (under-snow) stays soil albedo (their SNICAR handles under-snow moss at merge; our slot-0 assignment covers the stub).
- [ ] **Step 4:** `sabg_chk` consistency — note it is computed in **`SoilTemperatureMod.F90:1689`** (`frac_sno_eff*sabg_snow + (1-frac_sno_eff)*sabg_soil`) and consumed at `BalanceCheckMod.F90:989`, not in `SoilFluxesMod` as an earlier draft of this step said. If `eflx_soil_grnd`'s solar bracket (`SoilFluxesMod.F90:348`) gains a `sabg_nvp` term and `sabg_chk` does not, `errseb` fails by exactly the moss's absorbed solar — the one thing `errseb` can actually detect, with a fatal `endrun` at `BalanceCheckMod.F90:1096` at tolerance `1e-5`. Consistency check (Task 11's `eflx_soil_grnd` used the same partition — verify with a grep that `sabg_nvp` appears in exactly: SurfaceRadiation (producer), eflx_soil_grnd, sabg_chk, hs_nvp).
- [ ] **Step 4a — unit tests for what this task lands.** Per Global Constraints, write the pFUnit coverage for this task's code before the commit, and put the **mutation evidence** for each new test in the hand-off: name the mutation, and give the binary counts with it applied and with it reverted. A test for which no mutation can be constructed is not pinning anything — cut it rather than keep it. If this task genuinely lands nothing a unit test can reach, say so explicitly in the hand-off and say why; silence is not a considered "none".
- [ ] **Step 5: Run build check. Step 6: Commit** `git commit -am "Constant-transmissivity NVP radiation partition"` → review/approval gate.

**Testing changes and expectations.**

- **Suites.** `aux_clm` and `fates` pass, every pre-existing test bit-for-bit against the previous baseline. The zero-thickness and global NVP-on entries, passing since Task 11, compare b4b against the most recent baseline containing them. The two partial-cover entries remain expected fails until Task 14.
- **Answer changes.** **None in any test that is currently passing** — and that is a falsifiable claim, not a hope. Spec §4f forces transmissivity to 1 wherever `dz(c,0) = 0`, so a zero-thickness moss absorbs nothing and the partition reduces to stock deposition. Every passing NVP entry runs `clm/Nvp`, which is the `dz_nvp = 0` case. **So if the zero-thickness or global entries move at this task, the forced-transmissivity rule is broken.** Real answer changes are confined to the partial-cover configurations, which no passing test exercises yet.
- **Tests added or changed.** No system tests. Unit tests only, for the radiation partition this task lands.
- **Expected fails.** Unchanged; none retire here.
- **Baselines.** No new baseline, given the claim above holds. If a passing NVP entry does move, treat it as a defect rather than regenerating around it.

**Note carried from §10.7.** That row was dropped, so spec §1.9's requirement — transmissivity = 1 reproduces stock energy deposition everywhere — is verified by no test. This task's reviewers carry it.

---

### Task 13: NVP water balance + soil-side plumbing

**In brief.** Task 13 closes the moss water budget — in from rain, snowmelt, snow percolation and dew; out by evaporation, drainage and an ice push to snow — and wires the result into soil hydrology, infiltration, condensation renewal and surface water. Three things beyond that:

1. **The withheld and credited amounts must match exactly.** Whatever `SetQflxInputs` holds back from the soil is precisely what the moss is credited, in the same timestep, at every snow state. Any mismatch is a rain-through-snow leak.
2. **The reference branch's evaporation clamp creates water.** Replace `max(0, h2osoi_net)` with a limiter on the demand side: cap evaporation at what is available and pass the residual demand to the soil evaporation pathway.
3. **This task lands the retention-curve and hydraulic-conductivity functions**, which may require adding `NVPLayerDynamicsMod` and `NVPParamsMod` to the pFUnit build's source list.

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
- [ ] **Step 5a — unit tests for what this task lands.** Per Global Constraints, write the pFUnit coverage for this task's code before the commit, and put the **mutation evidence** for each new test in the hand-off: name the mutation, and give the binary counts with it applied and with it reverted. A test for which no mutation can be constructed is not pinning anything — cut it rather than keep it. If this task genuinely lands nothing a unit test can reach, say so explicitly in the hand-off and say why; silence is not a considered "none".
- [ ] **Step 6: Run build check. Step 7: Commit** `git commit -am "NVP water balance and soil-side routing"` → review/approval gate.

**Testing changes and expectations.**

- **Suites.** `aux_clm` and `fates` pass, every pre-existing test bit-for-bit against the previous baseline. The zero-thickness and global NVP-on entries, passing since Task 11, compare b4b against the most recent baseline containing them. The two partial-cover entries remain expected fails until Task 14.
- **Answer changes.** **None in any currently passing test.** Every term this task adds is gated on `nvp_is_present(c)`, which is false throughout the `dz_nvp = 0` configuration that all passing NVP entries run. As at Task 12, a move in the zero-thickness or global entries means a gate is missing, not that the expectation was wrong. Real changes are confined to partial cover.
- **Tests added or changed.** No system tests. Unit tests only, for the moss water budget and the soil-side routing.
- **Expected fails.** Unchanged; none retire here.
- **Baselines.** No new baseline, given the claim above holds.

---

### Task 14: Conservation accounting

**In brief.** Task 14 makes moss water and heat appear in the column totals exactly once, keeps moss out of the snow total, and adds the moss-to-snow ice flux as a snow source. Two things beyond that:

1. **Mass and heat must share one predicate.** The reference branch adds the water but omits the heat when `snl == 0`, which is the kind of asymmetry that only shows up as a balance failure much later.
2. **No `select type` downcast** for the new snow source — either move the flux to the generic water-flux type, or apply the correction in a bulk-only wrapper. Some of this task was pulled forward into Task 5 to keep the balance checks from firing; verify rather than redo those parts.

**Files:**
- Modify: `src/biogeophys/TotalWaterAndHeatMod.F90` (:282, :485, :688-757, :1015 stock), `src/biogeophys/WaterStateType.F90` (`CalculateTotalH2osno` :891, `CheckSnowConsistency` :936), `src/biogeophys/BalanceCheckMod.F90` (snow sources :813-840 their numbering)

**Interfaces:**
- Consumes: everything prior.
- Produces: moss water+heat in column totals exactly once (both `snl` states); moss excluded from `h2osno_total`; `qflx_nvp_to_snow_col` as a snow source; NO `select type` downcast.

- [ ] **Step 0: Plan review (orchestrator; do not delegate).** Read this task's text against the spec and the code it touches. **STOP** and put to the user: clarifying questions, problems foreseen, cleanup the task text needs, unmet dependencies. Write the resolutions into this plan file before dispatching the implementer. Known going in: Step 3 offers two ways to avoid the `select type` downcast (move the flux to the generic `waterflux_type`, or correct in a bulk-only wrapper) — pick one here.

- [ ] **Step 1:** snow loops in `TotalWaterAndHeatMod` → `get_jtop_snow..jbot_sno` bounds; add the moss terms unconditionally on `nvp_layer_exists` columns (zero when empty): water mass `h2osoi_liq/ice(c,0)`; heat: `AccumulateLiquidWaterHeat(t_soisno(c,0), h2osoi_liq(c,0))` + ice `TempToHeat(cv=h2osoi_ice(c,0)*cpice)` + solid `TempToHeat(cv=csol_nvp*(1-watsat_nvp)*dz(c,0))` — **both** mass and heat, **both** with the same single predicate (their §2b bug: heat side missing when `snl==0`). **Task 5c Step 6 already moved the *lower* bound of the two non-lake loops (`:282`, `:691`) to `get_jtop_snow`, leaving the upper bound at `0`** so the balance checks would not fire spuriously with the stopgap gone; this step supersedes that intermediate with the full `jtop..jbot`-plus-explicit-moss-terms form. The lake loops (`:485`, `:1015`) are still stock and stay that way — NVP columns are never lake.
- [ ] **Step 2:** ~~`CalculateTotalH2osno` excludes slot 0 via the loop bound; `CheckSnowConsistency` range shifts likewise.~~ **Both were pulled forward into Task 5c Step 4** — without them `errh2osno` cannot close once Task 5's stopgap is removed, so `use_nvp=.true.` would abort in the armed balance check on every run. Verify here that they are present and correct rather than re-doing them. Layerless-snow heat temperature source: `t_soisno(c, merge(0, 1, nvp_is_present(c)))` at their :688 counterpart (consistent with Task 7 Step 4).
- [ ] **Step 3 [fix]:** `BalanceCheckMod`: add `qflx_nvp_to_snow_col` to `snow_sources` WITHOUT `select type` — route it via the generic `waterflux_type` (add the member there rather than the bulk type; check how `qflx_snow_drain` is declared — same home) or compute the correction in a bulk-only wrapper before the generic check. `qflx_sl_top_soil` now set correctly by Task 5, so no other snow-balance change. All `endrun`s untouched (armed).
- [ ] **Step 3a — unit tests for what this task lands.** Per Global Constraints, write the pFUnit coverage for this task's code before the commit, and put the **mutation evidence** for each new test in the hand-off: name the mutation, and give the binary counts with it applied and with it reverted. A test for which no mutation can be constructed is not pinning anything — cut it rather than keep it. If this task genuinely lands nothing a unit test can reach, say so explicitly in the hand-off and say why; silence is not a considered "none". **This task also takes two obligations recorded in the §10 coverage table (10.8a and 10.8b):** NVP coverage in `src/biogeophys/test/Balance_test/`, which spec §7 names and which has none today; and a test that lake, glacier, urban and wetland columns get `jbot_sno = 0` with all three presence predicates false. Both belong here because this task writes the conservation accounting, and `ComputeLiqIceMassNonLake`/`ComputeHeatNonLake` are already where the lake/non-lake split lives.
- [ ] **Step 3b — retire the partial-cover `ExpectedTestFails.xml` entries.** The two `clm/NvpMoss03`/`clm/NvpMoss07` entries added at Task 7 Step 5d have been failing since then because `qflx_nvp_to_snow_col` raised `h2osno_total` with no matching term in `snow_sources`. Step 3 adds that term, which is the last thing keeping them from closing. **Remove both entries in this task's commit.** With that, no NVP test carries an expected fail; if one still does, it is a gap, not an expectation.
- [ ] **Step 4: Run build check. Step 5: Commit** `git commit -am "NVP conservation accounting in totals and balance checks"` → review/approval gate.

**Testing changes and expectations.**

- **Suites.** `aux_clm` and `fates` pass, every pre-existing test bit-for-bit against the previous baseline. **The two partial-cover entries start passing here**, once Step 3 adds `qflx_nvp_to_snow_col` to `snow_sources`. With that, no NVP test carries an expected fail.
- **Answer changes.** None in pre-existing tests, and none in the zero-thickness or global entries — but the risk to watch is Step 1. Restructuring the `TotalWaterAndHeatMod` sums must add the moss terms **only inside `if (col%nvp_layer_exists(c))`**: adding zero-valued terms unconditionally changes the summation order on stock columns and moves the last bit. Partial-cover answers are established for the first time here, so there is no prior baseline for them to move against.
- **Tests added or changed.** No new entries. Step 3b removes the two partial-cover `ExpectedTestFails.xml` entries. Unit tests: the `Balance_test` NVP coverage and the non-soil-landunit test, both from §10 coverage rows 10.8a and 10.8b.
- **Expected fails.** The partial-cover pair retired. **None should remain on any NVP test after this task**; one that does is a gap, not an expectation.
- **Baselines.** **A complete new baseline is required.** The partial-cover entries produce comparable output for the first time. Generate as `<branchbasename>.<shorthash>>`; compare against the previous baseline.

---

### Task 15: History snow-field fill + SNO_* slices

**In brief.** Task 15 keeps the moss slot out of the 19 `SNO_*` history fields. The bottom-justification in `hist_set_snow_field_2d` ends at `jbot_sno` instead of 0, and `num_snow_layers` is already honest. The one open question is whether excluding it in the fill is sufficient or the field slices need their bounds changed too — decide by reading the fill rather than by inspecting the registrations.

**Files:**
- Modify: `src/main/histFileMod.F90` (`hist_set_snow_field_2d` :2209-2300) **and nothing else.**

**Do not touch the 19 `SNO_*` field registrations.** An earlier draft of this line left that open ("plus the registrations if their slices need bound changes"); the answer is settled and it is no. Their slices are `(:, -nlevsno+1:0)` literals, and narrowing them to `(:, -nlevsno+1:-1)` would shrink the `levsno` dimension **for every column in every configuration, `use_nvp = .false.` included**, so every existing baseline would fail on shape. The fix belongs entirely in the fill, because the bottom-justification is per-column and keys on `col%jbot_sno(c)`.

- [ ] **Step 0: Plan review (orchestrator; do not delegate).** Read this task's text against the spec and the code it touches. **STOP** and put to the user: clarifying questions, problems foreseen, cleanup the task text needs, unmet dependencies. Write the resolutions into this plan file before dispatching the implementer.

- [ ] **Step 1:** `hist_set_snow_field_2d`: the change is one term at `:2288` — `field_out(point, level) = field_in(point, level + num_nonexistent_layers + col%jbot_sno(c))`, leaving `num_snow_layers = abs(snl(c))` and `num_nonexistent_layers` alone. That reduces to the stock expression term for term at `jbot_sno == 0`. Do not restructure `num_nonexistent_layers` itself; it is on the stock path. Verify no `SNO_*` field can expose slot 0 on an NVP column.
- [ ] **Step 1a — unit tests for what this task lands.** Per Global Constraints, write the pFUnit coverage for this task's code before the commit, and put the **mutation evidence** for each new test in the hand-off: name the mutation, and give the binary counts with it applied and with it reverted. A test for which no mutation can be constructed is not pinning anything — cut it rather than keep it. If this task genuinely lands nothing a unit test can reach, say so explicitly in the hand-off and say why; silence is not a considered "none".
- [ ] **Step 2: Run build check. Step 3: Commit** `git commit -am "Exclude NVP slot from snow history fields"` → review/approval gate.

**Testing changes and expectations.**

- **Suites.** `aux_clm` and `fates` pass, every pre-existing test bit-for-bit against the previous baseline. All NVP entries pass and compare against the most recent baseline containing them.
- **Answer changes.** **History output changes on NVP columns**, deliberately: the 19 `SNO_*` fields stop reporting the moss slot as the bottom snow layer and start reporting the true snow pack. Pre-existing tests are untouched — the fill keys on `col%jbot_sno(c)`, which is 0 everywhere with NVP off, and **no field's dimension changes**, since the registrations are not touched. That last point is what protects every existing baseline; if a `levsno` dimension moves, Step 1 was done wrong.
- **Tests added or changed.** No system tests. Unit tests only, for the bottom-justification change.
- **Expected fails.** None outstanding.
- **Baselines.** **A complete new baseline is required** — NVP-on history content changes.

---

### Task 16: Unit-test coverage audit

**In brief.** Task 16 no longer batches unit tests — Global Constraints now require each task to add the tests for the code it lands, with mutation evidence, at the earliest task where the test can be written. What is left here is the audit: review the coverage accumulated across Tasks 5-15 against the spec, name what is untested, and close the gaps. The one case that was still queued in this task — `CombineSnowLayers` on an NVP column where the bottom layer vanishes, depositing into the moss when it has thickness and passing through to soil when it does not, booking `qflx_sl_top_soil` either way — moves to the task that first makes it writable, which is the one that gives the moss water to hold.

**This case is worth the audit on its own.** `BalanceCheckMod.F90:764` gates the snow balance on `snl < 0` and forces `errh2osno = 0` otherwise, and `BalanceCheck` runs after `HydrologyNoDrainage` — so on the timestep the last snow layer dissolves, `snl` is already 0 and the check is skipped. `errh2o` still closes, and cannot tell "into the moss" from "into soil layer 1" because both are inside the column total. A unit test is the only thing that can pin it.

**Files:**
- Modify: `src/unit_test_shr/unittestSubgridMod.F90` (:471-493 `init_nlevsno` area — add optional `jbot_sno` setup), `src/biogeophys/test/SnowHydrology_test/*`, `src/biogeophys/test/TotalWaterAndHeat_test/*`, `src/biogeophys/test/Balance_test/*` (run existing suites both ways; add NVP-specific cases)

- [ ] **Step 0: Plan review (orchestrator; do not delegate).** Read this task's text against the spec and the code it touches. **STOP** and put to the user: clarifying questions, problems foreseen, cleanup the task text needs, unmet dependencies. Write the resolutions into this plan file before dispatching the implementer. Known going in: the ordering question that used to sit here is settled — tests land with the code they cover, per Global Constraints, and this task is the audit rather than the batch. The test-authoring rules that used to sit here are also in Global Constraints, so every task carries them.

- [ ] **Step 1 — audit.** Walk the spec's requirement list against the tests that now exist, and produce a written table: requirement, the test that pins it, and the mutation that proves the test has teeth. Any row without a mutation is not covered, whatever the assertions look like. Close what is missing here.
  - Specific things to check, because each was invisible to the suites at the time it was written: the `CombineSnowLayers` vanishing-bottom-layer hand-off (see above); the moss slot excluded from `CalculateTotalH2osno`; `TotalWaterAndHeat` counting moss water and heat exactly once at both `snl == 0` and `snl < 0`; and the interface-recursion guards recorded in Step 2a.
  - Confirm the fixtures still hold their reasons. `test_total_water_and_heat.pf`'s `ComputeLiqIceMass_nvp`/`_stock` and `test_WaterState_CalculateTotalH2osno.pf`'s `totalH2osno_nvp`/`_nvpNoSnowLayers` are what stop Task 14 from moving the moss slot out of the column total or counting it twice; they must not be weakened.
- [ ] **Step 2:** Run the pFUnit suites (the standard per-commit unit-test command from the Execution Process — from `src/`, `qcmd -- ../cime/scripts/fortran_unit_testing/run_tests.py --build-dir unit_tests.temp`) with the new cases included.
- [x] **Step 2a — closed here: the interface-recursion guards in `DivideSnowLayers` and `InitSnowLayers` now have coverage.** Both routines end by walking `z(c,j) = zi(c,j) - 0.5*dz(c,j)`, `zi(c,j-1) = zi(c,j) - dz(c,j)` upward from the snowpack base, and both are guarded so the walk stops at the pack bottom and never reaches the moss slot — `j <= col%get_jbot_snow(c)` in `DivideSnowLayers`' final loop, `do j = jbot, snl(c)+1+jbot, -1` in `InitSnowLayers`. Each guard had **zero** coverage, confirmed by running the mutations rather than inferred: reverting the first to the pre-NVP `j <= 0`, and starting the second's loop at `0` instead of `jbot`, each left all 60 unit-test binaries passing. Only the `DivideSnowLayers` hole was known when this step was written; the `InitSnowLayers` one was found later and both are fixed in the same commit. **The durable lesson is why, and it is structural rather than accidental: any physically consistent moss geometry is a fixed point of that recursion.** A moss layer genuinely occupying `[-dz_nvp, 0]` has `zi(c,0) = 0`, `dz(c,0) = dz_nvp`, `z(c,0) = -0.5*dz_nvp` and `zi(c,-1) = -dz_nvp`; substitute those into the recursion and it reproduces them exactly, so letting the walk run one slot too far changes nothing and **no physical fixture could detect either guard, however it were asserted over**. The user weighed that and chose the unphysical fixture, because the alternative is two load-bearing guards shipping untested forever: both NVP fixtures now put the moss node at `-moss_node_fraction*dz_nvp`, deliberately not the layer midpoint, with the reasoning at the named constant in each file. Nothing under test reads `z(c,0)` — `DivideSnowLayers` and `InitSnowLayers` only write it — so the unphysical value feeds back into nothing. Acceptance was the two mutations plus a control for each: the `DivideSnowLayers` mutation is caught by `assertMossUntouched`'s node-depth assertion in `divide_roundTrip_nvp`, `divide_packLimit_nvp` and `divide_growsToNlevsnoMinusOne_nvp`; the `InitSnowLayers` one by the moss-node survival assertion in `test_initSnowLayers_overfillPack_nvp`; and with the fixture change reverted both mutations pass 60/60 again, which is what shows the fixture change is where the coverage came from.
- [ ] **Step 3: Commit** → review/approval gate. Stage explicitly; never `git commit -a` (see Execution Process).

**Testing changes and expectations.**

- **Suites.** `aux_clm` and `fates` pass, every pre-existing test bit-for-bit against the previous baseline. All NVP entries pass and compare b4b against the most recent baseline containing them; this task changes no model code.
- **Answer changes.** None. The audit adds tests and, where it finds gaps, the tests that close them — it does not change behaviour.
- **Tests added or changed.** Unit tests only, as the audit dictates. If the audit concludes a requirement genuinely needs a *system* test, adding one makes this a baseline-generating task; say so explicitly rather than letting it pass unnoticed.
- **Expected fails.** None; none should exist by this point.
- **Baselines.** No new baseline unless the audit adds a system test.

---

### Task 17: Remove the NVP debug traces

**In brief.** Task 17 deletes every `NVP_TRACE:` debug line, along with any wrapper, import or local that existed only to support one, before the final verification gates run. The acceptance test is not that the traces are gone but that `git diff ctsm5.4.028` contains zero `write(iulog` additions outside `use_nvp` guards: the reference branch's roughly 128 debug writes, many unguarded, are exactly what makes its `use_nvp=.false.` fail to reproduce the baseline. One judgement call up front — whether any trace has earned promotion to a permanent guarded diagnostic, which the spec allows.

Runs **before** Task 18 so the final verification gates and the merge rehearsal see the code that actually ships. Every trace added under the Global Constraints debug-trace rule is removed here.

**Files:** whichever carry `NVP_TRACE:` when this task starts — do not work from a list written earlier, it will be stale.

- [ ] **Step 0: Plan review (orchestrator; do not delegate).** Read this task's text against the spec and the code it touches. **STOP** and put to the user: clarifying questions, problems foreseen, cleanup the task text needs, unmet dependencies. Write the resolutions into this plan file before dispatching the implementer. Known going in: decide whether any trace has proven useful enough to keep as a permanent `if (use_nvp)`-guarded diagnostic, which spec §1.11 does allow — if so it stops being a trace, loses the marker, and gets a comment saying what invariant it reports.

- [ ] **Step 1: Remove them.** `grep -rn 'NVP_TRACE:' src/ bld/` is the complete work list. Delete each line, and any `if (masterproc)` wrapper, `use` statement, or local variable that existed only to support it. Removing a trace must not change indentation or spacing of surviving lines.

- [ ] **Step 2: Prove none survive.** `grep -rn 'NVP_TRACE:' src/ bld/` returns nothing. Also confirm no orphaned `use shr_sys_mod, only : ...`/`masterproc` imports remain that nothing else uses — a dangling import compiles fine and ships as noise.

- [ ] **Step 2a — unit tests for what this task lands.** Per Global Constraints, write the pFUnit coverage for this task's code before the commit, and put the **mutation evidence** for each new test in the hand-off: name the mutation, and give the binary counts with it applied and with it reverted. A test for which no mutation can be constructed is not pinning anything — cut it rather than keep it. If this task genuinely lands nothing a unit test can reach, say so explicitly in the hand-off and say why; silence is not a considered "none". This task removes traces and lands no new behaviour, so the expected answer is no new tests — say that in the hand-off rather than leaving it implicit.
- [ ] **Step 3: Verify.** Build check and unit tests (baseline 59/59). Then the check that matters: `git diff ctsm5.4.028 -- src/ bld/` must contain **zero** `write(iulog` additions outside `if (use_nvp)` guards. Spec §9c.2 lists their branch's ~128 debug writes, many unguarded, as the blocking defect that makes `use_nvp=.false.` non-bit-for-bit. This step is what keeps us from shipping the same defect.

- [ ] **Step 4: Commit** `git commit -am "Remove NVP development debug traces"` → review/approval gate.

---

## Spec §10 coverage

Every item in spec §10 has a row here. Tasks fill in the evidence column as they go, and **Task 18 audits this table** and does not declare the branch done while a row is unsatisfied. The evidence column names what actually satisfies the requirement — a test, a procedure, a fixture — not a task number.

The rows are of four kinds, because §10's items are not all the same shape — and a row can be more than one, as 10.4a and 10.5 are:

- **Standing** — must hold after *every* task, verified by the per-task suite expectation rather than by one named test.
- **Unit** — satisfied by a named pFUnit test, together with the mutation that proves it has teeth. This is the only kind that can reach a requirement the suites are structurally blind to, which is why 10.4b is unit-only rather than unit-as-well.
- **Suite entry** — satisfied by a named system test in a named task.
- **Manual** — satisfied by a procedure a human runs, because CIME has no test type for it. These rows name the procedure and the expected result, not just the intent.

A row whose Kind reads *(unassigned)* has no kind yet — that is an open question rather than a fifth category, and Task 18's audit does not pass while one remains.

| § | Requirement | Kind | Satisfied by |
|---|---|---|---|
| 10.1 | `use_nvp = .false.` bit-for-bit vs `ctsm5.4.028` | Standing | The **Suites** bullet of every task: pre-existing tests b4b against the previous baseline. |
| 10.2 | All balance checks armed at tight tolerance throughout | Standing | No task may disable or loosen a check. Audited at Task 18 by diffing the branch against the tag for changes to `BalanceCheckMod`, the `sabg_lyr` `endrun` at `SurfaceRadiationMod.F90:846`, the `errsoi` thresholds, and `BandDiagonalMod.F90:212`. |
| 10.3 | Exact restart (`ERS`/`ERI`) with `use_nvp = .true.` | Suite entry | `ERS` at ALP2 with the NVP testmod, added at Task 7 behind an `ExpectedTestFails` entry on `COMPARE_base_rest`. Cannot pass before Task 9 (the `Phasechange` init guard, which is what makes `imelt` restart-consistent) and cannot *run* to completion before Task 11. Entry comes off at Task 11. |
| 10.4a | First snowfall onto moss (`snl 0 → −2`) | Unit + suite entry | The correctness assertion is the unit test: pack creation on an NVP column is covered from Task 5a. The suite entry adds only what a stock `SMS`/`ER*` can report — that an ALP2 winter run, which crosses this transition repeatedly, completes without aborting and with every armed balance check closed. |
| 10.4b | Last layer vanishing (`−2 → 0`) | Unit only | **No system test can see this** — `BalanceCheckMod.F90:764` skips the snow balance once `snl` reaches 0, and `errh2o` cannot distinguish a deposit into the moss from one into soil layer 1. Owned by the task that gives the moss water to hold; audited at Task 16. |
| 10.4c | Single-layer combination | Unit | `CombineSnowLayers` coverage from Task 5b. |
| 10.4d | Deep-pack subdivision at the `nlevsno−1` cap | Unit | `test_SnowHydrology_divideSnowLayers.pf` (Task 5d) — `divide_packLimit_nvp` and `divide_growsToNlevsnoMinusOne_nvp`. |
| 10.4e | Layerless snow (`h2osno_no_layers > 0, snl == 0`) over moss | Unit | **Reached routinely at ALP2 — this is the mandatory transition band, not an edge case.** New snow accumulates into `h2osno_no_layers` whenever `snl == 0` (`SnowHydrologyMod.F90:605`), and a pack resolves into layers only once `frac_sno_eff(c)*snow_depth(c) >= dzmin(1)` (`:907`, `:912`; default `snow_dzmin_1 = 0.010 m`), with `CombineSnowLayers` dissolving it back below the same threshold (`:2379`). Every seasonal snowpack crosses that band on the way in and on the way out, and partial cover prolongs it, since the test is on `frac_sno_eff*snow_depth` rather than depth alone. Reachability was never the problem: a suite entry could still only show the run does not abort, which is why this is unit-only. **Where the tests come in.** The NVP-specific behaviour here is Task 7 Step 4 — `cv(c,1) += cpice*h2osno_no_layers` becomes `cv(c,0) += ...` when `nvp_is_present`. **Task 7** owns a test that the layerless-snow heat capacity lands on `cv(c,0)` with moss present and stays on `cv(c,1)` when the slot is empty or the column is stock. **Task 8** owns the follow-up: between the two tasks that heat capacity is assigned to a row the solve does not contain — `jtop(c) = snl(c) = 0` on a snow-free NVP column until Task 8 puts the moss row in — so it is briefly deleted from the system with no armed check noticing, and Task 8's test pins that `cv(c,0)` is actually consumed. The pack-creation hand-off, where `h2osno_no_layers` moves into `h2osoi_ice(c,jbot)` (`:961`), is already covered by Task 5a. |
| 10.5 | `use_nvp = .true.` with `dz_nvp = 0` reproduces `use_nvp = .false.` answers | Unit + suite entry + manual | **The invariant holds to roundoff, not exactly — §10.5 leaves that open and §3 settles it.** Spec §3 keeps the moss row in the matrix, because deleting it would make the snow↔soil coupling span 3 rows and break `nband = 5`. So the band solve carries one more row than the `use_nvp = .false.` run, `dgbsv` takes a different pivot sequence, and the two differ in the last bits from the first solve — and the snow-bottom row's own coefficient is a different number, equal to stock's only after elimination. A `SystemTestsCompareTwo` test type in the `LWISO`/`LCISO` mould therefore cannot pass, since that framework has no tolerance anywhere in its cprnc path. **The suite entry** asserts instead that a `dz_nvp = 0` run completes with every balance check armed. **The unit tests** carry the rest, and §10.5 names four skip paths, of which only the first has coverage today — the other three are gaps owned by the task that writes the code, per the Global Constraints rule that tests land with what they verify: **(a) the §2 skip invariant** — covered, by `test_initSnowLayers_overfillPack_nvp`, `divide_roundTrip_nvp`, `divide_subdivides_nvp`, `divide_packLimit_nvp`, `divide_growsToNlevsnoMinusOne_nvp`, `zeroEmpty_fullPack_nvp`, `zeroEmpty_partialPack_nvp`, `zeroEmpty_noSnow_nvp`, `postPercolation_nvp`, `totalH2osno_nvp`, `totalH2osno_nvpNoSnowLayers` and `ComputeLiqIceMass_nvp`; **(b) the §4 zero-`dz` routings** — **no coverage**, and `postPercolation_nvp` does not supply it (it pins thickness adjustment, not routing). Owned by Task 6, which is where percolation either passes through to soil or lands in the moss; the deposit and the `qflx_rain_plus_snomelt` exclusion are complementary halves and a test must fail if either is done without the other. **(c) the §3 degenerate row** — **no coverage**; the row does not exist until Task 8, which owns it. **(d) the §4b fraction rule** — **no coverage**; `NVPEffectiveFractions` lands at Task 8, which owns it. **The manual leg**: a `cprnc` between the NVP-on and NVP-off runs stays available as a **diagnostic**, to catch gross divergence, never as a PASS/FAIL gate. |
| 10.6 | Partial-cover closure at `frac_nvp` 0.3 and 0.7 through winters, exciting both `frac_sno_eff < frac_nvp` and `frac_sno_eff > frac_nvp`, with `frac_h2osfc > 0` | Suite entry | Needs multi-year ALP2 runs with two testmod variants. Cannot pass before **Task 14** — Task 11 fixes the `errsoi` weighting and Task 14 adds `qflx_nvp_to_snow_col` to `snow_sources`. This is the row that actually tests the Task 8 coupling-weight fix; the `dz_nvp = 0` case cannot, because `frac_nvp_eff` is identically 0 there. |
| 10.7 | ~~Sensitivity sanity~~ | **DROPPED** | The bounded-convergence half has no automation path — `SystemTestsCompareTwo` passes only on exact agreement, and asserting convergence needs at least two parameter values, which a two-case framework does not provide. Its second clause, conservation exact at any parameter values, is not lost: §10.2 keeps every check armed and §10.6 requires exact closure at two fractions. **Consequence to carry:** spec §1.9's requirement that transmissivity = 1 reproduce stock energy deposition everywhere still stands as a design requirement but is now verified by no test, so Task 12's reviewers carry it. |
| 10.8a | Unit tests run **both ways** — every NVP-relevant routine covered with a stock column (`jbot_sno = 0`) and with an NVP column (`jbot_sno = -1`) — across the SnowHydrology, TotalWaterAndHeat and Balance suites (spec §7) | Unit | "Both ways" is the `_stock`/`_nvp` complementary-pair convention, and Global Constraints already require each pair to announce the other and differ in as few lines as possible. **Two of the three suites spec §7 names are covered; `Balance_test` has none.** SnowHydrology: `test_SnowHydrology_initSnowLayers.pf`, `_divideSnowLayers.pf`, `_zeroEmptySnowLayers.pf`, `_postPercolation.pf`. TotalWaterAndHeat: `ComputeLiqIceMass_nvp`/`_stock`. Also `test_WaterState_CalculateTotalH2osno.pf`, which spec §7 does not name but which pins the same invariant. **Gap: `src/biogeophys/test/Balance_test/` has no NVP coverage.** Assigned to Task 14, which is where the conservation accounting in `BalanceCheckMod` is written. |
| 10.8b | Lake, glacier, urban and wetland columns unaffected **with `use_nvp = .true.`** | Unit + suite entry | **The per-task Suites bullet does not reach this requirement:** those tests run with `use_nvp = .false.`, which says nothing about whether non-soil landunits are affected when NVP is on. Three legs instead: **(i)** the runtime guard, already armed in every run — `NVPLayerDynamicsMod.F90:83` `endrun`s if any column that is neither `istsoil` nor `istcrop` ever carries `jbot_sno /= 0`; **(ii)** a unit test that non-soil landunits get `jbot_sno = 0` and that all three presence predicates are false on them — assigned to **Task 14** alongside the `Balance_test` gap, since `ComputeLiqIceMassNonLake`/`ComputeHeatNonLake` are where the lake/non-lake split already lives; **(iii)** a `use_nvp = .true.` system test at a grid that actually contains those landunits. **ALP2 contains none of them** — `PCT_LAKE = 0`, `PCT_GLACIER = 0`, `PCT_URBAN = 0, 0, 0`, `PCT_WETLAND = 0` — so global tests (such as what exist in the `aux_clm` test suite) are what covers it. |
| 10.9 | Merge rehearsal into `ctsm5.4.028_nvp`, conflict set matches the intentional list, resolutions in MERGE_NOTES | Manual | Task 18 Step 5. Not a CIME test of any kind — a trial merge in a scratch worktree, with the conflict set compared against the intentional list by hand. |

**Two notes this table carries.** §10.4 could not be placed as a unit — its five sub-cases are a mix of unit-tested, suite-visible, and suite-*invisible*, and 10.4b is the sharpest example of a requirement no system test can reach. And §10.5 and §10.6 are not redundant: the zero-thickness case exercises the skip paths and none of the closure algebra, because every 4-way weight collapses to the stock 3-way when `frac_nvp_eff` is zero.

**Testing changes and expectations.**

- **Suites.** `aux_clm` and `fates` pass, every pre-existing test bit-for-bit against the previous baseline. All NVP entries pass and compare b4b against the most recent baseline containing them.
- **Answer changes.** None. Every trace removed is a `write(iulog,...)`, which cannot reach history, restart or the coupler. If any test moves, something other than a trace was deleted.
- **Tests added or changed.** None expected — say so in the hand-off rather than leaving it implicit.
- **Expected fails.** None.
- **Baselines.** No new baseline: no test added or changed.

---

### Task 18: Verification & merge rehearsal (spec §10)

**In brief.** Task 18 runs the four verification gates — `use_nvp=.false.` bit-for-bit against `ctsm5.4.028`, the zero-thickness case against `use_nvp=.false.`, partial moss cover across a winter with every balance check armed, and exact restart — then rehearses the merge against `ctsm5.4.028_nvp` and checks the real conflict list against the one MERGE_NOTES predicts. Two things beyond that:

1. **The cases are not specified anywhere.** Compsets, resolutions, run lengths and baselines all have to be settled before this task can start.
2. **The rehearsal target may have moved.** It must be whichever `ctsm5.4.028_nvp` commit is the actual merge destination, which is not necessarily the one the code was harvested from.

No new source files. Run and record results in MERGE_NOTES.md § "Verification results":

- [ ] **Step 0: Plan review (orchestrator; do not delegate).** Read this task's text against the spec and the code it touches. **STOP** and put to the user: clarifying questions, problems foreseen, cleanup the task text needs, unmet dependencies. Write the resolutions into this plan file before dispatching the implementer. Known going in: Steps 1–4 need real cases on Derecho (compsets, resolutions, run lengths, baselines) that this plan never names — settle them here. Step 5's merge rehearsal must target whichever `ctsm5.4.028_nvp` commit is the actual merge destination, which may not be the commit harvested from.

- [ ] **Step 1:** `use_nvp=.false.` bit-for-bit vs `ctsm5.4.028` — strongest available: full case SMS comparison on the user's machine; locally: assert `git diff ctsm5.4.028 -- src/ | grep -v <new files>` touches only guarded lines, and unit suites pass with `jbot_sno=0`.
- [ ] **Step 2:** Zero-thickness, `use_nvp=T, dz_nvp=0, frac_nvp=0`. **What this asserts is that the run completes with every balance check armed and closed** — not that it reproduces `use_nvp=F` bit-for-bit, which is impossible: spec §3 keeps the moss row in the matrix, so the band solve carries one more row than the stock run, `dgbsv` takes a different pivot sequence, and the two diverge from the first solve. Run a `cprnc` against the `use_nvp=F` history as a **diagnostic** — agreement should degrade from roundoff, and gross divergence means something is wrong — but it is not a PASS/FAIL gate and must not be reported as one. The correctness claims for the skip paths are carried by the unit tests in Tasks 6, 7 and 8; see §10 coverage row 10.5.
- [ ] **Step 3:** Partial-cover closure: `frac_nvp=0.3` and `0.7`, winter-crossing run, all balance checks armed — zero balance failures.
- [ ] **Step 4:** ERS exact-restart with `use_nvp=T, dz_nvp>0`.
- [ ] **Step 5:** Merge rehearsal: `git worktree add /tmp/nvp_merge_rehearsal ctsm5.4.028_nvp && cd /tmp/nvp_merge_rehearsal && git merge --no-commit --no-ff <working branch from Task 0>`; diff the conflict list against MERGE_NOTES "Intentional merge conflicts"; record; `git merge --abort`, remove the rehearsal worktree.
- [ ] **Step 5a — audit the "Spec §10 coverage" table.** Walk every row and confirm it is satisfied by what its evidence column names, rather than by what the row intends. **The branch is not done while any row is unsatisfied, and the audit does not pass while any row's Kind reads `(unassigned)`.** Row by kind: for each **Unit** row, the named test exists and its mutation evidence was recorded when it landed; for each **Suite entry** row, the named test is in `testlist_clm.xml`, has no leftover `ExpectedTestFails.xml` entry, and reported PASS; for each **Manual** row, the procedure was run and its result written down; for each **Standing** row, the condition held after *every* task, not merely the last. §10.2 is audited by diffing the branch against `ctsm5.4.028` for changes to `BalanceCheckMod`, the `sabg_lyr` `endrun` at `SurfaceRadiationMod.F90:846`, the `errsoi` thresholds and `BandDiagonalMod.F90:212` — no check may have been disabled or loosened anywhere along the way. Record the audit result in MERGE_NOTES beside the verification results.
- [ ] **Step 6: Commit MERGE_NOTES updates** → final review/approval gate.

**Testing changes and expectations.**

- **Suites.** This is the task that runs the full set rather than one that changes it. `aux_clm` and `fates` pass, every pre-existing test bit-for-bit against the previous baseline. Every NVP entry passes and compares b4b against the most recent baseline containing it, across `nvp`, `bigleaf_nvp` and `fates_nvp`.
- **Answer changes.** None. This task lands no source changes.
- **Tests added or changed.** None. Step 5a audits the §10 coverage table instead, and the branch is not done while any row is unsatisfied.
- **Expected fails.** None may remain. An `ExpectedTestFails.xml` entry surviving to this task is an unfinished task, not an accepted limitation — find which task owed its removal.
- **Baselines.** None generated here; this task consumes the baselines earlier tasks produced.

---

## Self-Review (performed per writing-plans skill)

- **Spec coverage:** §1 decisions → Tasks 1-3 (1,2,7,8), §2 → Tasks 2,5; §3 → Tasks 7-9; §4a → 6,13; §4b → 10,11; §4c → 9; §4d → 5; §4e → 6; §4f → 12; §4g → 6; §5 → 14; §6 → 3; §7 → 1,3,15,16; §10 → 17. Gap check: spec §7 cold-start ordering → Task 3 Step 2 + Task 5 Step 1; `ch4Mod` clarifying comment (spec §2) → **added to Task 5 Step 5's sweep scope** (one comment at ch4Mod's `j==0` pseudo-layer sites; include in that commit).
- **Type consistency:** `get_jtop_snow`/`nvp_layer_exists`/`nvp_is_present`/`nvp_is_empty` (Task 2) used with those exact names throughout; `NVPEffectiveFractions` (Task 3) is the only fraction source in Tasks 8-13; `NVPParamsMod` names match Task 1 declarations.
- **Placeholders:** `<their value>` items in Task 1 are read-from-disk data, not deferred design; Task 8 Step 2's weight rule states the governing constraint (moss loss = soil gain identically) with implementation latitude — resolved in **Task 8 Step 0** (the derivation is written into the task text before dispatch), then re-checked by the spec-compliance reviewer to confirm the algebra note landed in code comments.
- **Note on this section:** implementer subagents never see it — they receive only their own task's text (Execution Process 4). Anything recorded here that an implementer must act on has to be written into the task's steps, which is what each task's Step 0 is for. The `ch4Mod` item above is exactly this failure mode: it is claimed as "added to Task 5 Step 5" but Task 5 Step 5's text never mentions it, so Task 5 Step 0 must land it there or drop it deliberately.
