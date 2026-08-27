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

**The `ccs_config` and `cdeps` pointers mirror the merge target, quirks included** (Task 5f).
`ctsm5.4.028_nvp` pins `ccs_config` at `b6387972b` and `cdeps` at `42f9a6b06`, and we match
both so the merge stays clean — but its `.gitmodules` handles the two inconsistently and we
inherit that. `ccs_config` moves `url` to `samsrabin/ccs_config_cesm.git` and leaves
`fxDONOTUSEurl` upstream, which is the normal shape, and which `git fleximod test` correctly
reports as a personal fork. `cdeps` does the opposite: `url` stays at `ESCOMP/CDEPS.git` and the
**fork URL is parked in `fxDONOTUSEurl`**, so a fresh clone tries to fetch `42f9a6b06` from
upstream. This checkout already has the object, so it bites only a new clone. Not a divergence —
matching them is the point — but it is the first thing to check if a fresh clone of this branch
fails to populate `components/cdeps`, and neither entry should be "tidied up" before the merge.

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
| Bit-for-bit vs `ctsm5.4.028` | `use_nvp=.false.` | **`clm_short` reported good at `1db676ea9` (through Task 5c)** by the user; full `aux_clm` at that commit not yet run. Earlier: **interim pass at `23a59c7a9` (through Task 4).** aux_clm on derecho: **285 BASELINE PASS**, 3 BASELINE FAIL — two flagged EXPECTED FAIL, one (`SSPMATRIXCN_Ly5...ciso_monthly`) a stale baseline whose files are dated 2027-12 against our 2016-12, so cprnc compared nothing. Re-run at Task 18. |
| Zero-thickness | `use_nvp=T, dz_nvp=0, frac_nvp=0` vs `use_nvp=F` | |
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
| `src/biogeophys/SnowHydrologyMod.F90` | `PostPercolation_AdjustLayerThicknesses` is declared in the "public just for the sake of unit testing" block instead of the `private ::` block, so the pFUnit test of its reindexed range guard can call it; theirs leaves it private. Their branch leaves the declaration untouched at their `:109` and does not modify the header block at all, so a 3-way merge applies our move cleanly — there is no conflict here. The row exists so the `public` is not silently reverted if their version of the file is taken wholesale. | Ours — the routine takes only plain arrays, so a direct test is the cheapest coverage of the guard. |
| `src/biogeophys/SnowHydrologyMod.F90` | The module variables `dzmin`, `dzmax_l` and `dzmax_u` are declared `public, protected` instead of `private`, so the pFUnit test of `InitSnowLayers` can derive its overfill fixture depth from the layer schedule (`sum(dzmax_u(1:nlevsno-1))`) rather than hard-coding a depth that happens to exceed it; `protected` keeps write access inside the module. Their branch leaves all three declarations stock and private at their `:149-151` and does not touch them, so a 3-way merge applies our attribute change cleanly — there is no conflict here. The row exists so the `public, protected` is not silently reverted if their version of the file is taken wholesale. | Ours — the test would otherwise restate the schedule and go stale the next time the schedule moves. |
| `src/biogeophys/SnowHydrologyMod.F90` | Both `is_lake` blocks in `DivideSnowLayers` are left stock, with one comment recording why: NVP columns are istsoil/istcrop only, so `nvp_layer_exists` is false and `jbot` is 0 on every lake column. Theirs also leaves them stock, without the reasoning. | Either — same code; ours carries the constraint. |
| `src/biogeophys/WaterStateType.F90` | `CalculateTotalH2osno` runs `get_jtop_snow(c) .. get_jbot_snow(c)` and `CheckSnowConsistency` runs `-nlevsno+1 .. get_jtop_snow(c)-1`; theirs keeps the stock bounds and bolts on a `cycle`-at-`j==0` opt-out in each (their :925, :972). Pulled forward from Task 14 so `errh2osno` has a consistent other side once Task 5b's `qflx_sl_top_soil` booking lands, and so `CheckSnowConsistency` cannot abort a debug build on a snow-free NVP column (spec §5). | Ours. |
| `src/biogeophys/TotalWaterAndHeatMod.F90` | `ComputeLiqIceMassNonLake` and `ComputeHeatNonLake` take the lower bound `col%get_jtop_snow(c)`, with the upper bound deliberately left at `0` so the NVP slot stays inside the column total and the snow-to-moss hand-off remains an internal transfer for `errh2o`/`errsoi`. Theirs keeps the stock `snl(c)+1,0` bounds — the intended `merge(-1, 0, ...)` upper bound is commented out at their :294 and :734 — patches the mass routine with a separate `snl(c) == 0` companion (their :308), adds a moss dry-mass heat term (their :752) that Task 14 still owes on our side, and carries six `[NVP DBG]` writes — three unguarded (their :271, :282, :425; :282 prints the loop variable `j` before the loop that sets it, the spec §9c.2 instance) and three `use_nvp`-guarded (their :300, :315, :349). Task 14 Step 1 supersedes this minimal form. | Ours for the bounds; their :752 solid-heat term arrives with Task 14. Never their debug writes. |
| `src/biogeophys/SnowHydrologyMod.F90` | `Bulk_InitializeSnowPack` / `UpdateState_InitializeSnowPack` create the first snow layer at `jbot` with honest `snl = -1`; theirs places the layer at `(c,-1)` exactly as ours does (their :948-954 for `h2osoi_ice`/`h2osoi_liq`, :1005-1024 for `dz`/`z`/`zi`). The sole divergence is `snl(c) = -2` (their :1006), carrying the `-(N_snow+1)` convention (spec §1.2). Their branch anchor: :944-1029. | Ours — honest `snl` is the design. |
| `src/biogeophys/SnowHydrologyMod.F90` | `InitSnowLayers` caps the layer count at `nlevsno - merge(1,0,col%nvp_layer_exists(c))` and anchors its geometry loop at `zi(c,jbot)` via `do j = jbot, snl(c)+1+jbot, -1`. Their branch leaves the routine entirely unmodified. The cap is load-bearing for bounds safety, not just design: without it a full NVP pack writes one element below the start of `dz`, `z` and `zi`. | Ours. |
| `src/biogeophys/SnowHydrologyMod.F90` | `CombineSnowLayers` carries four `[fix]`es over theirs (:2171-2634): the `nvp_is_empty` hand-off passes through to soil layer 1 rather than into a zero-thickness slot; `qflx_sl_top_soil` is booked for the bottom-layer dissolution in all cases (theirs never sets it under NVP, leaving a systematic `errh2osno` residual — audit §1b); aerosol masses are dropped rather than merged into slot 0 (their guard covers `dz` only, so the mass strands — spec §4d); and the whole-pack liquid hand-off targets moss where `nvp_is_present`. Their `snl == -1 -> 0` fixups are deliberately not ported — they patch the `-(N_snow+1)` convention and would be a bug under honest `snl` (spec §1.2). Both `j`-outer loops take guard changes, not per-column bounds; theirs uses a `cycle`-at-`j==0` in the whole-pack accumulation (their :2399) and leaves the geometry recursion (their :2598-2606) entirely stock. Theirs also carries a four-line `[NVP DBG snow]` block (their :2608-2630) — `use_nvp`-guarded but per-column over `filter_snowc` and not rate-limited; not ported. | Ours. |
| `src/biogeochem/ch4Mod.F90` | Two comments in `ch4_tran`: index 0 in its `j = 0,nlevsoi` loops is the atmosphere pseudo-layer, not the NVP slot, and is exempt from the spec §2 idiom table; and the `-nlevsno+1,0` snow-resistance loop is a genuine snow loop that still owes the transformation (see "Snow-index sites found by sweep, not by audit" — assigned to Task 6). Their branch does not touch the file. | Ours — comment only. |
| `src/biogeophys/SnowSnicarMod.F90` | Their branch implements full SNICAR "Approach B": `SNICAR_RT` takes three new optional column arguments (`nvp_tau_col`, `nvp_omega_vis_col`, `nvp_omega_nir_col`, their :194 and :251-253) and, where `nvp_tau_col(c) > 0` with resolved snow, drives the moss slot through the Delta-Eddington solver as a real optical layer — unit effective mass at `h2osno_ice_lcl(0)`, zeroed layer-0 aerosols, `ss_alb_snw_lcl(0)`/`ext_cff_mss_snw_lcl(0)`/`asm_prm_snw_lcl(0)` taken from the NVP properties instead of the grain-radius Mie tables, and every grain-size loop stopped at `merge(-1, snl_btm, nvp_active)` (their :710-733, :740-763, :838-874). **Ours has none of it**: spec §1.9 fixes transmissivity at a constant and spec §8 defers "Beer's-law transmissivity + SNICAR layer-0 optics" outright, so Task 12 partitions absorbed flux outside SNICAR and leaves the solver stock. This is why the plan never opened the file, and why the omission is a deferral rather than the gap it looks like. | Theirs, when the deferred optics land. Ours is not a competing implementation, it is the absence of one. |
| `src/biogeophys/SnowSnicarMod.F90` | `SnowAge_grain` (ours :1461) is left **entirely stock on both branches** — their diff stops at their :1230 — but stock is wrong under both conventions, differently. `snl_btm = 0` (:1576) is the moss slot either way, so `cdz(snl_top:snl_btm) = frac_sno*dz(...)` (:1579) puts `dz(c,0)` into the denominators at :1604 and :1607 on their branch as much as ours: a **zero-thickness divide-by-zero neither branch has fixed**. Ours is additionally wrong at the other end, because `snl_top = snl(c_idx)+1` (:1577) misses the top snow layer under honest `snl`. `snw_rds(c_idx,0) = snw_rds_min` (:1721) hardcodes the moss slot on both. `WaterDiagnosticBulkType.F90:1283` (`ResetBulk`, called from `SnowHydrologyMod.F90:855` for a freshly created pack) writes the moss slot the same way. Task 6 fixes all four. | Ours. Their branch has the `cdz` bug too, so this is a fix to carry across rather than a convention difference — flag it to them. |
| `src/biogeophys/SnowSnicarMod.F90` | Their branch also carries Delta-Eddington robustness work that has nothing to do with NVP: `denom_dir`/`denom_dif` guards that skip the direct-beam and Gaussian-loop `alp`/`gam` terms when `abs(1 - lm^2*mu^2) < 1.e-4` rather than dividing through the resonance (their :1192-1206, :1220-1228), and a `swt > c0` guard on the `rdif_a`/`tdif_a` angular average (their :1233). Alongside them sits an **unguarded** `SNICAR_SIGFPE_DIAG` / `SNICAR_SIGFPE_INPUTS` write pair (their :1159-1179) firing per column, layer and band whenever `ws > 0.9999` — the class spec §9c.2 rejects. Ours has neither, because ours never puts the moss slot into the solver, which is what made the resonance reachable. | Guards: theirs, and they belong in a CTSM PR of their own — they fix stock SNICAR, not NVP. Debug writes: neither. |
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
| `clm_driver.F90:1637-1638` `clm_drv_init` | `frac_iceold(c,j)` over `j >= snl(c)+1` | **divide by zero** in the `dz_nvp = 0` case: `h2osoi_ice(c,0)/(h2osoi_liq(c,0)+h2osoi_ice(c,0))`, both terms zero. Every timestep the column carries resolved snow | Task 6 — **do this one first** |
| `ch4Mod.F90:3793-3841` `ch4_tran` snow resistance | `do j = -nlevsno+1,0` / `j >= snl(c)+1`, and `dz(c,j)` in a denominator | counts moss as snow, misses the top snow layer, and **divides by `dz(c,0)`** in the zero-thickness case. Whenever `use_lch4` and the column has resolved snow, so every BGC compset | Task 6 (by domain; no task owns `ch4Mod`) |
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

## Sites found by the per-task run/abort analysis

A second group, found on 2026-08-27/28 by a different method than the Task 5c sweep and
missed by it for a different reason. The sweep grepped for the **pattern** `snl(c)+1`; this
pass asked, task by task, **what actually happens when the model runs** once each task's
change has landed. That catches a class the pattern search structurally cannot: sites that
are *correct today* and only break after some other task moves a partner expression. The two
`SoilFluxesMod` rows are the pure case — they are consistent with `SnowHydrologyMod`'s
`lev_top` right now, and Task 6 desynchronizes them.

The extra column matters here. Their branch left every one of these stock, and under their
`snl = -(N_snow+1)` convention that is mostly **correct**, because `snl+1` really does name
the top snow layer there. So these are not sites they missed and we caught; they are sites
where the convention decision alone forces our diff to differ. The exception is the
`SnowAge_grain` `cdz` denominator, which is wrong on both branches — worth telling them.

| Site | What it does | Consequence on an NVP column (ours) | Their branch | Assigned |
|---|---|---|---|---|
| `WaterStateType.F90:471-476` `InitCold` | refills the blanket `spval` of `:391-392` with 250 kg/m3 pure ice over `do j = -nlevsno+1, 0` / `if (j > snl(c))` | selects `-N+1 .. 0`, so the **top snow layer keeps `h2osoi_liq/ice = spval`** and the moss slot is written with `dz(c,0)*250` of ice. `clm_instMod.F90:261` gives every `istsoil` column poleward of 60 deg `h2osno = 100`, ~4 cold-start snow layers, so this fires on any grid with high-latitude land — ALP2 is at 60.82 N. The moss clobber is harmless (`NVPColdStart` overwrites slot 0 straight after); **the `spval` is repaired by nothing** and reaches the first timestep's SWE sum, thermal properties and water balance. Water half of the pair whose temperature half (`TemperatureType.F90:736`) the Task 5c sweep did catch | Stock, and correct under theirs: `j > snl` selects `-N .. 0`. Their 39/3 diff for the file is all `h2onvp_col` and two `cycle` guards; nothing in this hunk | Task 7 |
| `SoilFluxesMod.F90:213` and `:280` `SoilFluxes` | `j = col%snl(c)+1` splits ground evaporation into evaporation vs sublimation by the top layer's liquid:ice ratio (`:237-239`, `:257-259`) and sets `evaporation_limit` from its contents (`:287`, `:292-293`) | `j = -N+1`, one slot below `get_jtop_snow(c)`. At `N = 1` that is the **moss slot**: the sublimation cap becomes `(moss ice + moss liq)/(frac_sno_eff*dtime)` and both evaporation components come from moss water. **Consistently wrong today** — `SnowHydrologyMod.F90:1241` applies the fluxes at the same off-by-one `lev_top` — and **inconsistent the moment either is converted without the other**, which is what Task 6 does. Unbounded removal then arms the negative-mass `endrun`s at `SnowHydrologyMod.F90:1283-1292`/`:1296-1306` | Stock, and correct under theirs. Their 337/21 diff for the file skips stock lines 208-337 entirely; moss evaporation rides their separate `qflx_ev_nvp` path instead | Task 6, same commit as `lev_top` |
| `SoilTemperatureMod.F90:1765` `ComputeGroundHeatFluxAndDeriv` | `lyr_top = snl(c)+1` names the layer whose SNICAR-absorbed solar feeds `eflx_gnet_top`/`_snow`/`_soil` (`:1769`, `:1774`, `:1777`) and starts the `sabg_lyr_col` accumulation loop (`:1782`) | **No double count today**, because the matrix top-row tests are still stock too (`:2131`, `:2136`, `:2663`, `:2665`, `jtop(c) = snl(c)` at `:273`) and still agree with it. Once those move to `get_jtop_snow(c)` and `lyr_top` does not, row `-N` takes `hs_top_snow` carrying `sabg_lyr(p,snl+1)` while row `-N+1` *also* receives `fact*sabg_lyr_col(c,-N+1)` — the same quantity. Energy created, positive sign, order 100 W/m2 in daylight | Stock, and **consistently** so: they left `jtop` and the top-row tests stock as well, so nothing double-counts on their branch. Their comment at their :2272-2274 reasons explicitly about this and guards their new `hs_nvp` block with `snl(c) == 0`. Their own `[SOLAR DOUBLE-COUNT FIX]` at their :2975-2986 is a different site | Task 8, same commit as the `jtop` conversion |
| `SoilTemperatureMod.F90:1670` `ComputeGroundHeatFluxAndDeriv` | `lwrad_emit_snow(c) = emg(c)*sb*t_soisno(c,snl(c)+1)**4`, the snow endmember of the longwave fractionation balanced in `CanopyFluxes` and `Biogeophysics2` | reads the second snow layer, or the moss slot at `N = 1`, for the snow surface's emission temperature. No abort — wrong-but-plausible longwave — but it is the same class as `lyr_top`, in the same routine, and sits two statements from where Task 11 adds `lwrad_emit_nvp` | Stock, and correct under theirs | Task 11, alongside its `lwrad_emit_nvp` |
| `SnowSnicarMod.F90:1576-1579`, `:1721` `SnowAge_grain`; `WaterDiagnosticBulkType.F90:1283` `ResetBulk` | grain-size evolution over `snl_top .. snl_btm` with `cdz` as the density and dT/dz denominator, plus two hardcoded `snw_rds(...,0) = snw_rds_min` writes | `snl_top = snl(c_idx)+1` misses the top snow layer; `snl_btm = 0` puts the moss slot in the window, so `cdz(0) = frac_sno*dz(c,0)` is a **zero-thickness divide-by-zero** at `:1604` and `:1607`. `ResetBulk` is called from `SnowHydrologyMod.F90:855` for a freshly created pack and writes the moss slot instead of the new snow layer | Stock — their diff stops at their :1230, above the routine. **Their `cdz` denominator is wrong too**, since `snl_btm = 0` is the moss slot under either convention; only the `snl_top` half is ours alone | Task 6 |

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
