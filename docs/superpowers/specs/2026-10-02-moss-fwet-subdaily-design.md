# Moss wetness proxy: liquid/total split and sub-daily refresh — design

**Date:** 2026-10-02
**Author:** Sam Rabin, with Claude
**Amends:** `docs/superpowers/specs/2026-08-19-moss-grass-pft-design.md` (the "main spec";
§5, §6, §7, §9, §10, §11 point here)
**Plan:** `docs/superpowers/plans/2026-10-02-moss-fwet-subdaily.md` (to be written from this
spec). It replaces Step 3a of Task 12 in the main plan and runs before Task 12 Step 3b.
**Upstream input:** ESCOMP/CTSM#4198 (resolves ESCOMP/CTSM#4197), commit `9040710b0`,
fetched locally as `refs/remotes/escomp-pr/4198`.

## 1. Problem

The moss wetness proxy `fwet_moss = max(top-layer saturation, canopy wetted fraction)` is
diagnosed once a day, in `ed_ecosystem_dynamics`. The reason is what `bc_in%h2o_liqvol_sl`
contains. The daily `dynamics_driv` fill writes total water (liquid + ice) into it, while
`wrap_btran` overwrites it with liquid-only water at every canopy-flux step. Task 8 wanted
total water and so confined the proxy to the daily call.

The single daily value then feeds four consumers that run at different frequencies and
want different water:

| Consumer | Runs | Uses the proxy for |
|---|---|---|
| vcmax scaler `min(1, fwet/thresh)` | sub-daily | is the thallus hydrated enough to be active |
| leaf maintenance respiration, same scaler | sub-daily | same |
| CO₂ water-film resistance in the moss Ci solve | sub-daily | how much water blocks CO₂ diffusion |
| moss fuel moisture | daily | how wet the fuel is |

Two consequences follow. Moss's wetness limitation is constant through each day, because
photosynthesis reads a once-a-day value, so an afternoon rain cannot reach moss
photosynthesis until the next day. Moss GPP still varies within the day with light. And a
frozen top layer reads as fully wet to photosynthesis, so frozen moss runs at full
capacity.

## 2. Decisions (Sam, 2026-10-02 to 2026-10-05)

- Bring in ESCOMP/CTSM#4198 first, as its own task, so that `h2o_liqvol_sl` is
  liquid-only at both host fills. Fix, in a local commit in the same task, the PR's
  off-filter defect (§5, Task A).
- Capacity and respiration see **liquid water only**: frozen moss is inactive.
- The CO₂ water film sees **total water**: ice blocks diffusion as a water film does.
- Fuel moisture keeps **total water** (the Task 8 decision: frozen moss damps fire), read
  **instantaneously at the daily fire call**, as now. Basing it on a daily mean, as every
  other fuel class's weather is, is out of scope here and recorded in main spec §11.
- The total-water ingredient comes from a new coupler field carrying **total** volumetric
  water, not from liquid plus a separate ice field.
- No exposure guard on the daily proxy update, in any task.

## 3. Design

### 3.1 Two proxies

Both are patch members, both in [0, 1], both `max(soil ingredient, fwet_veg)`:

- **`fwet_moss_liq`**, soil ingredient `liq_top / watsat_top`. Consumers: the wetness
  scaler (`moss_wetness_scaler`, now derived from this proxy), and through it vcmax and
  leaf maintenance respiration.
- **`fwet_moss_tot`**, soil ingredient `tot_top / watsat_top`, from the total-water field
  of §3.2. Consumers: the CO₂ water-film factor (`MossCO2FilmFactor`, via the argument
  threaded into the moss Ci solve) and moss fuel moisture (`UpdateFuelMoisture`).

`fwet_moss` and its ingredient members `fwet_moss_soil` / `fwet_moss_canopy` are replaced by
`fwet_moss_liq`, `fwet_moss_tot`, `fwet_moss_soil_liq`, `fwet_moss_soil_tot` and
`fwet_moss_canopy`. The proxy argument threaded through `LeafBiophysicsMod` is renamed
`fwet_moss_tot` (Sam, 2026-10-05). It no longer encodes moss-ness in its sign. An explicit
`logical :: is_moss` argument selects the moss CO₂ path, and the negative sentinel
`fwet_moss_vascular` is removed. The NaN check in photosynthesis stays and covers both
proxies. Its job becomes catching a proxy that was never set, since a NaN can no longer
select the wrong physics. Every other site that names `fwet_moss` follows the new names.

Under freezing, CTSM's effective-porosity clamp already hands FATES zero liquid for a
fully frozen layer (main plan, upstream-observations bullet on that clamp). So
`fwet_moss_liq` falls toward the canopy ingredient, capacity collapses, and the film
resistance from `fwet_moss_tot` stays high. Both terms suppress frozen-moss GPP.

### 3.2 One new coupler field: total volumetric soil water

A new per-layer `bc_in` field, `h2o_totvol_sl` (name settled, Sam, 2026-10-05), carrying total volumetric water
[m³/m³], liquid plus ice, filled from `waterstatebulk_inst%h2osoi_vol_col` via the
standard 4-touch recipe. That is the field the daily fill of `h2o_liqvol_sl` read before
#4198. It is valid on every soil column, because it is derived from prognostic state, so
the total proxy never depends on `h2osoi_liqvol_col` or on exposure. It is filled at both
places `h2o_liqvol_sl` is filled, `dynamics_driv` and `wrap_btran`, following each site's
existing pattern for its neighbours (including `wrap_btran`'s -999 branch outside the
exposed-vegetation filter). That way the two fields' contents never depend on which host
routine wrote last. It takes the main spec's new coupler-field count from one to two.

`fwet_veg_pa` (Task 8's field) gains a sub-daily fill alongside its daily one.

### 3.3 Where the proxies are computed

Each proxy has one routine that defines it. The sub-daily call refreshes both. The daily
call refreshes only the total proxy:

- **Sub-daily, both proxies:** at the top of `FatesPlantRespPhotosynthDrive`, for every
  non-bareground patch that `wrap_photosynthesis` has flagged as exposed
  (`bc_in%filter_photo_pa == 2`), before any cohort reads them. That is the flag
  photosynthesis itself is gated on (`FatesPlantRespPhotosynthMod.F90:367`). The refresh
  must be gated on it too, because `FatesPlantRespPhotosynthDrive` visits every site, and
  on a fully buried column `wrap_btran` has written -999 into the soil fields. An ungated
  refresh would clamp that to a zero soil ingredient. Buried patches keep their last
  values. Photosynthesis is reached inside CTSM's canopy-flux iteration loop, so the
  refresh may run more than once per timestep. Its inputs are fixed within a timestep, so
  repeated calls are idempotent.
- **Daily, total proxy only:** the existing slot in `ed_ecosystem_dynamics`, ahead of
  `DailyFireModel`, for every non-bareground patch, so that snow-buried patches still get a
  fresh fuel-moisture input. The liquid proxy is not refreshed here: it has no daily
  consumer, and its sub-daily refresh is the only one that runs when the patch is about to
  photosynthesize.

The comments that tie the proxy to the daily call are rewritten to state the new contract.
Two forbid a sub-daily writer (`EDMainMod.F90` at the `UpdateMossFwet` call, and
`UpdateMossFwet`'s header in `FatesPatchMod.F90`). One explains the daily placement by the
fill's water phase (`clmfates_interfaceMod.F90` `dynamics_driv`).

### 3.4 History, restart, fusion

- History: `FATES_MOSS_FWET_LIQ`, `FATES_MOSS_FWET_TOT`, `FATES_MOSS_FWET_SOIL_LIQ`,
  `FATES_MOSS_FWET_SOIL_TOT`, `FATES_MOSS_FWET_CANOPY`, `FATES_MOSS_WETNESS_SCALER`. They
  replace `FATES_MOSS_FWET`, `FATES_MOSS_FWET_SOIL` and `FATES_MOSS_FWET_CANOPY`. Because the
  values change every timestep, they move from the daily (`update_history_dyn`) group to
  the high-frequency (`update_history_hifrq`) group. Registration otherwise follows the main
  plan's Global Constraint for moss history variables, including the `FatesNvp`
  `hist_fincl1 +=` entries. The wetness scaler's long name is updated to say it derives
  from the liquid proxy.
- Restart: both proxies and all three ingredients are restarted (`fates_fwet_moss_*`), for
  the reason Task 8 found: `restart()` writes history before the first update. The wetness
  scaler stays recomputed on restart read, from `fwet_moss_liq`.
- Fusion: area-weighted, as now, for all five members, then the scaler is recomputed.

## 4. Behaviour that changes

- **ESCOMP/CTSM#4198 and its local fix change answers for every FATES run, moss on or
  off.** Daily `smp_sl` becomes liquid-based, which moves `smp_memory` and so drought
  phenology, and `FATES_MEANLIQVOL_DROUGHTPHEN_PF` reports liquid water. From Task A on,
  the main spec's rule that moss-off runs are bit-for-bit with baseline holds against
  baselines generated after Task A, not against the Task 0 baselines.
- **The daily and sub-daily liquid fills are sampled at different points in the
  timestep.** After Task A's fix, the daily fill computes liquid from end-of-timestep soil
  water, as the pre-#4198 total-water fill did. The sub-daily fill uses liquid as
  `CanopyFluxes` computed it, before that timestep's soil hydrology. Both use the same
  routines and the same clamp, so the difference is one timestep of hydrology on exposed
  columns.
- **Moss's wetness limitation varies within the day** (Task D), following sub-daily soil
  liquid and canopy wetting.
- **Frozen moss stops photosynthesizing.** The main plan's Step 3f measured the moss
  patch's total-water saturation at 0.75-1.00 on the zero-btran (frozen) days, which put
  moss at full capacity then. With the liquid proxy those days read near-dry. Main plan
  Task 12 Step 3b's productive-window analysis must be read against the two proxies, not
  against the old single one.
- **Fuel moisture is unchanged in meaning** (total water, end-of-day instantaneous).
  Between Task A and Task C it is temporarily liquid-based (§5).

## 5. Work breakdown

Four tasks, strictly in order.

- **Task A: bring in ESCOMP/CTSM#4198 and fix its off-filter defect.** Two commits:
  1. Cherry-pick `9040710b0` unchanged.
  2. A local fix. #4198 makes `dynamics_driv` read `waterdiagnosticbulk_inst%h2osoi_liqvol_col`
     for every FATES column, but that field is not valid on all of them. Its only writer
     is `calc_volumetric_h2oliq` (`SoilMoistStressMod.F90:171-217`). That is called only
     from `CanopyFluxes` (`CanopyFluxesMod.F90:851`), over the columns of the
     `filter_exposedvegp` patches. The field is allocated as NaN
     (`WaterDiagnosticBulkType.F90:202`), and it has no cold-start value, no restart
     variable and no history field. So at the daily call, a column with no exposed patch
     holds NaN if it has been buried since the run segment began, or otherwise a stale
     value from its last exposure. A restart resets it to NaN, so a column buried across a
     restart would differ between the restarted and straight-through runs. The fix: in
     `dynamics_driv`, compute liquid volumetric water into a local array for every FATES
     column with `calc_effective_soilporosity` then `calc_volumetric_h2oliq` (the same
     routines and arguments `CanopyFluxes` uses), from `h2osoi_liq`, `h2osoi_ice`,
     `watsat` and `dz`. Use that array for both lines #4198 changes: the `h2o_liqvol_sl`
     fill and the `s_node` behind `smp_sl`. `h2osoi_liqvol_col` itself is untouched.
     The `s_node` denominator also switches from `soilstate_inst%eff_porosity_col` to the
     locally computed effective porosity (Sam, 2026-10-05). That field has two writers with
     different formulas: `calc_effective_soilporosity` from `CanopyFluxes`, unfloored, on
     exposed columns; and `SetSoilWaterFractions`, floored at 0.01, on every soil column.
     ESCOMP/CTSM#4244 reports the duplication. With the switch, the daily `s_node` uses
     exactly `wrap_btran`'s formula.

  The second commit also corrects the comments #4198 makes false (the `dynamics_driv` fill
  comment, `EDMainMod`'s writer comment, `UpdateMossFwet`'s header). This leaves an
  accepted interim state: one daily proxy, liquid-only and valid on every column, feeding
  all four consumers.
- **Task B: add the total-water field and split the proxy into liquid and total**, both
  still refreshed daily, with every consumer still reading the liquid proxy so the split
  can be shown to change no answers (Sam, 2026-10-06). It opens with two bit-for-bit
  commits: the `fwet_moss_tot` rename, then the `is_moss` logical (§3.1). The total-water
  field is filled at both host sites (§3.2). History and restart are renamed and extended
  (§3.4), still in the daily group, and the `FatesNvp` testmod gains an instantaneous
  `H2OSOI`. Check, on the moss ALP2 tape:
  - every history field shared with the post-Task-A baseline is bit-for-bit;
  - `FATES_MOSS_FWET_SOIL_TOT` equals `min(1, H2OSOI/WATSAT)` for layer 1, times the
    vegetated area fraction the main plan's Step 3b describes. It reads the same CTSM
    field, so the match is exact.
  - `FATES_MOSS_FWET_SOIL_LIQ` ≤ `FATES_MOSS_FWET_SOIL_TOT` on every day, with equality on
    thawed days.
- **Task C: move the CO₂ film and fuel moisture to the total proxy.** Capacity and
  respiration stay on the liquid proxy. This is the answer-changing half of the split. It
  closes with a separate commit adding a 12-hourly history tape to the `FatesNvp` testmod,
  for Task D's diurnal check (Sam, 2026-10-05).
- **Task D: refresh both proxies sub-daily**: the sub-daily `fwet_veg_pa` fill, the gated
  call at the top of `FatesPlantRespPhotosynthDrive` (§3.3), the daily call reduced to the
  total proxy, and the move to the high-frequency history group. Step 0 must verify that
  CTSM's `fwet_patch` has been updated for the current timestep when FATES photosynthesis
  runs, and that FATES's high-frequency history is written after photosynthesis within the
  timestep. If either is false, stop and report. A one-step lag is a design change for
  Sam, not something to adopt silently. Check: on the 12-hourly tape Task C adds, the two
  daily records of `FATES_MOSS_FWET_LIQ` and `FATES_MOSS_WETNESS_SCALER` differ on some
  snow-free days, where under Task C they were always equal.

**Why A comes before B is load-bearing:** before #4198 the daily fill of `h2o_liqvol_sl`
carries total water, so B's liquid proxy would be fed total water at the daily call and
the split would be meaningless. **B before C** is load-bearing too: B's bit-for-bit check
is the evidence that the split changes nothing, and it can only be made before C changes
answers. **C before D** is the project's strict-ordering convention, and D's diurnal check
reads C's tape. Finishing the split first lets its checks isolate the liquid/total
semantics before D changes when the proxies are sampled.

**Failed verifications are stops.** In particular: Task B's three checks and Task D's two
timing checks (above). If the total ingredient does not match `H2OSOI`, the new field is
not what §3.2 says. Do not document any of these as a limitation and carry on.

## 6. Out of scope

- Moss fuel moisture from a daily mean of `fwet_moss_tot` (main spec §11).
- Standing water and water-table depth as proxy ingredients (main spec §11).
- Changing which quantity stands in for thallus water (main plan Task 12 Step 3b's open
  question).
