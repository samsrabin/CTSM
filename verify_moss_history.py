#!/usr/bin/env python
"""Verify the moss diagnostics on the history output of a finished CTSM-FATES moss run.

What this is
------------
The moss work on this branch adds a wetness proxy, two moss fuel classes, a moss fuel
moisture map, a moss wetness scaler on photosynthetic capacity, and a set of history
variables that expose all of it. Those additions are covered by unit tests at the routine
level and by system tests at the "does it run" level. Neither says whether the assembled
model produces the quantities the design asked for, in the units and with the relationships
it asked for, over a multi-year run. That is what this script reads out of a completed
run's daily history files.

It is analysis only. It launches nothing, and the only things it writes are the PNGs in
--out-dir and, when --cache-dir is given, the history cache in that directory.

Each check prints one of:

  PASS / FAIL   an identity or a threshold that the run either meets or does not
  INFO          a number reported for a human to judge; several steps of the plan ask
                for a value to look at rather than a criterion to meet
  SKIP          the check could not be made. Either the tape lacks a variable it needs
                (chiefly in FATES-SP runs), or the variables are there and hold nothing to
                test -- SPITFIRE never ran, or a litter pool is carrying the FATES-SP
                unset-litter sentinel rather than a number.
  WARN          something about THIS run that must not be scrolled past, and that no
                PASS/FAIL can carry: a path the run never exercised, or a configuration
                degeneracy that leaves a check establishing less than its label claims.
                A WARN is not a failed identity. It does not enter the PASS/FAIL/SKIP/INFO
                tallies and it does not move the exit code; every warning raised is
                reprinted in the closing verdict block, where it cannot be missed.

One check here can FAIL for a reason that is not about the diagnostics. The moss-survival
check in section 5 fails when moss never carries any biomass at all, and when it carries
some, reaches zero and is never recruited back. Both are science findings about the model
configuration, not broken identities, and both still drive exit code 1 -- which a caller will
read as "the diagnostics are broken". It is deliberately left that way, because it is the one
result here that must not be scrolled past. On a run in which moss persists that check is an
INFO and does not move the exit code at all. A caller that wants only the identity checks has
to read the labels rather than the exit code. The rest of the scheme is under "Exit codes",
at the end of this docstring.

Two conventions the output follows throughout, both of which change how a number reads:

  * NUMBERS ARE MOSS-NATIVE. Almost every moss diagnostic reaches the history tape as a
    patch-area weighted site mean, so the tape's number is diluted by area fractions that
    have nothing to do with moss. What is printed as the headline number is the site value
    divided back out by whichever fraction dilutes it, which is what moss itself carries;
    where the tape's own value is still worth seeing it follows in brackets, marked "on the
    tape". Only the DISPLAY is converted -- every identity was checked against the
    site-level values, since that is what the tape holds and converting first would add a
    division that buys nothing and perturbs the deviations. Which divisor belongs to which
    quantity is under "Three families of moss diagnostic" below.

  * A PARAMETER IS NEVER A BARE NUMBER. Any figure that came off a parameter file or a
    namelist is written as `name = value (where it came from)`. A bare decimal in this
    output is therefore, by construction, something the run produced.

Usage
-----
Run in the ctsm_pylib conda env; uses netCDF4, numpy and, unless --no-plots is given,
matplotlib:

  /glade/work/samrabin/conda-envs/ctsm_pylib/bin/python3 verify_moss_history.py \\
      /glade/derecho/scratch/$USER/<testname>/run

The argument is the CIME case's `run/` directory. Everything below counts in days and
compares a day against its neighbour, so the tape has to be one daily-mean sample per file
and one file per day -- what `hist_nhtfrq = -24` with `hist_mfilt = 1` writes. That is a
property of the case, not of the model, so it is read off the tape rather than assumed: a
tape written at any other cadence is refused with the cadence it actually has, instead of
being reported over with every "days" count wrong. PNGs go to --out-dir, which defaults to
the directory you invoked the script from.

What each check establishes
---------------------------
The output is grouped into five sections, each opening with a plain-language note on what
the quantity is and why it matters for moss. The plan coordinates the checks were written
against survive only as trailing parentheticals, for a reader who has the plan.

  1. THE WETNESS PROXY -- WHAT MOSS FEELS.
     Each of the two proxies, FATES_MOSS_FWET_LIQ (liquid soil water) and
     FATES_MOSS_FWET_TOT (liquid plus ice), is exactly the wetter of its two ingredients,
     and never below either. Also reports how often the canopy ingredient actually sets the
     liquid proxy, and states once the branch-uniformity precondition that this section's
     and section 2's identities all rest on.

  2. MOSS PHOTOSYNTHETIC RESPONSE TO WETNESS.
     FATES_MOSS_WETNESS_SCALER is the configured wetness map applied to the liquid proxy, in
     the two halves the map's kink splits it into: below the threshold the scaler is exactly
     proxy/threshold, which is what pins the threshold; above it the scaler sits at exactly
     1 in moss-native units, which on the tape is the non-bareground area fraction and is
     where the naive site-level min(1, fwet/threshold) goes wrong. Then how much of the run
     sits on each side, what moss produced there, and whether the productive window is
     visited at all.

  3. MOSS FUEL LOADING.
     The live-moss fuel class carries the live-moss biomass FATES_LIVEMOSS_FUEL reports,
     and the dead-moss class carries the dead-moss litter FATES_MOSS_FINES reports, one day
     stale. That litter pool is nonzero and accumulates.

  4. MOSS FUEL MOISTURE AND FLAMMABILITY.
     Both moss fuel classes' moisture is an exact linear function of the moss wetness proxy
     it reads (the total-water one) and of nothing else, with the fitted
     slope pinned against the configured map and against a moisture of extinction that does
     not come out of the fit, and the crossing point pinned against the configured intercept
     -- which at the configured intercept of zero says only that there is no offset; the
     non-moss classes still track the Nesterov index.
     Then how often moss sits at or above its moisture of extinction, whether any fire
     occurred, and how much moss fuel burned.

  5. MOSS SIZE, STRUCTURE AND SURVIVAL.
     Moss leaf and stem area per unit crown area and per unit moss patch, moss height, moss
     crown area against the prescribed nocomp patch area where the tape carries one,
     prescribed cover, mortality, and -- the part worth the most attention -- what the moss
     population actually did over the run.

What this script CANNOT establish
---------------------------------
Two of the things the verification plan asks for are not answerable from one run's h0a tape
by any script, and this script says so rather than substituting a proxy. Neither is a
property of the run in front of it, so neither can be redeemed by a better run:

  * Anything that is a comparison between two runs. Two of the plan's questions are of
    that kind, and no single tape answers either.

    The first is whether moss biomass was RELOCATED into the live-moss fuel class or
    DUPLICATED into it. Before this branch, UpdateLiveNonwoody summed every non-woody
    cohort's aboveground biomass into one accumulator, `livegrass`, which feeds the
    live-grass fuel class; moss, had it existed, would have been counted there. The branch
    splits that loop on `vascular` (biogeochem/FatesPatchMod.F90:855-875) so non-vascular
    cohorts go to a new `livemoss` accumulator instead. If the split works, the same carbon
    that used to land in live grass now lands in live moss; if it is wrong, moss is counted
    in both and the site's total fuel is overstated. Deciding which needs the live-grass
    loading from a run built before the split, on the same forcing, to difference against
    (Task 6). One tape holds one side of that subtraction.

    The second is that perturbing the moss fuel-moisture coefficients changes fire
    behaviour, which likewise compares this run against one with different coefficients
    (Task 12 Step 3).

  * An error in FATES's own moisture-of-extinction formula. The moss fuel-moisture slope
    has to be checked against an MEF that does not come out of the fit, and the only one
    available is the one this script computes by reproducing MoistureOfExtinction
    (fire/FatesFuelMod.F90:367-374). That is what the duplication costs: a checker that
    reproduces a formula cannot catch a mistake in that formula. Were FATES's MEF wrong,
    this script would be wrong the same way and the slope would still PASS. What the check
    does catch is the moss map being applied with the wrong coefficients, or to the wrong
    quantity, which is what it exists for.

Everything else that limits what a given run can show -- fire that never burned, moss fuel
classes whose parameters are indistinguishable from another class's, a canopy ingredient
that never wins -- is a property of THAT run, is detected at runtime, and is reported as a
WARN rather than written down here as though it were permanent.

Which runs this fits
--------------------
The area-weighted identities need the non-bareground area fraction, and where that comes
from depends on the run's configuration, which is read from its lnd_in rather than guessed
off the tape.

FATES creates a bareground patch only under nocomp AND fixed biogeography
(main/EDInitMod.F90:841 guards it with hlm_use_nocomp .and. hlm_use_fixed_biogeog).
Under full competition there is no such patch, the patch areas sum to AREA, and the fraction
is 1.0 exactly -- so a full-competition tape loses nothing at all, and every check runs in
full. FATES_NOCOMP_PATCHAREA_PF, which is where the fraction is read from when the run does
have a bareground patch, is registered under hlm_use_nocomp alone
(main/FatesHistoryInterfaceMod.F90:7688), so on a nocomp-without-fixed-biogeog run it is
present and sums to 1.0 anyway. The two facts agree.

What actually degrades the script is not full competition but a nocomp+fixed-biogeog run
whose FATES_NOCOMP_PATCHAREA_PF was left out of hist_fincl1, or a run with no readable
lnd_in to say which configuration it is. Then the fraction is genuinely unknown: the script
does not abort, but runs every check that does not need it, SKIPs the ones that do, and
WARNs saying which and why. What is lost is the above-threshold half of the section 2
scaler identity, the crossing-point half of each section 4 moisture check where the configured
intercept is nonzero (at the configured intercept of zero that half constrains nothing extra
whatever the area fraction is, and the check says so at runtime), the patch-level readings
of moss extinction and of the canopy ceiling, and the prescribed-cover report. What survives
is every identity whose area weighting cancels -- all of section 1 and section 3, the
below-threshold half of section 2, the moisture slope, and section 5. A tape without the
patch area also loses the moss-native DISPLAY of everything it dilutes: those numbers fall
back to site units, each with a one-line note saying so, rather than being dropped.

Three families of moss diagnostic
---------------------------------
Which divisor turns a site-level number moss-native depends on which patches the quantity
lives on, and there is no single factor. Each is verified against the FATES source rather
than assumed, and each is printed in the preamble with where it came from.

  A. PATCH PROPERTIES, diluted only by bareground. Divisor: the non-bareground area
     fraction. FATES_MOSS_FWET_LIQ, FATES_MOSS_FWET_TOT, FATES_MOSS_FWET_SOIL_LIQ,
     FATES_MOSS_FWET_SOIL_TOT, FATES_MOSS_FWET_CANOPY, FATES_MOSS_WETNESS_SCALER, and
     FATES_FUEL_MOISTURE_FC at the two moss classes. UpdateMossFwetLiq and
     UpdateMossFwetTot run on every patch whose label is not nocomp_bareground
     (main/EDMainMod.F90:232-237), so the proxies and everything derived from them per patch
     carry the same value on a grass patch as on a moss patch, and only bareground
     contributes zero to the site mean.

  B. MOSS-ONLY QUANTITIES. Divisor: the moss patch area fraction, NOT the non-bareground
     one. FATES_LIVEMOSS_FUEL, FATES_MOSS_FINES, and FATES_FUEL_AMOUNT_FC at the moss
     classes. cpatch%livemoss sums only the non-vascular cohorts of that patch
     (biogeochem/FatesPatchMod.F90:855-875) and moss_fines_in is fed only by non-vascular
     cohorts (biogeochem/EDPhysiologyMod.F90:367, :2965, :3065), so both are zero on a
     grass patch and the site value is the moss-patch value times the moss patch area.
     FATES_FUEL_AMOUNT_FC follows them: frac_loading for a class with no loading in the
     patch is zero, so those columns get nothing from a grass patch either.

  C. PER-PFT QUANTITIES AT THE MOSS INDEX. FATES_GPP_PF, FATES_LEAFC_PF,
     FATES_CROWNAREA_PF, FATES_LAI_PF, FATES_SAI_PF and the per-PFT mortality rates are all
     "per m2 land area" and have two defensible native denominators. Anything physiological
     or allometric is headlined per m2 of moss CROWN area, which is what a moss measurement
     would be compared against and which for LAI is already FATES's own treelai, with the
     per-moss-patch value beside it for the "did moss fill the patch it was given" reading.
     Crown area is itself reported per moss patch, since dividing it by itself says nothing.
     Moss crown area is exactly zero on every day moss is absent, so every crown-native
     number is guarded and reported as undefined on those days rather than as inf or nan.

FATES_MOSS_HEIGHT belongs to none of the three. It is accumulated as a crown-area weighted
sum and then divided by the MOSS CROWN AREA rather than by land area
(main/FatesHistoryInterfaceMod.F90:3070-3074, :3122-3123), so it is already a height and
must not be converted again.

FATES_FUEL_BURNT_BURNFRAC_FC is a fourth case and not a class-B one, despite sitting on the
same fuel axis as FATES_FUEL_AMOUNT_FC. frac_burnt is a function of a class's moisture and
not of its loading (fire/FatesFuelMod.F90:471-497), so a patch with no moss fuel at all
still contributes a moss column; and the value is a product with the patch's burnt
fraction. Dividing by the site's burnt area turns it back into a fraction, and it is
undefined -- said so in words -- on a run in which nothing burned.

Its own long name says to divide by FATES_BURNFRAC and stop there, and that instruction is
dimensionally wrong: FATES_BURNFRAC carries a /sec_per_day and units='s-1'
(main/FatesHistoryInterfaceMod.F90:2769, :6839) that FATES_FUEL_BURNT_BURNFRAC_FC, at
units='1' (:4302-4303, :7885), does not, so the bare quotient is in seconds and reads
86400x too large. What is divided by here is sec_per_day*FATES_BURNFRAC, which is the plain
burnt-area fraction, and the reason is restated at the conversion because a reader checking
it against the long name will find that the two disagree.

Two things the identities encode
-------------------------------
Both are commented again at the check that uses them, because both will read as arbitrary
to anyone who has not been told why they are there.

  1. Neither max() nor min() commutes with an area-weighted sum in general, and both
     proxies and the wetness scaler are built out of one. Pushing the area weight through one
     of them is therefore a PRECONDITION of those identities, not an observation about any
     run: they hold only while the same branch is taken on every vegetated patch -- the same
     ingredient wins on all of them, or all of them sit on the same side of the threshold. A
     site-level tape cannot test that, since it has already summed the patches away. What it
     can do is watch the one quantity that decides it. Each proxy's two ingredients are
     asymmetric: the soil one is a column-level saturation and is therefore the same number
     on every patch of the site, while the canopy one is CTSM's per-patch fwet_veg,
     hard-capped at maximum_leaf_wetted_fraction
     (src/fates/biogeochem/FatesPatchMod.F90:919-926). So while the soil ingredients stay
     clear of that cap, each proxy is identical on every vegetated patch, both branches are
     uniform by construction, and the identities are safe. The margin is reported once at
     the head of section 1, and WARNed about when it narrows to where per-patch divergence
     becomes possible.

     A FAIL on one of those identities is much more likely to be branches that diverged
     across patches than a model defect, and each of them says so in its own FAIL text.

  2. FATES_FUEL_AMOUNT_FC and the moss pools it is checked against report fuel loading
     under two different conventions: with mineral content removed, and with it included.
     SFMainMod.F90's CalculateSurfaceRateOfSpread scales the patch's stored
     `fuel%non_trunk_loading` by (1 - SF_val_miner_total) after `frac_loading` was
     normalized against the undamped total, and FATES_FUEL_AMOUNT_FC is reconstructed
     downstream as `frac_loading(i) * non_trunk_loading`. The two normalizations compose
     to exactly (1 - fates_fire_miner_total) * loading(i) -- a self-consistent mineral-free
     loading for every class that carries loading at all, and for FATES_FUEL_AMOUNT itself.
     Trunks are the exception, and their column is empty rather than mineral-free:
     `frac_loading` is forced to zero for trunks (fire/FatesFuelMod.F90:212), so
     FATES_FUEL_AMOUNT_FC[trunks] is identically zero by construction and no convention
     applies to it. FATES_LIVEMOSS_FUEL and FATES_MOSS_FINES carry mineral content still in
     them, so the checks against them encode the factor 1 - fates_fire_miner_total, read
     from the run's own parameter file and printed by the check. See the live-moss loading
     check in section 3 for the file:line.

     Two things about that relationship are worth stating here. First, no long name says
     which convention its variable uses: FATES_FUEL_AMOUNT_FC is "spitfire fuel-class level
     fuel amount in kg carbon per m2 land area", with no mention that mineral content has
     been removed. That documentation gap is why this script has to encode the relationship
     rather than infer it. Second -- and this is not something a long name could carry --
     the scaling is applied by mutating the persistent patch fuel object in place, so what
     `non_trunk_loading` holds depends on where in the daily sequence it is read, which is
     the fact to reason from when reading these identities.

Exit codes
----------
No WARN moves any of these. A warning says a check established less than its label suggests
or that a path went unexercised, which is a thing to read, not a thing to fail on; the
warnings are reprinted in the verdict block for that reason.

  0  Nothing FAILed and the moss PFT index was confirmed. INFO and SKIP do not bear on
     this: several checks report a number for a human to judge rather than testing one,
     and a SKIP means a check could not be made, not that it failed. A 0 can still be a
     degraded result -- a PASS from a check that could not pin all of its constraints is
     counted separately in the verdict line, and the checks say which constraint was
     missing.

  1  At least one check FAILed. Read the paragraph on FAIL above before reading this as
     "the diagnostics are broken": a moss-population FAIL, if the output carries one, is a
     finding about the model configuration and not about the diagnostics.

  2  No trustworthy verdict. Either the script was pointed at the wrong thing or told the
     wrong thing about it -- no history files, a variable it cannot run without, an
     out-of-range --pft-moss, a patch-area variable that is present but not a fraction, or
     a tape shaped in a way that would make every number below mean something other than it
     says: more than one gridcell, more than one sample per file, a cadence other than
     daily, files whose field lists disagree, or dates that repeat or go backwards -- or it
     ran to the end but could not confirm which PFT is moss, in which case every moss-keyed
     number in the output may be about some other PFT. This outranks 1: numbers about an
     unverified PFT are not results, so an unconfirmed index exits 2 even when nothing
     FAILed. A full-competition tape is NOT one of these, and neither is a tape without the
     patch-area variable: both are handled, as described under "Which runs this fits".

  3  An unexpected error inside the script: a tape shaped in some way it does not detect
     and cannot handle -- a fuel axis shorter than the eight classes indexed here, say --
     or a missing matplotlib. A traceback is printed. This is a defect in the script or in
     its environment and says nothing whatever about the run, which is why it does not
     share a code with either of the two above. The tape shapes listed under 2 are the ones
     it does detect, and those are refused with a sentence rather than a traceback.
"""

import argparse
import glob
import hashlib
import json
import os
import re
import sys
import textwrap
import traceback

import netCDF4
import numpy as np

# --help is for someone who already knows what this does and wants the flags, so it carries
# the shortest thing that lets them run it and read the exit code. Everything else -- the
# physics, the unit conventions, what a given run cannot establish -- lives in the module
# docstring above for a reader of the source, and in the output itself next to the check it
# bears on, which is where it is actually needed.
HELP_DESCRIPTION = """Check the moss diagnostics on a finished CTSM-FATES moss run.

The argument is the CIME case's run/ directory. Reads the daily history tape plus that
run's own FATES and CLM parameter files and lnd_in, and prints PASS / FAIL / SKIP / INFO
per check, WARN for anything about this particular run that a reader must not scroll past,
and a closing verdict. Numbers are reported moss-native; the identities are checked
against the site-level values on the tape.

Needs netCDF4 and numpy, plus matplotlib unless --no-plots. The module docstring at the
top of this file explains the physics, the conventions and the limits."""

HELP_EPILOG = """exit codes:
  0  nothing FAILed and the moss PFT index was confirmed. INFO and SKIP do not bear on
     this, and a PASS that could not pin all its constraints is counted separately in the
     verdict line
  1  at least one check FAILed. A moss-population FAIL is a finding about the model
     configuration rather than about the diagnostics, and still exits 1 deliberately
  2  no trustworthy verdict: pointed at the wrong thing, told the wrong thing about it, or
     unable to confirm which PFT is moss. Outranks 1
  3  an unexpected error inside the script; a traceback is printed. Says nothing about the
     run

No WARN moves any of these."""

EXIT_OK = 0
EXIT_CHECK_FAILED = 1
EXIT_NO_VERDICT = 2
EXIT_INTERNAL_ERROR = 3

# Fuel class indices, 1-based, in the order FatesFuelClassesMod.F90 defines them. The
# fates_levfuel coordinate on the tape is a bare integer axis with no class names, so this
# mapping is the only thing that says which column is which.
FUEL_CLASSES = {
    "twigs": 1,
    "small_branches": 2,
    "large_branches": 3,
    "trunks": 4,
    "dead_leaves": 5,
    "live_grass": 6,
    "live_moss": 7,
    "dead_moss": 8,
}

# The classes whose moisture comes from the fire weather index rather than from the moss
# proxy: everything except the two moss classes. Trunks belong here even though they are
# left out of the fire model's non-trunk aggregates -- that exclusion is about loading, not
# moisture. UpdateFuelMoisture computes effective_moisture for every class including trunks
# (fire/FatesFuelMod.F90:284-285), and the plan's Task 9 Step 4 asks for classes 1-6.
NESTEROV_DRIVEN = [
    FUEL_CLASSES[k]
    for k in (
        "twigs",
        "small_branches",
        "large_branches",
        "trunks",
        "dead_leaves",
        "live_grass",
    )
]

# The moss wetness proxy that moss fuel moisture reads (fire/SFMainMod.F90, the
# UpdateFuelMoisture call). FATES keeps two proxies, one from liquid soil water and one from
# liquid plus ice; fuel moisture reads the total one, FATES_MOSS_FWET_TOT. The wetness scaler
# follows the liquid proxy, so section 2 reads FATES_MOSS_FWET_LIQ directly.
FUEL_MOISTURE_PROXY = "FATES_MOSS_FWET_TOT"

# Shipped namelist defaults, used only when the run's lnd_in cannot be read. The script
# prefers the run's own values and says which it used.
DEFAULT_NAMELIST = {
    "fates_moss_vcmax_fwet_thresh": 0.6,
    "fates_moss_fuel_moisture_live_slope": 0.7,
    "fates_moss_fuel_moisture_live_intercept": 0.0,
    "fates_moss_fuel_moisture_dead_slope": 0.7,
    "fates_moss_fuel_moisture_dead_intercept": 0.0,
}

# Total mineral content of the fuel (Thonicke et al. 2010 Table A1). Shipped value on the
# FATES parameter file; overridden from the run's own paramfile when it can be read.
DEFAULT_MINER_TOTAL = 0.055

# MoistureOfExtinction, fire/FatesFuelMod.F90:367-374: MEF = MEF_A - MEF_B*log(SAV), Eq. 27
# of Peterson and Ryan (1986). Reproduced here only so the Task 9 fit can be checked against
# an MEF that does NOT come out of the fit itself; the SAV it is applied to is read from the
# run's own parameter file. Without an independent MEF, a model that halved every moss
# moisture would still fit a perfect straight line and would only shift the number this
# script prints as the "implied" MEF.
MEF_A = 0.524
MEF_B = 0.066

# CTSM's maximum_leaf_wetted_fraction on the standard CLM parameter file
# (src/biogeophys/CanopyHydrologyMod.F90:1171 applies it). The canopy ingredient of the moss
# wetness proxies cannot exceed this at patch level. Used only when the run's own CLM
# parameter file cannot be read: this is a tuning candidate on this branch, and how much of
# what the checks below say survives raising it is exactly what they have to report from the
# run's own value rather than from this one.
DEFAULT_MAX_LEAF_WETTED_FRACTION = 0.05

# How much clearance the soil ingredient must keep over the canopy ingredient's per-patch
# ceiling before the max()/min() commutation preconditions are treated as merely watched
# rather than secure. A calibration, not a measurement, and what it trades off is worth
# knowing before moving it: the cost of warning too early is one paragraph a reader skims,
# while the cost of warning too late is a Task 8 or Task 10 FAIL whose label points at the
# model when the real cause is a branch that diverged across patches. The warning is the
# cheap side, so this is deliberately set to fire while there is still headroom -- at a
# factor of 2 the soil ingredient would have to halve within a single day, from a value it
# never approaches in a run that does not warn, before two patches of the same site could
# take different branches.
COMMUTATION_MARGIN_FACTOR = 2.0

# Prefixed to any FAIL on an identity that needs the commutation precondition. A reader who
# meets one of these has a model defect and a violated precondition to choose between, and
# the precondition is far the likelier of the two -- it is an assumption this script makes
# about the run, while the identity is arithmetic the model has no room to get wrong.
DIVERGENCE_FIRST_SUSPECT = (
    "BEFORE READING THIS AS A MODEL DEFECT: this identity assumes every vegetated patch "
    "takes the same branch, which a site-level tape cannot check. A branch that differs "
    "between two patches of this site breaks the identity with nothing whatever wrong in "
    "the model, and is the first thing to suspect. See the precondition line at the foot "
    "of this check, and the margin it refers to at the head of section 1."
)

# The two treelai values Task 12 Step 3d predicts for a recruit and for a maximum-size moss
# cohort: cohort leaf area per unit crown area. Reference points to read the diagnosed values
# against, not thresholds anything is tested against.
#
# Unlike the recruit height and the height ceiling beside them in the same INFO, these two
# are NOT recomputed from the run's parameter file. Getting them takes the whole allometry
# chain -- blmax under dh2blmax_3pwr_grass, crown area under carea_2pwr, and then
# FatesAllometryMod.F90:667's tree_lai, which needs the canopy-layer context, slamax and a
# vcmax25top that this branch's own wetness scaler modulates. Reproducing that here would be
# a second implementation of the model, which is the thing this script exists not to do.
# So they are quoted from where they were derived, and the quote is gated: the parameters
# they were derived from are listed below with the values they had, read back from the run's
# own parameter file at the moss index, and the reference line prints only when they still
# agree. A parameter file that has moved on gets told which parameter moved instead of a
# number that is no longer true of it.
TREELAI_AT_RECRUIT = 0.0065
TREELAI_AT_MAX = 0.61
TREELAI_PREDICTION_SOURCE = (
    "Task 12 Step 3d, derived from src/fates/parameter_files/fates_params_moss.json"
)
TREELAI_PREDICTION_PARAMS = {
    "fates_allom_hmode": 3.0,
    "fates_allom_lmode": 5.0,
    "fates_allom_cmode": 1.0,
    "fates_allom_d2h1": 0.1812,
    "fates_allom_d2h2": 0.6384,
    "fates_allom_dbh_maxheight": 20.0,
    "fates_recruit_height_min": 0.02,
    "fates_allom_d2bl1": 0.0004,
    "fates_allom_d2bl2": 1.7092,
    "fates_allom_d2bl3": 0.3417,
    "fates_c2b": 2.0,
    "fates_allom_d2ca_coefficient_min": 0.0408,
    "fates_allom_d2ca_coefficient_max": 0.0408,
    "fates_leaf_slatop": 0.027,
    "fates_leaf_slamax": 0.05,
    "fates_leaf_vcmax25top": 30.0,
    "fates_leafn_vert_scaler_coeff1": 0.00963,
    "fates_leafn_vert_scaler_coeff2": 2.43,
}

# FatesConstantsMod.F90's fates_unset_r8. Under FATES-SP, EDInitMod.F90:863-868 initializes
# the litter and seed pools to fates_unset_r8 instead of to zero, so litter diagnostics on an
# SP tape report ndcmpy or numpft multiples of it rather than zero. Any value this negative
# is that sentinel showing through, not a physical number.
FATES_UNSET_R8 = -1.0e36

# FatesConstantsMod.F90's sec_per_day. Needed for exactly one conversion, and only because
# two variables on the same fuel axis disagree about whether they carry it: see
# check_fuel_burnt.
SEC_PER_DAY = 86400.0

# Categorical slots 1-3 of the default plotting palette. The three panels are independent
# forms rather than a stack, so the palette is doing nothing more than keeping them apart.
COLOR_SERIES = ["#2a78d6", "#eb6834", "#1baf7a"]
COLOR_TEXT = "#0b0b0b"
COLOR_MUTED = "#52514e"
COLOR_SURFACE = "#fcfcfb"

# Tolerances. The identities checked here are algebraic rearrangements of what the model
# stores, so they should hold to roundoff on an accumulation of a few patches, not merely
# "closely". A relative deviation above this means something structural, not numerical.
TOL_EXACT = 1.0e-12
TOL_RELATIVE = 1.0e-9

# --pft-moss validation. The moss index is cross-checked against witnesses that are keyed
# off the model's own notion of which PFT is moss rather than off the index passed in, so a
# wrong-but-in-range index is caught rather than producing confident nonsense about some
# other PFT. WITNESS_MIN is the agreement a witness must reach before the index is called
# CONFIRMED.
#
# It is a calibration, and it is deliberately not what refutes an index. A correct index can
# score below it for an innocent reason: the PFT-level variable and the site-level witness
# can disagree by a day at each appearance and disappearance, so moss that blinks in and out
# often enough drags its own score down, and an absolute floor used as a test would abort a
# perfectly good run. What refutes an index is another PFT agreeing BETTER by more than
# WITNESS_LEAD -- a comparison, which needs no floor -- and only where the parameter file has
# not already settled the index; see validate_pft_moss. Scoring below WITNESS_MIN while still
# being the best index leaves the witness silent rather than damning: it neither confirms nor
# refutes, and the run continues with the unverified-index banner if nothing else confirms.
WITNESS_MIN = 0.99

# How far ahead another PFT has to be before it refutes the index passed in. Also a
# calibration. The witnesses disagree by a day at each appearance and disappearance, and
# which of two PFTs eats that day is arbitrary, so two indices can finish a run separated by
# a couple of days out of several hundred with neither of them wrong. Refuting an index costs
# the whole verdict, so a lead that small must not do it.
WITNESS_LEAD = 0.02

# Task 12 Step 3. A final step this many times the median daily step, taken from this much
# of the peak, is a cohort being removed rather than a decay tail arriving.
DISCONTINUITY_STEP_RATIO = 10.0
DISCONTINUITY_PEAK_FRACTION = 0.05


# Printed when nothing available on a run can confirm which PFT is moss. Every moss-keyed
# number in the output is then about whichever PFT the index happened to name, so this is
# not a caveat on the results -- it is the statement that there are none.
#
# The middle of it is assembled from the reasons the witnesses actually gave, because the
# three reasons a witness can go quiet want three different remedies and only one of them is
# "run something other than FATES-SP". A banner that names the wrong reason sends the reader
# to change the wrong thing.
PFT_UNVERIFIED_HEAD = """\
THE MOSS PFT INDEX IS UNVERIFIED.
Nothing on this run confirms that --pft-moss {pft} is the moss PFT. fates_vascular could not
be read from the run's FATES parameter file, which is the authoritative answer, and no
witness on this tape settled it either:"""

PFT_UNVERIFIED_TAIL = """\
Every moss-keyed number in this run's output may therefore be about some other PFT, and
none of it is a result until the index is confirmed. Hence exit code {code} and not {ok},
whatever the verdict line says; see "Exit codes" in --help.
What would fix it: {remedy}"""

# reason token -> (what the reader is told went wrong, what to do about it)
PFT_WITNESS_REASONS = {
    "absent": (
        "the witness variables are not on this tape at all, so no witness could be "
        "evaluated. That is a hist_fincl1 omission, not a property of the run",
        "put FATES_CROWNAREA_PF, FATES_MOSS_HEIGHT, FATES_LEAFC_PF and FATES_LIVEMOSS_FUEL "
        "in hist_fincl1",
    ),
    "static": (
        "the witnesses are on the tape but never change over the run, so they separate "
        "nothing: every PFT present on all of those days scores the same. Prescribed cover "
        "does this, which is what FATES-SP runs look like",
        "use a tape on which moss appears and disappears",
    ),
    "noisy": (
        "the given index is the best match on this tape but does not agree closely enough "
        "to confirm anything. Moss that blinks in and out drags its own score down that way",
        "nothing about the tape -- read the per-witness agreement above and decide whether "
        "it is moss blinking or the wrong index",
    ),
}

PFT_PARAMFILE_REMEDY = "give this script a readable fates_paramfile"


def unverified_warning(pft_moss, reasons):
    """The banner, with the middle assembled from the reasons the witnesses actually gave."""
    seen = [r for r in ("absent", "static", "noisy") if r in reasons]
    if not seen:
        seen = ["absent"]
    lines = [PFT_UNVERIFIED_HEAD.format(pft=pft_moss)]
    lines += [f"  - {PFT_WITNESS_REASONS[r][0]}." for r in seen]
    remedy = "; or ".join(
        [PFT_PARAMFILE_REMEDY] + [PFT_WITNESS_REASONS[r][1] for r in seen]
    )
    lines.append(
        PFT_UNVERIFIED_TAIL.format(code=EXIT_NO_VERDICT, ok=EXIT_OK, remedy=remedy + ".")
    )
    return "\n".join(lines)


def print_warning(text):
    """A block a reader cannot mistake for one more line of output."""
    print("!" * 79)
    for line in text.splitlines():
        print(f"!! {line}")
    print("!" * 79)


class HistoryContentError(ValueError):
    """The history output is not shaped the way this script requires."""


def emit_detail(detail, indent=5):
    """Print a check's message, one bullet per statement.

    A message is several statements joined by newlines, and without a marker it is not
    obvious where one ends and the next begins -- several of them run long enough to wrap
    in a terminal. A line that already begins with whitespace is a deliberate continuation
    of the statement above it (the second half of an identity, a figure aligned under its
    label), so it is indented to match rather than given a bullet of its own.
    """
    pad = " " * indent
    for line in str(detail).splitlines():
        if line.strip() and not line[:1].isspace():
            print(f"{pad}• {line}")
        else:
            print(f"{pad}  {line}")


class Reporter:
    """Accumulates check outcomes so the run can end with a one-line verdict."""

    def __init__(self):
        self.counts = {"PASS": 0, "FAIL": 0, "INFO": 0, "SKIP": 0}
        self.unconstrained = []
        self.warnings = []

    def warn(self, label, detail):
        """Record something about THIS run that a reader must not scroll past.

        Kept off `counts` and out of the exit code on purpose. A warning is not a check: it
        says a check established less than its label claims, or that a path this run never
        exercised is therefore untested. Neither is a result the run failed, and folding
        either into FAIL would make the exit code stop meaning "an identity broke".

        Warnings print where they are raised, next to the check they qualify, and are
        reprinted together in the verdict block -- the same treatment the unverified-index
        banner gets, and for the same reason: by the time a reader reaches the verdict, the
        line that qualifies it is hundreds of lines up.
        """
        self.warnings.append((label, str(detail)))
        print(f"[WARN] {label}")
        emit_detail(detail)
        print()

    def __call__(self, status, label, detail, unconstrained=None):
        """Print one outcome. `unconstrained` says what this check could not pin down.

        A check can pass everything it was able to test while one of its constraints was
        simply unavailable -- the Task 9 slope when fates_fire_SAV cannot be read off the
        run's parameter file. That is not the same result as a fully constrained PASS, and
        the two must not read identically in the verdict line, which is the only line some
        callers look at.
        """
        self.counts[status] += 1
        if unconstrained:
            self.unconstrained.append((label, unconstrained))
        print(f"[{status:4s}] {label}")
        emit_detail(detail)
        print()

    def verdict(self):
        c = self.counts
        print("=" * 79)
        degraded = (
            f" ({len(self.unconstrained)} of them not fully constrained)"
            if self.unconstrained
            else ""
        )
        print(
            f"PASS {c['PASS']}{degraded}   FAIL {c['FAIL']}   SKIP {c['SKIP']}   "
            f"INFO {c['INFO']} (reported for judgement, not tested)"
        )
        for label, why in self.unconstrained:
            print(f"  not fully constrained -- {label}")
            emit_detail(why, indent=7)
        if self.warnings:
            print()
            print(
                f"{len(self.warnings)} WARNING(S) about this run. None of them bears on the "
                "tallies above or on the exit code; each says that something the labels "
                "above appear to claim was not actually established here. Search the "
                "headline above to read one in full."
            )
            for label, _ in self.warnings:
                print(f"  [WARN] {label}")
        return EXIT_CHECK_FAILED if c["FAIL"] else EXIT_OK


# ---------------------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------------------


def history_files(run_dir):
    files = sorted(glob.glob(os.path.join(run_dir, "*.clm2.h0a.*.nc")))
    if not files:
        raise HistoryContentError(
            f"no *.clm2.h0a.*.nc files under {run_dir}. Point this at a finished case's "
            "run/ directory, which holds one daily-mean history file per day."
        )
    return files


def check_tape_shape(path):
    """Refuse a tape whose shape would make every number below mean something else.

    Two properties of the CASE, not of the model, are load-bearing for everything after
    this point, and neither is visible in the output once the arrays are stacked:

      * ONE GRIDCELL. Every check indexes (day,) or (day, level) arrays. On a tape with
        more than one gridcell the trailing-axis squeeze below does not fire, the gridcell
        axis survives, and the checks run on arrays one rank too high -- producing confident
        PASSes whose "days" counts are counting rows, followed by a crash somewhere further
        down when a number is finally formatted. Confident output from a tape the script
        cannot handle is the worst failure available here, so this is refused rather than
        degraded.

      * ONE DAILY-MEAN SAMPLE PER FILE. Everything downstream counts in days and compares a
        day against the day before it. hist_mfilt > 1 puts several samples in a file, which
        the squeeze below cannot even represent; a cadence other than daily leaves the shape
        intact and quietly redefines every "days" count in the output, and makes the Task 7
        one-day-lag identity compare two samples that are not a day apart, which then FAILs
        against the model for a property of the testmod.
    """
    with netCDF4.Dataset(path) as ds:
        for name in ("lndgrid", "gridcell"):
            if name in ds.dimensions and int(ds.dimensions[name].size) != 1:
                raise HistoryContentError(
                    f"this tape has {int(ds.dimensions[name].size)} gridcells "
                    f"({name} = {int(ds.dimensions[name].size)} in "
                    f"{os.path.basename(path)}), and every check here is written for a "
                    "single-point run: it would report per-gridcell rows as though they "
                    "were days. Point this at a single-point case."
                )
        nsample = int(ds.dimensions["time"].size) if "time" in ds.dimensions else 1
        if nsample != 1:
            raise HistoryContentError(
                f"{os.path.basename(path)} holds {nsample} samples, not one. This script "
                "needs one daily mean per file, which is hist_mfilt = 1; at hist_mfilt = "
                f"{nsample} every 'days' count below would be a count of files instead. "
                "Re-run the case with hist_mfilt = 1, or point this at a tape written that "
                "way."
            )
        span = None
        if "time_bounds" in ds.variables:
            bounds = np.ravel(np.asarray(ds["time_bounds"][:], dtype=np.float64))
            units = getattr(ds["time_bounds"], "units", "days since")
            if bounds.size >= 2 and "day" in units:
                span = float(bounds[1] - bounds[0])
        if span is not None and abs(span - 1.0) > 1.0e-6:
            hours = 24.0 * span
            raise HistoryContentError(
                f"{os.path.basename(path)} is a {hours:g}-hour mean, not a daily one "
                f"(its time_bounds span {span:g} days), which is hist_nhtfrq other than "
                "-24. Every count below is a count of days and the Task 7 identity compares "
                "a sample against the one a DAY earlier, so at this cadence the numbers "
                "would be wrong rather than merely finer. Re-run the case with hist_nhtfrq "
                "= -24, or point this at the h0a tape that has it."
            )


def load_history(run_dir, cache_dir=None):
    """Concatenate the daily h0a files into (name -> array) with time as the first axis.

    Each file holds one daily-mean sample, so the arrays come out (nday,) for site
    variables and (nday, nlev) for the fates_levfuel / fates_levpft ones. Concatenating a
    two-year run means opening ~730 files, which is slow enough to be worth caching when
    the same run is examined more than once.
    """
    files = history_files(run_dir)
    # Ahead of the cache lookup, not after it: a refusal has to be the same refusal whether
    # or not this run has been read before.
    check_tape_shape(files[0])
    cache_path = None
    if cache_dir:
        # The key has to carry the file mtimes, not just the count: the second leg of an
        # ERS test rewrites the tail of the run's h0a files in place without changing how
        # many there are, so a count-only key would serve a stale first-leg cache.
        stamp = "".join(f"|{os.path.basename(f)}:{os.path.getmtime(f):.0f}" for f in files)
        key = hashlib.md5(f"{os.path.abspath(run_dir)}:{stamp}".encode()).hexdigest()[:16]
        # The case name is here so a stray cache file can be traced back to its run by
        # reading it; the digest stays because it is what INVALIDATES the cache, and the
        # mtimes it carries cannot be put in a filename.
        suffix = f"_{key}.npz"
        cache_path = os.path.join(
            cache_dir, case_tag(run_dir, reserve=len(suffix)) + suffix
        )
        if os.path.exists(cache_path):
            with np.load(cache_path) as z:
                return {k: z[k] for k in z.files}, files

    with netCDF4.Dataset(files[0]) as ds:
        names = [
            v
            for v in ds.variables
            if "time" in ds[v].dimensions and ds[v].dtype.kind in "fi"
        ]
    stacks = {v: [] for v in names}
    for path in files:
        with netCDF4.Dataset(path) as ds:
            # The variable list is taken from the first file, so a later file that does not
            # carry all of them is a real possibility -- hist_fincl1 changing across a
            # restart is the ordinary way it happens -- and one that must name the file it
            # found rather than dying on a netCDF4 IndexError whose message is "not found
            # in /".
            missing = [name for name in names if name not in ds.variables]
            if missing:
                raise HistoryContentError(
                    f"{os.path.basename(path)} does not carry "
                    + ", ".join(missing[:6])
                    + (f" and {len(missing) - 6} more" if len(missing) > 6 else "")
                    + f", which {os.path.basename(files[0])} does. The files in this "
                    "directory were written with different field lists -- hist_fincl1 "
                    "changed across a restart, or two cases' output is mixed together here "
                    "-- and there is no single record to concatenate. Separate them, or "
                    "point this at a directory holding one field list."
                )
            for name in names:
                # Read the raw values, not the auto-masked view: FATES writes real
                # sentinels (see FATES_UNSET_R8) that must stay visible as numbers so the
                # checks below can name them, rather than silently becoming NaN.
                arr = np.asarray(ds[name][:], dtype=np.float64)
                arr = np.squeeze(arr, axis=0)  # drop the length-1 time axis
                if arr.ndim and arr.shape[-1] == 1:
                    arr = np.squeeze(arr, axis=-1)  # drop the length-1 lndgrid axis
                stacks[name].append(arr)
    data = {v: np.array(vals) for v, vals in stacks.items()}

    if cache_path:
        os.makedirs(cache_dir, exist_ok=True)
        np.savez_compressed(cache_path, **data)
    return data, files


def read_lnd_in(run_dir):
    """Scalar settings from the run's lnd_in, so the checks test what this run configured.

    Returns {} if lnd_in is absent, in which case the caller falls back to the configured
    defaults and says so. Only simple `name = value` scalars are parsed; the multi-line
    list variables (hist_fincl1 and friends) are not needed here.
    """
    path = os.path.join(run_dir, "lnd_in")
    if not os.path.exists(path):
        return {}
    settings = {}
    pattern = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.+?)\s*$")
    with open(path) as handle:
        for line in handle:
            match = pattern.match(line)
            if not match:
                continue
            name, raw = match.group(1), match.group(2).rstrip(",")
            if raw.startswith("'") and raw.endswith("'"):
                settings[name] = raw[1:-1]
            elif raw in (".true.", ".false."):
                settings[name] = raw == ".true."
            else:
                try:
                    settings[name] = float(raw)
                except ValueError:
                    pass
    return settings


class RunConfig:
    """What this run's lnd_in says about the configuration the checks have to reason about.

    Every attribute is None where lnd_in did not say, and None means UNKNOWN -- never "off".
    That distinction is the whole reason this exists. A configuration read off the tape
    instead is read off the absence of a variable, and a variable is absent from a tape when
    it was left out of hist_fincl1, which says nothing whatever about how the run was
    configured. FATES_NESTEROV_INDEX and FATES_BURNFRAC are both registered unconditionally
    with use_default='active' (main/FatesHistoryInterfaceMod.F90:6754, :6839), so neither
    one's absence is evidence that fire is off; FATES_NOCOMP_PATCHAREA_PF's absence is not
    evidence that the run is full competition. lnd_in says all of it outright.
    """

    KEYS = (
        "use_fates_sp",
        "use_fates_nocomp",
        "use_fates_fixed_biogeog",
        "fates_spitfire_mode",
    )

    def __init__(self, namelist):
        self.readable = any(key in namelist for key in self.KEYS)
        self.use_sp = namelist.get("use_fates_sp")
        self.nocomp = namelist.get("use_fates_nocomp")
        self.fixed_biogeog = namelist.get("use_fates_fixed_biogeog")
        self.spitfire_mode = namelist.get("fates_spitfire_mode")

    @property
    def bareground_patch(self):
        """Whether FATES made this run a bareground patch, or None where lnd_in did not say.

        EDInitMod.F90:841 makes one under hlm_use_nocomp .and. hlm_use_fixed_biogeog and
        under nothing else, so this is exactly the condition under which the patch areas of
        the vegetated PFTs sum to less than 1 and the site-to-patch factor is not 1.
        """
        if self.nocomp is None or self.fixed_biogeog is None:
            return None
        return bool(self.nocomp) and bool(self.fixed_biogeog)

    @property
    def spitfire_on(self):
        """Whether SPITFIRE ran, or None where lnd_in did not say."""
        if self.use_sp is None and self.spitfire_mode is None:
            return None
        return not bool(self.use_sp) and float(self.spitfire_mode or 0) > 0

    def settings_phrase(self):
        return (
            f"use_fates_sp = {self.use_sp}, fates_spitfire_mode = {self.spitfire_mode}, "
            f"use_fates_nocomp = {self.nocomp}, "
            f"use_fates_fixed_biogeog = {self.fixed_biogeog}"
        )


def fire_status_sentence(config, spitfire_on, gate_note):
    """One sentence saying what is actually known about whether fire ran in this run.

    Used wherever a check would otherwise be tempted to conclude something about fire from a
    variable not being on the tape. It never concludes anything from the tape itself.
    """
    if config.spitfire_on is None:
        return (
            "Whether fire ran in this run is not known here: its lnd_in does not say."
            + (
                f" Taking it as {'ON' if spitfire_on else 'OFF'} for the checks above."
                + gate_note
                if gate_note
                else ""
            )
        )
    if config.spitfire_on:
        return (
            f"Fire DID run in this case: {config.settings_phrase()}, from this run's lnd_in."
        )
    return (
        f"Fire did not run in this case: {config.settings_phrase()}, from this run's lnd_in."
    )


def read_pft_names(paramfile, npft):
    """fates_pftname off the run's FATES parameter file, or None where it cannot be read.

    Handled apart from read_params because the two file formats store it differently: JSON
    holds a list of strings, NetCDF a (pft, string_length) character array.
    """
    if not paramfile or not os.path.exists(paramfile):
        return None
    try:
        if paramfile.endswith(".json"):
            with open(paramfile) as handle:
                params = json.load(handle)["parameters"]
            if "fates_pftname" not in params:
                return None
            names = [str(v).strip() for v in params["fates_pftname"]["data"]]
        else:
            with netCDF4.Dataset(paramfile) as ds:
                if "fates_pftname" not in ds.variables:
                    return None
                raw = netCDF4.chartostring(ds["fates_pftname"][:])
                names = [str(v).strip() for v in np.ravel(raw)]
    except (OSError, KeyError, ValueError, IndexError, TypeError):
        return None
    return names if len(names) == npft else None


def read_params(paramfile, names):
    """Named parameters off the run's FATES parameter file (JSON or NetCDF), as 1-D arrays.

    Missing names are simply absent from the returned dict, so the caller can fall back and
    say so rather than quietly asserting a number this run may not have used.
    """
    values = {}
    if not paramfile or not os.path.exists(paramfile):
        return values
    try:
        if paramfile.endswith(".json"):
            with open(paramfile) as handle:
                params = json.load(handle)["parameters"]
            for name in names:
                if name in params:
                    values[name] = np.ravel(np.asarray(params[name]["data"]))
        else:
            with netCDF4.Dataset(paramfile) as ds:
                for name in names:
                    if name in ds.variables:
                        values[name] = np.ravel(np.asarray(ds[name][:]))
    except (OSError, KeyError, ValueError, IndexError):
        return values
    return values


def pft_axis_length(files, data):
    """Length of the fates_levpft axis, which --pft-moss and --pft-grass are validated on.

    Taken from the tape's own dimension rather than off the shape of some variable, because
    which per-PFT variables a run writes depends on how it was configured: the obvious
    candidate, FATES_NOCOMP_PATCHAREA_PF, exists only under nocomp. The fallback covers a
    tape whose axis is named something else.
    """
    try:
        with netCDF4.Dataset(files[0]) as ds:
            if "fates_levpft" in ds.dimensions:
                return int(ds.dimensions["fates_levpft"].size)
    except OSError:
        pass
    for name, values in data.items():
        if name.endswith("_PF") and values.ndim == 2:
            return int(values.shape[1])
    raise HistoryContentError(
        "this tape has no fates_levpft dimension and no per-PFT variable, so there is "
        "nothing to interpret --pft-moss and --pft-grass against."
    )


def non_bareground_fraction(data, config, nday):
    """The area fraction relating a site-level moss diagnostic to the patch value it reports.

    Almost every site-level moss diagnostic is a patch-area weighted sum in which bareground
    contributes zero, so a site value is the patch value times this fraction.

    Returns (fraction per day or None, reason it is None, where it came from, the per-PFT
    prescribed patch area or None). The last is returned alongside rather than looked up
    again by the callers that report prescribed cover, so that the whole script decides once
    whether that variable is usable; two gates that disagree about it produced a run
    reporting prescribed cover in one place and saying the report was skipped in another.

    Where the fraction comes from is a question about the run's CONFIGURATION, and it is
    answered from lnd_in:

      * FATES makes a bareground patch only under nocomp AND fixed biogeography
        (main/EDInitMod.F90:841). Under any other configuration there is no bareground
        patch, the patch areas sum to AREA, and the fraction is 1.0 exactly -- so a
        full-competition run loses nothing at all and every check runs in full.
      * FATES_NOCOMP_PATCHAREA_PF, where the fraction is read from when there IS a
        bareground patch, is registered under hlm_use_nocomp alone
        (main/FatesHistoryInterfaceMod.F90:7688). On a nocomp run without fixed biogeography
        it is therefore present and sums to 1.0 anyway, which agrees with the line above.

    So the variable being absent is not by itself informative -- a variable is absent from a
    tape when it was left out of hist_fincl1 -- and only two cases leave the fraction
    genuinely unknown: a nocomp+fixed-biogeog run that did not write it, and a run with no
    readable lnd_in to say which configuration it is. Those two degrade, and are told apart
    in the reason, because the remedies differ.

    A patch area that is present but is not a fraction is a different thing -- a tape this
    script does not understand, rather than a configuration it can degrade for -- and it
    still stops the run. A patch area that is zero on some days is NOT that: zero is a legal
    fraction, and the days it makes unusable are handled by the divisions that need it
    rather than by rejecting the tape.
    """
    if "FATES_NOCOMP_PATCHAREA_PF" not in data:
        if config.bareground_patch is False:
            return (
                np.ones(nday),
                None,
                "1.0 exactly: this run's lnd_in says it has no bareground patch",
                None,
            )
        if config.bareground_patch is None:
            return (
                None,
                "FATES_NOCOMP_PATCHAREA_PF is not on this tape, and this run's lnd_in "
                "could not be read to say whether the run has a bareground patch at all. "
                "Without a bareground patch the fraction would be 1.0 and nothing would be "
                "lost (main/EDInitMod.F90:841); with one it is whatever that variable "
                "would have said. It is the unreadable lnd_in, not the configuration, that "
                "leaves this unknown.",
                None,
                None,
            )
        return (
            None,
            "FATES_NOCOMP_PATCHAREA_PF is not on this tape, and this run's lnd_in says it "
            f"IS a nocomp + fixed-biogeography run ({config.settings_phrase()}), so it "
            "does have a bareground patch and the fraction is genuinely missing rather "
            "than equal to 1. FATES registers that variable under hlm_use_nocomp "
            "(main/FatesHistoryInterfaceMod.F90:7688), so this run wrote it and it was "
            "left out of hist_fincl1.",
            None,
            None,
        )
    patch_area = data["FATES_NOCOMP_PATCHAREA_PF"]
    fraction = patch_area.sum(axis=1)
    if float(np.nanmax(fraction)) <= 0.0:
        return (
            None,
            "FATES_NOCOMP_PATCHAREA_PF is on this tape but reads zero on every day of the "
            "run, so there is no non-bareground area fraction to weight by.",
            None,
            None,
        )
    if (
        float(np.nanmin(fraction)) < -TOL_EXACT
        or float(np.nanmax(fraction)) > 1.0 + TOL_EXACT
    ):
        raise HistoryContentError(
            f"the non-bareground area fraction from FATES_NOCOMP_PATCHAREA_PF is "
            f"{np.nanmin(fraction):.4g} - {np.nanmax(fraction):.4g}, which is outside "
            "[0, 1] and so is not a fraction at all. That is neither a nocomp tape nor a "
            "full-competition one, both of which this script handles; it is a tape it does "
            "not understand."
        )
    return fraction, None, "FATES_NOCOMP_PATCHAREA_PF on this tape", patch_area


# ---------------------------------------------------------------------------------------
# Small numerical helpers
# ---------------------------------------------------------------------------------------


def relative_deviation(actual, expected):
    """max|actual - expected| scaled by the magnitude of what is being compared.

    NaN over an empty comparison, which is what a one-day tape hands the Task 7 one-day-lag
    slice. That is a check that could not be evaluated, and the caller has to SKIP it; the
    reductions below would raise on the empty array instead.
    """
    actual, expected = np.asarray(actual), np.asarray(expected)
    if actual.size == 0 or expected.size == 0:
        return np.nan
    scale = max(float(np.nanmax(np.abs(expected))), float(np.nanmax(np.abs(actual))))
    if scale == 0.0:
        return 0.0
    return float(np.nanmax(np.abs(actual - expected)) / scale)


# Why a fit or a correlation could not be computed. NaN alone reaches the caller as "this
# check failed", printed as `nan`, which is a wrong label on a run that was simply too short
# or too flat -- and the two want different answers from the reader, so they are named apart.
FIT_MIN_POINTS = 3
FIT_TOO_FEW = (
    "too few usable days -- {n}, out of the {nday} this tape holds -- and a fit needs 3"
)
FIT_NO_SPREAD = (
    "the predictor does not vary over the {n} usable days of this run, so there is no "
    "spread for a fit or a correlation to key off"
)


def fit_obstacle(x, y, nday, both=False):
    """Why linear_fit/correlation cannot be computed here, or None when they can.

    `both` for a correlation, which needs spread on both sides; a fit needs it only in x.
    """
    x, y = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    ok = np.isfinite(x) & np.isfinite(y)
    n = int(ok.sum())
    if n < FIT_MIN_POINTS:
        return FIT_TOO_FEW.format(n=n, nday=nday)
    if np.ptp(x[ok]) == 0 or (both and np.ptp(y[ok]) == 0):
        return FIT_NO_SPREAD.format(n=n)
    return None


def linear_fit(x, y):
    """Least-squares slope, intercept and R^2 over the finite, non-degenerate points."""
    ok = np.isfinite(x) & np.isfinite(y)
    if ok.sum() < FIT_MIN_POINTS or np.ptp(x[ok]) == 0:
        return np.nan, np.nan, np.nan
    slope, intercept = np.polyfit(x[ok], y[ok], 1)
    residual = y[ok] - (slope * x[ok] + intercept)
    total = y[ok] - y[ok].mean()
    r2 = 1.0 - np.sum(residual**2) / np.sum(total**2) if np.sum(total**2) > 0 else np.nan
    return float(slope), float(intercept), float(r2)


def correlation(x, y):
    ok = np.isfinite(x) & np.isfinite(y)
    if ok.sum() < FIT_MIN_POINTS or np.ptp(x[ok]) == 0 or np.ptp(y[ok]) == 0:
        return np.nan
    return float(np.corrcoef(x[ok], y[ok])[0, 1])


def evaluated(nday, *arrays):
    """How many of the tape's days every one of these arrays actually carries a number on.

    Every comparison in this script goes through np.nanmax/np.nanmin, and the `<` tests that
    count violations are False on NaN, so a NaN day is silently dropped from whatever check
    reads it and the verdict comes out identical to a clean run's. That is the one failure
    mode here that produces no output at all, so each check says how many days it evaluated
    whenever that is fewer than the tape holds.
    """
    ok = np.ones(nday, dtype=bool)
    for array in arrays:
        values = np.asarray(array, dtype=float)
        finite = np.isfinite(values)
        while finite.ndim > 1:
            finite = finite.all(axis=-1)
        ok &= finite[:nday]
    return int(ok.sum())


def coverage_note(nday, *arrays):
    """One line saying how many days a check evaluated, or "" when it evaluated them all."""
    used = evaluated(nday, *arrays)
    if used >= nday:
        return ""
    return (
        f"\nEVALUATED ON {used} of the tape's {nday} days: the other {nday - used} carry a "
        "non-finite value in one of the quantities above and are dropped by every "
        "comparison here, including the ones that count violations."
    )


def divide_by_fraction(values, fraction):
    """values / fraction, NaN where the fraction is zero rather than an inf or a warning.

    A zero-area day is a legal day of a legal tape. What it is not is a day on which a site
    value can be divided back out to a patch value, so it drops out of the reductions that
    read the result and is counted by coverage_note.
    """
    fraction = np.asarray(fraction, dtype=float)
    usable = fraction > 0
    safe = np.where(usable, fraction, 1.0)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(usable, np.asarray(values, dtype=float) / safe, np.nan)


def is_unset(values):
    """True where a FATES-SP unset-litter sentinel is showing through, not a real number."""
    return np.asarray(values) <= FATES_UNSET_R8 / 2.0


def spikiness(series):
    """Ratio of the largest day-to-day jump to the mean jump: high means event-driven.

    NaN where there are no day-to-day steps to take a ratio of, which a one-day tape has.
    """
    steps = np.abs(np.diff(series))
    if steps.size == 0 or not np.any(np.isfinite(steps)):
        return np.nan
    mean = np.nanmean(steps)
    return float(np.nanmax(steps) / mean) if mean > 0 else np.nan


def span(values, fmt="{:.4f}"):
    """"lo - hi" over the finite values, or a phrase where there are none.

    np.nanmin/np.nanmax raise a warning and return NaN on an all-NaN input, which is a
    real possibility for anything divided by a quantity that is zero all run.
    """
    values = np.asarray(values, dtype=float)
    if not np.any(np.isfinite(values)):
        return "no day with a finite value"
    lo, hi = float(np.nanmin(values)), float(np.nanmax(values))
    return f"{fmt.format(lo)} - {fmt.format(hi)}"


def named(value, name, source, fmt="{:g}"):
    """A parameter written the only way this script writes one: name = value (source).

    A bare decimal in this output is a run output, by construction. That is only true while
    every number that came off a parameter file or a namelist goes through here, so this is
    a rule rather than a convenience: `0.05` on the screen means the run reached it, while
    `maximum_leaf_wetted_fraction = 0.05 (this run's CLM parameter file)` means it was
    configured. Nothing else distinguishes the two, and the difference between a realized
    maximum and a ceiling is exactly the thing a reader has to be able to see at a glance.
    """
    return f"{name} = {fmt.format(value)} ({source})"


# ---------------------------------------------------------------------------------------
# Moss-native display units
# ---------------------------------------------------------------------------------------


class NativeUnits:
    """The divisors that turn a site-level moss diagnostic into a moss-native one.

    Nothing here is applied to a CHECK. The tape is site-level, every identity below is
    checked against the values the tape holds, and converting before comparing would add a
    division that buys nothing and perturbs the deviations. This exists so that the numbers
    a reader is asked to judge -- what moss's wetness proxy reached, how much fuel a moss
    mat carries, what a moss cohort produced -- are the numbers moss itself carries, rather
    than those numbers diluted by area fractions belonging to the rest of the gridcell.

    Three families, three divisors, each traced to the FATES source rather than assumed:

      PATCH   a property diagnosed on every non-bareground patch, so only bareground
              dilutes it. UpdateMossFwetLiq and UpdateMossFwetTot are called on every
              patch whose label is not nocomp_bareground (main/EDMainMod.F90:232-237),
              which makes both proxies, their ingredients, the wetness scaler and the moss
              classes' fuel moisture all the same number on the grass patch as on the moss
              patch. Divisor: the non-bareground area fraction.

      MOSS    a quantity that exists only where moss does. cpatch%livemoss sums only the
              non-vascular cohorts of its own patch (biogeochem/FatesPatchMod.F90:855-875),
              and moss_fines is fed only by non-vascular cohorts
              (biogeochem/EDPhysiologyMod.F90:367, :2965, :3065), so both are identically
              zero on a grass patch. Divisor: the MOSS patch area, which is not the
              non-bareground fraction and is smaller than it.

      CROWN   a per-PFT quantity at the moss index, which the tape reports per m2 land.
              Divisor: moss crown area, giving the per-plant quantity a moss measurement
              would be compared against. Crown area is exactly zero on every day moss is
              absent, so this one is undefined on those days and says so.

    A divisor that is not available on a run does not cost the number: it falls back to the
    tape's site value with a one-line note saying which fraction was missing. The only run
    that reaches that is a nocomp+fixed-biogeog one whose FATES_NOCOMP_PATCHAREA_PF was
    left out of hist_fincl1, or one with no readable lnd_in -- under full competition there
    is no bareground patch and moss is in every patch, so both area divisors are 1.0 and
    nothing whatever is lost.
    """

    # The denominator each family's native value is per. Substituted for the word "land" in
    # the tape's own units string, so that "kg m-2 land" becomes "kg m-2 of moss patch" and
    # a dimensionless quantity is simply called moss-native.
    DENOM = {
        "patch": "vegetated patch",
        "moss": "moss patch",
        "crown": "moss crown",
    }

    def __init__(self, data, veg_frac, veg_frac_source, no_veg_frac_reason, patch_area, moss):
        self.divisor = {"patch": veg_frac}
        self.source = {"patch": veg_frac_source}
        self.missing = {"patch": no_veg_frac_reason}

        if patch_area is not None:
            self.divisor["moss"] = patch_area[:, moss]
            self.source["moss"] = "FATES_NOCOMP_PATCHAREA_PF at the moss index on this tape"
            self.missing["moss"] = None
        elif veg_frac is not None:
            # The only way to get here is a run FATES gave no bareground patch, where
            # veg_frac is 1.0 exactly. Moss is then in every patch rather than confined to
            # one, so "per m2 of moss patch" and "per m2 land" are the same statement.
            self.divisor["moss"] = veg_frac
            self.source["moss"] = veg_frac_source + ", and moss is in every patch"
            self.missing["moss"] = None
        else:
            self.divisor["moss"] = None
            self.source["moss"] = None
            self.missing["moss"] = no_veg_frac_reason

        crown = data.get("FATES_CROWNAREA_PF")
        self.divisor["crown"] = None if crown is None else crown[:, moss]
        self.source["crown"] = (
            None if crown is None else "FATES_CROWNAREA_PF at the moss index on this tape"
        )
        self.missing["crown"] = (
            None
            if crown is not None
            else "FATES_CROWNAREA_PF is not on this tape, so moss crown area is unknown here"
        )

    # The full reason a divisor is missing is a paragraph, and it is already printed twice
    # -- in the preamble and in the WARN that says which checks are degraded. Repeating it
    # under every number it touches is the same crime as the precondition paragraph that
    # used to print three times, only worse: a run without a patch area carries a dozen such
    # numbers. Each of those gets this instead, and the paragraph stays where it was said.
    SHORT_MISSING = {
        "patch": "no non-bareground area fraction on this run; see the WARN above",
        "moss": "no moss patch area on this run; see the WARN above",
        "crown": "FATES_CROWNAREA_PF is not on this tape",
    }

    def has(self, kind):
        return self.divisor[kind] is not None

    def native(self, values, kind):
        """values in moss-native units, or None where the divisor is not available.

        NaN, not inf, on a day whose divisor is zero -- a day moss is absent has no crown
        area to divide by, and there is no moss-native number for it to have.
        """
        if self.divisor[kind] is None:
            return None
        return divide_by_fraction(values, self.divisor[kind])

    def undefined_because(self, kind):
        return (
            "moss carries no crown area on those days"
            if kind == "crown"
            else "the area fraction is zero on those days"
        )

    def units_of(self, kind, site_units):
        """What the converted number is per, phrased from the tape's own units string."""
        if not site_units:
            return "moss-native"
        return site_units.replace(" land", " of " + self.DENOM[kind])

    def spans(self, values, kind, fmt="{:.4f}", site_units="kg m-2 land"):
        """"lo - hi" moss-native, with the tape's own value after it in brackets."""
        values = np.asarray(values, dtype=float)
        site = "on the tape " + span(values, fmt) + (f" {site_units}" if site_units else "")
        converted = self.native(values, kind)
        if converted is None:
            return (
                span(values, fmt)
                + (f" {site_units}" if site_units else "")
                + f", on the tape ({self.SHORT_MISSING[kind]})"
            )
        if not np.any(np.isfinite(converted)):
            return f"undefined ({self.undefined_because(kind)}); {site}"
        blank = int(np.sum(~np.isfinite(converted)))
        tail = (
            f"; undefined on {blank} of {values.shape[0]} days "
            f"({self.undefined_because(kind)})"
            if blank
            else ""
        )
        return (
            f"{span(converted, fmt)} {self.units_of(kind, site_units)}   ({site}){tail}"
        )

    def value(self, number, kind, fmt="{:.4g}", site_units="kg m-2 land"):
        """One scalar converted, or a phrase where it cannot be."""
        if self.divisor[kind] is None:
            return (
                fmt.format(number)
                + (f" {site_units}" if site_units else "")
                + f", on the tape ({self.SHORT_MISSING[kind]})"
            )
        scale = float(np.nanmean(self.divisor[kind]))
        if not np.isfinite(scale) or scale <= 0:
            return f"undefined ({self.undefined_because(kind)})"
        return f"{fmt.format(number / scale)} {self.units_of(kind, site_units)}"

    def preamble(self):
        """What the reader needs to read every number below, said once."""
        lines = [NATIVE_NOTE]
        for kind, what in (
            ("patch", "non-bareground area fraction"),
            ("moss", "moss patch area fraction"),
            ("crown", "moss crown area"),
        ):
            divisor = self.divisor[kind]
            if divisor is None:
                lines.append(f"  {what}: NOT AVAILABLE -- {self.missing[kind]}")
                continue
            values = np.asarray(divisor, dtype=float)
            lo, hi = float(np.nanmin(values)), float(np.nanmax(values))
            # A divisor that never moves is one number, not a range. Printing "0.8 - 0.8"
            # invites a reader to look for the variation that is not there.
            shown = f"{lo:.4g}" if lo == hi else f"{lo:.4g} - {hi:.4g}"
            zero = int(np.sum(values <= 0))
            lines.append(
                f"  {what}: {shown} (from {self.source[kind]})"
                + (
                    f"; zero on {zero} of {values.size} days, on which no moss-native "
                    "number can be formed"
                    if zero
                    else ""
                )
            )
        return "\n".join(lines)


NATIVE_NOTE = (
    "Numbers below are MOSS-NATIVE: the tape's site means divided back out by the area\n"
    "fraction that dilutes each one, so they read as what moss itself carries. Where the\n"
    "tape's own number is still worth seeing it follows in brackets, marked \"on the "
    "tape\".\n"
    "The identities were checked against the site-level values on the tape; only the\n"
    "display is converted. Three divisors are in play, and they are not interchangeable:"
)


def dates(data, nday, files):
    """YYYYMMDD per sample from mcdate, or a 1-based day index if mcdate is absent.

    The dates also settle whether these files are ONE record. Two cases' output landing in
    the same directory concatenates without complaint otherwise -- the file names sort into
    an interleaved order, every array comes out the right shape, and the whole verdict is
    computed over a duplicated, non-monotonic series with the preamble reporting twice as
    many days as either run has. So a repeated or backwards date stops the run here.
    """
    if "mcdate" not in data:
        return list(range(1, nday + 1))
    when = [int(v) for v in np.ravel(data["mcdate"])[:nday]]
    steps = np.diff(np.asarray(when))
    if when and np.any(steps <= 0):
        first = int(np.argmax(steps <= 0))
        raise HistoryContentError(
            f"the dates on these files do not increase: file {first + 1} "
            f"({os.path.basename(files[first])}) is {when[first]} and file {first + 2} "
            f"({os.path.basename(files[first + 1])}) is {when[first + 1]}. "
            + (
                "The same date appears twice"
                if when[first] == when[first + 1]
                else "The series goes backwards"
            )
            + ", so this directory is not one run's record -- most likely two cases' output "
            "in one place. Every count and every day-to-day comparison below would be "
            "computed over that mixture. Separate them and point this at one case's run/."
        )
    return when


def absent(data, *names):
    """The names not on this tape, so a check can SKIP rather than raise KeyError."""
    return [name for name in names if name not in data]


# ---------------------------------------------------------------------------------------
# Preconditions on the arguments
# ---------------------------------------------------------------------------------------


def witness_agreement(present_pft, present_site):
    """Per-PFT fraction of days on which "this PFT is present" matches a moss witness.

    Returns None when the witness is the same on every day of the run. It separates nothing
    then: every PFT that happens to be present on all of those days scores 1.0, which is
    exactly what happens in FATES-SP, where cover is prescribed and nothing ever appears or
    disappears.
    """
    if present_site.all() or not present_site.any():
        return None
    return np.mean(present_pft == present_site[:, None], axis=0)


def validate_pft_moss(data, moss, npft, params):
    """Abort unless --pft-moss really names the moss PFT.

    Returns (lines describing what was looked at, whether the index was actually confirmed).

    A wrong-but-in-range index is the failure mode this exists for. Nothing downstream
    notices one: every check indexes the array it was handed, and the run prints a full set
    of confident PASSes about whichever PFT was named.

    Two handles on which index is moss, neither of them the index passed in:

      * fates_vascular on the run's own FATES parameter file. FATES decides what is moss
        from prt_params%vascular (main/FatesHistoryInterfaceMod.F90:3069), so this is the
        model's own answer, and it is authoritative whenever the parameter file can be read.

      * cross-checks on the tape itself, for when it cannot. FATES_MOSS_HEIGHT accumulates
        over the cohorts whose PFT is non-vascular, so "moss is present today" is keyed off
        vascular rather than off the index passed in, and FATES_CROWNAREA_PF[moss] > 0 has
        to agree with it day for day. FATES_LEAFC_PF[moss] against FATES_LIVEMOSS_FUEL is a
        second one. Both go quiet when their witness never changes over the run, which is
        the FATES-SP case, and both go quiet when the given index is the best match on the
        tape but not a clean one; the parameter file is what covers either.

    Neither handle is guaranteed. An unreadable parameter file on a FATES-SP tape leaves
    both silent, and then the index is neither confirmed nor refuted -- which is a third
    outcome, not a pass, and the caller has to be able to tell it from one.

    Returns (lines, confirmed, why the witnesses went quiet, warnings to raise once the
    reporter exists). The reasons are kept because the three ways a witness can go quiet
    want three different remedies; the banner is assembled from them.
    """
    lines = []
    reasons = []
    warnings = []
    confirmed = False
    vascular = params.get("fates_vascular")
    if vascular is not None and len(vascular) == npft:
        nonvascular = [i + 1 for i, v in enumerate(vascular) if int(v) == 0]
        if moss + 1 not in nonvascular:
            raise HistoryContentError(
                f"--pft-moss {moss + 1} is not the moss PFT. fates_vascular on this run's "
                "FATES parameter file marks "
                + (
                    "PFT " + ", ".join(str(i) for i in nonvascular) + " non-vascular"
                    if nonvascular
                    else "no PFT at all as non-vascular"
                )
                + ", and non-vascular is what FATES itself keys the moss code off"
                + (
                    f". Re-run with --pft-moss {nonvascular[0]}."
                    if len(nonvascular) == 1
                    else ". Re-run with --pft-moss set to one of those."
                    if nonvascular
                    else ". This does not look like a moss run."
                )
            )
        confirmed = True
        lines.append(
            f"--pft-moss {moss + 1} confirmed non-vascular by fates_vascular on this run's "
            f"FATES parameter file"
            + (f" (non-vascular PFTs: {nonvascular})" if len(nonvascular) > 1 else "")
        )
    else:
        lines.append(
            "fates_vascular could not be read from this run's FATES parameter file; "
            "falling back to the tape cross-checks below"
        )

    witnesses = (
        (
            "FATES_CROWNAREA_PF > 0 vs FATES_MOSS_HEIGHT > 0",
            "FATES_CROWNAREA_PF",
            "FATES_MOSS_HEIGHT",
        ),
        (
            "FATES_LEAFC_PF > 0 vs FATES_LIVEMOSS_FUEL > 0",
            "FATES_LEAFC_PF",
            "FATES_LIVEMOSS_FUEL",
        ),
    )
    for label, pft_name, site_name in witnesses:
        if absent(data, pft_name, site_name):
            gone = ", ".join(absent(data, pft_name, site_name))
            lines.append(f"{label}: {gone} not on this tape, so this witness was not run")
            reasons.append("absent")
            continue
        agreement = witness_agreement(data[pft_name] > 0, data[site_name] > 0)
        if agreement is None:
            lines.append(
                f"{label}: witness never changes over the run, so it separates nothing here"
            )
            reasons.append("static")
            continue
        best = int(np.argmax(agreement)) + 1
        leader = float(np.max(agreement))
        got = float(agreement[moss])
        if leader - got > WITNESS_LEAD:
            # A better-agreeing PFT refutes an index the parameter file has NOT settled. It
            # does not refute one the parameter file HAS settled: fates_vascular is what
            # FATES itself keys the moss code off, and a tape witness that disagrees with it
            # is a fact about the witness -- moss blinking in and out, a PFT-level and a
            # site-level variable disagreeing by a day at each transition -- not evidence
            # against the model's own answer. Aborting there would throw away a verdict on
            # the strength of the weaker of two pieces of evidence.
            disagreement = (
                f"{label} agrees on {100 * got:.1f}% of days at PFT {moss + 1}, against "
                f"{100 * leader:.1f}% at PFT {best}."
            )
            if confirmed:
                warnings.append(
                    (
                        "A tape witness disagrees with the moss index the parameter file "
                        "confirmed",
                        f"{disagreement}\n"
                        f"fates_vascular on this run's FATES parameter file says PFT "
                        f"{moss + 1} is the non-vascular one, and that is what FATES keys "
                        "the moss code off, so the index stands and every moss-keyed number "
                        "below is about moss.\n"
                        "What the disagreement means instead is that this witness is not "
                        "clean on this run -- a PFT-level and a site-level variable "
                        "disagreeing by a day at each appearance and disappearance will do "
                        f"it, and so will PFT {best} tracking moss's presence more closely "
                        "than moss's own per-PFT variable does. Worth a look if the "
                        "moss-keyed numbers below look like some other PFT's.",
                    )
                )
                lines.append(f"{disagreement} See the WARN below.")
                continue
            raise HistoryContentError(
                f"--pft-moss {moss + 1} does not look like the moss PFT. {disagreement} The "
                "site-level witness is keyed off the model's own notion of which PFT is "
                "moss, not off the index passed in, so it is independent evidence that this "
                "index is wrong, and nothing on this run's parameter file says otherwise."
            )
        behind = (
            f", behind PFT {best} at {100 * leader:.1f}% but by less than the "
            f"{100 * WITNESS_LEAD:.0f} points that would refute it"
            if leader > got
            else ""
        )
        if got < WITNESS_MIN:
            # Best of any index, but noisy. Not a refutation, so not an abort: see the
            # WITNESS_MIN comment for the blinking-moss run this would otherwise kill.
            lines.append(
                f"{label}: agrees on {100 * got:.1f}% of days at PFT {moss + 1}{behind}, "
                f"below the {100 * WITNESS_MIN:.0f}% needed to call the index confirmed, so "
                "this witness neither confirms nor refutes it"
            )
            reasons.append("noisy")
            continue
        confirmed = True
        lines.append(
            f"{label}: agrees on {100 * got:.1f}% of days at PFT {moss + 1}{behind}"
        )
    return lines, confirmed, reasons, warnings


def validate_pft_grass(pft_names, params, grass, npft):
    """Whatever the run's parameter file can say about --pft-grass, and whether it said it.

    Nothing keys off the grass index the way the moss code keys off vascular, so there is no
    tape witness for it and no equivalent of the moss abort. What there is is the parameter
    file's own naming and its two flags, and that is enough to catch the failure mode that
    matters here: the default of 12 is a property of the surface datasets these testmods use,
    and on any other configuration it silently relabels some other PFT's GPP and cover as
    grass.

    Returns (line for the preamble, whether the index was confirmed).
    """
    if pft_names is not None and 0 <= grass < len(pft_names):
        name = pft_names[grass]
        if "grass" in name.lower():
            return (
                f"--pft-grass {grass + 1} confirmed by fates_pftname on this run's FATES "
                f"parameter file: '{name}'",
                True,
            )
        return (
            f"--pft-grass {grass + 1} is '{name}' on this run's FATES parameter file, which "
            "is not a grass",
            False,
        )
    woody = params.get("fates_woody")
    vascular = params.get("fates_vascular")
    if woody is not None and vascular is not None and len(woody) == npft == len(vascular):
        herbaceous = int(woody[grass]) == 0 and int(vascular[grass]) == 1
        return (
            f"--pft-grass {grass + 1} is "
            + ("non-woody and vascular" if herbaceous else "NOT non-woody and vascular")
            + " on this run's FATES parameter file, which is as far as fates_woody and "
            "fates_vascular can settle it; fates_pftname could not be read",
            herbaceous,
        )
    return (
        f"--pft-grass {grass + 1} is unconfirmed: neither fates_pftname nor fates_woody "
        "could be read from this run's FATES parameter file",
        False,
    )


# ---------------------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------------------
#
# The checks are grouped by the concept they test rather than by the plan task that asked
# for them, and each group opens with a note saying what that concept is. The reader this
# is written for is fluent in land-surface science and has never seen this branch, so a
# label like "Task 12 Step 3b" is an index into a document they do not have; it survives
# only as a trailing parenthetical, for whoever does have it.

SECTIONS = (
    (
        "THE WETNESS PROXY -- WHAT MOSS FEELS",
        """Moss in this design carries no water store of its own, so a diagnostic quantity
stands in for how wet the moss mat is: the wetter of the top soil layer's saturation and
the canopy's wetted fraction. It comes in two versions that differ only in the soil
water counted. FATES_MOSS_FWET_LIQ counts liquid water, so a frozen top layer reads dry;
FATES_MOSS_FWET_TOT counts liquid plus ice. Photosynthetic capacity and leaf
respiration read the liquid one, while the CO2 water film and both moss fuel classes'
moisture read the total one, so a proxy built wrong makes the moss numbers below wrong
with it. The checks here ask only whether each is the quantity
it claims to be: the larger of its two ingredients on every day of the run, and never
smaller than either.""",
    ),
    (
        "MOSS PHOTOSYNTHETIC RESPONSE TO WETNESS",
        """Moss photosynthesis is throttled by wetness through a single scaler on
photosynthetic capacity, which rises linearly with the liquid proxy up to a threshold and is
flat at full capacity above it. That threshold is the knob deciding how wet moss has to
be before it works at all, so a scaler keyed off the wrong quantity, or off the right
one with the wrong threshold, would put moss's productive window in the wrong place
without anything else looking amiss. The checks pin the map, and then report where in
it this run actually sat and what moss produced there.""",
    ),
    (
        "MOSS FUEL LOADING",
        """SPITFIRE sorts surface fuel into classes, and this branch adds two: live moss, fed
by the standing moss mat, and dead moss, fed by the moss litter (duff) pool. Each has
to carry the pool it is drawn from and only that pool. Before this branch every
non-woody cohort's biomass went into one accumulator feeding the live-grass class, so
what the split has to achieve is that moss biomass MOVES into the new classes rather
than being counted in both; that this run cannot check, and the docstring says why.
Two bookkeeping offsets separate a fuel class from its pool and both
are structural rather than approximate: fuel loading is reported with mineral content
removed while the pools are not, and the dead class is read a day before the litter pool
is advanced.""",
    ),
    (
        "MOSS FUEL MOISTURE AND FLAMMABILITY",
        """Every fuel class in SPITFIRE has a MOISTURE OF EXTINCTION, abbreviated MEF below:
the moisture content above which fuel of that kind is too damp to carry fire at all.
FATES derives each class's MEF from that class's surface-area-to-volume ratio, a
parameter-file quantity, and then reports the class's moisture ALREADY DIVIDED BY it.
So FATES_FUEL_MOISTURE_FC is dimensionless, and a value at or above 1 means that class
cannot burn. Calling it "effective moisture" below is a reminder that it is a ratio and
not a water content.

Where a class's moisture comes from is what this branch changes. Every other class takes
it from fire weather, through the Nesterov index, which climbs as the air stays warm and
dry and is reset by rain. The two moss classes instead take it from a wetness proxy of
section 1 (the total-water one), through a straight line --
max(0, intercept + slope * fwet) -- whose intercept and slope this run sets in its
namelist, because a moss mat is wet when the GROUND is wet rather than when the air has
lately been dry.

That division by MEF is why the checks below do not compare against the configured slope
directly. If FATES applied the line correctly, the moisture reported for a moss class is
the line divided by that class's MEF, so a straight-line fit through the run should
recover slope/MEF and not slope. The MEF used to form that expectation is rebuilt here
from the run's own parameter file rather than taken from the fit, so the two sides are
independent. The checks ask whether each moss class really follows that line and nothing
else, whether the non-moss classes still follow fire weather, and how much of the run
moss spends too wet to burn.""",
    ),
    (
        "MOSS SIZE, STRUCTURE AND SURVIVAL",
        """The last group is about the moss cohort itself: how much leaf and stem area it
carries, how tall it stands, how much of the ground it was given it actually covers, and
whether it lasts the run. Almost none of it is an identity -- one tape holds nothing to
check a diagnosed height against -- so these are numbers reported for judgement, to be
read against the allometry parameters the run was given. Persistence is the exception:
moss that is handed a patch and reaches zero biomass in it, or never carries any, is a
finding about the model configuration rather than about the diagnostics, and it is
reported as a failure so that it cannot be scrolled past.""",
    ),
)


def print_section(number, extra=None):
    """Open a section, so its boundary is visible rather than inferred from the labels.

    The explainers are hand-wrapped in SECTIONS; `extra` is assembled at runtime and is
    wrapped here, so that a paragraph carrying this run's numbers does not arrive as one
    300-character line in the middle of prose that is not.
    """
    title, explainer = SECTIONS[number - 1]
    print("=" * 79)
    print(f"SECTION {number} OF {len(SECTIONS)}.  {title}")
    print("=" * 79)
    print(explainer)
    if extra:
        print()
        for paragraph in extra.splitlines():
            print(textwrap.fill(paragraph, 79))
    print()


# ---------------------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------------------


def commutation_watch(data, veg_frac, leaf_cap, leaf_cap_source):
    """How safe the max()/min() commutation preconditions of Tasks 8 and 10 are here.

    Both identities need every vegetated patch to take the same branch, and a site-level
    tape has already summed the patches away, so neither can be tested directly. One
    quantity decides both, and it can be watched. Each proxy is max(soil saturation, canopy
    wetted fraction) per patch (FatesPatchMod.F90:UpdateMossFwetLiq, UpdateMossFwetTot). The
    soil ingredient comes from the column -- bc_in%h2o_liqvol_sl(1) or h2o_totvol_sl(1), and
    the column's porosity -- so it is the same number on every patch of the site. The
    canopy ingredient is CTSM's per-patch fwet_veg, which CTSM caps at
    maximum_leaf_wetted_fraction. While the soil ingredient stays above that cap, the soil
    ingredient wins on every patch, the proxy is identical on every patch, and both
    branches are uniform whatever the threshold is. That is what makes the identities
    safe, and losing it is what would make them fail for a reason that is not a model
    defect. The two proxies share the canopy ingredient and differ only in the soil one, so
    the watch takes the lower of the two soil ingredients on each day: a margin that holds
    for it holds for both proxies.

    The margin is reported in PATCH units, since that is where the cap lives, and the site
    value is the patch value times the non-bareground area fraction. Without that fraction
    the site-level soil value is used instead: it is the patch value times a fraction no
    greater than 1, so it understates the true clearance and the watch stays conservative.

    Returns (the paragraph to print once at the head of section 1, the one line each check
    that rests on the precondition carries, the warning or None). It used to return only the
    paragraph, which then printed in full under three separate checks across two sections;
    a reader met the same nine lines three times and had no way to tell that it was the same
    statement rather than three related ones.
    """
    soil = np.fmin(data["FATES_MOSS_FWET_SOIL_LIQ"], data["FATES_MOSS_FWET_SOIL_TOT"])
    canopy = data["FATES_MOSS_FWET_CANOPY"]

    if veg_frac is None:
        floor = float(np.nanmin(soil))
        floor_units = (
            "site units, a lower bound on the moss-native value, because the "
            "non-bareground area fraction is not on this tape"
        )
        observed_ceiling = float(np.nanmax(canopy))
    else:
        floor = float(np.nanmin(divide_by_fraction(soil, veg_frac)))
        floor_units = "moss-native"
        observed_ceiling = float(np.nanmax(divide_by_fraction(canopy, veg_frac)))

    # The comparison carries a tolerance because the observed ceiling has been through a
    # division by the area fraction, and a canopy ingredient sitting exactly on the cap all
    # run comes back a few ulps above it.
    if leaf_cap is not None and observed_ceiling <= float(leaf_cap) * (1.0 + TOL_RELATIVE):
        ceiling, ceiling_what = float(leaf_cap), (
            "its ceiling of "
            + named(leaf_cap, "maximum_leaf_wetted_fraction", leaf_cap_source)
            + ", which no patch's canopy ingredient can exceed"
        )
    elif leaf_cap is not None:
        # The cap is only a bound while it describes the run. A canopy ingredient reported
        # above it means it does not -- a different host, a changed parameter file, a
        # variable that is not what this script takes it for -- and the tape wins.
        ceiling, ceiling_what = observed_ceiling, (
            f"the largest canopy value this run reached, {observed_ceiling:.4f}, which is "
            "ABOVE "
            + named(leaf_cap, "maximum_leaf_wetted_fraction", leaf_cap_source)
            + ". That cap does not describe this tape, so it is not trusted as a bound here"
        )
    else:
        ceiling, ceiling_what = observed_ceiling, (
            f"the largest canopy value this run reached, {observed_ceiling:.4f}. CTSM's "
            "maximum_leaf_wetted_fraction could not be read, and an observed maximum of an "
            "area-weighted mean is a LOWER bound on what a single patch reached, so this "
            "margin is optimistic"
        )

    # A ceiling of zero is the strongest case rather than a degenerate one: a canopy
    # ingredient that is zero all run cannot win on any patch whatever the soil does.
    clear = ceiling <= 0.0 or floor > COMMUTATION_MARGIN_FACTOR * ceiling
    ratio = floor / ceiling if ceiling > 0 else np.inf
    margin = (
        "The canopy ingredient never leaves zero, so"
        if ceiling <= 0.0
        else f"That is a factor of {ratio:.1f}, so"
    )
    preamble = (
        "PRECONDITION shared by the identities in this section and the next (it is a "
        "condition ON them, not an observation about this run): each pushes an area weight "
        "through a max() or a min(), which is valid only while every vegetated patch takes "
        "the same branch -- the same ingredient wins on all of them, or all of them sit on "
        "the same side of the threshold. A site-level tape has already summed the patches "
        "away and cannot test it. What it can watch is the one quantity that decides it. "
        "The soil ingredients come from the column and are the same on every patch of "
        "the site; the canopy ingredient is CTSM's per-patch fwet_veg, which the host caps. "
        "While the soil ingredients stay clear of that cap each proxy is identical on every "
        "vegetated patch and both branches are uniform by construction.\n"
        + (
            f"On this run: the lower of the liquid and total soil "
            f"ingredients never falls below {floor:.4f} "
            f"({floor_units}), against a canopy ingredient bounded by {ceiling_what}. "
            f"{margin} both soil ingredients win on every patch and each proxy is uniform "
            "across them."
            if clear
            else "On this run the margin that would make it safe has NARROWED -- see the "
            "WARN below."
        )
    )
    reference = (
        f"Rests on the branch-uniformity precondition stated at the head of section 1; on "
        f"this run the lower soil ingredient clears the canopy ceiling by a factor of "
        f"{ratio:.1f}."
        if clear
        else "Rests on the branch-uniformity precondition stated at the head of section 1, "
        "whose margin has narrowed on this run -- see the WARN."
    )
    if clear:
        return preamble, reference, None
    return preamble, reference, (
        f"The moss wetness proxies' soil ingredients no longer stay clear of their "
        f"canopy one in this run: the lower soil ingredient falls to {floor:.4f} "
        f"({floor_units}) while the "
        f"canopy ingredient is bounded only by {ceiling_what}. That is a ratio of "
        f"{ratio:.2f}.\n"
        "Two site-level identities are built on those never crossing on any single patch -- "
        "the proxies' max() in section 1 and the wetness scaler's min() in section 2, "
        "neither of which commutes with the area-weighted sum that puts these quantities on "
        "the tape. While the soil ingredients are clear of the canopy ceiling each proxy is "
        "the same number on every vegetated patch and both identities are safe by "
        "construction. That clearance is now inside the "
        f"factor of {COMMUTATION_MARGIN_FACTOR:g} this script asks for, so a day on which "
        "the branch differs between two patches of this site is no longer implausible.\n"
        "Nothing here says either identity DID break -- read their PASS/FAIL above. What it "
        "says is that a FAIL on either can no longer be assumed to be a model defect, and "
        "that a PASS is now a weaker statement than it looks."
    )


def check_proxy_identity(report, data, units, precondition, water, suffix):
    """One proxy is the wetter of its two ingredients, and never below either (Task 8).

    `water` names the proxy in the labels ("liquid-water", "total-water"); `suffix` picks
    its fields, FATES_MOSS_FWET_<suffix> and FATES_MOSS_FWET_SOIL_<suffix>.
    """
    fwet_name, soil_name = f"FATES_MOSS_FWET_{suffix}", f"FATES_MOSS_FWET_SOIL_{suffix}"
    fwet = data[fwet_name]
    soil = data[soil_name]
    canopy = data["FATES_MOSS_FWET_CANOPY"]

    deviation = float(np.nanmax(np.abs(fwet - np.maximum(soil, canopy))))
    ok = deviation < TOL_EXACT
    report(
        "PASS" if ok else "FAIL",
        f"Is the {water} moss wetness proxy the wetter of its two ingredients? (Task 8)",
        ("" if ok else DIVERGENCE_FIRST_SUSPECT + "\n")
        + f"identity: {fwet_name} == max({soil_name}, FATES_MOSS_FWET_CANOPY)\n"
        + f"max |deviation| = {deviation:.3e}\n"
        f"proxy  {units.spans(fwet, 'patch', site_units='')}\n"
        f"soil   {units.spans(soil, 'patch', site_units='')}\n"
        f"canopy {units.spans(canopy, 'patch', site_units='')}"
        + coverage_note(len(fwet), fwet, soil, canopy)
        + "\n"
        + precondition,
    )

    below = int(np.sum((fwet < soil - TOL_EXACT) | (fwet < canopy - TOL_EXACT)))
    report(
        "PASS" if below == 0 else "FAIL",
        f"Does the {water} proxy stay at or above both of its ingredients, every day? "
        "(Task 8)",
        f"days below one of its ingredients: {below} of {len(fwet)}\n"
        "Unlike the identity above this one is structural: a sum of max(a_p, b_p) weighted "
        "by non-negative areas is at least the same sum of a_p, and at least the same sum "
        "of b_p, whatever each patch does. A FAIL here would mean a corrupt tape."
        + coverage_note(len(fwet), fwet, soil, canopy),
    )


def check_task8_proxy(report, data, units, precondition, leaf_cap, leaf_cap_source):
    """Each proxy is the wetter of its two ingredients, and never below either (Task 8).

    The two proxies share the canopy ingredient and differ in the soil one: top-layer
    liquid saturation for FATES_MOSS_FWET_LIQ, liquid plus ice for FATES_MOSS_FWET_TOT.
    Both identities are checked. The report on the canopy ingredient that follows is about
    the liquid proxy, the one the wetness scaler reads; the CO2 water film and fuel moisture
    read the total one.
    """
    for water, suffix in (("liquid-water", "LIQ"), ("total-water", "TOT")):
        check_proxy_identity(report, data, units, precondition, water, suffix)

    fwet = data["FATES_MOSS_FWET_LIQ"]
    soil = data["FATES_MOSS_FWET_SOIL_LIQ"]
    canopy = data["FATES_MOSS_FWET_CANOPY"]

    canopy_binds = int(np.sum(canopy > soil))
    canopy_max = float(np.nanmax(canopy))
    at_max = int(np.sum(np.isclose(canopy, canopy_max)))
    native_canopy_max = float(np.nanmax(units.native(canopy, "patch"))) if units.has(
        "patch"
    ) else canopy_max
    # Whether the canopy ingredient is sitting on its structural ceiling or merely at the
    # largest value this run happened to reach is the difference between "the design pins
    # it here" and "the weather put it here", and it is not something a reader should have
    # to work out by comparing two decimals several lines apart.
    at_ceiling = leaf_cap is not None and native_canopy_max >= float(leaf_cap) * (
        1.0 - TOL_RELATIVE
    )
    lines = [
        f"canopy sets the liquid proxy (canopy > liquid soil) on {canopy_binds} of "
        f"{len(fwet)} days",
        f"canopy is nonzero on {100 * np.mean(canopy > 0):.0f}% of days and "
        + (
            "reaches its ceiling of "
            + named(leaf_cap, "maximum_leaf_wetted_fraction", leaf_cap_source)
            if at_ceiling
            else f"tops out at {native_canopy_max:.4f}"
            + (
                ", short of its ceiling of "
                + named(leaf_cap, "maximum_leaf_wetted_fraction", leaf_cap_source)
                if leaf_cap is not None
                else ""
            )
        )
        + f" on {at_max} of {len(fwet)} days",
    ]
    canopy_spike, soil_spike = spikiness(canopy), spikiness(soil)
    lines.append(
        "largest daily change / mean daily change (1.0 = perfectly steady, high = "
        f"event-driven): canopy {canopy_spike:.1f}, liquid soil {soil_spike:.1f}"
        if np.isfinite(canopy_spike) and np.isfinite(soil_spike)
        else "largest daily change / mean daily change: not defined on this tape -- "
        "there are no day-to-day steps to take a ratio of"
    )

    # The verification plan asks for a correlation between the canopy ingredient and rain
    # events. Whether that is worth computing is a question about THIS run, not about the
    # model: it turns on whether the canopy ingredient ever wins, which turns on where
    # CTSM's maximum_leaf_wetted_fraction sits relative to this site's soil saturation. That
    # parameter is a global scalar on the host parameter file and a tuning candidate on this
    # branch, so the conclusion is stated against the value the run actually used.
    cap_phrase = (
        named(leaf_cap, "maximum_leaf_wetted_fraction", leaf_cap_source)
        if leaf_cap is not None
        else "CTSM's maximum_leaf_wetted_fraction, which could not be read from this run"
    )
    native_soil = span(units.native(soil, "patch"), "{:.4f}") if units.has(
        "patch"
    ) else span(soil, "{:.4f}") + " in site units"
    if canopy_binds == 0:
        # Whether RAIN is on the tape is a fact about this tape, so it is read off the tape
        # rather than asserted from what a FATES-SP field list usually carries.
        rain_note = (
            "Nothing is blocking the correlation itself -- RAIN is on this tape."
            if "RAIN" in data
            else "RAIN is not on this tape either, so the correlation could not have been "
            "computed here in any case; put RAIN in hist_fincl1 if that ceiling is ever "
            "raised."
        )
        # The ceiling is named before the note that points at it. It used to be the other
        # way round, with the note saying "the ceiling below" and the ceiling arriving a
        # sentence later -- a pointer that only worked while the two sat in a fixed order.
        lines.append(
            f"AGAINST RAIN (Task 8 Step 4): the canopy ingredient tops out at "
            f"{native_canopy_max:.4f} against a liquid soil ingredient spanning {native_soil}, "
            "so it never sets the liquid proxy in this run and a correlation between it and "
            "rain would say nothing about that proxy here. What makes it pointless is the "
            f"ceiling, {cap_phrase}: raise that above this site's soil saturation floor and "
            "the limitation dissolves, so this is a statement about the run in front of you "
            f"and not one about the design. {rain_note}"
        )
    else:
        rain = (
            f" corr(RAIN, canopy ingredient) = {correlation(data['RAIN'], canopy):+.3f}."
            if "RAIN" in data
            else " RAIN is not on this tape, so it is not computed here."
        )
        lines.append(
            f"AGAINST RAIN (Task 8 Step 4): the canopy ingredient DOES set "
            "the liquid proxy, on "
            f"{canopy_binds} of {len(fwet)} days, so unlike a run in which it is pinned "
            f"below the liquid soil ingredient by {cap_phrase}, a rain-event correlation is "
            "meaningful on this tape and worth computing." + rain
        )
    report(
        "INFO",
        "Is the canopy ingredient event-driven, and does it ever matter? (Task 8)",
        "\n".join(lines) + coverage_note(len(fwet), fwet, soil, canopy),
    )

    # An ingredient that never wins is exactly the class of thing the WARN channel exists
    # for: a path this run never exercised, which no PASS above can carry, and which is a
    # property of the run rather than of the design. Raised after the INFO so the numbers it
    # refers to are already on the screen. Its headline stays declarative: a warning exists
    # to state something that must not be scrolled past, and a question form buries it.
    if canopy_binds == 0:
        report.warn(
            "The canopy ingredient never sets the liquid moss wetness proxy in this run",
            f"FATES_MOSS_FWET_CANOPY tops out at {native_canopy_max:.4f} while "
            f"FATES_MOSS_FWET_SOIL_LIQ spans {native_soil}, so on all "
            f"{len(fwet)} days of this run the liquid proxy is its soil ingredient and "
            "nothing else.\n"
            "The liquid-water identity above therefore PASSes on max(a, b) == a: the canopy "
            "branch of UpdateMossFwetLiq was never taken, and neither the canopy "
            "ingredient's own arithmetic nor its effect on anything downstream of the proxy "
            "-- the wetness scaler in section 2, moss GPP -- is under test here at all. A "
            "correlation between the canopy ingredient and rain events, which the plan also "
            "asks for (Task 8 Step 4), is untestable for the same reason: an ingredient that "
            "never sets the proxy cannot be shown to drive it.\n"
            f"The ceiling that does it is {cap_phrase}. That is a property of THIS run: "
            "raise it above this site's soil saturation floor, or run a drier site, and the "
            "canopy branch starts being exercised with nothing else changed.",
        )


SCALER_BELOW = (
    "Below the threshold, is the wetness scaler the liquid proxy over the threshold? "
    "(Task 10)"
)
SCALER_ABOVE = "Above the threshold, does the wetness scaler sit at exactly 1? (Task 10)"


def check_task10_scaler(
    report, data, units, threshold, threshold_source, precondition, no_veg_frac_reason
):
    """The wetness scaler is the configured wetness map, in its two halves (Task 10).

    The area weighting is the whole subtlety here. Per patch the scaler is
    min(1, fwet_patch/threshold), where fwet is the liquid proxy, FATES_MOSS_FWET_LIQ.
    Both the scaler and the proxy reach history as sums of patch values weighted by patch
    area, with bareground contributing zero to each, so each site value is its patch value
    times `veg_frac`, the non-bareground area fraction. Pushing that weight through the min
    gives

        scaler_site = veg_frac * min(1, (fwet_site/veg_frac)/threshold)
                    = min(veg_frac, fwet_site/threshold)

    which is two different statements on the two sides of the kink, and they are checked
    apart because they need different things:

      * BELOW the plateau the min picks the second branch and the area weight cancels
        identically -- veg_frac*(fwet_site/veg_frac)/threshold is fwet_site/threshold,
        whether or not veg_frac varies from day to day. This half needs no area fraction at
        all, and it is the half that pins the THRESHOLD, since the threshold is the only
        thing in it. It runs on every tape.

      * ON the plateau the scaler is veg_frac and nothing else, so this half pins the area
        weighting and nothing else. It is where the naive min(1, fwet_site/threshold) is
        wrong, by exactly the area fraction, and it is the half a tape without an area
        fraction loses.

    Which days are which is decided without using the quantity under test on that day. With
    veg_frac in hand the kink is at fwet_site = threshold*veg_frac exactly. Without it, the
    largest scaler the run reached is a lower bound on veg_frac -- the scaler is at most
    veg_frac every day -- so days whose fwet/threshold falls below that bound are certainly
    below the kink. That uses one number from the whole record rather than the day's own
    value, so it is not the identity selecting the days it is then tested on. A day the
    bound misclassifies is a day veg_frac dipped below its own run maximum, and the check
    FAILs and says so, which is the right answer for a run with time-varying cover.

    Pushing the area weight through the min() is valid only while every vegetated patch is
    on the same side of the threshold, since min() does not commute with an area-weighted
    sum. See commutation_watch for what decides that and what is watched in its place.
    """
    if absent(data, "FATES_MOSS_WETNESS_SCALER"):
        for label in (SCALER_BELOW, SCALER_ABOVE):
            report("SKIP", label, "FATES_MOSS_WETNESS_SCALER is not on this tape.")
        return

    veg_frac = units.divisor["patch"]
    scaler = data["FATES_MOSS_WETNESS_SCALER"]
    fwet = data["FATES_MOSS_FWET_LIQ"]
    nday = len(fwet)
    ratio = fwet / threshold
    threshold_named = named(
        threshold, "fates_moss_vcmax_fwet_thresh", threshold_source
    )

    if veg_frac is None:
        bound = float(np.nanmax(scaler)) if np.any(np.isfinite(scaler)) else 0.0
        if bound <= 0.0:
            # The lower bound on the area fraction is the largest scaler the run reached, so
            # a scaler that never leaves zero leaves no bound and no day that can be called
            # sub-plateau. That is a check that could not be made, not one that failed.
            for label in (SCALER_BELOW, SCALER_ABOVE):
                report(
                    "SKIP",
                    label,
                    f"FATES_MOSS_WETNESS_SCALER never rises above zero on any of the {nday} "
                    "days of this run, and the area fraction is not available to say where "
                    "the kink of the map should be, so neither half of the identity has a "
                    "day to be tested on.\n" + no_veg_frac_reason,
                )
            return
        bound_note = (
            "below-the-threshold days are the {n} on which the site-level proxy over the "
            f"threshold falls under {bound:.4f}, the largest scaler this run reached, which "
            "is a lower bound on the non-bareground area fraction (the scaler is at most "
            "that fraction every day). The area fraction itself is not on this tape, so "
            "moss-native numbers below fall back to site units"
        )
        sub = ratio < bound * (1.0 - TOL_RELATIVE)
    else:
        bound_note = (
            "below-the-threshold days are the {n} on which the moss-native proxy is under "
            + threshold_named
        )
        sub = ratio < veg_frac * (1.0 - TOL_RELATIVE)

    if not sub.any():
        report(
            "SKIP",
            SCALER_BELOW,
            "This run never leaves the flat top of the wetness map: the moss-native proxy "
            f"is at or above {threshold_named} on all {nday} days, so there is no day on "
            "which the rising branch of min(1, proxy/threshold) was taken and nothing "
            "here pins the threshold. A drier run would.",
        )
    else:
        deviation = relative_deviation(scaler[sub], ratio[sub])
        ok = deviation < TOL_RELATIVE
        report(
            "PASS" if ok else "FAIL",
            SCALER_BELOW,
            ("" if ok else DIVERGENCE_FIRST_SUSPECT + "\n")
            + "identity: scaler == FATES_MOSS_FWET_LIQ / threshold on the days below the "
            "threshold, where the area weighting cancels out of both sides and the site "
            "value and the moss-native value give the same test\n"
            f"with {threshold_named}\n"
            f"max relative deviation = {deviation:.3e} over {int(sub.sum())} of {nday} days\n"
            + bound_note.format(n=int(sub.sum()))
            + "\n"
            "This is the half that pins the threshold: it is the only quantity in it, and "
            "it holds whether or not the area fraction is known and whether or not it "
            "varies in time."
            + coverage_note(nday, fwet, scaler)
            + "\n"
            + precondition,
        )

    if veg_frac is None:
        report(
            "SKIP",
            SCALER_ABOVE,
            f"{no_veg_frac_reason}\n"
            "Moss-native, the claim is that the scaler saturates at exactly 1. On the tape "
            "that reads as the scaler being exactly the non-bareground area fraction, so "
            "this half is the area weighting and nothing else and there is no weaker "
            "version of it left to test. It is also the only place the naive unweighted "
            "min(1, fwet/threshold) differs: above the threshold it is wrong by exactly the "
            "missing factor, while below it agrees with the identity, which is why the half "
            "above still runs.",
        )
        return

    plateau = ratio > veg_frac * (1.0 + TOL_RELATIVE)
    naive = float(np.nanmax(np.abs(scaler - np.minimum(1.0, ratio))))
    if not plateau.any():
        report(
            "SKIP",
            SCALER_ABOVE,
            f"The moss-native proxy never reaches {threshold_named} on any of the {nday} "
            "days of this run, so the flat branch of the map was never taken and there is "
            "nothing here to test it on. A wetter run would.",
        )
        return
    deviation = relative_deviation(scaler[plateau], veg_frac[plateau])
    ok = deviation < TOL_RELATIVE
    report(
        "PASS" if ok else "FAIL",
        SCALER_ABOVE,
        ("" if ok else DIVERGENCE_FIRST_SUSPECT + "\n")
        + "identity: moss-native, the scaler saturates at exactly 1 on the "
        "days above the threshold, which on the site-level tape it was checked against "
        f"reads as scaler == the non-bareground area fraction, {np.mean(veg_frac):.4f}\n"
        f"max relative deviation = {deviation:.3e} over {int(plateau.sum())} of {nday} days "
        f"({100.0 * plateau.mean():.1f}% of the run)\n"
        f"scaler {units.spans(scaler, 'patch', site_units='')}\n"
        "for contrast, reading the tape's site values straight into the unweighted "
        f"min(1, fwet/threshold) form misses by {naive:.3e} -- that is the area weighting, "
        "and this half is where it shows"
        + coverage_note(nday, fwet, scaler, veg_frac)
        + "\n"
        + precondition,
    )


LIVE_MOSS_LOADING = "Does the live-moss fuel class carry the live moss biomass? (Task 6)"
def livemoss_divisor_note(data, units, livemoss, moss):
    """Whether this tape can rule out the wrong divisor for FATES_LIVEMOSS_FUEL, and say so.

    The class assignments elsewhere in this script are traced to the FATES source and taken
    on that authority. Two of them the tape can also falsify, and where it can, saying so
    turns an assumption into a check. This is the second: the moss fuel-moisture slope is
    the other.

    cpatch%livemoss is the leaf PLUS sapwood PLUS structural carbon of the patch's
    non-vascular cohorts (biogeochem/FatesPatchMod.F90:855-875), while FATES_LEAFC_PF at the
    moss index is the leaf carbon alone. Whatever divisor is right, live moss biomass cannot
    come out BELOW moss leaf carbon -- so if the two are given divisors that differ, and the
    ratio lands under 1, the assignment is refuted. It is the impossibility that settles it,
    not how close the ratio is to any particular number.

    Returns "" when the tape cannot discriminate: no leaf carbon on it, no moss ever, or a
    configuration in which the two candidate divisors are the same number and there is
    nothing to tell apart.
    """
    leafc = data.get("FATES_LEAFC_PF")
    veg, moss_area = units.divisor["patch"], units.divisor["moss"]
    if leafc is None or veg is None or moss_area is None:
        return ""
    ratio = float(np.mean(moss_area)) / float(np.mean(veg))
    if abs(ratio - 1.0) <= TOL_RELATIVE:
        # Full competition, or nocomp without a bareground patch: both divisors are the same
        # number, so there are not two assignments here to tell apart.
        return ""
    leaf = leafc[:, moss]
    both = (leaf > 0) & np.isfinite(livemoss) & np.isfinite(leaf)
    if not both.any():
        return ""
    with np.errstate(invalid="ignore", divide="ignore"):
        observed = livemoss[both] / leaf[both]
    if not np.any(np.isfinite(observed)):
        return ""
    return (
        "\nThat this variable takes the MOSS patch area as its divisor, and not the "
        "non-bareground area fraction, is a claim this tape can settle rather than one you "
        "have to take on trust: live moss biomass is leaf plus sapwood plus structural "
        "carbon, so it cannot fall below moss leaf carbon, and "
        f"against FATES_LEAFC_PF at the moss index it runs {span(observed, '{:.4f}')}. Had "
        "it been a vegetated-patch quantity while leaf carbon stayed a moss-patch one, the "
        f"same two columns would give {span(ratio * observed, '{:.4f}')} -- live moss "
        "biomass below its own leaf carbon, which is impossible. The impossibility settles "
        "it; the closeness of the first number to 1 does not. (The two are read a day apart "
        "in the daily sequence, so the ratio carries a fraction of a percent of drift that "
        "is not tissue.)"
    )


def check_task6_livemoss(
    report, data, units, moss, fuel_amount, miner_total, miner_source
):
    """The live-moss fuel class carries the live-moss biomass (Task 6).

    The two variables report the same biomass under different conventions, and the factor
    below is the relationship between them.

    FATES_FUEL_AMOUNT_FC is mineral-free. fire/SFMainMod.F90:315, inside
    CalculateSurfaceRateOfSpread, does

        currentPatch%fuel%non_trunk_loading = &
             currentPatch%fuel%non_trunk_loading*(1.0_r8 - SF_val_miner_total)

    in place on the persistent patch fuel object, after fire/FatesFuelMod.F90:194-220
    normalized `frac_loading` against the *undamped* total, and
    main/FatesHistoryInterfaceMod.F90:4300 then reconstructs the per-class loading as
    `frac_loading(i) * non_trunk_loading`. The two normalizations compose to exactly
    (1 - SF_val_miner_total) * loading(i) for every class of FATES_FUEL_AMOUNT_FC that
    carries loading at all, and for FATES_FUEL_AMOUNT itself. Trunks are outside that
    statement: `frac_loading` is forced to zero for them (fire/FatesFuelMod.F90:212), so
    their column is identically zero and no convention applies to it. Nothing compounds
    across days: UpdateFuelCharacteristics rebuilds the loading from the patch state each
    day. FATES_LIVEMOSS_FUEL is written straight from `cpatch%livemoss` (:2782), with
    mineral content still in it, so the two differ by the constant factor
    1/(1 - fates_fire_miner_total), which the check prints from the run's own value.
    """
    live_moss = fuel_amount[:, FUEL_CLASSES["live_moss"] - 1]
    reference = data["FATES_LIVEMOSS_FUEL"]
    damping = 1.0 - miner_total
    deviation = relative_deviation(live_moss, damping * reference)

    # relative_deviation reports 0 when both sides are identically zero, which is a real
    # possibility here -- a run in which moss never exists -- and would otherwise print a
    # PASS for an identity that was never exercised.
    nonzero = float(np.nanmax(np.abs(reference))) > 0

    report(
        "PASS" if deviation < TOL_RELATIVE and nonzero else "FAIL",
        LIVE_MOSS_LOADING,
        f"identity: FATES_FUEL_AMOUNT_FC[live_moss] == "
        f"(1 - fates_fire_miner_total) * FATES_LIVEMOSS_FUEL\n"
        f"          = {damping:.6f} * FATES_LIVEMOSS_FUEL, with "
        + named(miner_total, "fates_fire_miner_total", miner_source)
        + f"\nmax relative deviation = {deviation:.3e}\n"
        f"FATES_LIVEMOSS_FUEL {units.spans(reference, 'moss', '{:.4e}', 'kg m-2 land')}"
        f"\n                    nonzero on {int(np.sum(reference > 0))} of "
        f"{len(reference)} days\n"
        + (
            ""
            if nonzero
            else "FAIL because FATES_LIVEMOSS_FUEL is identically zero: there was no moss "
            "biomass in this run for the identity to be tested on, so a small deviation "
            "would mean nothing.\n"
        )
        + "The factor is the mineral-content convention: FATES_FUEL_AMOUNT_FC is "
        "mineral-free (SFMainMod.F90:315), FATES_LIVEMOSS_FUEL is not, and no long name "
        "says which is which."
        + livemoss_divisor_note(data, units, reference, moss)
        + coverage_note(len(reference), reference, live_moss),
    )


def check_mossfines_sentinel(report, data):
    """Report the FATES-SP unset-litter sentinel if FATES_MOSS_FINES is carrying it.

    This runs whether or not the fuel checks run, because it is a property of the
    diagnostic rather than of the fire model, and it is easy to mistake for a real number.
    Returns True when the sentinel is present, meaning there is no litter state to test.
    """
    if "FATES_MOSS_FINES" not in data:
        return False
    fines = data["FATES_MOSS_FINES"]
    n_unset = int(np.sum(is_unset(fines)))
    if n_unset == 0:
        return False
    report(
        "INFO",
        "Is FATES_MOSS_FINES a litter pool here, or the FATES-SP unset sentinel? (Task 7)",
        f"FATES_MOSS_FINES is {np.nanmax(fines):.4e} kg m-2 on {n_unset} of {len(fines)} "
        "days, which is ndcmpy x fates_unset_r8 (3 x -1e36) showing through rather than a "
        "physical value. It is left in site units deliberately: a sentinel is not a "
        "quantity, and dividing it by an area fraction would dress it up as one.\n"
        "Under FATES-SP, EDInitMod.F90:863-868 initializes the litter and seed pools to "
        "fates_unset_r8 rather than to zero, so this is the same convention "
        "FATES_SEEDLING_POOL and FATES_UNGERM_SEED_BANK already follow on an SP tape -- "
        "not moss-specific, and not a netCDF fill value. There is no litter state in SP "
        "mode for the dead-moss checks below to test.",
    )
    return True


DEAD_MOSS_LOADING = "Does the dead-moss fuel class carry the moss litter pool? (Task 7)"
DEAD_MOSS_ACCUMULATES = "Does the moss litter pool accumulate over the run? (Task 7)"


def check_task7_mossfines(report, data, units, fuel_amount, miner_total, miner_source):
    """The dead-moss fuel class carries the dead-moss litter, one day stale (Task 7).

    Two offsets between the two variables, both structural:

      * the same mineral-content convention as the live-moss class: FATES_FUEL_AMOUNT_FC is
        mineral-free, FATES_MOSS_FINES is not (see check_task6_livemoss)

      * a one-day lag. EDMainMod.F90 calls DailyFireModel (:249) -- which is where
        UpdateFuelCharacteristics reads `sum(litter%moss_fines(:))` into the fuel object
        (SFMainMod.F90:172-174) -- before ed_integrate_state_variables (:257), which is
        where PreDisturbanceIntegrateLitter advances `litt%moss_fines` by the day's input
        and fragmentation (EDPhysiologyMod.F90:589-591). History is written after both, so
        the fuel class holds yesterday's litter and FATES_MOSS_FINES holds today's. The
        live-moss class has no such lag because `cpatch%livemoss` is computed inside
        UpdateFuelCharacteristics itself and is not touched again that day.
    """
    dead_moss = fuel_amount[:, FUEL_CLASSES["dead_moss"] - 1]
    fines = data["FATES_MOSS_FINES"]
    nday = len(fines)

    damping = 1.0 - miner_total
    lagged = fines[:-1]
    deviation = relative_deviation(dead_moss[1:], damping * lagged)

    # The same guard the live-moss check carries, for the same reason: relative_deviation
    # reports 0 when both sides are identically zero, so an all-zero litter state would
    # otherwise print a PASS for an identity that was never exercised on a single day.
    nonzero = lagged.size > 0 and float(np.nanmax(np.abs(lagged))) > 0

    if nday < 2:
        # A comparison between a day and the day before it needs two days. Nothing failed
        # here; there was nothing to compare.
        report(
            "SKIP",
            DEAD_MOSS_LOADING,
            f"this tape holds {nday} day, and the identity compares "
            "FATES_FUEL_AMOUNT_FC[dead_moss] on one day against FATES_MOSS_FINES on the "
            "day before it. Two days of output would be enough.",
        )
    else:
        report(
            "PASS" if deviation < TOL_RELATIVE and nonzero else "FAIL",
            DEAD_MOSS_LOADING,
            f"identity: FATES_FUEL_AMOUNT_FC[dead_moss](t) == {damping:.6f} * "
            f"FATES_MOSS_FINES(t-1), with "
            + named(miner_total, "fates_fire_miner_total", miner_source)
            + f"\nmax relative deviation = {deviation:.3e}\n"
            f"FATES_MOSS_FINES {units.spans(fines, 'moss', '{:.4e}', 'kg m-2 land')}"
            f"\n                 nonzero on {int(np.sum(fines > 0))} of {nday} days\n"
            + (
                ""
                if nonzero
                else "FAIL because FATES_MOSS_FINES is identically zero over the days this "
                "identity compares: there was no dead-moss litter in this run for it to be "
                "tested on, so a small deviation would mean nothing.\n"
            )
            + "The one-day lag is the daily call order: the fire model reads the litter pool "
            "(SFMainMod.F90:172-174) before PreDisturbanceIntegrateLitter advances it "
            "(EDPhysiologyMod.F90:589-591), and history is written after both."
            + coverage_note(nday, fines, dead_moss),
        )

    if nday < 2:
        report(
            "SKIP",
            DEAD_MOSS_ACCUMULATES,
            f"this tape holds {nday} day, so there is no first half and second half to "
            "compare and no trend over the run to read.",
        )
        return
    half = nday // 2
    first, second = np.nanmean(fines[:half]), np.nanmean(fines[half:])
    grew = np.nanmax(fines) > 0 and second > first
    report(
        "PASS" if grew else "FAIL",
        DEAD_MOSS_ACCUMULATES,
        f"first-half mean {units.value(first, 'moss', '{:.4e}')}, second-half mean "
        f"{units.value(second, 'moss', '{:.4e}')}\n"
        f"day 1 {units.value(fines[0], 'moss', '{:.4e}')} -> day {nday} "
        f"{units.value(fines[-1], 'moss', '{:.4e}')}, peak "
        f"{units.value(float(np.nanmax(fines)), 'moss', '{:.4e}')}\n"
        f"on the tape, {span(fines, '{:.4e}')} kg m-2 land"
        + coverage_note(nday, fines),
    )


def moisture_of_extinction(sav):
    """MEF from a surface-area-to-volume ratio: MoistureOfExtinction, FatesFuelMod:367-374.

    Reproduced here for one reason only: without an MEF that comes from somewhere other
    than the fit, the Task 9 slope is unconstrained. See the check below.
    """
    return MEF_A - MEF_B * np.log(sav)


def warn_sav_degeneracy(report, sav, sav_source, task9_ran):
    """Warn if this run's fates_fire_SAV cannot tell a moss fuel class from a NON-moss one.

    The Task 9 slope is checked against a moisture of extinction rebuilt from
    fates_fire_SAV at the moss class's own index. That is only evidence that FATES reached
    for a moss entry if the moss entry holds a number no non-moss class holds: where classes
    share an SAV they share an MEF, and a model that had reached past moss altogether would
    fit the slope exactly as well.

    The two moss classes sharing an SAV with each other is a different question -- it says
    nothing about whether moss was indexed, only about whether live and dead moss can be
    told apart -- so live_moss and dead_moss are excluded from each other's twin list here
    and warn_live_dead_degeneracy covers that on its own.

    Nothing about this is a property of this script. It is a property of the parameter file
    in front of it, and it ends the day the moss classes are given an SAV no other class
    shares -- at which point the same slope check silently starts discriminating, with
    nothing new to say and nothing to warn about.
    """
    if sav is None:
        report.warn(
            "Whether the moisture of extinction separates moss from the other fuel classes "
            "could not be examined (Task 9)",
            "fates_fire_SAV could not be read from this run's FATES parameter file, so the "
            "moss classes' surface-area-to-volume ratios were never compared against the "
            "other classes'.\n"
            "Where the moss classes share an SAV with a non-moss class they share a moisture "
            "of extinction, and the moss moisture-slope check then cannot tell that FATES "
            "reached for a moss entry rather than that class's. Whether this run is in that "
            "position is unknown here, not ruled out. It is settled by giving this script a "
            "readable fates_paramfile, and nothing about the run has to change.",
        )
        return
    known = {
        name: float(sav[index - 1])
        for name, index in FUEL_CLASSES.items()
        if len(sav) >= index
    }
    moss_classes = ("live_moss", "dead_moss")
    lines = []
    for moss_name in moss_classes:
        if moss_name not in known:
            continue
        # The same tolerance the Task 9 slope check works to. Two SAVs a part per billion
        # apart give moisture-of-extinction values that check cannot tell apart either, so
        # exact float equality here would leave it silent on exactly the case it exists for.
        twins = sorted(
            n
            for n, v in known.items()
            if n not in moss_classes
            and abs(v - known[moss_name])
            <= TOL_RELATIVE * max(abs(v), abs(known[moss_name]), 1.0)
        )
        if twins:
            lines.append(
                named(
                    known[moss_name],
                    f"fates_fire_SAV[{FUEL_CLASSES[moss_name]}] ({moss_name})",
                    sav_source,
                )
                + ", which is also its value for "
                + ", ".join(twins)
            )
    if not lines:
        return
    report.warn(
        "The moisture of extinction does not separate moss from the other fuel classes "
        "(Task 9)",
        "\n".join(lines) + "\n"
        "The MEF this script rebuilds for a moss class is therefore the same number it "
        "would rebuild for those non-moss classes, and the moss moisture-slope check "
        + (
            "would have passed just as well had FATES indexed one of them. What that check "
            "does establish here is that the configured moss map was applied to the moss proxy "
            "with the configured coefficients; what it CANNOT establish in this run is that "
            "FATES reached for a moss SAV entry at all rather than a neighbouring class's."
            if task9_ran
            else "could not have separated them either -- though it did not run in this "
            "case at all, so nothing above rests on this. It is recorded because it is a "
            "property of the parameter file this run was given, and it would bite on the "
            "next run whose fire model produces fuel moisture."
        )
        + "\n"
        "Whether live and dead moss are distinguishable from EACH OTHER is a separate "
        "question, and the answer is below: a second warning says so if they are not, and "
        "no second warning means the two classes' maps do differ in this run.\n"
        "Give the moss classes an SAV that no other class shares and the same check "
        "separates them from the rest, with nothing else changed.",
    )


def close_enough(a, b, scale=1.0):
    """Whether two parameter values are within the tolerance the checks themselves work to.

    Exact float equality is the wrong test wherever it decides whether a check established
    what its label says: two coefficients a part per billion apart produce a map the Task 9
    slope check cannot separate, so a warning that fires only on bit equality stays silent on
    precisely the run it exists for.
    """
    return abs(float(a) - float(b)) <= TOL_RELATIVE * max(abs(float(a)), abs(float(b)), scale)


def warn_live_dead_degeneracy(
    report, namelist, namelist_source, fuel_moisture, sav, sav_source, task9_ran
):
    """Warn if the dead-moss moisture map is indistinguishable from the live-moss one.

    Live and dead moss are separate fuel classes fed by separate pools, and Tasks 6 and 7
    do separate them -- livemoss is patch biomass, moss_fines is litter. What can collapse
    is the Task 9 MOISTURE map: it is the same function of the same proxy for both classes
    whenever the two configured coefficient sets agree and the two classes share an SAV, and
    then the dead-moss fit is the live-moss fit computed a second time.

    Both halves of that matter, and the SAV half is the one that goes missing. Where there
    are no tape columns to settle it, the coefficients alone do not: FATES_FUEL_MOISTURE_FC
    reports moisture/MEF, so two moss classes given different SAVs report different columns
    from identical coefficients and are perfectly distinguishable. An unreadable parameter
    file therefore leaves this question open rather than answered yes, and the warning has to
    say which of the two it is -- otherwise the only thing on the screen about the SAVs is a
    claim made without having looked at them.
    """
    live = (
        namelist["fates_moss_fuel_moisture_live_slope"],
        namelist["fates_moss_fuel_moisture_live_intercept"],
    )
    dead = (
        namelist["fates_moss_fuel_moisture_dead_slope"],
        namelist["fates_moss_fuel_moisture_dead_intercept"],
    )
    live_index, dead_index = FUEL_CLASSES["live_moss"], FUEL_CLASSES["dead_moss"]
    same_sav = (
        None
        if sav is None or len(sav) < dead_index
        else close_enough(sav[live_index - 1], sav[dead_index - 1])
    )
    same_coefficients = close_enough(live[0], dead[0]) and close_enough(live[1], dead[1])

    columns = None
    if fuel_moisture is not None:
        live_column = fuel_moisture[:, live_index - 1]
        dead_column = fuel_moisture[:, dead_index - 1]
        spread = max(
            float(np.nanmax(np.abs(live_column))), float(np.nanmax(np.abs(dead_column)))
        )
        columns = float(np.nanmax(np.abs(live_column - dead_column)))
        same_columns = columns <= TOL_RELATIVE * max(spread, 1.0)

    # The tape settles it outright where there is a tape to settle it with. Where there is
    # not, identical coefficients are only half the answer, and the other half is the SAVs:
    # unknown SAVs leave the conclusion hedged rather than dropped, because a warning that
    # said nothing would be the wrong answer too.
    sav_unexamined = False
    if columns is not None:
        degenerate = same_columns
    elif same_sav is None:
        degenerate = same_coefficients
        sav_unexamined = same_coefficients
    else:
        degenerate = same_coefficients and same_sav
    if not degenerate:
        return

    lines = [
        "configured map, live moss: "
        + named(live[0], "fates_moss_fuel_moisture_live_slope", namelist_source)
        + ", "
        + named(live[1], "fates_moss_fuel_moisture_live_intercept", namelist_source),
        "configured map, dead moss: "
        + named(dead[0], "fates_moss_fuel_moisture_dead_slope", namelist_source)
        + ", "
        + named(dead[1], "fates_moss_fuel_moisture_dead_intercept", namelist_source),
    ]
    if same_sav is not None:
        lines.append(
            f"fates_fire_SAV[{live_index}] and [{dead_index}] ({sav_source}) "
            + ("agree, so the two classes share a moisture of extinction too"
               if same_sav
               else "differ")
        )
    else:
        lines.append(
            f"fates_fire_SAV[{live_index}] and [{dead_index}] could not be read from this "
            "run's FATES parameter file, so they were NOT compared"
        )
    if columns is not None:
        lines.append(
            "the live-moss and dead-moss columns of FATES_FUEL_MOISTURE_FC (fuel classes "
            f"{live_index} and {dead_index}) differ by at most {columns:.3e} over the "
            "whole run"
        )
    if sav_unexamined:
        verdict = (
            "The two moss classes are carrying the same COEFFICIENTS, which is as far as "
            "this run can be read. It is not the whole question: FATES_FUEL_MOISTURE_FC "
            "reports moisture divided by the moisture of extinction, so moss classes given "
            "different SAVs report different columns from these same coefficients and are "
            "perfectly distinguishable. With no readable fates_fire_SAV and no fuel-moisture "
            "columns on the tape, whether the dead-moss half adds coverage here is open, not "
            "settled -- give this script a readable fates_paramfile and it is settled either "
            "way."
        )
    elif task9_ran:
        verdict = (
            "The two moss classes are carrying the same moisture map applied to the same "
            "proxy, so the dead-moss fit above is the live-moss fit run a second time and "
            "passing it says nothing the live-moss one did not already say."
        )
    else:
        verdict = (
            "The two moss classes are carrying the same moisture map applied to the same "
            "proxy, so a dead-moss fit would be the live-moss fit run a second time. "
            "Neither fit ran in this case, so nothing above rests on this; it is recorded "
            "because it is a property of the parameters this run was given, and it would "
            "bite on the next run whose fire model produces fuel moisture."
        )
    report.warn(
        "The dead-moss fuel-moisture check adds no coverage in this run (Task 9)",
        "\n".join(lines) + "\n" + verdict + "\n"
        "The fuel-LOADING checks in section 3 are NOT affected: they check the two classes "
        "against different pools, livemoss and moss_fines, and those are genuinely "
        "separate. It is the moisture check alone that is duplicated, and it earns its "
        "place the day the two coefficient sets diverge.",
    )


MOSS_MOISTURE_MAP = (
    "Is moss fuel moisture a linear function of the moss wetness proxy alone? (Task 9)"
)
NESTEROV_CONTRAST = (
    "Do the non-moss fuel classes still follow fire weather rather than the moss proxy? "
    "(Task 9)"
)
MOSS_EXTINCTION = "How often is live moss too wet to carry fire? (Task 9, Task 12 Step 4)"


def moisture_label(index, name):
    # The class number is the parenthetical, not the subject: a reader who does not already
    # know FATES's fuel-class ordering cannot be told "fuel class 7" and be any wiser.
    return (
        f"Is {name.replace('_', '-')} fuel moisture a linear function of the moss wetness "
        f"proxy alone? (fuel class {index}, Task 9)"
    )


def check_task9_moisture(
    report,
    data,
    units,
    fuel_moisture,
    namelist,
    namelist_source,
    sav,
    sav_source,
    no_veg_frac_reason,
    fire_status,
):
    """Moss fuel moisture is an exact linear map of the proxy; others are not (Task 9).

    The proxy is the one fuel moisture reads, FUEL_MOISTURE_PROXY.

    Three properties of the fit have to be pinned, not merely described:

      * the SLOPE. FATES_FUEL_MOISTURE_FC reports EFFECTIVE moisture, moisture/MEF, so the
        fitted slope is the configured slope divided by the moss classes' moisture of
        extinction. Recovering MEF from the fitted slope and printing it constrains
        nothing -- a model that halved every moss moisture would fit an equally perfect
        straight line and would only halve the printed number. So the MEF is rebuilt from
        the run's own fates_fire_SAV and the slope is checked against it. Where the
        parameter file cannot be read the implied MEF is still printed, but then the slope
        really is unconstrained and the check says so.

      * the INTERCEPT, relative to the slope. Both sides of the fit carry the same patch
        area weighting, so it cancels out of the slope -- but not out of the intercept. Per
        patch the map is max(0, a + b*fwet_patch)/MEF; area-weighting gives
        veg_frac*(a + b*fwet_site/veg_frac)/MEF, whose slope is b/MEF but whose intercept
        is veg_frac*a/MEF. The fitted intercept/slope is therefore veg_frac*a/b, not a/b.
        Written below as the crossing point of the fitted line, which is the same test with
        a tolerance that can be scaled by the range of fwet the run actually sampled.

        This is the one part of the check that needs the area fraction -- but only while the
        configured intercept is nonzero. At a configured intercept of zero, which is the configured
        default for both moss classes, the expected crossing is zero for EVERY value of
        veg_frac, so the area fraction drops out and the check runs unchanged on a tape that
        has none. It is then still worth running -- a model that offset every moss moisture
        by a constant fails it -- but it is not pinning the intercept against the area
        weighting, because at zero there is nothing to pin. Both facts are said at runtime,
        and a run in that position is not counted as having lost a constraint.

      * the FLOOR. The map is wrapped in max(0, ...) (fire/FatesFuelMod.F90:274-277), so a
        negative configured intercept makes it piecewise and it is linear only above the kink.
        Days on the floor are excluded from the fit and counted, rather than being left to
        drag R^2 below 1 for a legitimate reason.
    """
    fwet = data[FUEL_MOISTURE_PROXY]
    veg_frac = units.divisor["patch"]
    veg = None if veg_frac is None else float(np.mean(veg_frac))
    # The one place on this tape where the choice of divisor is falsifiable rather than
    # merely traced. FATES_FUEL_MOISTURE_FC at a moss class and FUEL_MOISTURE_PROXY are fitted
    # against each other, and the fitted slope depends on which area fraction dilutes each
    # of them. If the moss moisture column were a moss-patch quantity while the proxy is a
    # vegetated-patch one, the same configured map would fit a slope smaller by exactly the
    # ratio of the two areas. Both expectations are printed below where they differ, so the
    # fit says which family the moisture column belongs to instead of the reader taking it
    # on trust.
    moss_area = units.divisor["moss"]
    area_ratio = (
        float(np.mean(moss_area)) / veg
        if veg is not None and moss_area is not None and veg > 0
        else np.nan
    )
    discriminates = np.isfinite(area_ratio) and abs(area_ratio - 1.0) > TOL_RELATIVE

    for name, prefix in (("live_moss", "live"), ("dead_moss", "dead")):
        index = FUEL_CLASSES[name]
        moisture = fuel_moisture[:, index - 1]
        configured_slope = namelist[f"fates_moss_fuel_moisture_{prefix}_slope"]
        configured_intercept = namelist[f"fates_moss_fuel_moisture_{prefix}_intercept"]

        if veg is None:
            # Where the kink sits cannot be predicted without the area fraction, but it can
            # be seen: max(0, ...) makes the effective moisture exactly zero on the floor
            # and positive above it, so the reported value locates the kink itself.
            above_floor = moisture > 0
        else:
            above_floor = configured_intercept + configured_slope * (fwet / veg) > 0
        floored = int(np.sum(~above_floor))
        obstacle = fit_obstacle(fwet[above_floor], moisture[above_floor], len(fwet))
        if obstacle is not None:
            # A fit that could not be computed is not a fit that failed. Reporting it as a
            # FAIL printing `nan` puts a short or flat run's shape on the model's account.
            report(
                "SKIP",
                moisture_label(index, name),
                f"the linear fit could not be computed: {obstacle}.\n"
                + (
                    f"{floored} of {len(fwet)} days sit at or below the max(0, ...) floor "
                    "of the configured map and are excluded from the fit before this is "
                    "counted.\n"
                    if floored
                    else ""
                )
                + "Nothing here says the map is wrong -- it says this run does not contain "
                "the days it would take to test it. A longer run, or one that samples a "
                f"range of {FUEL_MOISTURE_PROXY}, would.",
            )
            continue
        slope, intercept, r2 = linear_fit(fwet[above_floor], moisture[above_floor])
        span = float(np.ptp(fwet[above_floor])) if above_floor.any() else 0.0

        mef = (
            float(moisture_of_extinction(sav[index - 1]))
            if sav is not None and len(sav) >= index and sav[index - 1] > 0
            else np.nan
        )
        implied_mef = configured_slope / slope if slope else np.nan

        # A configured intercept of zero puts the crossing point at zero whatever veg_frac is,
        # so the area fraction cancels out of this half and it runs on any tape. It is not
        # then pinning the area weighting -- there is nothing at zero for the weighting to
        # scale -- which is why it is not counted as a constraint lost when the fraction is
        # missing. It still catches an offset, so it still runs.
        degenerate_crossing = abs(configured_intercept) <= TOL_EXACT
        crossing = -intercept / slope if slope else np.nan
        expected_crossing = (
            0.0
            if degenerate_crossing and configured_slope
            else -veg * configured_intercept / configured_slope
            if veg is not None and configured_slope
            else np.nan
        )
        ok_crossing = (
            np.isfinite(crossing)
            and np.isfinite(expected_crossing)
            and abs(crossing - expected_crossing)
            <= TOL_RELATIVE * max(abs(expected_crossing), span)
        )
        expected_slope = configured_slope / mef if np.isfinite(mef) else np.nan
        ok_slope = (
            np.isfinite(slope)
            and np.isfinite(expected_slope)
            and abs(slope - expected_slope) <= TOL_RELATIVE * abs(expected_slope)
        )
        ok_r2 = bool(np.isfinite(r2) and r2 > 1.0 - 1e-9)
        ok = (
            ok_r2
            and (ok_crossing or not np.isfinite(expected_crossing))
            and (ok_slope or not np.isfinite(expected_slope))
        )

        intercept_named = named(
            configured_intercept,
            f"fates_moss_fuel_moisture_{prefix}_intercept",
            namelist_source,
        )
        slope_named = named(
            configured_slope, f"fates_moss_fuel_moisture_{prefix}_slope", namelist_source
        )
        if np.isfinite(expected_crossing) and degenerate_crossing:
            crossing_note = (
                f"crossing point: expected 0 exactly, fitted {crossing:+.6e}. With "
                f"{intercept_named} the crossing is zero whatever the area weighting, so "
                "this half needs no area fraction and would read the same on any tape. What "
                "it catches at these parameters is a moss moisture offset from zero; what "
                "it is NOT doing is pinning the area weighting, since at an intercept of "
                "zero there is nothing for the weighting to scale. Give the moss classes a "
                "nonzero configured intercept and this half starts constraining the area "
                "fraction as well.\n"
            )
        elif np.isfinite(expected_crossing):
            crossing_note = (
                f"crossing point: expected {expected_crossing:+.6e} in the site units the "
                f"fit was run in, fitted {crossing:+.6e}\n"
                f"        that is -(non-bareground area fraction {veg:.4f}) x intercept / "
                f"slope, with {intercept_named} and {slope_named}; the area factor is there "
                "because the weighting cancels out of the slope but not out of the "
                f"intercept, and moss-native the crossing is at {crossing / veg:+.6e}\n"
            )
        else:
            crossing_note = (
                f"crossing point: NOT CONSTRAINED. {no_veg_frac_reason} The fitted "
                f"intercept is veg_frac * configured intercept / MEF, so without the area "
                f"fraction there is no number to check the fitted {crossing:+.6e} against. "
                "The SLOPE reported above is unaffected: the weighting cancels out of it "
                "exactly. The R^2 is not quite unaffected -- the days entering the fit are "
                "the days whose reported moisture is positive rather than the days the "
                "configured map predicts above its kink, so a day the model wrongly floored "
                "drops out of the fit instead of pulling R^2 down, and the survivors still "
                "fit a perfect line. Read the floored-day count below against what the "
                "configured map would predict.\n"
            )

        # The slope is the one number in this check that is the same in site units and in
        # moss-native ones -- both sides of the fit carry the same area weight, so it
        # cancels exactly -- which is why the fitted slope is quoted without conversion.
        divisor_note = (
            f"       that slope is also what says FATES_FUEL_MOISTURE_FC at this class is "
            f"diluted by the same area fraction {FUEL_MOISTURE_PROXY} is, and not by the moss "
            f"patch area: had it been a moss-patch quantity the same configured map would have "
            f"fitted {area_ratio * expected_slope:.6f} instead, which is a factor of "
            f"{area_ratio:.4f} away and nothing like the deviation above\n"
            if discriminates and np.isfinite(expected_slope) and ok_slope
            else ""
        )
        report(
            "PASS" if ok else "FAIL",
            moisture_label(index, name),
            f"fit: effective_moisture = {slope:.6f} * fwet {intercept:+.3e}, "
            f"R^2 = {r2:.10f}   (site units, in which the slope is identical to its "
            "moss-native value: the area weight cancels out of it exactly)\n"
            f"configured map is max(0, intercept + slope * fwet), with {intercept_named} and "
            f"{slope_named}\n"
            + (
                f"slope: expected configured slope / MEF = {configured_slope:g} / {mef:.6f} = "
                f"{expected_slope:.6f}, fitted {slope:.6f}, relative deviation "
                f"{abs(slope - expected_slope) / abs(expected_slope):.3e}\n"
                f"       MEF is rebuilt from "
                + named(sav[index - 1], f"fates_fire_SAV[{index}]", sav_source)
                + ", not from this fit\n"
                + divisor_note
                if np.isfinite(expected_slope)
                else f"slope: NOT CONSTRAINED. fates_fire_SAV could not be read, so the "
                f"only MEF available is the one implied by this fit, "
                f"{implied_mef:.6f} m3 m-3. A model that scaled every moss moisture by a "
                "constant would still pass everything below.\n"
            )
            + crossing_note
            + (
                f"floor: {floored} of {len(fwet)} days sit at or below the max(0, ...) "
                "floor and are excluded from the fit; the map is piecewise there and R^2 "
                "over the whole record would legitimately be below 1\n"
                if floored
                else ""
            )
            + coverage_note(len(fwet), fwet, moisture),
            unconstrained="; ".join(
                part
                for part in (
                    None
                    if np.isfinite(expected_slope)
                    else "fates_fire_SAV could not be read, so the moisture of extinction "
                    "the slope is checked against is the one implied by the fit itself. A "
                    "model that scaled every moss moisture by a constant would have passed "
                    "this too.",
                    None
                    if np.isfinite(expected_crossing)
                    else "the configured intercept could not be checked: it survives the area "
                    "weighting and the area fraction is not on this tape. A model that "
                    "offset every moss moisture by a constant would have passed this too.",
                )
                if part
            )
            or None,
        )

    if "FATES_NESTEROV_INDEX" not in data:
        report(
            "SKIP",
            NESTEROV_CONTRAST,
            "FATES_NESTEROV_INDEX is not on this tape. That says nothing about whether fire "
            "ran: FATES registers it unconditionally with use_default='active' "
            "(main/FatesHistoryInterfaceMod.F90:6754), so it is on any tape whose "
            "hist_fincl1 does not exclude it, and off any tape whose does.\n"
            + fire_status,
        )
    else:
        nesterov = data["FATES_NESTEROV_INDEX"]
        nday = len(fwet)
        # A correlation that cannot be computed is not a correlation that failed, and the
        # difference is a whole verdict on a short run: at this kind of site the non-moss
        # fuel moistures are bit-identical for as long as the Nesterov index sits at zero
        # through the winter, so a run of a few weeks has no spread for any of these to key
        # off. Reported as SKIP, naming what was insufficient so the reader knows whether a
        # longer run would settle it.
        obstacles = []
        for c in NESTEROV_DRIVEN:
            column = fuel_moisture[:, c - 1]
            for label, predictor in (
                (FUEL_MOISTURE_PROXY, fwet),
                ("FATES_NESTEROV_INDEX", nesterov),
            ):
                why = fit_obstacle(predictor, column, nday, both=True)
                if why:
                    obstacles.append(f"class {c} against {label}: {why}")
        if obstacles:
            report(
                "SKIP",
                NESTEROV_CONTRAST,
                "at least one of the correlations this contrast is made of could not be "
                "computed:\n  " + "\n  ".join(obstacles[:6])
                + (f"\n  ... and {len(obstacles) - 6} more" if len(obstacles) > 6 else "")
                + "\nNothing here says the contrast is false -- it says this run does not "
                "hold the variation it would take to measure. A longer run would.",
            )
        else:
            with_proxy = np.array(
                [correlation(fwet, fuel_moisture[:, c - 1]) for c in NESTEROV_DRIVEN]
            )
            with_index = np.array(
                [correlation(nesterov, fuel_moisture[:, c - 1]) for c in NESTEROV_DRIVEN]
            )
            ok = (
                float(np.max(np.abs(with_proxy))) < 0.9
                and float(np.min(np.abs(with_index))) > 0.9
            )
            report(
                "PASS" if ok else "FAIL",
                NESTEROV_CONTRAST,
                "classes " + ", ".join(str(c) for c in NESTEROV_DRIVEN) + "\n"
                f"{'corr with ' + FUEL_MOISTURE_PROXY + ':':<32}"
                + ", ".join(f"{r:+.3f}" for r in with_proxy)
                + "\n"
                "corr with FATES_NESTEROV_INDEX: "
                + ", ".join(f"{r:+.3f}" for r in with_index)
                + "\nPRECONDITION on the 0.9 against the proxy: the moss proxy is "
                "essentially top-soil saturation and the Nesterov index is rezeroed on "
                "rain, so the two are driven by the same forcing and are not independent. "
                "In a wet run the non-moss classes can correlate strongly with the proxy "
                "with nothing wrong, and this half of the check would FAIL for a physical "
                "reason. Read a FAIL here against the correlations printed above rather "
                "than as a defect."
                + coverage_note(nday, fwet, nesterov, fuel_moisture),
            )

    # Effective moisture at or above 1 means the class is at or past its moisture of
    # extinction and cannot carry fire. The threshold is a property of a PATCH, so the
    # site-level value has to be divided back out by the non-bareground area fraction --
    # comparing the area-weighted site value against 1 understates how wet the moss is.
    site = fuel_moisture[:, FUEL_CLASSES["live_moss"] - 1]
    if veg_frac is None:
        report(
            "SKIP",
            MOSS_EXTINCTION,
            f"{no_veg_frac_reason}\n"
            f"The site-level FATES_FUEL_MOISTURE_FC value is "
            f"{np.nanmin(site):.4f} - {np.nanmax(site):.4f}, but the extinction threshold "
            "of 1 applies to a PATCH, and the site value is the patch value times the "
            "non-bareground area fraction. Comparing the site value against 1 understates "
            "the moss's wetness, so with no area fraction to divide back out this is not "
            "reported at all rather than reported wrong.",
        )
        return
    patch = divide_by_fraction(site, veg_frac)
    report(
        "INFO",
        MOSS_EXTINCTION,
        f"effective moisture {units.spans(site, 'patch', site_units='')}\n"
        f"at or past extinction (moss-native value >= 1) on "
        f"{100 * np.mean(patch >= 1.0):.1f}% of days; reading the tape's site value "
        f"against 1 instead would say {100 * np.mean(site >= 1.0):.1f}%, which understates "
        "the moss's wetness because the threshold belongs to a patch and the site value is "
        "diluted by everything that is not vegetated"
        + coverage_note(len(site), site, patch),
    )


MOSS_GPP = "Is moss photosynthesizing at all, and how much? (Task 10)"
MOSS_WINDOW = "Is moss's productive window ever visited? (Task 12 Step 3b)"


def check_moss_productivity(report, data, units, patch_area, moss, grass, fwet):
    """Is moss productive, and is the productive window visited? (Task 10, Task 12 Step 3b)

    Moss GPP is a class-C quantity: the tape reports it per m2 of LAND, and there are two
    denominators worth having. Per m2 of moss CROWN is what a moss measurement would be
    compared against, so it leads; per m2 of moss PATCH answers the different question of
    whether moss filled the ground it was handed, and follows. Grass GPP is here only to
    give moss GPP a scale, so it is converted to per m2 of grass patch for the same reason
    grass fuel loading is: a native moss number read against a site-level grass one carries
    a ratio of two patch areas that has nothing to do with either plant.

    `fwet` is the liquid proxy, FATES_MOSS_FWET_LIQ, the one the wetness scaler follows.
    """
    gone = absent(data, "FATES_GPP_PF")
    if gone:
        for label in (MOSS_GPP, MOSS_WINDOW):
            report("SKIP", label, f"{', '.join(gone)} is not on this tape.")
        return None
    gpp = data["FATES_GPP_PF"][:, moss]
    grass_gpp = data["FATES_GPP_PF"][:, grass]
    positive = int(np.sum(gpp > 0))
    # Reported rather than tested, and the reason is a property of the test rather than of
    # any run: "is moss GPP strictly greater than zero" is satisfied by a single day of
    # roundoff-sized carbon, so it would PASS on a run in which moss is, for every practical
    # purpose, not productive at all. Any threshold worth having is a science judgement
    # about what counts as productive moss, which is not this script's to make. What is
    # printed instead is the number itself next to the grass in the same run, so that
    # whoever does make that judgement has the scale in front of them.
    grass_area = None if patch_area is None else patch_area[:, grass]
    if grass_area is not None and float(np.nanmax(grass_area)) > 0:
        grass_line = (
            "grass, for scale  "
            + span(divide_by_fraction(grass_gpp, grass_area), "{:.4e}")
            + " kg m-2 of grass patch s-1   (on the tape "
            + span(grass_gpp, "{:.4e}")
            + " kg m-2 land s-1)"
        )
    else:
        grass_line = (
            "grass, for scale  "
            + span(grass_gpp, "{:.4e}")
            + " kg m-2 land s-1, on the tape (no usable grass patch area on this tape)"
        )
    report(
        "INFO",
        MOSS_GPP,
        f"moss, per crown  {units.spans(gpp, 'crown', '{:.4e}', 'kg m-2 land s-1')}\n"
        f"moss, per patch  {units.spans(gpp, 'moss', '{:.4e}', 'kg m-2 land s-1')}\n"
        + grass_line
        + (
            f"\nmoss peaks {np.nanmax(grass_gpp) / np.nanmax(gpp):.3g}x below grass, both "
            "read per m2 land as the tape holds them"
            if np.nanmax(gpp) > 0
            else ""
        )
        + f"\npositive on {positive} of {len(gpp)} days "
        f"({100 * positive / len(gpp):.1f}%)",
    )

    # np.unique collapses the decile edges of a proxy that never moves down to one, leaving
    # no bin at all and an INFO with an empty table under its heading. A constant proxy is a
    # legitimate thing for a run to have, so it gets a row of its own saying so rather than
    # a blank.
    edges = np.unique(np.nanpercentile(fwet, np.arange(0, 101, 10)))
    # The bins are chosen on the SITE-level proxy, which is what the tape holds and what
    # every other check reads, so that converting the display cannot move a day from one bin
    # to another. What is printed for each bin is the moss-native proxy range the days in it
    # actually spanned, which is exact rather than a converted edge and does not depend on
    # the area fraction being constant in time.
    native_fwet = units.native(fwet, "patch")
    native_gpp = units.native(gpp, "crown")

    def proxy_range(sel):
        if native_fwet is None:
            return f"proxy {span(fwet[sel], '{:.3f}')} (site units)"
        return f"proxy {span(native_fwet[sel], '{:.3f}')}"

    def gpp_mean(sel):
        if native_gpp is None or not np.any(np.isfinite(native_gpp[sel])):
            return (
                f"mean GPP = {float(np.nanmean(gpp[sel])):.4e} kg m-2 land s-1, on the tape"
            )
        return (
            f"mean GPP = {float(np.nanmean(native_gpp[sel])):.4e} kg m-2 of moss crown s-1"
        )

    rows, means = [], []
    if edges.size < 2:
        rows.append(
            "The liquid moss wetness proxy does not vary over this run -- it reads "
            + (
                f"{edges[0]:.6f} (site units)"
                if native_fwet is None
                else f"{float(np.nanmax(native_fwet)):.6f} moss-native"
            )
            + f" on all {len(fwet)} days -- so there are no deciles to bin by. Over the "
            f"whole run, {gpp_mean(np.ones(len(fwet), dtype=bool))} and GPP > 0 on "
            f"{100 * np.mean(gpp > 0):.1f}% of days."
        )
    for low, high in zip(edges[:-1], edges[1:]):
        sel = (fwet >= low) & (fwet < high)
        if not sel.sum():
            continue
        mean = float(np.nanmean(gpp[sel]))
        means.append((mean, sel))
        rows.append(
            f"{proxy_range(sel)}:  n = {int(sel.sum()):4d}   {gpp_mean(sel)}   "
            f"GPP > 0 on {100 * np.mean(gpp[sel] > 0):5.1f}% of days"
        )
    peak = max(means, key=lambda item: item[0]) if means else None
    report(
        "INFO",
        MOSS_WINDOW,
        "\n".join(rows)
        + (
            f"\npeak bin: {proxy_range(peak[1])}, {gpp_mean(peak[1])}"
            if peak
            else ""
        )
        + (
            f"\noverall corr(proxy, moss GPP) = {correlation(fwet, gpp):+.3f} (a "
            "correlation is unitless, so it is the same moss-native)\n"
            if fit_obstacle(fwet, gpp, len(fwet), both=True) is None
            else "\noverall corr(proxy, moss GPP): not computed -- "
            + fit_obstacle(fwet, gpp, len(fwet), both=True)
            + "\n"
        )
        + "The moss response to wetness is expected to be HUMPED, not monotonic, so a "
        "negative overall correlation is not by itself a failure. The question this step "
        "asks is whether the productive window is visited -- read the bins, and read them "
        "against the seasonal cycle, which confounds them at a site where the wet season "
        "and the growing season do not coincide."
        + coverage_note(len(fwet), fwet, gpp),
    )
    return gpp


def moss_allometry_reference(moss_params, moss, treelai_mismatch):
    """The reference heights and leaf areas the diagnosed values are read against.

    Every number here belongs to a PARAMETER FILE, not to this script, so each is taken from
    the run's own -- and where one cannot be, the statement that quotes it is dropped rather
    than printed unattributed. A moss parameter file that has been retuned otherwise gets a
    "For reference" line that is false about it and, worse, silently loses the note that
    says the cohort never grew, because that note is keyed off a recruit height the run does
    not use.

    Returns (line for the height INFO, recruit height or None, line for the leaf-area INFO).
    """
    recruit = moss_params.get("fates_recruit_height_min")
    d2h1 = moss_params.get("fates_allom_d2h1")
    d2h2 = moss_params.get("fates_allom_d2h2")
    dbh_max = moss_params.get("fates_allom_dbh_maxheight")

    source = f"this run's FATES parameter file at PFT {moss + 1}"
    parts = []
    if recruit is not None:
        parts.append(
            "recruit height is "
            + named(recruit, "fates_recruit_height_min", source, "{:g} m")
        )
    if None not in (d2h1, d2h2, dbh_max) and dbh_max > 0:
        ceiling = float(d2h1) * float(dbh_max) ** float(d2h2)
        parts.append(
            f"the height power law the moss allometry borrows saturates at {ceiling:.2f} m, "
            "which is fates_allom_d2h1 x fates_allom_dbh_maxheight ** fates_allom_d2h2 at "
            f"fates_allom_d2h1 = {d2h1:g}, fates_allom_dbh_maxheight = {dbh_max:g} and "
            f"fates_allom_d2h2 = {d2h2:g} ({source})"
        )
    height_line = (
        "\nFor reference: " + "; and ".join(parts) + "."
        if parts
        else "\nNo reference heights: fates_recruit_height_min and the height allometry "
        "coefficients could not be read from this run's FATES parameter file, so there is "
        "nothing here to read the diagnosed height against."
    )

    if treelai_mismatch is None:
        leaf_line = (
            f"   for reference, the allometry predicts {TREELAI_AT_RECRUIT} at recruit size "
            f"and {TREELAI_AT_MAX} at maximum ({TREELAI_PREDICTION_SOURCE}; this run's "
            "parameter file still carries every value at the moss index that those two "
            "were derived from, so they are restated here)\n"
        )
    else:
        leaf_line = (
            "   No prediction to read these against: the allometry figures of "
            f"{TREELAI_AT_RECRUIT} at recruit size and {TREELAI_AT_MAX} at maximum come "
            f"from {TREELAI_PREDICTION_SOURCE}, and this run does not use it -- "
            f"{treelai_mismatch}. They are not restated because they would not be true of "
            "this run.\n"
        )
    return height_line, recruit, leaf_line


def treelai_prediction_mismatch(paramfile, moss):
    """Why the Step 3d treelai figures do not describe this run, or None where they do.

    They are quoted rather than recomputed (see TREELAI_PREDICTION_PARAMS), so the quote is
    only honest while the run's own parameter file still holds the values they came from.
    """
    values = read_params(paramfile, tuple(TREELAI_PREDICTION_PARAMS))
    for name, expected in TREELAI_PREDICTION_PARAMS.items():
        got = values.get(name)
        if got is None or got.size <= moss:
            return f"{name} could not be read from its FATES parameter file"
        if not close_enough(got[moss], expected):
            return (
                f"its {name} at PFT {moss + 1} is {float(got[moss]):g}, where those figures "
                f"were derived at {expected:g}"
            )
    return None


MOSS_AREA = "How much leaf and stem area does moss carry? (Task 10b, Task 12 Step 3d)"
MOSS_HEIGHT = "How tall does the moss stand? (Task 12 Step 3c)"
MOSS_COVER = "How much ground was moss given? (Task 12 Step 3)"


def check_moss_structure(
    report,
    data,
    units,
    moss,
    grass,
    pft_moss,
    pft_grass,
    sp_mode,
    patch_area,
    moss_params,
    treelai_valid,
):
    """Moss leaf area, crown area and height (Task 10b, Task 12 Steps 3c and 3d)."""
    # In FATES-SP, LAI, SAI and height are read straight off the surface dataset rather
    # than produced by the allometry, so the numbers below report the fsurdat and say
    # nothing about whether the moss allometry works.
    sp_note = (
        "\nFATES-SP: LAI, SAI, crown area and height are PRESCRIBED from the surface "
        "dataset here, so these values test the fsurdat, not the moss allometry."
        if sp_mode
        else ""
    )
    height_line, recruit_height, leaf_line = moss_allometry_reference(
        moss_params, moss, treelai_valid
    )
    gone = absent(data, "FATES_LAI_PF", "FATES_SAI_PF", "FATES_CROWNAREA_PF")
    if gone:
        report("SKIP", MOSS_AREA, f"{', '.join(gone)} not on this tape.")
    else:
        lai = data["FATES_LAI_PF"][:, moss]
        sai = data["FATES_SAI_PF"][:, moss]
        crown = data["FATES_CROWNAREA_PF"][:, moss]

        # Per m2 of CROWN is FATES's own treelai and treesai, and it is what the allometry
        # is reasoned about and what a moss measurement would be compared against, so it
        # leads. Per m2 of moss PATCH answers a different question -- did moss fill the
        # ground it was handed -- and follows.
        crown_lai = units.spans(lai, "crown", "{:.6g}", "m2 m-2 land")
        crown_sai = units.spans(sai, "crown", "{:.6g}", "m2 m-2 land")
        crown_vai = units.spans(lai + sai, "crown", "{:.6g}", "m2 m-2 land")

        # Crown area is the divisor for the two lines above, so dividing it by itself says
        # nothing; per m2 of moss patch is its native reading. Whether the patch-area
        # variable is usable was decided once, in non_bareground_fraction, and handed here
        # -- so that a patch area present but identically zero cannot come out reported in
        # one place and skipped in another, with a division by zero between them.
        moss_patch = None if patch_area is None else float(np.nanmax(patch_area[:, moss]))
        if moss_patch is not None and moss_patch > 0:
            against_patch = (
                "moss crown area  "
                + units.spans(crown, "moss", "{:.4e}", "m2 m-2 land")
                + f"\n   moss fills at most {100 * np.nanmax(crown) / moss_patch:.4f}% of "
                "the patch it was given"
            )
        elif moss_patch is not None:
            against_patch = (
                f"moss crown area  {span(crown, '{:.4e}')} m2 m-2 land; the prescribed "
                "nocomp patch area for moss is zero on every day of this run, so there is "
                "no patch for the crown to fill a fraction of"
            )
        else:
            against_patch = (
                f"moss crown area  {span(crown, '{:.4e}')} m2 m-2 land; there is no usable "
                "prescribed patch area on this tape to read it against"
            )

        report(
            "INFO",
            MOSS_AREA,
            f"leaf area (treelai)  {crown_lai}\n"
            f"stem area (treesai)  {crown_sai}\n"
            f"VAI = LAI + SAI      {crown_vai}\n"
            + leaf_line
            + f"per moss patch: LAI {units.spans(lai, 'moss', '{:.4e}', 'm2 m-2 land')}\n"
            + against_patch
            + sp_note
            + coverage_note(len(lai), lai, sai, crown),
        )

    if absent(data, "FATES_MOSS_HEIGHT"):
        report("SKIP", MOSS_HEIGHT, "FATES_MOSS_HEIGHT is not on this tape.")
        check_nocomp_cover(report, patch_area, moss, grass, pft_moss, pft_grass)
        return

    # FATES_MOSS_HEIGHT is the one moss diagnostic that is NOT per unit land area: it is
    # accumulated as a crown-area weighted sum over the non-vascular cohorts and then
    # divided by the moss crown area (main/FatesHistoryInterfaceMod.F90:3068-3074,
    # :3120-3124), so it is already a height and gets no veg_frac factor.
    height = data["FATES_MOSS_HEIGHT"]
    live = height[height > 0]
    pinned = (
        recruit_height is not None
        and live.size > 0
        and np.allclose(live, recruit_height, rtol=0, atol=1e-6)
    )
    report(
        "INFO",
        MOSS_HEIGHT,
        f"FATES_MOSS_HEIGHT {span(height, '{:.5f}')} m "
        f"({len(np.unique(np.round(height, 8)))} distinct values)\n"
        "Already moss-native and not converted here: FATES normalizes this one by moss "
        "crown area rather than by land area, so unlike every other moss diagnostic in this "
        "output it carries no area weight to divide back out."
        + height_line
        + (
            "\nEvery day moss is present it stands at exactly its "
            + named(
                recruit_height,
                "fates_recruit_height_min",
                f"this run's FATES parameter file at PFT {moss + 1}",
                "{:g} m",
            )
            + ", so the cohort never grew past recruit size."
            if pinned
            else ""
        )
        + sp_note
        + coverage_note(len(height), height),
    )

    check_nocomp_cover(report, patch_area, moss, grass, pft_moss, pft_grass)


def check_nocomp_cover(report, patch_area, moss, grass, pft_moss, pft_grass):
    """The prescribed cover the rest of the run is read against (Task 12 Step 3).

    Gated on the same decision non_bareground_fraction made, not on a second look at the
    tape: whether that variable is usable is one question, and answering it twice produced a
    run that reported prescribed cover here while the WARN inventory said the report had been
    skipped.
    """
    if patch_area is None:
        report(
            "SKIP",
            MOSS_COVER,
            "There is no usable FATES_NOCOMP_PATCHAREA_PF on this tape -- see the reason "
            "given with the area-fraction WARN above.\n"
            "A run with no prescribed cover has none for this step to report: what each PFT "
            "holds is then an outcome of the run rather than something it was given.",
        )
        return
    area = patch_area
    report(
        "INFO",
        MOSS_COVER,
        "These are already fractions of the site, which is their native reading, so nothing "
        "is converted here. They are also the divisors the moss-native numbers elsewhere in "
        "this output are made with.\n"
        f"moss  (PFT {pft_moss}) {np.nanmean(area[:, moss]):.4f}\n"
        f"grass (PFT {pft_grass}) {np.nanmean(area[:, grass]):.4f}\n"
        f"vegetated total {np.nanmean(area.sum(axis=1)):.4f}, "
        f"bareground {1 - np.nanmean(area.sum(axis=1)):.4f}",
    )


def warn_fire_status(report, data, config, spitfire_on, gate_note):
    """Warn about whatever this run's fire configuration leaves untested.

    Two different situations, kept apart because they read completely differently.

    SPITFIRE off is the expected configuration of a FATES-SP run and unremarkable to whoever
    set the case up. It is still said out loud, because half of what the moss work does is a
    fire story -- two fuel classes, a fuel-moisture map, a moisture of extinction -- and a
    reader who came for that half will otherwise read a screenful of moss PASSes as covering
    it. None of them touches fire when fire is off.

    SPITFIRE on with nothing ever burning is the surprising one, and it is a different
    statement: the fire model DID run, the fuel loadings and moistures the checks above test
    are real numbers produced by it, and the burn path still went unexercised because the
    site never met the conditions to ignite.

    Which of the two this is comes from lnd_in. Where lnd_in could not be read it is an
    inference off an all-zero fuel array, which is also exactly what a genuine SPITFIRE
    failure looks like, so the disclaimer that says so travels with every branch here -- the
    fire-off one included, since that is the branch the inference reaches most easily.
    """
    if not spitfire_on:
        sp_note = (
            " This is the expected configuration for a FATES-SP case."
            if config.use_sp
            else ""
        )
        report.warn(
            "Fire is off in this run, so nothing here tests the moss burn path",
            f"{config.settings_phrase()}\n"
            f"SPITFIRE did not run.{sp_note}{gate_note} It is worth stating either way: a "
            "reader may reasonably be surprised that the moss FIRE work is not under test "
            "in a run whose output is full of moss diagnostics.\n"
            "Untested in this run: fuel loading by class, fuel moisture and its moss map, "
            "the moisture of extinction, and every burn-side quantity -- sections 3 and 4. "
            "The moss checks that do run here are the wetness proxies, the photosynthetic "
            "scaler, and moss structure and survival -- sections 1, 2 and 5, none of which "
            "goes near the burn path.",
        )
        return

    if "FATES_BURNFRAC" not in data:
        report.warn(
            "SPITFIRE ran but this tape cannot say whether anything burned",
            f"{config.settings_phrase()}, but FATES_BURNFRAC is not on this tape."
            + gate_note
            + "\nWhether the burn-side diagnostics in this run mean anything turns "
            "entirely on whether any fire occurred, and nothing here answers that. FATES "
            "registers FATES_BURNFRAC unconditionally with use_default='active' "
            "(main/FatesHistoryInterfaceMod.F90:6839), so this run wrote it and it was left "
            "out of hist_fincl1. Put it back to find out.",
        )
        return

    burn = data["FATES_BURNFRAC"]
    if float(np.nanmax(burn)) > 0.0:
        return
    report.warn(
        "SPITFIRE ran and nothing burned, so nothing here tests how moss burns",
        f"{config.settings_phrase()}, and FATES_BURNFRAC is identically zero on "
        f"all {len(burn)} days of the run." + gate_note + "\n"
        "This is not the same as fire being off, and it is the more surprising of the two: "
        "the fire model ran, and the fuel loadings and moistures the checks in sections 3 "
        "and 4 test are real quantities it produced. What never happened is combustion.\n"
        "So every burn-side diagnostic in this run, FATES_FUEL_BURNT_BURNFRAC_FC included, "
        "is structurally zero, and no PASS or number below establishes anything whatever "
        "about how moss burns. To test that, this site has to be driven to ignite.",
    )


FUEL_BURNT = "How much of the moss fuel burned? (Task 12)"

# Printed wherever the burnt-fraction normalization is mentioned, because a reader who
# checks it against the FATES long name will find that they disagree, and the long name is
# the one that is wrong.
# How the quantity is named, in every branch that names it. It is one string so that no
# branch can state the naive form that the note below exists to refute: the correction used
# to arrive a sentence after the assertion, which read as the output contradicting itself
# rather than as one consistent definition with an explanation attached.
BURNT_FRACTION_FORMULA = (
    "FATES_FUEL_BURNT_BURNFRAC_FC divided by (sec_per_day x FATES_BURNFRAC)"
)

BURNT_UNITS_NOTE = (
    "\nWhy sec_per_day is in that denominator: the two variables disagree about whether "
    "they carry a per-second rate. FATES_BURNFRAC is accumulated with a /sec_per_day and "
    "registered units='s-1' (main/FatesHistoryInterfaceMod.F90:2769, :6839), while "
    "FATES_FUEL_BURNT_BURNFRAC_FC is accumulated with no time division and registered "
    "units='1' (:4302-4303, :7885). Multiplying FATES_BURNFRAC back up by sec_per_day "
    "recovers the plain burnt-area fraction, which is what this has to be divided by. "
    "FATES's own long name says to divide by FATES_BURNFRAC and stop there; that "
    "instruction is dimensionally wrong, and following it leaves a quantity in SECONDS, "
    "86400x too large to be the fraction it is called."
)


def check_fuel_burnt(report, data, fire_status):
    """Report FATES_FUEL_BURNT_BURNFRAC_FC, which the moss testmod asks for (Task 12).

    It has no check because there is nothing to check it against on one tape, and because
    it is structurally zero unless something burned. It is reported so that a reader can
    see it was looked at, and told plainly what it is worth.

    This is the one moss-relevant fuel diagnostic that is NOT a moss-patch quantity, despite
    sitting on the same fuel axis as FATES_FUEL_AMOUNT_FC. frac_burnt is a function of a
    class's moisture and not of its loading (fire/FatesFuelMod.F90:471-497), so a patch with
    no moss fuel at all still contributes to the moss columns, and each contribution is
    multiplied by that patch's own burnt fraction. Normalizing by the site's burnt area is
    what turns that product back into a fraction, and it is undefined rather than
    zero-over-zero on a run in which nothing burned.

    THE FACTOR OF sec_per_day IS NOT A MISTAKE, AND THE LONG NAME IS. FATES_FUEL_BURNT_-
    BURNFRAC_FC's long name says "divide by FATES_BURNFRAC to get burned-area-weighted mean
    fraction fuel burnt", and that instruction is dimensionally wrong as written. The two
    variables disagree about whether they carry a per-second rate:

      main/FatesHistoryInterfaceMod.F90:4302-4303 accumulates
          frac_burnt(i_fuel) * cpatch%frac_burnt * cpatch%area * AREA_INV
      with no time division, and :7885 registers it units='1'. Write it b*f, for the
      fraction b of the class's fuel consumed where it burned and the fraction f of the
      site that burned.

      main/FatesHistoryInterfaceMod.F90:2769 accumulates
          cpatch%frac_burnt * cpatch%area * AREA_INV / sec_per_day
      and :6839 registers it units='s-1'. That is f/sec_per_day.

    Their quotient is b*sec_per_day: units of SECONDS, and sec_per_day times too large to be
    a fraction. What recovers b is dividing by sec_per_day, which is done here by putting
    the factor on the denominator instead -- sec_per_day*FATES_BURNFRAC is f, the plain
    burnt-area fraction, and b*f over f is b. Note the direction: "the quotient is 86400x
    too large" and "multiply the quotient by 86400" cannot both be true, and it is the
    first. Do not "fix" this back to match the long name; the long name is what needs
    fixing, upstream.
    """
    burnt = data["FATES_FUEL_BURNT_BURNFRAC_FC"]
    moss_burnt = burnt[:, [FUEL_CLASSES["live_moss"] - 1, FUEL_CLASSES["dead_moss"] - 1]]
    burn = data.get("FATES_BURNFRAC")
    if burn is None:
        # Not "fire is off": FATES_BURNFRAC is registered unconditionally, so its absence is
        # a hist_fincl1 omission. What fire did is taken from the namelist instead.
        native = (
            f"The burned-area-weighted fraction of each class burnt is "
            f"{BURNT_FRACTION_FORMULA}. FATES_BURNFRAC is not on this tape, so it cannot be "
            "formed here." + BURNT_UNITS_NOTE
        )
        tail = (
            "FATES_BURNFRAC is not on this tape, so whether anything actually burned cannot "
            "be read here. " + fire_status
        )
    elif float(np.nanmax(burn)) <= 0.0:
        native = (
            f"The burned-area-weighted fraction of each class burnt is "
            f"{BURNT_FRACTION_FORMULA}. FATES_BURNFRAC is zero on every day of this run, so "
            "it is undefined here rather than zero." + BURNT_UNITS_NOTE
        )
        tail = (
            "FATES_BURNFRAC is zero on every day of this run, so these are structurally "
            "zero and establish nothing whatever about the moss burn path -- see the WARN "
            "that says so in full."
        )
    else:
        alive = burn > 0
        # SEC_PER_DAY on the DENOMINATOR, which is where the missing factor belongs:
        # FATES_BURNFRAC is the site's burnt-area fraction already divided by sec_per_day,
        # so multiplying it back up restores the plain fraction this has to be divided by.
        # The docstring above has the two line numbers and the two units attributes.
        burnt_area_fraction = SEC_PER_DAY * burn
        native = (
            f"burned-area-weighted fraction burnt, {BURNT_FRACTION_FORMULA}: live moss "
            + span(
                divide_by_fraction(moss_burnt[:, 0], burnt_area_fraction)[alive], "{:.4f}"
            )
            + ", dead moss "
            + span(
                divide_by_fraction(moss_burnt[:, 1], burnt_area_fraction)[alive], "{:.4f}"
            )
            + f", over the {int(alive.sum())} days something burned" + BURNT_UNITS_NOTE
        )
        tail = (
            "There is no second run to check these against, so they are reported rather "
            "than tested."
        )
    report(
        "INFO",
        FUEL_BURNT,
        native + "\n"
        f"on the tape: live moss {span(moss_burnt[:, 0], '{:.4e}')}, dead moss "
        f"{span(moss_burnt[:, 1], '{:.4e}')}\n"
        f"nonzero on {int(np.sum(np.any(moss_burnt != 0.0, axis=1)))} of {len(burnt)} days\n"
        + tail
        + coverage_note(len(burnt), moss_burnt),
    )


FIRE_OCCURRED = "Did any fire occur at all? (Task 12 Step 3)"
MOSS_MORTALITY = "What is killing moss? (Task 12 Step 3)"
MOSS_SURVIVAL = "Did moss survive the run? (Task 12 Step 3)"


def check_fire_occurred(report, data, fire_status):
    """Whether anything burned. Site-level burnt area, and native as it stands (Task 12).

    FATES_BURNFRAC is a fraction of the site's area that burned, per second. It is not a
    moss diagnostic and carries no moss area weight, so there is nothing to divide out of
    it; the moss-relevant burnt fractions are reported separately, normalized by this.
    """
    if "FATES_BURNFRAC" not in data:
        report(
            "SKIP",
            FIRE_OCCURRED,
            "FATES_BURNFRAC is not on this tape. That says nothing about whether fire ran: "
            "FATES registers it unconditionally with use_default='active' "
            "(main/FatesHistoryInterfaceMod.F90:6839), so it is on any tape whose "
            "hist_fincl1 does not exclude it.\n" + fire_status,
        )
        return
    burn = data["FATES_BURNFRAC"]
    report(
        "INFO",
        FIRE_OCCURRED,
        f"FATES_BURNFRAC mean {np.nanmean(burn):.3e} s-1, max {np.nanmax(burn):.3e}, "
        f"nonzero on {int(np.sum(burn > 0))} of {len(burn)} days"
        + (
            ""
            if np.nanmax(burn) > 0
            else "\nNo fire occurred, so every burn-side diagnostic in this run is "
            "structurally zero and says nothing about the moss burn path."
        ),
    )


def check_moss_population(report, data, units, moss, when):
    """Moss mortality and what the moss population actually did (Task 12 Step 3).

    This is the check most likely to say something the plan did not anticipate, so it
    reports the trajectory in enough detail to tell slow decline from seasonality from
    outright loss, rather than only a first-half/second-half mean.

    Leaf carbon is reported both per m2 of moss crown and per m2 of moss patch, because on
    a declining population those two say different things: crown-native biomass holding
    steady while the patch-native value falls is cohorts being thinned out, and both falling
    together is each moss mat shrinking.
    """
    gone = absent(data, "FATES_MORTALITY_HYDRAULIC_PF", "FATES_MORTALITY_TERMINATION_PF")
    if gone:
        report("SKIP", MOSS_MORTALITY, f"{', '.join(gone)} not on this tape.")
    else:
        hydraulic = data["FATES_MORTALITY_HYDRAULIC_PF"][:, moss]
        termination = data["FATES_MORTALITY_TERMINATION_PF"][:, moss]
        report(
            "INFO",
            MOSS_MORTALITY,
            "These are number densities of individuals lost per year, so the moss patch is "
            "the denominator that makes them a moss rate; crown area would give deaths per "
            "unit of living crown, which is a different and less useful quantity.\n"
            f"hydraulic    {units.spans(hydraulic, 'moss', '{:.4e}', 'm-2 land yr-1')}, "
            f"nonzero on {int(np.sum(hydraulic > 0))} days\n"
            f"termination  {units.spans(termination, 'moss', '{:.4e}', 'm-2 land yr-1')}, "
            f"nonzero on {int(np.sum(termination > 0))} days",
        )

    if absent(data, "FATES_LEAFC_PF"):
        report("SKIP", MOSS_SURVIVAL, "FATES_LEAFC_PF is not on this tape.")
        return

    leafc = data["FATES_LEAFC_PF"][:, moss]
    nday = len(leafc)
    half = nday // 2
    day = np.arange(1, nday + 1, dtype=float)
    alive = leafc > 0
    peak = float(np.nanmax(leafc))
    lines = [
        "moss leaf carbon, per crown  "
        + units.spans(leafc, "crown", "{:.4e}", "kg m-2 land"),
        "moss leaf carbon, per patch  "
        + units.spans(leafc, "moss", "{:.4e}", "kg m-2 land"),
        # A first half and a second half need two days to divide between them.
        f"first-half mean {units.value(float(np.nanmean(leafc[:half])), 'moss', '{:.4e}')} "
        f"-> second-half mean "
        f"{units.value(float(np.nanmean(leafc[half:])), 'moss', '{:.4e}')}"
        if half
        else "one day on this tape, so there is no first half and second half to compare",
        f"peak on day {int(np.nanargmax(leafc)) + 1} ({when[int(np.nanargmax(leafc))]})",
    ]

    never_present = not alive.any()
    lost = False
    if not never_present:
        last = int(np.nonzero(alive)[0][-1])
        steps = np.diff(leafc[: last + 1])

        # How moss ends matters more than how fast it declined, and the two invite opposite
        # readings. A decay rate suggests moss faded out; but a moss trajectory can equally
        # end by removal -- a substantial fraction of peak biomass on the last day moss
        # exists and exactly zero on the next, in one step orders of magnitude larger than
        # any step taken while moss was alive. That is a cohort being taken out at standing
        # biomass rather than a decay tail reaching the floor, it means something quite
        # different, and a decay rate printed above it would be read as the explanation. So
        # the discontinuity is looked for first and reported first.
        if last + 1 < nday:
            median_step = float(np.median(np.abs(steps))) if steps.size else 0.0
            drop = float(leafc[last] - leafc[last + 1])
            ratio = drop / median_step if median_step > 0 else np.inf
            frac = leafc[last] / peak if peak > 0 else np.nan
            lines.append(
                f"last day with biomass is day {last + 1} ({when[last]}), still holding "
                f"{100 * frac:.1f}% of peak leaf carbon; day {last + 2} "
                f"({when[last + 1]}) reads "
                + units.value(float(leafc[last + 1]), "moss", "{:.4e}")
            )
            lines.append(
                f"that final step is {ratio:.0f}x the median daily step over the "
                f"{last + 1} days moss is present ("
                + units.value(median_step, "moss", "{:.4e}")
                + ")"
                if np.isfinite(ratio)
                else "moss took no nonzero daily step at all before it went to zero"
            )
            if "FATES_NCOHORTS" in data:
                cohorts = data["FATES_NCOHORTS"]
                lines.append(
                    f"FATES_NCOHORTS goes {cohorts[last]:.0f} -> {cohorts[last + 1]:.0f} "
                    "across that same step"
                )
            if (
                np.isfinite(frac)
                and frac >= DISCONTINUITY_PEAK_FRACTION
                and ratio >= DISCONTINUITY_STEP_RATIO
            ):
                lines.append(
                    "THIS IS A DISCONTINUOUS COHORT REMOVAL AT SUBSTANTIAL STANDING "
                    "BIOMASS, not a decay tail reaching the floor. Moss did not shrink to "
                    "nothing; it was taken out while it still had biomass. That is the "
                    "sharpest clue this tape carries as to why moss disappears, and it is "
                    "the thing to chase."
                )

        rises, falls = int(np.sum(steps > 0)), int(np.sum(steps < 0))
        constant = rises == 0 and falls == 0
        if constant:
            shape = " -- exactly constant, i.e. prescribed rather than prognosed"
        elif rises == 0:
            shape = " -- strictly monotonic decline"
        else:
            shape = ""
        lines.append(
            f"over the {last + 1} days moss is present, biomass rises on {rises} and "
            f"falls on {falls} of {len(steps)} day-to-day steps" + shape
        )

        positive = alive[: last + 1]
        # A constant series is excluded before the fit rather than after it. ln(biomass)
        # then has no variance for the fit to explain, so R^2 comes back NaN and polyfit
        # returns a roundoff-sized negative slope whose reciprocal is an e-folding time of
        # order 1e17 days -- a decay rate printed directly beneath the line saying the
        # series never moved. The np.isfinite(r2) term below covers the same degeneracy
        # arriving by another route, e.g. a series that varies only among the days the
        # floor excludes.
        if int(positive.sum()) > 10 and not constant:
            # Fitted against DAY NUMBER, not against position within the filtered positive
            # series: if moss ever went absent and came back, filtering would close the gap
            # and compress the time axis, overstating the rate.
            slope, _, r2 = linear_fit(
                day[: last + 1][positive], np.log(leafc[: last + 1][positive])
            )
            if np.isfinite(slope) and slope < 0 and np.isfinite(r2):
                lines.append(
                    f"exponential fit of ln(biomass) against day number: {slope:.4e} /day, "
                    f"an e-folding time of {-1 / slope:.0f} days "
                    f"({100 * (np.exp(slope * 365) - 1):.1f}%/yr), R^2 = {r2:.4f}"
                )
                if last + 1 < nday:
                    lines.append(
                        "  -- that is the rate of the decline that preceded the removal, "
                        "not a time to extinction. Moss did not reach zero by decaying, so "
                        "extrapolating this rate to zero describes something the run did "
                        "not do."
                    )

        if not alive.all():
            gone = int(np.nonzero(~alive)[0][0])
            recovered = bool(alive[gone:].any())
            lines.append(
                f"moss first reads zero on day {gone + 1} ({when[gone]}) and "
                + (
                    "recovers later in the run"
                    if recovered
                    else f"never recovers -- it is absent for the remaining "
                    f"{nday - gone} days, with no recruitment replacing it"
                )
            )
            lost = not recovered
    else:
        lines.append("moss carries zero leaf biomass on every day of the run")

    # Moss that reaches zero biomass and is never recruited back has failed to persist in
    # the patch it was prescribed; moss that never carries biomass on any day has failed
    # more completely still, and that case has to fail here rather than pass as an INFO.
    # Under FATES-SP it is the only thing that would catch it: there is no fuel state, so
    # Task 6's nonzero guard never runs. Either way this is a finding about the
    # configuration rather than about the diagnostics, and too important to report as a
    # number to be read past.
    if never_present:
        closing = (
            "\nThis FAIL is a statement about the model configuration, not about this "
            "script: the moss PFT was given a nocomp patch and never carried leaf carbon "
            "in it on any day of the run. That is a more complete failure to persist than "
            "moss appearing and later being lost, and every other moss-keyed number in "
            "this run was computed off that same absent PFT. It sets exit code 1 for the "
            "same reason the loss case does -- see the note on FAIL at the top of this "
            "file."
        )
    elif lost:
        closing = (
            "\nThis FAIL is a statement about the model configuration, not about this "
            "script: the moss PFT was given a nocomp patch and did not persist in it. It "
            "still sets exit code 1, deliberately -- see the note on FAIL at the top of "
            "this file."
        )
    else:
        closing = ""

    report(
        "FAIL" if never_present or lost else "INFO",
        MOSS_SURVIVAL,
        "\n".join(lines) + closing + coverage_note(nday, leafc),
    )


# ---------------------------------------------------------------------------------------
# Plots
# ---------------------------------------------------------------------------------------


def make_plots(data, moss, fwet, gpp, out_dir, tag):
    """Moss GPP against the liquid wetness proxy, its distribution, and moss biomass."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    leafc = data["FATES_LEAFC_PF"][:, moss]
    day = np.arange(1, len(fwet) + 1)

    fig, axes = plt.subplots(1, 3, figsize=(15.0, 4.4), facecolor=COLOR_SURFACE)
    for ax in axes:
        ax.set_facecolor(COLOR_SURFACE)
        ax.grid(True, color="#e4e3df", linewidth=0.8)
        ax.set_axisbelow(True)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        for side in ("left", "bottom"):
            ax.spines[side].set_color("#d5d4cf")
        ax.tick_params(colors=COLOR_MUTED, labelsize=9, length=3)

    axes[0].scatter(
        fwet, gpp, s=16, color=COLOR_SERIES[0], alpha=0.55, linewidths=0, zorder=3
    )
    axes[0].set_xlabel("FATES_MOSS_FWET_LIQ [1]", color=COLOR_MUTED, fontsize=9)
    axes[0].set_ylabel("moss FATES_GPP_PF [kg m-2 s-1]", color=COLOR_MUTED, fontsize=9)
    axes[0].set_title(
        "Moss GPP against the liquid wetness proxy", color=COLOR_TEXT, fontsize=11, loc="left"
    )

    axes[1].hist(fwet, bins=40, color=COLOR_SERIES[1], edgecolor=COLOR_SURFACE, zorder=3)
    axes[1].set_xlabel("FATES_MOSS_FWET_LIQ [1]", color=COLOR_MUTED, fontsize=9)
    axes[1].set_ylabel("days", color=COLOR_MUTED, fontsize=9)
    axes[1].set_title(
        "Distribution of the liquid wetness proxy", color=COLOR_TEXT, fontsize=11, loc="left"
    )

    axes[2].plot(day, leafc, color=COLOR_SERIES[2], linewidth=2.0, zorder=3)
    axes[2].set_xlabel("day of run", color=COLOR_MUTED, fontsize=9)
    axes[2].set_ylabel("moss FATES_LEAFC_PF [kg m-2]", color=COLOR_MUTED, fontsize=9)
    axes[2].set_title(
        "Moss leaf biomass over the run", color=COLOR_TEXT, fontsize=11, loc="left"
    )
    if (leafc > 0).any() and not (leafc > 0).all():
        gone = int(np.nonzero(leafc <= 0)[0][0])
        axes[2].axvline(gone + 1, color=COLOR_MUTED, linewidth=1.0, linestyle="--")
        axes[2].annotate(
            f"zero from day {gone + 1}",
            xy=(gone + 1, np.nanmax(leafc) * 0.6),
            xytext=(6, 0),
            textcoords="offset points",
            color=COLOR_MUTED,
            fontsize=9,
        )

    fig.tight_layout()
    path = os.path.join(out_dir, f"{tag}_moss_gpp_fwet.png")
    fig.savefig(path, dpi=140, facecolor=COLOR_SURFACE)
    plt.close(fig)
    return path


# ---------------------------------------------------------------------------------------


def case_tag(run_dir, reserve=0):
    """The case name, verbatim where the filesystem allows it, for naming this run's outputs.

    An output file has to be traceable to the run that produced it by reading its name, so
    the tag is the case directory's own name rather than a digest of it. CIME test names are
    long -- around 160 characters for the moss ALP2 tests -- but a filename component may be
    255, so the full name normally fits and is kept intact, dots and all. Only characters a
    path cannot carry are replaced.

    `reserve` is how many characters the caller will append. If the name plus that reserve
    would not fit, the tag is cut to fit and a digest of the whole name is appended, so the
    result stays unique; that is a fallback for a pathological case name, not the usual path.
    """
    case = os.path.basename(os.path.dirname(os.path.abspath(run_dir)))
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", case).strip("-.") or "case"
    limit = 255 - reserve
    if len(safe) <= limit:
        return safe
    digest = hashlib.md5(case.encode()).hexdigest()[:8]
    return f"{safe[: max(0, limit - 9)]}-{digest}"


def main():
    parser = argparse.ArgumentParser(
        description=HELP_DESCRIPTION,
        epilog=HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "run_dir",
        help="A finished case's run/ directory, holding the daily *.clm2.h0a.*.nc files.",
    )
    parser.add_argument(
        "--pft-moss",
        type=int,
        default=15,
        help="1-based moss PFT index on the fates_levpft axis. Default: 15",
    )
    parser.add_argument(
        "--pft-grass",
        type=int,
        default=12,
        # Why 12 is not a general default, and what happens when the index cannot be
        # confirmed, is said by the WARN that fires in that case -- where it is actually
        # needed -- rather than here.
        help="1-based grass PFT index on the fates_levpft axis. Default: 12. Nothing "
        "PASSes or FAILs on it.",
    )
    parser.add_argument(
        "--out-dir",
        default=os.getcwd(),
        help="Where the PNGs go. Default: the directory you invoked the script from.",
    )
    parser.add_argument(
        "--cache-dir",
        help="Optional directory for a .npz cache of the concatenated history, so a "
        "re-run does not reopen several hundred files.",
    )
    parser.add_argument(
        "--no-plots", action="store_true", help="Run the checks; write no PNGs."
    )
    args = parser.parse_args()

    if not os.path.isdir(args.run_dir):
        raise FileNotFoundError(f"run_dir does not exist: {args.run_dir}")

    data, files = load_history(args.run_dir, args.cache_dir)
    nday = len(files)
    moss, grass = args.pft_moss - 1, args.pft_grass - 1

    # These five are the ones the script cannot run at all without: they are indexed
    # unconditionally. Everything else a check indexes directly is looked for by the check
    # itself, which SKIPs rather than raising KeyError -- a tape written by an older testmod,
    # or a tape from a configuration that never registers a variable, should not stop the
    # run. FATES_NOCOMP_PATCHAREA_PF used to be a fourth entry here and is not one any more,
    # because a run may legitimately have none and the checks that need it now SKIP;
    # FATES_MOSS_WETNESS_SCALER came off the list for the same reason, its only consumer
    # being a check that SKIPs.
    for name in (
        "FATES_MOSS_FWET_LIQ",
        "FATES_MOSS_FWET_TOT",
        "FATES_MOSS_FWET_SOIL_LIQ",
        "FATES_MOSS_FWET_SOIL_TOT",
        "FATES_MOSS_FWET_CANOPY",
    ):
        if name not in data:
            raise HistoryContentError(
                f"{name} is not on this tape. This script expects a moss run with the moss "
                "history variables in hist_fincl1."
                + (
                    " This tape carries FATES_MOSS_FWET instead, so it was written before "
                    "the moss wetness proxy was split into liquid and total proxies, which "
                    "this script no longer reads."
                    if "FATES_MOSS_FWET" in data
                    else ""
                )
            )
    npft = pft_axis_length(files, data)
    if not 0 <= moss < npft or not 0 <= grass < npft:
        raise HistoryContentError(
            f"--pft-moss {args.pft_moss} / --pft-grass {args.pft_grass} out of range for "
            f"a fates_levpft axis of length {npft}."
        )
    if moss == grass:
        raise HistoryContentError(
            f"--pft-moss and --pft-grass both name PFT {args.pft_moss}."
        )

    namelist = dict(DEFAULT_NAMELIST)
    run_namelist = read_lnd_in(args.run_dir)
    namelist_source = "configured namelist defaults (lnd_in not readable)"
    if any(key in run_namelist for key in DEFAULT_NAMELIST):
        namelist.update({k: v for k, v in run_namelist.items() if k in DEFAULT_NAMELIST})
        namelist_source = "this run's lnd_in"

    config = RunConfig(run_namelist)
    paramfile = run_namelist.get("fates_paramfile")
    params = read_params(
        paramfile,
        (
            "fates_fire_miner_total",
            "fates_vascular",
            "fates_fire_SAV",
            "fates_woody",
            "fates_recruit_height_min",
            "fates_allom_d2h1",
            "fates_allom_d2h2",
            "fates_allom_dbh_maxheight",
        ),
    )
    # The moss-index values of the allometry parameters the Task 12 Step 3c and 3d reference
    # numbers are made of. Read here rather than assumed, so a retuned moss parameter file
    # gets its own numbers instead of the ones this script was written beside.
    moss_params = {
        name: float(params[name][moss])
        for name in (
            "fates_recruit_height_min",
            "fates_allom_d2h1",
            "fates_allom_d2h2",
            "fates_allom_dbh_maxheight",
        )
        if name in params and params[name].size > moss
    }
    treelai_mismatch = treelai_prediction_mismatch(paramfile, moss)
    miner = params.get("fates_fire_miner_total")
    if miner is not None and miner.size:
        miner_total, miner_source = float(miner[0]), "this run's FATES parameter file"
    else:
        miner_total, miner_source = DEFAULT_MINER_TOTAL, "the configured FATES default"
    sav = params.get("fates_fire_SAV")
    sav_source = "this run's FATES parameter file"

    # The canopy ingredient's structural ceiling, read from the run's own CLM parameter file
    # rather than assumed: it is a tuning candidate on this branch, and how much of what the
    # Task 8 canopy INFO says survives raising it is exactly the question a reader has.
    host = read_params(
        run_namelist.get("paramfile"), ("maximum_leaf_wetted_fraction",)
    ).get("maximum_leaf_wetted_fraction")
    if host is not None and host.size:
        leaf_cap, leaf_cap_source = float(host[0]), "this run's CLM parameter file"
    else:
        leaf_cap, leaf_cap_source = (
            DEFAULT_MAX_LEAF_WETTED_FRACTION,
            "the standard CLM parameter file, not this run's, which could not be read",
        )

    veg_frac, no_veg_frac_reason, veg_frac_source, patch_area = non_bareground_fraction(
        data, config, nday
    )

    validation, pft_confirmed, pft_reasons, pft_warnings = validate_pft_moss(
        data, moss, npft, params
    )
    grass_line, grass_confirmed = validate_pft_grass(
        read_pft_names(paramfile, npft), params, grass, npft
    )

    units = NativeUnits(
        data, veg_frac, veg_frac_source, no_veg_frac_reason, patch_area, moss
    )

    case = os.path.basename(os.path.dirname(os.path.abspath(args.run_dir)))
    when = dates(data, nday, files)
    print(f"{nday} daily history files from")
    print(f"  {case}")
    print(f"  first {when[0]}, last {when[-1]}")
    print(f"  moss PFT {args.pft_moss}, grass PFT {args.pft_grass}")
    if config.readable:
        print(f"  {config.settings_phrase()}")
    else:
        print("  this run's lnd_in could not be read, so nothing here comes from its "
              "namelist")
    for line in validation:
        print(f"  {line}")
    print(f"  {grass_line}")
    print()
    print(units.preamble())
    print()
    print(
        "A number that came off a parameter file or a namelist is always written here as "
        "name = value\n(source). A bare decimal is therefore something this run produced."
    )
    print()
    if not pft_confirmed:
        print_warning(unverified_warning(args.pft_moss, pft_reasons))
        print()

    report = Reporter()
    for label, detail in pft_warnings:
        report.warn(label, detail)
    if not grass_confirmed:
        report.warn(
            "The grass PFT index is unconfirmed, so the grass-labelled numbers below may "
            "be about some other PFT",
            f"{grass_line}.\n"
            "Nothing keys off the grass index the way FATES's moss code keys off "
            "fates_vascular, so there is no tape witness for it and no equivalent of the "
            "moss abort: --pft-grass is taken on trust. Its default of 12 is a property of "
            "the surface datasets the ALP2 moss testmods use and of nothing more general.\n"
            "What rests on it: the grass columns that give moss GPP and moss fuel loading "
            "a scale, and the grass line of the prescribed-cover report. Nothing else, and "
            "no PASS or FAIL anywhere.",
        )
    fwet = data["FATES_MOSS_FWET_LIQ"]

    fuel_amount = data.get("FATES_FUEL_AMOUNT_FC")
    fuel_moisture = data.get("FATES_FUEL_MOISTURE_FC")

    # Whether SPITFIRE ran is a namelist fact, and gating on the namelist rather than on the
    # tape is the point. The old gate asked whether the fuel arrays were all zero, which
    # would SKIP precisely the run Task 9 exists to catch -- a SPITFIRE run whose moss fuel
    # moisture came back zero -- and would take Tasks 6 and 7 down with it, neither of which
    # has anything to do with moisture. Under SPITFIRE an all-zero fuel array now FAILs.
    if config.spitfire_on is not None:
        spitfire_on = config.spitfire_on
        gate_note = ""
    else:
        spitfire_on = fuel_moisture is not None and bool(np.any(fuel_moisture != 0.0))
        gate_note = (
            " This run has no readable lnd_in, so that was inferred from the fuel arrays on "
            "the tape -- which is also what a genuine SPITFIRE failure would look like, so "
            "read it as a guess rather than as the configuration."
        )
    fire_status = fire_status_sentence(config, spitfire_on, gate_note)

    # Raised before the first check rather than beside the checks it degrades: it changes
    # what several labels below mean, and a reader who meets it afterwards has already read
    # them.
    if veg_frac is None:
        report.warn(
            "No non-bareground area fraction: the area-weighted checks are degraded",
            f"{no_veg_frac_reason}\n"
            "SKIPPED, because the area fraction is the whole content of the identity: the "
            "above-threshold half of the wetness-scaler identity in section 2; the "
            "crossing-point half of each moss fuel-moisture check in section 4, where the "
            "configured intercept is nonzero; the reading of how often moss sits past its "
            "moisture of extinction; and the prescribed-cover report.\n"
            "STILL RUN, because the weighting cancels out of them: the proxy identities in "
            "section 1, both fuel-loading identities in section 3, the below-threshold half "
            "of section 2, which is what pins the threshold, the slope and R^2 halves of "
            "the fuel-moisture checks, the fire-weather contrast, and all of section 5.\n"
            "DEGRADED IN DISPLAY ONLY: every moss-native number below falls back to the "
            "tape's site value, each carrying a note saying so. Nothing is dropped for it.",
        )
    elif veg_frac_source is not None and "FATES_NOCOMP_PATCHAREA_PF" not in data:
        report(
            "INFO",
            "Does this run need an area conversion at all?",
            f"No. The non-bareground area fraction is {veg_frac_source} "
            f"({config.settings_phrase()}). FATES makes a bareground patch only under "
            "nocomp AND fixed biogeography (main/EDInitMod.F90:841), so on this run the "
            "patch areas sum to AREA, moss is in every patch, and each site value IS the "
            "moss-native value.\n"
            "FATES_NOCOMP_PATCHAREA_PF is not on this tape and does not need to be: every "
            "area-weighted check below runs in full, with the same arithmetic a nocomp tape "
            "gets and the factor equal to one. Nothing is degraded and nothing is skipped "
            "for want of a patch area.",
        )

    precondition_preamble, precondition, commutation_warning = commutation_watch(
        data, veg_frac, leaf_cap, leaf_cap_source
    )

    # ---------------------------------------------------------------------------------
    print_section(1, precondition_preamble)
    if commutation_warning:
        report.warn(
            "The branch-uniformity precondition of the proxy and scaler identities is no "
            "longer safe on this run",
            commutation_warning,
        )
    check_task8_proxy(report, data, units, precondition, leaf_cap, leaf_cap_source)

    # ---------------------------------------------------------------------------------
    print_section(2)
    check_task10_scaler(
        report,
        data,
        units,
        namelist["fates_moss_vcmax_fwet_thresh"],
        namelist_source,
        precondition,
        no_veg_frac_reason,
    )
    gpp = check_moss_productivity(report, data, units, patch_area, moss, grass, fwet)

    if fuel_amount is None or fuel_moisture is None:
        reason = "FATES_FUEL_AMOUNT_FC or FATES_FUEL_MOISTURE_FC is not on this tape."
    elif not spitfire_on:
        reason = (
            f"SPITFIRE did not run in this case ({config.settings_phrase()}), so there is "
            "no fuel state to test." + gate_note
        )
    else:
        reason = None
    moisture_checks_ran = reason is None

    # ---------------------------------------------------------------------------------
    print_section(3)
    litter_unset = check_mossfines_sentinel(report, data)
    if reason is not None:
        report("SKIP", LIVE_MOSS_LOADING, reason)
        report("SKIP", DEAD_MOSS_LOADING, reason)
    else:
        if absent(data, "FATES_LIVEMOSS_FUEL"):
            report("SKIP", LIVE_MOSS_LOADING, "FATES_LIVEMOSS_FUEL is not on this tape.")
        else:
            check_task6_livemoss(
                report, data, units, moss, fuel_amount, miner_total, miner_source,
            )
        if litter_unset or absent(data, "FATES_MOSS_FINES"):
            # Two checks go, so two SKIPs are printed. Folding them into one would drop the
            # accumulation check off the tally with no line of its own saying it was not
            # made, which reads as a check that never existed.
            why = (
                "FATES_MOSS_FINES is the unset-litter sentinel; see the INFO above."
                if litter_unset
                else "FATES_MOSS_FINES is not on this tape."
            )
            report("SKIP", DEAD_MOSS_LOADING, why)
            report("SKIP", DEAD_MOSS_ACCUMULATES, why)
        else:
            check_task7_mossfines(
                report, data, units, fuel_amount, miner_total, miner_source
            )

    # ---------------------------------------------------------------------------------
    print_section(4)
    if reason is not None:
        report("SKIP", MOSS_MOISTURE_MAP, reason)
    else:
        check_task9_moisture(
            report, data, units, fuel_moisture, namelist, namelist_source, sav,
            sav_source, no_veg_frac_reason, fire_status,
        )

    # What the moss fuel-moisture checks were and were not able to distinguish in this run.
    # Both are properties of the parameters this run was given, so both are asked whether or
    # not the checks themselves ran; the tape columns only settle the second where SPITFIRE
    # actually produced them, and whether the checks ran changes only the wording, since a
    # warning about a fit that is not in the output points the reader at nothing.
    warn_sav_degeneracy(report, sav, sav_source, moisture_checks_ran)
    warn_live_dead_degeneracy(
        report,
        namelist,
        namelist_source,
        fuel_moisture if spitfire_on else None,
        sav,
        sav_source,
        moisture_checks_ran,
    )
    warn_fire_status(report, data, config, spitfire_on, gate_note)
    check_fire_occurred(report, data, fire_status)
    if absent(data, "FATES_FUEL_BURNT_BURNFRAC_FC"):
        report("SKIP", FUEL_BURNT, "FATES_FUEL_BURNT_BURNFRAC_FC is not on this tape.")
    else:
        check_fuel_burnt(report, data, fire_status)

    # ---------------------------------------------------------------------------------
    print_section(5)
    check_moss_structure(
        report, data, units, moss, grass, args.pft_moss, args.pft_grass,
        bool(config.use_sp), patch_area, moss_params, treelai_mismatch,
    )
    check_moss_population(report, data, units, moss, when)

    if args.no_plots:
        pass
    elif gpp is None or absent(data, "FATES_LEAFC_PF"):
        print("Skipped the plots: FATES_GPP_PF or FATES_LEAFC_PF is not on this tape.\n")
    else:
        os.makedirs(args.out_dir, exist_ok=True)
        path = make_plots(
            data, moss, fwet, gpp, args.out_dir,
            case_tag(args.run_dir, reserve=len("_moss_gpp_fwet.png")),
        )
        print(f"Wrote {path}\n")

    exit_code = report.verdict()
    if not pft_confirmed:
        # Repeated here because the preamble it was first printed in is several hundred
        # lines up by now, and because this is the line that says the verdict above is not
        # a verdict. It outranks a FAIL: a FAIL is a result about moss, and there is no
        # evidence here that any of these results are about moss.
        print()
        print_warning(unverified_warning(args.pft_moss, pft_reasons))
        return EXIT_NO_VERDICT
    return exit_code


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (HistoryContentError, FileNotFoundError) as error:
        # These are all "you pointed this at the wrong thing, or told it the wrong thing
        # about what it is pointed at". A traceback buries the sentence that says which.
        print(f"\nverify_moss_history: {error}", file=sys.stderr)
        sys.exit(EXIT_NO_VERDICT)
    except Exception:
        # Anything else is a defect in this script or in the environment it was given: a
        # tape whose fuel axis is shorter than the eight classes indexed here, a missing
        # matplotlib. It gets its own code because exiting 1 would have a caller read a
        # crash as a FAILed check, and it keeps its traceback because that is what it
        # takes to fix one.
        traceback.print_exc()
        print(
            "\nverify_moss_history: the traceback above is an unexpected error inside this "
            "script, not a result about the run.",
            file=sys.stderr,
        )
        sys.exit(EXIT_INTERNAL_ERROR)
