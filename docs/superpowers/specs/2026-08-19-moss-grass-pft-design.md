# Moss as a grass-like FATES PFT: design

**Date:** 2026-08-19
**Author:** Sam Rabin, with Claude
**Base:** CTSM `ctsm5.4.028` (FATES `sci.1.91.1_api.43.1.0`)
**Reference implementation harvested from:** branch `ctsm5.4.028_nvp` (CTSM `997cb054a`, FATES `33640d372`; Hui Tang's NVP-layer port)

## 1. Motivation and goals

Moss is a major component of boreal surface fuel loads, and its moisture behavior differs
sharply from vascular vegetation. CTSM-FATES has no moss. This project adds a minimal
moss representation whose purpose is realistic moss contribution to **fuel loading** and
**fuel moisture** in SPITFIRE.

Requirements:

- Moss carbon, nitrogen, and water fluxes are fully **prognostic and conserving**
  (establishment, photosynthesis, respiration, death, decomposition, transpiration).
- Moss **fuel moisture is diagnostic**, driven by a soil-moisture proxy — consistent with
  how FATES treats all fuel moisture (no vegetation water content is prognostic anywhere
  in CTSM-FATES).
- The model reports moss **fractional area coverage**, the one variable for which we have
  site observations (two moss species at a few boreal sites).

Non-goals (this phase): prognostic vegetation water content; moss as a vertical column
layer with its own energy/water balance (the `ctsm5.4.028_nvp` approach); moss effects on
ground evaporation, soil insulation, or surface albedo; emergent (competitive) moss cover.

## 2. Approach and scope

Moss is implemented as a **new non-woody FATES PFT** — "a very special kind of grass" —
defined almost entirely on the FATES parameter file, piggybacking on grass code paths for
demography, competition, litter, and fuel, with targeted FATES-side changes for
physiology and fire. CTSM changes are limited to namelist plumbing.

Primary target configuration: **nocomp fixed-biogeography** at boreal sites, SPITFIRE on,
no plant hydraulics. Full competition mode is a later phase, but parameter and code
choices must not foreclose it (see §11).

**Satellite phenology (FATES-SP) is also supported.** Moss must run in both nocomp
fixed-biogeography and SP mode. SP is not where the science lives — LAI is prescribed
there, and CTSM's build-namelist makes `fates_spitfire_mode > 0` a fatal error whenever
`use_fates_sp` is true, so **no SP configuration can exercise the fire pathway at all**.
Its value is as a cheap, fast smoke test that the moss PFT initializes, allocates, and
conserves. Consequence for testing: every fuel and fire behaviour in §6 must be verified
in the non-SP nocomp fixed-biogeography configuration, which is the only one where
SPITFIRE can be on.

Why nocomp first: full-competition FATES is numerically and parametrically hostile to a
centimeter-scale PFT (strict-PPA shortest-first demotion, termination past
`nclmax` layers, state variables near termination floors). In nocomp, moss owns its own
patches, sits in canopy layer 1, and `FATES_NOCOMP_PATCHAREA_PF` provides a true
non-overlapping fractional cover. Cover is prescribed rather than emergent in this mode;
that is accepted for the initial implementation.

## 3. Moss PFT parameterization

A 15th PFT column on the FATES parameter file, harvested from
`fates_params_default_moss.json` on the NVP branch (Porada et al. 2013-based vcmax, SLA,
etc.), with these deliberate settings:

- `fates_woody = 0` — routes moss through all non-woody (grass) code paths: live biomass
  into the live fuel pool, stem litter into leaf fines, no treefall disturbance, dbh
  forced from leaf carbon.
- **Identification:** adopt the NVP branch's `fates_vascular` per-PFT parameter
  (currently unread there) as the flag that marks moss/NVP PFTs. Grass = `woody==0 &&
  vascular==1`; moss = `woody==0 && vascular==0`. Per-PFT parameters necessarily live on
  the parameter file.
- **Reproduction fixed (moss column only):** reproductive allocation is `seed_alloc`
  below the dbh reproduction threshold and `seed_alloc + seed_alloc_mature` above it
  (`PRTAllometricCarbonMod.F90:1074-1078`). Grass survives its `seed_alloc = 0` because it
  clears its 3 cm threshold and then collects `seed_alloc_mature = 0.25`; moss
  (dbh ~0.03 cm) never crosses 3 cm, so it would sit on the immature branch at zero
  forever and go extinct. **The fix is to drop the dbh threshold to ~0 — that alone is
  sufficient**, because it puts moss on the mature branch where the inherited
  `seed_alloc_mature = 0.25` applies. `fates_recruit_seed_alloc` is deliberately left at
  the grass/NVP value of 0: there is no positivity requirement on it (the only constraint
  is `seed_alloc + seed_alloc_mature <= 1`, `PRTParamsFATESMod.F90:722`), and the one
  other consumer — the Tree Recruitment Scheme branch — is unreachable for moss, being
  gated on `allom_dbh_maxheight > 15 cm`. Raising it would be a pure tuning increase, so
  it stays aligned with the NVP branch. Both `seed_alloc` and `seed_alloc_mature` are
  therefore inherited and must not be "tidied" out of the moss column. These are per-PFT
  (`fates_pft`-dimensioned) parameters, and all other PFTs keep their defaults. ("Seed" is
  a mass pool with first-order germination; representationally fine for spores/fragments.)

  *(Amended 2026-08-21. The original text said to "set `fates_recruit_seed_alloc > 0` and
  drop the dbh threshold to ~0". That rested on an incomplete premise — it treated
  `seed_alloc` as the operative lever and did not account for `seed_alloc_mature` carrying
  the mature branch.)*
- `fates_allom_dbh_maxheight` is **inherited from grass (20 cm), not made moss-specific.**
  An earlier version of this spec set it below 15 cm so germination would take the simple
  non-tree path rather than the tree-recruitment-scheme (TRS) machinery. That reason does
  not apply: every TRS gate is conjoined with a `hlm_regeneration_model` test, and
  `fates_regeneration_model` defaults to `default`, so with TRS off the parameter has no
  recruitment effect at all — and this project will not run TRS while it remains
  experimental. The parameter's other job is real but is accepted as a limitation: it is
  the diameter at which height and max-leaf-biomass saturate, entering `d2h_*` and
  `d2blmax_*` only as `min(d, dbh_maxh)`, so inheriting 20 cm leaves moss height
  effectively unbounded under the `grass_powerlaw` allometry (§4, §12).
- Recruit height (`hgt_min`): a **realistic** moss height — a taller recruit inflates
  the allometric per-plant target biomass. Raise it only as a fallback if cohort
  termination floors (`store_c` and number-density minima, which apply in all modes, not
  just full competition) actually cull moss in testing; watch the termination-mortality
  history diagnostics (`FATES_MORTALITY_TERMINATION_*`).
- **Shallow grass-style roots, NOT the NVP branch's no-root profile mode 4.** Water
  conservation requires it: moss transpiration is extracted from soil through the
  FATES-supplied root profile (`rootr`); an all-zero profile would break the water budget
  in this layerless design. Concentrate the rooting profile in soil layer 1
  (`fnrt_prof_mode`/params) so moss water status tracks surface moisture — the right
  signal through an admittedly fictitious pathway.
- Standard grass allometry modes otherwise (`allom_lmode=5`, `allom_amode=5`,
  `allom_smode=2`, `allom_dmode=1`). The resulting "sapwood" pool is a labeled carbon
  pool only; harmless without plant hydraulics, and it correctly burns as live fuel.

## 4. Height allometry: two modes, namelist-selectable

Moss height is dynamic for free (height = allometric function of dbh; dbh is continuously
forced from leaf carbon for non-woody PFTs). Two carbon-to-height mappings are
implemented, chosen by a CTSM namelist setting (§8):

1. **Grass power law** (existing `allom_hmode=3`, `d2h_2pwr`) with moss-tuned
   coefficients. Zero new allometry code.
2. **Mat thickness** (new `h_allom` mode): height = mat depth derived from leaf carbon
   via SLA and a moss bulk-density parameter, harvested from the NVP branch's
   `NVP_allom` (`FatesAllometryMod`). More mechanistic for a moss mat.

The new mode must be invertible (an `h2d_allom` case) so `ForceDBH` and recruitment
initialization work. Height feeds snow occlusion of LAI (`fraction_exposed =
1 − snow_depth/height`), so either mode gives seasonally sensible snow burial.

## 5. Physiology

All in FATES (`FatesPlantRespPhotosynthMod`, `LeafBiophysicsMod`):

- **Per-PFT conductance/photosynthesis model dispatch.** The stomatal model is currently
  a single global switch set from the CTSM namelist, which is why the NVP branch's
  moss formulation is dead code there. Add a per-PFT dispatch so moss uses its own path
  while vascular PFTs keep Ball-Berry/Medlyn.
- **Moss CO₂ path** (harvest from NVP branch `LeafBiophysicsMod` `nvp_model=3`): no
  stomatal solve; CO₂ diffuses through the leaf boundary layer with a water-film
  resistance factor `(1 − fwet)^12` (Porada et al. 2013).
- **Wetness-limited capacity:** `vcmax × min(1, fwet/0.6)` (full capacity above 60%
  saturation; Porada et al. 2013).
- **fwet proxy:** `fwet = max(top-soil-layer effective saturation, canopy wetted
  fraction)` for the moss patch. The soil part comes from moisture fields already present
  in `bc_in` (used by btran); the canopy wetted fraction is one new `bc_in` field (§7).
- **Interception supplies the thallus-wetness signal.** Moss interception comes free and
  unchanged from CTSM (`CanopyHydrologyMod`, no FATES branch): intercepted water enters
  the patch canopy store (`liqcan`/`snocan`, capacity ~ LAI+SAI) and exits only by
  evaporation from the wetted canopy fraction or by drip/throughfall to the ground —
  never entering the plant, fully conserving. Because this is an existing
  prognostic-water mechanism, the moss fwet proxy uses its wetted fraction directly (no
  new water state is created), and drip additionally feeds the soil half of the proxy.
- **Gas parameters use `t_veg`** (patch vegetation temperature) for moss initially. The
  NVP branch's per-cohort gas-parameter separation (FATES `33640d372`) is the drop-in
  pattern if a ground-temperature proxy is added later (§11).
- **btran** comes through the standard shallow-root pathway (§3); no override needed.
- Plant hydraulics is unsupported for moss (pre-existing FATES divide-by-zero for PFTs
  under ~10 cm); `use_fates_moss` + `use_fates_planthydro` is a fatal namelist error.

Conservation: moss C/N flows through standard PARTEH pools and litter fluxes; moss water
through the standard root-uptake/transpiration pathway. fwet only scales vcmax, the CO₂
water-film term, and fuel moisture — it stores no water. Existing CTSM/FATES balance
checks remain fatal.

## 6. Fire

All in FATES `fire/` plus the biomass routing points:

- **Two new fuel classes — "live moss" and "dead moss (duff)"** — growing
  `num_fuel_classes` from 6 to 8, each with its own SAV and bulk density (new entries on
  the `fates_litterclass` dimension). `num_fuel_classes` becomes a runtime value read from
  the size of the parameter file's `fates_litterclass` dimension, and the length-6
  `SF_val_*` parameter arrays and `fuel_type` members become allocatable. Because the moss
  classes are *appended*, indices 1–6 keep their meanings, and the fragile CWD-index
  aliasing in `EDPatchDynamicsMod` (burnt-litter loop assumes fuel classes 1–4 are CWD 1–4)
  needs no change — verified: every one of those loops is `do c = 1,ncwd`, so a longer fuel
  array never reaches them.
- **Live routing:** live biomass of moss PFTs (`vascular==0`) goes to the live-moss class
  instead of live grass (`UpdateLiveGrass` in `FatesPatchMod`).
- **Dead routing:** FATES litter carries no PFT tag — `litter%leaf_fines` is dimensioned
  by decomposability pool only (`FatesLitterMod.F90`) — so dead moss gets parallel
  `moss_fines` / `moss_fines_in` / `moss_fines_frag` pools on the litter object, threaded
  through allocation, init, copy, fuse, burn, and fragmentation. Moss-PFT leaf and stem
  turnover routes there instead of `leaf_fines`; the `moss_fines` pool feeds the
  dead-moss fuel class; fragmentation feeds the same CTSM-BGC decomposition flux as leaf
  fines, so carbon conservation holds end to end.
- **Moss fuel moisture is diagnostic from the fwet proxy** (§5), not the Nesterov index,
  via moss branches in `UpdateFuelMoisture`. Initial functional form: a simple monotonic
  mapping `moisture = a + b·fwet`, with separate coefficient pairs for the live-moss and
  dead-moss classes (all four on the CTSM namelist, §8); refinable if a better-supported
  form emerges.
- **Burn response mirrors grass, except for the burn-fraction cap:** each moss class
  burns per its own effective moisture. Moss cohorts take `leaf_burn_frac` from the
  live-moss class's `frac_burnt` (analogous to the existing live-grass keying in
  `EDPatchDynamicsMod`), combusting leaf + sapwood + structure, defoliating without
  individual mortality — regrowth from storage stands in for regrowth from surviving
  fragments. The `moss_fines` litter pool burns per the dead-moss class's `frac_burnt`,
  alongside the existing burnt-litter accounting.
- **Moss does NOT inherit grass's 0.8 maximum burn fraction.** Grass is capped by a
  hardcoded `max_grass_frac = 0.8` applied to the live-grass fuel class only, encoding
  surviving tillers and meristems; moss has no equivalent, and a moss mat can burn off
  completely. Live moss instead gets its own cap on the CTSM namelist (§8), defaulting to
  1.0 — i.e. no cap by default, with the knob present so it can be tightened during
  tuning without a code change. Grass's cap is untouched. Because moss cohort
  `leaf_burn_frac` is keyed off the live-moss class's `frac_burnt`, the cohort-level
  combustion inherits this limit automatically.

## 7. CTSM–FATES interface

One new coupler field: the per-patch canopy wetted fraction (CTSM's `fwet_patch`)
enters FATES as a new `bc_in` field via the standard 4-touch recipe (declare in
`FatesInterfaceTypesMod`, allocate in `allocate_bcin`, flush in `zero_bcs`, fill in
`clmfates_interfaceMod`), supplying the thallus-wetness half of the fwet proxy (§5).
Soil-moisture inputs already cross in `bc_in`. New scalar controls cross via the
existing `set_fates_ctrlparms` mechanism.

## 8. CTSM namelist

Per project convention, **all new scalar settings — switches and science constants — go
on the CTSM namelist**, not the FATES parameter file. (Reconsider individual constants
only at upstream-FATES merge time.) Standard seven-step plumbing (XML definition,
defaults, `CLMBuildNamelist.pm` logic, `clm_varctl`, `controlMod` read/broadcast,
`clmfates_interfaceMod` `set_fates_ctrlparms`, FATES-side `case` + is-set check):

- `use_fates_moss` (logical, default `.false.`) → `hlm_use_moss`. Gates the moss fuel class,
  moss physiology dispatch, and moss allometry mode. Fatal errors: `use_fates_moss` true with
  no `vascular==0` PFT on the parameter file (and vice versa); `use_fates_moss` with
  `use_fates_planthydro`.
- `fates_moss_height_allom` (string: `'grass_powerlaw'` | `'mat_thickness'`) → selects the
  height-allometry mode applied to moss PFTs (§4).
- Moss science scalars: at minimum, moss bulk density (mat-thickness allometry), the
  fuel-moisture coefficient pairs for the live-moss and dead-moss classes (`a`, `b` each;
  §6), and the live-moss maximum burn fraction (§6; default 1.0).
  Any further scalars discovered during implementation follow the same convention.
  (SAV and fuel bulk density for the two new classes are *array* entries on the existing
  `fates_litterclass` parameter-file dimension, which must grow to 8 regardless — they
  stay on the parameter file like other array parameters.)

## 9. Diagnostics and validation

- `FATES_NOCOMP_PATCHAREA_PF`: true per-PFT fractional cover in nocomp (prescribed;
  validates bookkeeping). `FATES_CROWNAREA_PF` etc. come free (requires
  `fates_history_dimlevel(2) >= 2`) and become the emergent-cover variables under full
  competition later.
- New history variables for debugging and evaluation, at minimum:
  - `FATES_MOSS_FWET` — the fwet proxy (patch-level), plus its two ingredients
    (top-soil-layer saturation and canopy wetted fraction as seen by FATES) so proxy
    behavior can be decomposed;
  - `FATES_MOSS_VCMAX_SCALER` — the `min(1, fwet/0.6)` wetness scalar actually applied;
  - fuel load and fuel moisture for the live-moss and dead-moss classes
    (fuel-class-dimensioned history variables extend automatically when the dimension
    grows to 8);
  - moss height and the `moss_fines` litter pool.
- Standard per-PFT biomass/GPP/crown-area variables come automatically.
- Validation target: observed fractional cover of two moss species at boreal sites; plus
  qualitative fuel-load and fuel-moisture behavior.

## 10. Testing

- Existing balance checks (C/N/water/energy) remain fatal and must pass with `use_fates_moss`
  on and off.
- `use_fates_moss = .false.` must be bit-for-bit with baseline (all changes gated).
- `use_fates_moss = .true.` with a parameter file lacking a moss PFT must abort cleanly.
- Site-level smoke/exact-restart tests in nocomp-fixedbiogeo with a moss parameter file;
  new testmods dir + ExpectedTestFails hygiene.
- Unit-testable pieces (mat-thickness allometry and its inverse, moss fuel-moisture
  function) get FATES functional/unit tests where the harness allows.

## 11. Later extensions (explicitly out of scope now)

- fwet proxy upgrades: standing water, water-table depth (new `bc_in` fields via the
  standard 4-touch recipe).
- Moss temperature proxy (`t_grnd`/top-soil temperature) for gas parameters, consuming
  the per-cohort gas-parameter separation pattern.
- Full competition: revisit `nclmax`, strict-PPA demotion, `comp_excln` weighting,
  termination-floor headroom; watch `FATES_MORTALITY_CANLEVEL_*`.
- Moss effects on ground evaporation (e.g., exporting a per-patch surface resistance),
  soil insulation, albedo — the NVP-layer branch's territory.
- A height/leaf-biomass ceiling for moss that does not collide with the TRS tree test.
  Today `fates_allom_dbh_maxheight` is both the saturation diameter and the TRS
  tree/non-tree discriminator, so moss cannot be given a mat-scale ceiling without also
  being classified a non-tree, or inherit grass's classification without also inheriting
  grass's 1.2 m ceiling (§12). Upstream, splitting the tree test onto `woody` or its own
  parameter would decouple these; see the upstream-observations note in the plan.

## 12. Accepted fictions and limitations

- Moss "roots" in soil layer 1 and a carbon pool labeled sapwood: conserving carbon/water
  plumbing, not mechanism claims.
- One patch-level leaf boundary layer for all cohorts (moss exchange overestimated).
- Moss lumped with grass in fire wind-attenuation and tree/grass area accounting.
- Snow > moss height fully occludes photosynthesis (real bryophytes photosynthesize under
  thin snow).
- Interception capacity uses the standard LAI-scaled formulation, which understates
  moss's real water-holding capacity.
- Dead moss decomposes at standard leaf-fines rates (its fuel identity is separate via
  `moss_fines`, but its decomposition is not moss-specific).
- In nocomp, moss cover is prescribed, not emergent.
- **The moss parameter file cannot be run with `use_fates_moss = .false.`, nor the default
  file with it on.** Both abort at initialization, deliberately (§8). Neither weakens the
  bit-for-bit constraint, which is scoped to a standard 6-litterclass file.

  Two independent mechanisms produce that abort, and it is worth knowing which does the work:
  - **The litterclass agreement check** (§6, the runtime fuel-class count) is what actually
    stops the real files. The count is read from the size of the file's own `fates_litterclass`
    dimension, then required to be 8 when `use_fates_moss` is on and 6 when it is off — so the
    8-class moss file with moss off fails 8 ≠ 6, and the 6-class default file with moss on
    fails 6 ≠ 8. The error names the dimension and the mode it expected.
  - **The `fates_vascular` biconditional** (§3) covers the case the count cannot see: a
    file whose litterclass count agrees but whose PFT content does not — e.g. a hand-built
    8-class file with `use_fates_moss = .true.` that omits the moss column. Without it, FATES
    would run "with moss" while no moss PFT exists.

  So the biconditional does **not**, on its own, foreclose isolating a dimension change from a
  physics change: the agreement check forecloses that for any real moss parameter file
  regardless. The only file the biconditional uniquely rejects is a 15-PFT-but-6-litterclass
  one, which this project does not produce.

  Two implementation notes, both non-obvious:
  - **The agreement check cannot live in the parameter read**, where the count is established.
    CTSM reads the FATES parameter file in `CLMFatesGlobals1` but does not pass the namelist
    switches until `CLMFatesGlobals2`, so at read time `hlm_use_moss` is still the unset
    sentinel. The check therefore sits in `SpitFireCheckParams`, reached after the switches
    arrive — the same placement, for the same reason, as the §3 biconditional.
  - **No per-array size check is needed.** The parameter reader already aborts if any 1-D
    parameter's data length disagrees with its declared dimension, so reading the count *from*
    that dimension makes every `SF_val_*` allocation and whole-array fill conforming by
    construction. The mode-agreement check above is the only one this project adds.

  Historical note: before the fuel-class count became a runtime value, an 8-class file was not
  safely fatal at all. The `SF_val_*` arrays were fixed length-6 and filled by whole-array
  assignment, so an 8-entry array was a non-conforming assignment — trapping in a
  bounds-checked build and silently wrong otherwise. Making the count runtime is what converted
  that into a clean, explained error.
- **Moss height is effectively unbounded under the `grass_powerlaw` height allometry.**
  Moss inherits grass's `fates_allom_dbh_maxheight` of 20 cm, and that parameter is the
  only ceiling in that mode: `d2h_2pwr` computes `h = p1*min(d,dbh_maxh)**p2`, so moss
  saturates only at ~1.23 m, versus ~4.2 cm had a moss-specific 0.1 cm been kept. Moss
  recruits at 2 cm height (dbh ~0.032 cm), so nothing stops it growing well past mat-like
  dimensions if it accumulates leaf carbon; `dh2blmax_3pwr_grass` caps target leaf biomass
  at the same diameter, so that is unbounded in practice too. The `mat_thickness` mode (§4)
  is the principled fix, and the `grass_powerlaw` mode should be read as a
  conservation-correct but dimensionally unconstrained baseline. Watch diagnosed moss
  height in any `grass_powerlaw` run. A second consequence: with 20 cm, moss sits above
  `min_max_dbh_for_trees` (15 cm), so if TRS is ever enabled moss would be classified a
  tree and routed through the tree-recruitment path.
- **Moss displaces an existing HLM PFT rather than adding one.** The host's `natpft`
  dimension is bare ground plus 14 natural PFTs, and `fates_hlm_pftno` stays 14, so there
  is no free HLM index to give moss. `fates_params_moss.json` therefore hands HLM PFT 4
  (broadleaf evergreen tropical tree) to moss, leaving that FATES column orphaned. The
  file is only sensible where HLM 4 carries no real area — true at the arctic ALP2 site,
  but at a tropical site it would silently convert broadleaf evergreen tropical tree into
  moss. HLM 4 is chosen over the NVP branch's HLM 12 so that `arctic_c3_grass` keeps its
  mapping and a grass-only surface dataset stays a grass run under either parameter file.

## 13. Harvest list from `ctsm5.4.028_nvp`

| Piece | Location (NVP branch) | Use |
|---|---|---|
| Moss PFT parameter column | `fates_params_default_moss.json` | §3, adapted (roots, repro) |
| `fates_vascular` per-PFT flag | parameter files (unread there) | §3, wired up as moss identifier |
| `NVP_allom` leaf-C ↔ LAI/thickness | `FatesAllometryMod` | §4 mode 2 |
| `vcmax × min(1, fwet/0.6)` | `FatesPlantRespPhotosynthMod` | §5 |
| Boundary-layer-only Ci, `(1−fwet)^12` | `LeafBiophysicsMod` (`nvp_model=3`) | §5, behind per-PFT dispatch |
| Per-cohort gas-params separation | FATES `33640d372` | §11 (temperature proxy, later) |
| Wet/dry albedo interpolation | `FatesRadiationDriveMod` | later, if moss albedo wanted |

Not harvested: everything keyed to the vertical moss layer (`jbot_sno`, layer-0 energy/
hydrology, snow reindexing, SNICAR coupling) — ~3300 of the branch's ~4100 CTSM lines.
