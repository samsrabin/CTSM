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
  **instantaneously at the daily fire call**: the value refreshed earlier in that timestep (§3.3). Basing it on a daily mean, as every other fuel class's weather is, is out of scope here and recorded in main spec §11.
- The total-water ingredient comes from a new coupler field carrying **total** volumetric
  water, not from liquid plus a separate ice field.
- No exposure guard on the proxy update, in any task. From Task D the proxies are refreshed every timestep for every non-bareground patch, snow-buried ones included, and the daily update is dropped (Sam, 2026-10-20). A buried patch needs current values for the planned daily-mean fuel moisture (main spec §11), and the moss proxy may later be untied from CTSM's canopy wetted fraction, which CTSM forces to zero under snow.
- The moss wetness scaler is not stored. It is a function of `fwet_moss_liq`, evaluated
  where it is used, so its correctness does not depend on call order or refresh frequency
  (Sam, 2026-10-07).
- The canopy ingredient splits by water phase like the soil one. CTSM's canopy wetted
  fraction is computed from canopy snow plus liquid, so it feeds the total proxy. The
  liquid proxy gets a wetted fraction computed from canopy liquid alone (Sam, 2026-10-07).

## 3. Design

### 3.1 Two proxies

Both are patch members, both in [0, 1], both `max(soil ingredient, canopy ingredient)`:

- **`fwet_moss_liq`**, soil ingredient `liq_top / watsat_top`, canopy ingredient the
  wetted fraction from canopy liquid alone (§3.2). Consumers: the wetness scaler
  (`MossWetnessScaler()`, a function of this proxy), and through it vcmax and leaf
  maintenance respiration.
- **`fwet_moss_tot`**, soil ingredient `tot_top / watsat_top`, from the total-water field
  of §3.2, canopy ingredient CTSM's `fwet` (canopy snow plus liquid). Consumers: the CO₂
  water-film factor (`MossCO2FilmFactor`, via the argument threaded into the moss Ci
  solve) and moss fuel moisture (`UpdateFuelMoisture`).

`fwet_moss` and its ingredient members `fwet_moss_soil` / `fwet_moss_canopy` are replaced by
`fwet_moss_liq`, `fwet_moss_tot`, `fwet_moss_soil_liq`, `fwet_moss_soil_tot`,
`fwet_moss_canopy_liq` and `fwet_moss_canopy_tot`. The proxy argument threaded through `LeafBiophysicsMod` is renamed
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
the total proxy never depends on `h2osoi_liqvol_col` or on exposure. It is filled where `h2o_liqvol_sl` is, in `dynamics_driv` and `wrap_btran` (including `wrap_btran`'s -999 branch outside the exposed-vegetation filter), and kept with those fills although moss is its only reader for now (Sam, 2026-10-20). It takes the main spec's new coupler-field count from one to two.

From Task D, `wrap_moss_wetness` also replaces `wrap_btran`'s -999 in `h2o_liqvol_sl`, `h2o_totvol_sl` and `watsat_sl` with real values on sites outside the filter, using the same liquid-water computation as Task A's daily fill. It writes after `wrap_btran`'s own consumers (`get_active_suction_layers`, `btran_ed`) have run. The only other sub-daily reader is plant-hydraulics history (`update_history_hydraulics`), whose root-weighted and per-layer soil water, saturation and matric potential averaged the sentinel on buried columns and now report real values, moss on or off (Sam, 2026-10-20). The fill is not gated on moss, so moss-off tests confirm that nothing else reads these fields.

`fwet_veg_pa` (Task 8's field) and `fwet_veg_liq_pa` are filled in `wrap_moss_wetness` every timestep for every patch. Task D drops their daily fills.

A second new per-patch `bc_in` field, `fwet_veg_liq_pa`, carries the canopy wetted
fraction computed from canopy liquid alone. CTSM computes it in `BulkDiag_FracWet` beside
`fwet`, with the same expression, exponent and cap but `liqcan` in place of
`snocan + liqcan`, into a new diagnostic `waterdiagnosticbulk_inst%fwet_liq_patch` with no history variable. It is filled wherever `fwet_veg_pa` is. That makes three new coupler fields in the main spec's count. Task D gives it a restart variable, `FWET_LIQ`, registered in every run (Sam, 2026-10-20). `BulkDiag_FracWet` rewrites it only for active patches and cold-start init zeroes it at every start, so without one, a FATES patch with zero canopy area (inactive) would feed the refresh a different value after a restart than in a straight-through run.

### 3.3 Where the proxies are computed

Each proxy has one routine that defines it, and both have one caller. From Task D, a FATES routine, `UpdateMossWetness` (`EDMainMod`), refreshes both proxies every timestep for every non-bareground patch, exposed or snow-buried. It is called at the end of a new interface method, `wrap_moss_wetness`, which `CanopyFluxes` calls immediately after `wrap_btran` (Sam, 2026-10-20). That placement gives:

- **every input current and real for every site.** `wrap_moss_wetness` fills the soil fields off the filter and both canopy wetted fractions for every patch (§3.2). CTSM computes the wetted fractions earlier in the same timestep, in `CanopyInterceptionAndThroughfall`.
- **one refresh per timestep, ahead of photosynthesis.** It runs before the canopy-flux iteration loop, so every photosynthesis call in a timestep sees the same proxies. It also runs on a timestep where no patch on the clump is exposed, when the loop, and so FATES photosynthesis, does not run at all.
- **fire reads the latest value.** At the day boundary, `DailyFireModel` reads the proxies refreshed earlier in the same timestep. The daily proxy call in `ed_ecosystem_dynamics` is removed, along with `dynamics_driv`'s fills that only it read.

The comments that tie the proxy to the daily call are removed with it. `UpdateMossWetness`'s header states the contract, and each proxy routine's header names it as the caller.

### 3.4 History, restart, fusion

- History: `FATES_MOSS_FWET_LIQ`, `FATES_MOSS_FWET_TOT`, `FATES_MOSS_FWET_SOIL_LIQ`,
  `FATES_MOSS_FWET_SOIL_TOT`, `FATES_MOSS_FWET_CANOPY_LIQ`, `FATES_MOSS_FWET_CANOPY_TOT`,
  `FATES_MOSS_WETNESS_SCALER`. They
  replace `FATES_MOSS_FWET`, `FATES_MOSS_FWET_SOIL` and `FATES_MOSS_FWET_CANOPY`. Because the
  values change every timestep, they move from the daily (`update_history_dyn`) group to
  the high-frequency (`update_history_hifrq`) group. Registration otherwise follows the main
  plan's Global Constraint for moss history variables, including the `FatesNvp`
  `hist_fincl1 +=` entries. The wetness scaler's long name is updated to say it derives
  from the liquid proxy.
- Restart: both proxies and all four ingredients are restarted (`fates_fwet_moss_*`), for
  the reason Task 8 found: `restart()` writes history before the first update. The wetness
  scaler needs no restart variable, because it is evaluated from `fwet_moss_liq`.
- Fusion: area-weighted, as now, for all six members.

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
  moss at full capacity then. With the liquid proxy those days read near-dry. Until Task R
  gives the liquid proxy a liquid-only canopy ingredient, canopy snow can still hold it at
  the canopy cap, as on the frozen days of the post-Task-C nocomp run. Main plan
  Task 12 Step 3b's productive-window analysis must be read against the two proxies, not
  against the old single one.
- **Fuel moisture is unchanged in meaning** (total water, instantaneous at the fire call). Between Task A and Task C it is temporarily liquid-based (§5). From Task D it reads the proxy refreshed earlier in the fire timestep, from soil water before that timestep's hydrology, rather than from end-of-timestep water.
- **Snow-buried patches' proxies follow soil water every timestep** (Task D), rather than holding a once-daily value.
- **Plant-hydraulics history reports real soil water on buried columns** (Task D, moss on or off; §3.2).
- **The CTSM restart file gains `FWET_LIQ`** (Task D, moss on or off; §3.2).

## 5. Work breakdown

Five tasks, strictly in order.

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
- **Task R: review fixes for Tasks B and C** (Sam, 2026-10-07), one commit per change.
  Bit-for-bit test and comment corrections; the wetness scaler becomes a function of
  `fwet_moss_liq` rather than a stored member; `fwet_moss_canopy` is renamed
  `fwet_moss_canopy_tot`. Last, and answer-changing for moss: the liquid proxy's canopy
  ingredient becomes the liquid-only wetted fraction of §3.2. Check:
  `FATES_MOSS_FWET_CANOPY_LIQ` ≤ `FATES_MOSS_FWET_CANOPY_TOT` on every day.
- **Task D: refresh both proxies every timestep** (§3.3), in three commits that change one thing each. First, `wrap_moss_wetness` fills real soil water off the filter and both canopy wetted fractions, with no refresh yet; Sam runs the `fates_nvp` suite, and anything other than the plant-hydraulics history fields changing is a stop that changes this task's strategy. This comes first because it is the change most likely to force a redesign. Second, the `FWET_LIQ` restart variable. Third, `UpdateMossWetness`, the removal of the daily call and its fills, and the move to the high-frequency history group. Step 0 must verify that CTSM's `fwet_patch` has been updated for the current timestep when `wrap_btran` runs, and that FATES's high-frequency history is written after photosynthesis within the timestep. If either is false, stop and report. A one-step lag is a design change for Sam, not something to adopt silently. Check: on the 12-hourly tape Task C adds, the two daily records of `FATES_MOSS_FWET_LIQ` and `FATES_MOSS_WETNESS_SCALER` differ on some snow-free days, where under Task C they were always equal; and `FATES_MOSS_FWET_SOIL_TOT` is nonzero on snow-buried days.

**Why A comes before B is load-bearing:** before #4198 the daily fill of `h2o_liqvol_sl`
carries total water, so B's liquid proxy would be fed total water at the daily call and
the split would be meaningless. **B before C** is load-bearing too: B's bit-for-bit check
is the evidence that the split changes nothing, and it can only be made before C changes
answers. **C before D** is the project's strict-ordering convention, and D's diurnal check
reads C's tape. **R before D** is load-bearing: D's sub-daily refresh feeds the liquid
proxy the canopy field R adds. Finishing the split first lets its checks isolate the liquid/total
semantics before D changes when the proxies are sampled.

**Failed verifications are stops.** In particular: Task B's three checks, Task D's two timing checks and its first-commit suite run (above). If the total ingredient does not match `H2OSOI`, the new field is
not what §3.2 says. Do not document any of these as a limitation and carry on.

## 6. Out of scope

- Moss fuel moisture from a daily mean of `fwet_moss_tot` (main spec §11).
- Standing water and water-table depth as proxy ingredients (main spec §11).
- Changing which quantity stands in for thallus water (main plan Task 12 Step 3b's open
  question).
