# Standalone tests for the moss wetness proxy: design

**Date:** 2026-09-04
**Author:** Sam Rabin, with Claude
**Parent spec:** `docs/superpowers/specs/2026-08-19-moss-grass-pft-design.md`
**Parent plan:** `docs/superpowers/plans/2026-08-19-moss-grass-pft.md`, Task 8

## 1. Why

Task 8 built the moss wetness proxy `fwet_moss` — the wetter of the top soil layer's
saturation and the patch canopy wetted fraction — and its two history ingredients. Its
Step 4 verification was skipped on 2026-09-01 because no machine was available. That step
expected, in a CTSM history file:

> `FATES_MOSS_FWET` tracks rain events (canopy ingredient spikes with precipitation and
> decays; soil ingredient varies smoothly; the max is always ≥ both).

This design covers standalone FATES tests that can be built and run without CTSM, and
says precisely which part of that expectation they discharge and which part they do not.

## 2. What a standalone test can and cannot verify

`fates_patch_type::UpdateMossFwet` (`biogeochem/FatesPatchMod.F90`) holds no state and
does no hydrology. It clamps `h2o_vol_top/watsat_top` into [0,1] behind a
`watsat_top > nearzero` guard, takes `max()` against the canopy wetted fraction it is
handed, and refreshes the derived wetness scaler.

So of the Step 4 expectation:

- **"the max is always ≥ both"** is FATES behaviour, and is assertable.
- **"spikes with precipitation and decays" / "varies smoothly"** are properties of the
  *inputs*, manufactured upstream in CTSM's canopy hydrology and soil water solver and
  delivered as arguments. No standalone FATES driver can verify them. It can only
  synthesize an input series and show what the proxy does with it.

That asymmetry sets the whole design: **assertions go in a pFUnit unit test; the picture
goes in a functional test; neither one closes Task 8 Step 4.**

## 3. Scope

Three quantities are pure functions of `fwet_moss` and are covered here alongside it:

| Consumer | Routine | Today's test coverage |
|---|---|---|
| Photosynthetic capacity & leaf respiration scaler | `fates_patch_type::UpdateMossWetnessScaler` | none |
| Moss CO₂ water-film factor | `LeafBiophysicsMod::MossCO2FilmFactor` | none (and the routine is `private`) |
| Live/dead moss fuel moisture | `FatesFuelMod::UpdateFuelMoisture` | `tests/unit/fire_fuel_test`, at three fixed proxy values |

This is spec §9's "one proxy, three consumers" made visible on one axis. The fuel-moisture
map already has unit coverage, so the new unit test covers the first two; the functional
test plots all three.

Out of scope: anything requiring CTSM to run — the `bc_in` plumbing, the daily-vs-subdaily
meaning of `h2o_liqvol_sl`, restart behaviour, and the area-weighted history fill.

One pre-existing defect in the shared fire-test netCDF writer is fixed first, because this
work reads from the same helper: `WriteFireData` writes the `litter_class` coordinate as a
literal `1..6` list, though the dimension it writes into is sized from the runtime
`num_fuel_classes`, which is 8 under the moss parameter file. Unverified as of writing;
confirming it is the first step of the plan's Task 0.

## 4. The unit test

A new `tests/unit/moss_fwet_test/` asserting, at minimum: soil ingredient wins, canopy
ingredient wins, the upper clamp at saturation, the lower clamp, the `watsat` guard
against the `-999` sentinel `wrap_btran` writes, the scaler below/at/above its threshold,
and `MossCO2FilmFactor`'s documented clamp behaviour.

Because the implementation already exists, every assertion must be shown to fail under a
deliberate mutation before it is believed. A test that passes on first run has proved
nothing about the code.

`MossCO2FilmFactor` is `private` in `LeafBiophysicsMod` and must be made public, following
the precedent already set in this branch by `FatesFuelMod::MoistureOfExtinction` and
`max_grass_frac` — both made public with a comment saying that a test needs them and that
restating the value in the test would let the two drift.

## 5. The functional test

A new functional-test group `tests/functional/moss/fwet/`, chosen over the existing `fire/`
group because the proxy feeds photosynthesis as well as fire. It produces two figures:

1. **A designed scenario ladder.** A short table of `(fwet_veg, h2o_vol, watsat)` triples
   chosen to separate the branches of `UpdateMossFwet` — soil-wins, canopy-wins,
   saturation, over-saturation, the `watsat` sentinel — with the proxy, both ingredients,
   and the scaler plotted per scenario. This is the same ground the unit test asserts on,
   shown rather than asserted.

2. **A year-long trajectory.** The existing `BONA_datm.nc` daily precipitation and
   temperature record drives a **surrogate** canopy store and top-soil bucket, and the
   proxy, its ingredients, the scaler, the CO₂ film factor and the two moss fuel moistures
   are plotted against precipitation. This is the figure Task 8 Step 4 describes.

**The surrogate is not CTSM's hydrology and must never be presented as it.** It is a
linear-reservoir canopy store and a leaky bucket with a freeze switch, whose only job is
to deliver inputs with the right qualitative shape: spiky canopy wetting capped at CTSM's
`maximum_leaf_wetted_fraction`, smooth soil moisture, a frozen winter in which the soil
ingredient stays high because the proxy consumes *total* (liquid + ice) water. It is
labelled as a surrogate in the driver, in the netCDF metadata, and on the figure. Nothing
is asserted about it.

## 6. Parameter-file policy

`run_functional_tests.py` passes one `--parameter-file` to every test in an invocation, so
requiring the 8-litterclass moss file would change what the other four functional tests
run under. The moss `fwet` test therefore works under the default file: the proxy, the
scaler and the CO₂ film factor need no moss parameters at all, and the host scalars that
would otherwise arrive from the CTSM namelist (`hlm_moss_vcmax_fwet_thresh`,
`lb_params%moss_co2_film_min`, the fuel-moisture coefficients) are set by hand in the
driver, as `FatesTestFuel` already does for the fuel-moisture coefficients.

The moss fuel-moisture panel needs the two moss fuel classes, so it appears only when the
run is given an 8-litterclass file. The driver branches on
`fuel_classes%moss_classes_present()` and records `num_fuel_classes` in the output so the
plotter can say why a panel is absent rather than silently omitting it.

## 7. What this does not do

Task 8 Step 4 stays open. Confirming that `bc_in%fwet_veg_pa` really carries CTSM's
`fwet_patch`, that `h2o_liqvol_sl(1)` really carries total water at the daily call, that
the three patch members survive restart, and that the history variables are correctly
area-weighted over bareground all require an ALP2 run. These tests narrow what that run
has to establish; they do not replace it.
