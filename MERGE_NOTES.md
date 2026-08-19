# MERGE_NOTES — NVP stub (`use_nvp`) branch

Working notes for merging this branch into `ctsm5.4.028_nvp`. Every deliberate
divergence from that branch gets a row in "Intentional merge conflicts" as the
task that creates it lands, so the merge rehearsal (Task 18) has a checklist to
compare the real conflict set against.

Plan: `.claude/plans/2026-08-18-nvp-stub-implementation-of-velvety-harp.md`
Spec: `.claude/plans/this-is-the-community-velvety-harp.md` (governs on conflict)

## Workspace

| | |
|---|---|
| Checkout | `/glade/work/samrabin/ctsm_hui-moss-permanent-nvp-layer` |
| Working branch | `hui-moss/permanent-nvp-layer`, based on the `ctsm5.4.028` tag |
| Harvest worktree (read-only) | `.worktrees/ctsm5.4.028_nvp`, detached at `103082a17` — the commit the spec audited, so its `:NNNN` line references hold verbatim |
| Build-check case | `test-bld/` (FATES compset, `DEBUG=TRUE`, 10x15) |

`test-bld` and `.worktrees` are listed in `.gitignore` under "DELETE THESE BEFORE
MERGING" — neither belongs in the merge.

## Verification commands

Run before every commit. Unit tests are required for any commit touching Fortran.

Build check:

```bash
cd test-bld && qcmd -- ./case.build
```

Unit tests:

```bash
cd src && qcmd -- ../cime/scripts/fortran_unit_testing/run_tests.py --build-dir unit_tests.temp
```

Namelist-touching tasks additionally run `bld/unit_testers/build-namelist_test.pl`.

**Five aux_clm tests fail for a reason that is not ours**, and will keep doing so:
`ERS_D_Ld7...decStart1851_noinitial`, `ERS_D...I2000Clm60FatesRs...FatesCold`,
`SMS_D_Ly6...cropMonthOutput`, `SMS_Ld10_D...NEON-FATES-NIWO`, and
`SMS_Lm3_D...FatesColdHydro` — all intel, debug, mpi-serial, and all running BGC or
FATES so they initialize the CH4 inundated-fraction stream. CTSM issue #3798: a
divide-by-zero in the ESMF regrid when `ch4finundatedmapalgo == bilinear` under
intel/2025.3.2. They are in `ExpectedTestFails.xml`; the entries originally carried a
testid suffix that stopped them auto-classifying, fixed in `6ad7df015`.

**Namelist baselines change from Task 1 onward.** Every generated `lnd_in` now carries
`use_nvp` in `clm_inparm` plus a 17-variable `nvp_inparm` group, so the test suite's
namelist-comparison baselines need regenerating. Expected for a namelist addition, but
it must be called out in the PR.

**Intermediate commits are only expected to hold for `use_nvp = .false.`.** The
`use_nvp = .true.` path is not coherent until the full task stack has landed —
as of Task 5c the snow lifecycle is reindexed, but the percolation, capping and
aerosol loops (Task 6), the thermal and radiation loops (Tasks 7-12), the moss
solid-heat term and the rest of conservation (Task 14) and the `SNO_*` history
fill (Task 15) are all still stock, as are the unassigned sites listed below.
Task 5c removed the last `use_nvp` stopgap so the configuration runs to
completion instead of aborting; it is not correct. `use_nvp=T` validation
belongs to Task 18.

## Verification results

Filled by Task 18. One row per spec §10 gate.

| Gate | Configuration | Result |
|---|---|---|
| Bit-for-bit vs `ctsm5.4.028` | `use_nvp=.false.` | **Interim pass at `23a59c7a9` (through Task 4).** aux_clm on derecho: **285 BASELINE PASS**, 3 BASELINE FAIL — two flagged EXPECTED FAIL, one (`SSPMATRIXCN_Ly5...ciso_monthly`) a stale baseline whose files are dated 2027-12 against our 2016-12, so cprnc compared nothing. Re-run at Task 18. |
| Golden zero-thickness | `use_nvp=T, dz_nvp=0, frac_nvp=0` vs `use_nvp=F` | |
| Partial-cover closure | `frac_nvp=0.3`, `0.7`, winter-crossing | |
| Exact restart | `ERS`, `use_nvp=T, dz_nvp>0` | |
| Merge rehearsal | trial merge into `ctsm5.4.028_nvp` | |

## Intentional merge conflicts

Where this branch deliberately differs from `ctsm5.4.028_nvp`. "Resolution"
records which side wins at merge time.

| File | Why ours differs | Resolution |
|---|---|---|
| `src/biogeophys/NVPParamsMod.F90` | Their `nvp_frac_min` (activation threshold) is omitted — the stub assigns `jbot_sno` statically at init and never activates a layer, so nothing consumes it. | Theirs. Their FATES-driven activation needs it. |
| `src/biogeophys/NVPParamsMod.F90` | Six stub-only parameters (`dz_nvp`, `frac_nvp`, `nvp_transmissivity`, `alb_nvp_vis`, `alb_nvp_nir`, `nvp_coldstart_saturation`) are namelist constants; theirs are FATES-prognostic (spec §1.8, §1.9). | Theirs. |
| `bld/CLMBuildNamelist.pm` | No FATES restriction on `use_nvp` — the stub works in standard CLM configurations (spec §1.10). Also adds a build-namelist check rejecting `use_nvp` with water tracers (spec §5), which theirs lacks. | FATES restriction: theirs. Water-tracer check: ours, until tracer support lands. |
| `bld/namelist_files/namelist_definition_ctsm.xml` | `nvp_inparm` is registered; their branch never registered the group, leaving it unsettable (spec §7, §9c.8). `rnvp_ice` is in our group though absent from theirs. | Ours — registering is the fix. |
| `src/main/ColumnType.F90` | Member names and positions match theirs exactly, but the declaration comments are ours: theirs assert FATES semantics that are false here ("aggregated from FATES bc_out", "Updated each FATES dynamics timestep", "Consumed by NVPLayerDynamicsMod%UpdateNVPLayer"). Conflict is confined to the comment lines. | Theirs, once FATES drives the values. |
| `src/main/ColumnType.F90` | Adds `get_jtop_snow` / `nvp_layer_exists` / `nvp_is_present` / `nvp_is_empty` — no counterpart on their branch, which re-derives these conditions inline per site (spec §1.2, §2). Purely additive, but their inline guards will conflict wherever later tasks replace them with calls. | Ours — the named predicates are the point of the honest-`snl` design. |
| `src/biogeophys/NVPLayerDynamicsMod.F90` | Static init (`NVPLayerInit`) replaces their FATES-driven `UpdateNVPLayer` (their :72-222), which is absent here entirely. `jbot_sno` is assigned once and never flipped, so their whole class of activation/deactivation conservation bugs is out of scope by construction (spec §1.1, §2). | Theirs, once FATES drives thickness — but the transition code needs redesign, not harvest (spec §8). |
| `src/biogeophys/NVPLayerDynamicsMod.F90` | `NVPLayerRestart` corrects `JBOT_SNO` to `interpinic_flag='skip'` (theirs: `'interp'`, spec §1.6) and replaces their silent zero-defaults with three cross-flag `endrun` guards (spec §7). Probes with `ncdio_pio::check_var` before `restartvar`, because `restartvar` routes a missing field to `missing_field_possibly_abort`, which aborts continue/branch runs — blind probing would break every stock `use_nvp=.false.` restart. | Ours. |
| `src/biogeophys/NVPLayerDynamicsMod.F90` | `NVPColdStart` partitions initial pore water by `t_soisno(c,1)` against `tfrz`; their `NVPColdStartIce` (:733) hard-codes an all-ice start (spec §7 — climate-agnostic). | Ours. |
| `src/biogeophys/SnowHydrologyMod.F90` | `InitSnowLayers` blanket slot assignments stop at `col%get_jbot_snow(c)` so they cannot overwrite the NVP geometry with `spval`. Their branch left `InitSnowLayers` unmodified, which is why their cold-start snow lands in the moss slot (spec §4d). Superseded by the Task 5 reindex. | Ours. |
| `src/biogeophys/WaterFluxType.F90` vs `WaterFluxBulkType.F90` | `qflx_nvp_to_snow_col` is declared in the **generic** `waterflux_type`; theirs is in the bulk type. `BalanceCheck` takes `class(waterflux_type)`, so the bulk placement is what forced their `select type` downcast, which spec §5 rejects. At merge the two declarations collide as a duplicate name. Consequence: the variable and its `QFLX_NVP_TO_SNOW` history field now exist on every water-tracer instance, not bulk only. | Ours — the whole point is that Task 14's snow balance reaches it without a downcast. |
| `src/biogeophys/WaterDiagnosticType.F90` vs `WaterDiagnosticBulkType.F90` | `qg_nvp_col` is declared in the generic `waterdiagnostic_type`, alongside `qg_col`; theirs is in the bulk type. Same duplicate-name collision at merge. | Ours. |
| `src/biogeophys/SnowHydrologyMod.F90` | `DivideSnowLayers` keeps honest `snl`: `msno = abs(snl(c))` with no adjustment and `snl(c) = -msno` on exit. Theirs subtracts one from `msno` (their :2802) and reconstructs `snl = -(msno + 1)` (their :2966) to carry its `-(N_snow+1)` convention. The offset lives in the staging map instead — `dz(c, j+snl(c)+jbot)` — so the pack is staged from `get_jtop_snow(c)` to `jbot` (spec §1.2, §4d). | Ours — the `-1` bookkeeping is meaningless under honest `snl`. |
| `src/biogeophys/SnowHydrologyMod.F90` | `DivideSnowLayers` keeps the `nlevsno-1` subdivision cap (their :2816) but expresses it as `merge(1, 0, col%nvp_layer_exists(c))`, and excludes the NVP slot from the un-staging loop through the range guard `j >= get_jtop_snow(c) .and. j <= get_jbot_snow(c)` plus the inverse offset map, not their `cycle`-at-`j==0` opt-out (their :2984). Structural exclusion, so a missed site fails with a wrong range instead of silently treating moss as snow (spec §1.2). | Ours. |
| `src/biogeophys/SnowHydrologyMod.F90` | Their `DivideSnowLayers` carries two unconditional debug writes, both inside the excess-dump branch — a bare `write(iulog,*) 'msno=',...` (their :2897) and a second at their :2940 that dumps whole `swliq(:,c,:)`/`swice(:,c,:)` slices, all tracers by all staging slots, on every excess-dump event — plus two `use_nvp`-guarded, `c == 1` writes, `[NVP DBG] DivSnow BEG`/`END` (their :2793-2797, :2972-2976). None are ported: the unguarded one is what spec §9c.2 rejects outright, and the guarded pair is per-column rather than rate-limited, which spec §1.11 does not license. | Ours — debug output must not survive. |
| `src/biogeophys/SnowHydrologyMod.F90` | The `swe_old` fill in `BulkDiag_NewSnowDiagnostics` runs `-nlevsno+1 .. get_jtop_snow(c)-1` and `get_jtop_snow(c) .. get_jbot_snow(c)`; theirs leaves both loops bare stock (their :500, :503), so the moss slot enters the melt-compaction term that `SnowCompaction` computes from it ([fix], spec §5). `swe_old(c,0)` is then never written on an NVP column and stays at its allocation-time `nan`; `SnowCompaction` is its only reader and does so inside the reindexed snow guard, so nothing reads it. | Ours. |
| `src/biogeophys/SnowHydrologyMod.F90` | `SnowCompaction`, `PostPercolation_AdjustLayerThicknesses` and `ZeroEmptySnowLayers` take range guards rather than their `cycle`-at-`j==0` guards (their :2046, :1817 and :3113 respectively; their :2399 is the matching `cycle` in `CombineSnowLayers`, covered by its own row); `ZeroEmptySnowLayers` takes the complement form `j < get_jtop_snow(c)`. `SnowCompaction`'s whole-pack slice feeding `FracSnowDuringMelt` is reindexed too — theirs leaves it at `snl(c)+1:0` (their :2105), which their own convention makes count the moss slot as snow. | Ours. |
| `src/biogeophys/SnowHydrologyMod.F90` | Both `is_lake` blocks in `DivideSnowLayers` are left stock, with one comment recording why: NVP columns are istsoil/istcrop only, so `nvp_layer_exists` is false and `jbot` is 0 on every lake column. Theirs also leaves them stock, without the reasoning. | Either — same code; ours carries the constraint. |
| `src/biogeophys/WaterStateType.F90` | `CalculateTotalH2osno` runs `get_jtop_snow(c) .. get_jbot_snow(c)` and `CheckSnowConsistency` runs `-nlevsno+1 .. get_jtop_snow(c)-1`; theirs keeps the stock bounds and bolts on a `cycle`-at-`j==0` opt-out in each (their :925, :972). Pulled forward from Task 14 so `errh2osno` has a consistent other side once Task 5b's `qflx_sl_top_soil` booking lands, and so `CheckSnowConsistency` cannot abort a debug build on a snow-free NVP column (spec §5). | Ours. |
| `src/biogeophys/TotalWaterAndHeatMod.F90` | `ComputeLiqIceMassNonLake` and `ComputeHeatNonLake` take the lower bound `col%get_jtop_snow(c)`, with the upper bound deliberately left at `0` so the NVP slot stays inside the column total and the snow-to-moss hand-off remains an internal transfer for `errh2o`/`errsoi`. Theirs keeps the stock `snl(c)+1,0` bounds — the intended `merge(-1, 0, ...)` upper bound is commented out at their :294 and :734 — patches the mass routine with a separate `snl(c) == 0` companion (their :308), adds a moss dry-mass heat term (their :752) that Task 14 still owes on our side, and carries six `[NVP DBG]` writes — three unguarded (their :271, :282, :425; :282 prints the loop variable `j` before the loop that sets it, the spec §9c.2 instance) and three `use_nvp`-guarded (their :300, :315, :349). Task 14 Step 1 supersedes this minimal form. | Ours for the bounds; their :752 solid-heat term arrives with Task 14. Never their debug writes. |
| `src/biogeophys/SnowHydrologyMod.F90` | `Bulk_InitializeSnowPack` / `UpdateState_InitializeSnowPack` create the first snow layer at `jbot` with honest `snl = -1`; theirs places the layer at `(c,-1)` exactly as ours does (their :948-954 for `h2osoi_ice`/`h2osoi_liq`, :1005-1024 for `dz`/`z`/`zi`). The sole divergence is `snl(c) = -2` (their :1006), carrying the `-(N_snow+1)` convention (spec §1.2). Their branch anchor: :944-1029. | Ours — honest `snl` is the design. |
| `src/biogeophys/SnowHydrologyMod.F90` | `InitSnowLayers` caps the layer count at `nlevsno - merge(1,0,col%nvp_layer_exists(c))` and anchors its geometry loop at `zi(c,jbot)` via `do j = jbot, snl(c)+1+jbot, -1`. Their branch leaves the routine entirely unmodified. The cap is load-bearing for bounds safety, not just design: without it a full NVP pack writes one element below the start of `dz`, `z` and `zi`. | Ours. |
| `src/biogeophys/SnowHydrologyMod.F90` | `CombineSnowLayers` carries four `[fix]`es over theirs (:2171-2634): the `nvp_is_empty` hand-off passes through to soil layer 1 rather than into a zero-thickness slot; `qflx_sl_top_soil` is booked for the bottom-layer dissolution in all cases (theirs never sets it under NVP, leaving a systematic `errh2osno` residual — audit §1b); aerosol masses are dropped rather than merged into slot 0 (their guard covers `dz` only, so the mass strands — spec §4d); and the whole-pack liquid hand-off targets moss where `nvp_is_present`. Their `snl == -1 -> 0` fixups are deliberately not ported — they patch the `-(N_snow+1)` convention and would be a bug under honest `snl` (spec §1.2). Both `j`-outer loops take guard changes, not per-column bounds; theirs uses a `cycle`-at-`j==0` in the whole-pack accumulation (their :2399) and leaves the geometry recursion (their :2598-2606) entirely stock. Theirs also carries a four-line `[NVP DBG snow]` block (their :2608-2630) — `use_nvp`-guarded but per-column over `filter_snowc` and not rate-limited; not ported. | Ours. |
| `src/biogeochem/ch4Mod.F90` | Two comments in `ch4_tran`: index 0 in its `j = 0,nlevsoi` loops is the atmosphere pseudo-layer, not the NVP slot, and is exempt from the spec §2 idiom table; and the `-nlevsno+1,0` snow-resistance loop is a genuine snow loop that still owes the transformation (see "Snow-index sites found by sweep, not by audit" — assigned to Task 6). Their branch does not touch the file. | Ours — comment only. |
| `cime_config/testdefs/ExpectedTestFails.xml` | Five CTSM issue #3798 entries had their testid suffix stripped so they classify in any run, not only the one they were recorded from (`6ad7df015`). Unrelated to NVP, but their branch also edits this file, so it may conflict. | Either — the change is upstream-appropriate and belongs in a CTSM PR of its own. |

## Snow-index sites found by sweep, not by audit

Expressions that index a snow slot and need the spec §2 transformation, found by a
tree-wide sweep at Task 5c rather than by the audit of `ctsm5.4.028_nvp`. They were
missing as a group for one reason: **the plan's per-task file lists were derived
from their branch's diff, so anywhere their branch missed, this plan had no entry
either.** Their branch does not transform any of these, so each is also a place
where our diff and theirs will differ at merge time.

Now assigned. Two lake-landunit categories are deliberately excluded — `LakeHydrologyMod`,
`LakeTemperatureMod`, `LakeFluxesMod` — because NVP columns are istsoil/istcrop only,
so `jbot_sno` is 0 there and every stock expression is already correct.

| Site | What it does | Consequence on an NVP column | Assigned |
|---|---|---|---|
| `SnowHydrologyMod.F90` `BulkDiag_NewSnowDiagnostics` | new snow depth added to `dz(c,snl(c)+1)` | was writing the moss thickness at `snl == -1` | **Done, Task 5c** |
| `SnowHydrologyMod.F90` `UpdateState_AddNewSnow` | new snow mass added to `h2osoi_ice(c,snl(c)+1)` | was booking snowfall into the moss slot, giving `errh2osno = -qflx_snow_grnd*dtime` and an abort | **Done, Task 5c** |
| `SnowHydrologyMod.F90:1237` `UpdateState_TopLayerFluxes` | `lev_top(c) = snl(c)+1` | top-layer sublimation/condensation applied to the moss slot at `snl == -1` | Task 6 (called from `SnowWater`) |
| `clm_driver.F90:1637-1638` `clm_drv_init` | `frac_iceold(c,j)` over `j >= snl(c)+1` | **divide by zero** in the golden `dz_nvp = 0` case: `h2osoi_ice(c,0)/(h2osoi_liq(c,0)+h2osoi_ice(c,0))`, both terms zero. Every timestep the column carries resolved snow | Task 6 — **do this one first** |
| `ch4Mod.F90:3793-3841` `ch4_tran` snow resistance | `do j = -nlevsno+1,0` / `j >= snl(c)+1`, and `dz(c,j)` in a denominator | counts moss as snow, misses the top snow layer, and **divides by `dz(c,0)`** in the golden case. Whenever `use_lch4` and the column has resolved snow, so every BGC compset | Task 6 (by domain; no task owns `ch4Mod`) |
| `AerosolMod.F90:788-796` `AerosolFluxes` | BC/OC/dust deposited into `mss_*(c,snl(c)+1)` | aerosol deposition into the moss slot | Task 6 (routine not previously named) |
| `AerosolMod.F90:621-624` `AerosolMasses` | `h2osno_top` / `mss_*_top` from `snl(c)+1` | SNICAR top-layer inputs read from moss | Task 6 (outside its cited `:570-580`) |
| `HydrologyNoDrainageMod.F90:704` | `h2osno_top(c)` from `snl(c)+1` | same SNICAR input as `AerosolMod:621` | Task 6 **by domain**, though Task 10 owns the file — cross-referenced in both |
| `WaterDiagnosticBulkType.F90:789-790` `InitBulkCold` | `snw_rds_col(c,snl(c)+1:0)` and `(c,-nlevsno+1:snl(c))` — array **slices**, not loops | cold-start grain radius written across the moss slot | Task 6 |
| `TemperatureType.F90:736` `InitCold` | `do j = snl(c)+1, 0` fills snow temperatures with 250 K after a blanket `spval` at `:732` | writes 250 K into the moss slot and leaves the **top snow layer at `spval`**, which reaches `SoilThermProp` on the first timestep | Task 7 — routine shared with Task 10 |
| `TemperatureType.F90:837` `InitCold` | `t_grnd_col(c) = t_soisno_col(c,snl(c)+1)` | cold-start ground temperature read from the moss slot | Task 10 — routine shared with Task 7 |
| `SoilTemperatureMod.F90:474` `SoilTemperature` | `if (j >= snl(c)+1)` in the non-urban `fn1` branch | outside Task 8's cited `:396-434`, inside a routine it names | Task 8 |
| `BiogeophysPreFluxCalcsMod.F90:354` | `h2osoi_liq/ice(c,snl(c)+1)` test | outside Task 10's cited `:334-341` | Task 10 |

**Lesson for the remaining tasks:** the line ranges each task cites are where their
branch made changes, not a complete inventory of that routine's snow-index
expressions. Sweep the whole routine — and grep for array *slices* (`(c, snl(c)+1:0)`),
which carry no loop keyword and are the easiest kind to miss.

## Deferred items

Out of scope for the stub; recorded in spec §8 with full rationale.

| Item |
|---|
| Global (non-per-column) `jbot_sno` with uniformly shifted special columns |
| Dynamic (FATES-prognostic) thickness with conservation |
| Beer's-law transmissivity + SNICAR layer-0 optics |
| FATES-side fractional-cover aggregation fix |
| Clean aerosol pass-through-and-discard (un-strand the moss slot) |
| Non-overloaded restart + init_interp third-segment support |
| Water-tracer support for NVP fluxes |
| NVP↔soil interface heat-flux history field |
