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

Initial target configuration: **nocomp fixed-biogeography** at boreal sites, SPITFIRE on,
no plant hydraulics, no satellite phenology. Full competition mode is a later phase, but
parameter and code choices must not foreclose it (see §11).

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
- **Reproduction fixed:** grass defaults give `seed_alloc = 0` below a 3 cm dbh
  reproduction threshold that moss (dbh ~0.03 cm) never crosses — moss would go extinct.
  Set `fates_recruit_seed_alloc > 0` and drop the dbh threshold to ~0. ("Seed" is a mass
  pool with first-order germination; representationally fine for spores/fragments.)
- `fates_allom_dbh_maxheight < 15 cm` so germination takes the simple non-tree path,
  skipping the tree-recruitment-scheme machinery.
- Recruit height (`hgt_min`) toward the tall end of moss reality (~5–10 cm equivalent)
  for numerical headroom above termination floors.
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
- **fwet proxy:** effective saturation of the top soil layer, computed from moisture
  fields already present in `bc_in` (used by btran) — no new CTSM→FATES coupler fields.
- **Gas parameters use `t_veg`** (patch vegetation temperature) for moss initially. The
  NVP branch's per-cohort gas-parameter separation (FATES `33640d372`) is the drop-in
  pattern if a ground-temperature proxy is added later (§11).
- **btran** comes through the standard shallow-root pathway (§3); no override needed.
- Plant hydraulics is unsupported for moss (pre-existing FATES divide-by-zero for PFTs
  under ~10 cm); `use_moss` + `use_fates_planthydro` is a fatal namelist error.

Conservation: moss C/N flows through standard PARTEH pools and litter fluxes; moss water
through the standard root-uptake/transpiration pathway. fwet only scales vcmax, the CO₂
water-film term, and fuel moisture — it stores no water. Existing CTSM/FATES balance
checks remain fatal.

## 6. Fire

All in FATES `fire/` plus the biomass routing points; design to be coordinated with
Adrianna Foster:

- **New seventh fuel class, "live moss,"** with its own SAV and bulk density (new entries
  on the `fates_litterclass` dimension). Requires touching `FatesFuelClassesMod`
  (`num_fuel_classes`), the length-6 parameter arrays, and the fragile CWD-index aliasing
  in `EDPatchDynamicsMod` (burnt-litter loop assumes fuel classes 1–4 are CWD 1–4).
- **Routing:** live biomass of moss PFTs (`vascular==0`) goes to the live-moss class
  instead of live grass (`UpdateLiveGrass` in `FatesPatchMod`). Dead moss leaf litter
  continues into the shared dead-leaves class (a distinct moss-duff class is a later
  extension, §11).
- **Moss fuel moisture is diagnostic from the fwet proxy** (top-layer soil saturation),
  not the Nesterov index, via a moss branch in `UpdateFuelMoisture`. Initial functional
  form: a simple monotonic mapping `moisture = a + b·fwet` (coefficients on the CTSM
  namelist, §8), to be refined with Adrianna if a better-supported form exists.
- **Burn response mirrors grass:** the live-moss class burns per its own effective
  moisture; moss cohorts take `leaf_burn_frac` from the live-moss class's `frac_burnt`
  (analogous to the existing live-grass keying in `EDPatchDynamicsMod`), combusting
  leaf + sapwood + structure with the same 0.8 cap, defoliating without individual
  mortality. Regrowth from storage stands in for regrowth from surviving fragments.

## 7. CTSM–FATES interface

No new coupler fields are required for the initial implementation (fwet proxy inputs
already cross in `bc_in`). New scalar controls cross via the existing
`set_fates_ctrlparms` mechanism.

## 8. CTSM namelist

Per project convention, **all new scalar settings — switches and science constants — go
on the CTSM namelist**, not the FATES parameter file. (Reconsider individual constants
only at upstream-FATES merge time.) Standard seven-step plumbing (XML definition,
defaults, `CLMBuildNamelist.pm` logic, `clm_varctl`, `controlMod` read/broadcast,
`clmfates_interfaceMod` `set_fates_ctrlparms`, FATES-side `case` + is-set check):

- `use_moss` (logical, default `.false.`) → `hlm_use_moss`. Gates the moss fuel class,
  moss physiology dispatch, and moss allometry mode. Fatal errors: `use_moss` true with
  no `vascular==0` PFT on the parameter file (and vice versa); `use_moss` with
  `use_fates_planthydro`.
- `moss_height_allom` (string: `'grass_powerlaw'` | `'mat_thickness'`) → selects the
  height-allometry mode applied to moss PFTs (§4).
- Moss science scalars: at minimum, moss bulk density (mat-thickness allometry) and the
  moss fuel-moisture coefficients `a`, `b` (§6). Any further scalars discovered during
  implementation follow the same convention. (Live-moss SAV and bulk density are *array*
  entries on the existing `fates_litterclass` parameter-file dimension, which must grow
  to 7 regardless — they stay on the parameter file like other array parameters.)

## 9. Diagnostics and validation

- `FATES_NOCOMP_PATCHAREA_PF`: true per-PFT fractional cover in nocomp (prescribed;
  validates bookkeeping). `FATES_CROWNAREA_PF` etc. come free (requires
  `fates_history_dimlevel(2) >= 2`) and become the emergent-cover variables under full
  competition later.
- New history: moss fuel load, moss fuel moisture, fwet proxy, plus standard per-PFT
  biomass/GPP variables which are automatic.
- Validation target: observed fractional cover of two moss species at boreal sites; plus
  qualitative fuel-load and fuel-moisture behavior.

## 10. Testing

- Existing balance checks (C/N/water/energy) remain fatal and must pass with `use_moss`
  on and off.
- `use_moss = .false.` must be bit-for-bit with baseline (all changes gated).
- `use_moss = .true.` with a parameter file lacking a moss PFT must abort cleanly.
- Site-level smoke/exact-restart tests in nocomp-fixedbiogeo with a moss parameter file;
  new testmods dir + ExpectedTestFails hygiene.
- Unit-testable pieces (mat-thickness allometry and its inverse, moss fuel-moisture
  function) get FATES functional/unit tests where the harness allows.

## 11. Later extensions (explicitly out of scope now)

- fwet proxy upgrades: standing water, water-table depth (new `bc_in` fields via the
  standard 4-touch recipe).
- Moss temperature proxy (`t_grnd`/top-soil temperature) for gas parameters, consuming
  the per-cohort gas-parameter separation pattern.
- A distinct dead-moss/duff fuel class.
- Full competition: revisit `nclmax`, strict-PPA demotion, `comp_excln` weighting,
  termination-floor headroom; watch `FATES_MORTALITY_CANLEVEL_*`.
- Moss effects on ground evaporation (e.g., exporting a per-patch surface resistance),
  soil insulation, albedo — the NVP-layer branch's territory.

## 12. Accepted fictions and limitations

- Moss "roots" in soil layer 1 and a carbon pool labeled sapwood: conserving carbon/water
  plumbing, not mechanism claims.
- One patch-level leaf boundary layer for all cohorts (moss exchange overestimated).
- Moss lumped with grass in fire wind-attenuation and tree/grass area accounting.
- Snow > moss height fully occludes photosynthesis (real bryophytes photosynthesize under
  thin snow).
- Moss dead material shares the dead-leaves fuel class and standard litter decomposition.
- In nocomp, moss cover is prescribed, not emergent.

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
