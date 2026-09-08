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

One check here can FAIL for a reason that is not about the diagnostics. The moss-population
check (Task 12 Step 3) fails when moss never carries any biomass at all, and when it carries
some, reaches zero and is never recruited back. Both are science findings about the model
configuration, not broken identities, and both still drive exit code 1 -- which a caller will
read as "the diagnostics are broken". It is deliberately left that way, because it is the one
result here that must not be scrolled past. On a run in which moss persists that check is an
INFO and does not move the exit code at all. A caller that wants only the identity checks has
to read the labels rather than the exit code. The rest of the scheme is under "Exit codes",
at the end of this docstring.

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
  Task 8   FATES_MOSS_FWET is exactly the wetter of its two ingredients, and never below
           either. Also reports how often the canopy ingredient actually sets the proxy.
  Task 10  FATES_MOSS_WETNESS_SCALER is the shipped wetness map, in the two halves the
           area weighting splits it into: below the plateau the weight cancels and the
           scaler is exactly fwet/threshold, which is what pins the threshold; on the
           plateau it is exactly the non-bareground area fraction, and the naive
           min(1, fwet/threshold) is wrong there by that factor. Also how much of the run
           sits on the plateau.
  Task 6   The live-moss fuel class carries the live-moss biomass FATES_LIVEMOSS_FUEL
           reports, and live grass and live moss are reported side by side.
  Task 7   The dead-moss fuel class carries the dead-moss litter FATES_MOSS_FINES reports,
           and that pool is nonzero and accumulates.
  Task 9   Both moss fuel classes' moisture is an exact linear function of the moss
           wetness proxy and of nothing else, with the fitted slope pinned against the
           shipped map and against a moisture of extinction that does not come out of the
           fit, and the crossing point pinned against the shipped intercept -- which at the
           shipped intercept of zero says only that there is no offset; the non-moss classes
           still track the Nesterov index. Also how often moss sits at or above its
           moisture of extinction.
  Task 10b Moss leaf and stem area, per unit land and per unit crown area, and moss crown
           area against the prescribed nocomp patch area where the tape carries one.
  Task 12  Prescribed cover, moss mortality, whether any fire occurred, and -- the part
           worth the most attention -- what the moss population actually did over the run.

What this script CANNOT establish
---------------------------------
Two of the things the verification plan asks for are not answerable from one run's h0a tape
by any script, and this script says so rather than substituting a proxy. Neither is a
property of the run in front of it, so neither can be redeemed by a better run:

  * Anything that is a comparison between two runs. That moss fuel loading MOVED out of the
    live-grass class rather than being added alongside it is a statement about the
    difference between this run and a pre-Task-6 run (Task 6). That perturbing the moss
    fuel-moisture coefficients changes fire behaviour is a statement about the difference
    between this run and one with different coefficients (Task 12 Step 3). A single tape
    holds one side of each.

  * An error in FATES's own moisture-of-extinction formula. The Task 9 slope has to be
    checked against an MEF that does not come out of the fit, and the only one available is
    the one this script computes by reproducing MoistureOfExtinction
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
WARNs saying which and why. What is lost is the plateau half of the Task 10 scaler identity,
the crossing-point half of Task 9 where the shipped intercept is nonzero (at the shipped
intercept of zero that half constrains nothing extra whatever the area fraction is, and the
check says so at runtime), the patch-level readings of moss extinction and of the canopy
ceiling, and the prescribed-cover report. What survives is every identity whose area
weighting cancels -- Tasks 6, 7, 8, the sub-plateau half of Task 10, the Task 9 slope,
Task 10b and Task 12.

Two conversion factors between tape and check
--------------------------------------------
Both are commented again at the check that uses them, because both will read as arbitrary
to anyone who has not been told why they are there.

  1. Almost every site-level moss diagnostic is area-weighted over patches with bareground
     contributing zero, so a site-level value is the patch value times the non-bareground
     area fraction (0.8, say, in a bare+grass+moss nocomp configuration -- the factor is
     read from FATES_NOCOMP_PATCHAREA_PF, or is 1.0 on a run whose configuration gives it
     no bareground patch, and either way it is printed in the preamble with its source and
     never assumed). Any identity between two site-level quantities that is nonlinear in
     the patch value (the proxy's max(), the wetness scaler's min(), the "is moss above its
     moisture of extinction" threshold) has to account for that.

     Neither max() nor min() commutes with an area-weighted sum in general. Pushing the
     area weight through one of them is therefore a PRECONDITION of those identities, not
     an observation about any run: they hold only while the same branch is taken on every
     vegetated patch -- the same ingredient wins on all of them, or all of them sit on the
     same side of the threshold. A site-level tape cannot test that, since it has already
     summed the patches away. What it can do is watch the one quantity that decides it. The
     proxy's two ingredients are asymmetric: the soil one is a column-level saturation and
     is therefore the same number on every patch of the site, while the canopy one is
     CTSM's per-patch fwet_veg, hard-capped at maximum_leaf_wetted_fraction
     (src/fates/biogeochem/FatesPatchMod.F90:907-914). So while the soil ingredient stays
     clear of that cap, the proxy is identical on every vegetated patch, both branches are
     uniform by construction, and both identities are safe. Each check reports that margin,
     and WARNs when it narrows to where per-patch divergence becomes possible.

     A FAIL on one of those identities is much more likely to be branches that diverged
     across patches than a model defect, and each of them says so in its own FAIL text.

     FATES_MOSS_HEIGHT is the exception to the area weighting. It is accumulated as a
     crown-area weighted sum and then divided by the MOSS CROWN AREA rather than by land
     area (main/FatesHistoryInterfaceMod.F90:3068-3074, :3120-3124), so it is already a
     height and must not be given the factor. Nothing is computed wrong either way; the
     point is only that the factor is not universal, and this is the paragraph a reader
     would otherwise use to decide that it is.

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
     from the run's own parameter file and printed by the check. See the Task 6 check for
     the file:line.

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
import traceback

import netCDF4
import numpy as np

# The exit-code scheme is written down once, as the last section of the module docstring.
# --help gets that section as its epilog -- after the options, which is where a reader
# hunting for it will be -- rather than a second copy of it inside the description.
_DESCRIPTION, _EXIT_HEADING, _EXIT_BODY = __doc__.partition("Exit codes\n----------\n")
HELP_DESCRIPTION = _DESCRIPTION.rstrip()
HELP_EPILOG = _EXIT_HEADING + _EXIT_BODY

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
# wetness proxy cannot exceed this at patch level. Used only when the run's own CLM
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
    "the model, and is the first thing to suspect. See the margin reported below."
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
        for line in str(detail).splitlines():
            print(f"       {line}")
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
        for line in str(detail).splitlines():
            print(f"       {line}")
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
            print(f"       {why}")
        if self.warnings:
            print()
            print(
                f"{len(self.warnings)} WARNING(S) about this run. None of them bears on the "
                "tallies above or on the exit code; each says that something the labels "
                "above appear to claim was not actually established here."
            )
            for label, detail in self.warnings:
                print(f"  [WARN] {label}")
                for line in detail.splitlines():
                    print(f"         {line}")
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
        key = hashlib.md5(f"{os.path.abspath(run_dir)}:{stamp}".encode()).hexdigest()
        cache_path = os.path.join(cache_dir, f"moss_hist_{key[:16]}.npz")
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

    Returns {} if lnd_in is absent, in which case the caller falls back to the shipped
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
# Checks
# ---------------------------------------------------------------------------------------


def commutation_watch(data, veg_frac, leaf_cap, leaf_cap_source):
    """How safe the max()/min() commutation preconditions of Tasks 8 and 10 are here.

    Both identities need every vegetated patch to take the same branch, and a site-level
    tape has already summed the patches away, so neither can be tested directly. One
    quantity decides both, and it can be watched. The proxy is max(soil saturation, canopy
    wetted fraction) per patch (FatesPatchMod.F90:UpdateMossFwet). The soil ingredient comes
    from the column -- bc_in%h2o_liqvol_sl(1) and the column's porosity -- so it is the same
    number on every patch of the site. The canopy ingredient is CTSM's per-patch fwet_veg,
    which CTSM caps at maximum_leaf_wetted_fraction. While the soil ingredient stays above
    that cap, the soil ingredient wins on every patch, the proxy is identical on every
    patch, and both branches are uniform whatever the threshold is. That is what makes the
    two identities safe, and losing it is what would make them fail for a reason that is not
    a model defect.

    The margin is reported in PATCH units, since that is where the cap lives, and the site
    value is the patch value times the non-bareground area fraction. Without that fraction
    the site-level soil value is used instead: it is the patch value times a fraction no
    greater than 1, so it understates the true clearance and the watch stays conservative.

    Returns (headline, warning or None).
    """
    soil = data["FATES_MOSS_FWET_SOIL"]
    canopy = data["FATES_MOSS_FWET_CANOPY"]

    if veg_frac is None:
        floor = float(np.nanmin(soil))
        floor_units = (
            "site units, a lower bound on the patch value because the non-bareground area "
            "fraction is not on this tape"
        )
        observed_ceiling = float(np.nanmax(canopy))
    else:
        floor = float(np.nanmin(divide_by_fraction(soil, veg_frac)))
        floor_units = "patch units"
        observed_ceiling = float(np.nanmax(divide_by_fraction(canopy, veg_frac)))

    # The comparison carries a tolerance because the observed ceiling has been through a
    # division by the area fraction, and a canopy ingredient sitting exactly on the cap all
    # run comes back a few ulps above it.
    if leaf_cap is not None and observed_ceiling <= float(leaf_cap) * (1.0 + TOL_RELATIVE):
        ceiling, ceiling_what = float(leaf_cap), (
            f"CTSM's maximum_leaf_wetted_fraction, {leaf_cap:g} ({leaf_cap_source}), which "
            "no patch's canopy ingredient can exceed"
        )
    elif leaf_cap is not None:
        # The cap is only a bound while it describes the run. A canopy ingredient reported
        # above it means it does not -- a different host, a changed parameter file, a
        # variable that is not what this script takes it for -- and the tape wins.
        ceiling, ceiling_what = observed_ceiling, (
            f"the largest canopy value this run reached, {observed_ceiling:.4f}, which is "
            f"ABOVE the maximum_leaf_wetted_fraction of {leaf_cap:g} read from "
            f"{leaf_cap_source}. That cap does not describe this tape, so it is not trusted "
            "as a bound here"
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
    headline = (
        f"PRECONDITION (of the identity, not an observation about this run): the branch "
        f"the area weight is pushed through has to be the same on every vegetated patch, "
        f"and a site-level tape cannot test that. What is watched instead: the soil "
        f"ingredient of the proxy never falls below "
        f"{floor:.4f} ({floor_units}), against a canopy ingredient bounded by "
        f"{ceiling_what}. {margin} the soil ingredient wins on "
        f"every patch and the proxy is uniform across them."
        if clear
        else (
            f"PRECONDITION (of the identity, not an observation about this run): the branch "
            f"the area weight is pushed through has to be the same on every vegetated "
            f"patch, and a site-level tape cannot test that. The margin that would make it "
            f"safe has NARROWED here -- see the WARN."
        )
    )
    if clear:
        return headline, None
    return headline, (
        f"The moss wetness proxy's soil ingredient no longer stays clear of its canopy one "
        f"in this run: the soil ingredient falls to {floor:.4f} ({floor_units}) while the "
        f"canopy ingredient is bounded only by {ceiling_what}. That is a ratio of "
        f"{ratio:.2f}.\n"
        "Two site-level identities are built on those never crossing on any single patch -- "
        "Task 8's max() and Task 10's min(), neither of which commutes with the area-"
        "weighted sum that puts these quantities on the tape. While the soil ingredient is "
        "clear of the canopy ceiling the proxy is the same number on every vegetated patch "
        "and both identities are safe by construction. That clearance is now inside the "
        f"factor of {COMMUTATION_MARGIN_FACTOR:g} this script asks for, so a day on which "
        "the branch differs between two patches of this site is no longer implausible.\n"
        "Nothing here says either identity DID break -- read their PASS/FAIL above. What it "
        "says is that a FAIL on either can no longer be assumed to be a model defect, and "
        "that a PASS is now a weaker statement than it looks."
    )


def check_task8_proxy(report, data, veg_frac, commutation, leaf_cap, leaf_cap_source):
    """Task 8: the proxy is the wetter of its two ingredients, and never below either."""
    fwet = data["FATES_MOSS_FWET"]
    soil = data["FATES_MOSS_FWET_SOIL"]
    canopy = data["FATES_MOSS_FWET_CANOPY"]

    deviation = float(np.nanmax(np.abs(fwet - np.maximum(soil, canopy))))
    ok = deviation < TOL_EXACT
    report(
        "PASS" if ok else "FAIL",
        "Task 8: FATES_MOSS_FWET == max(FATES_MOSS_FWET_SOIL, FATES_MOSS_FWET_CANOPY)",
        ("" if ok else DIVERGENCE_FIRST_SUSPECT + "\n")
        + f"max |deviation| = {deviation:.3e}\n"
        f"proxy  {np.nanmin(fwet):.4f} - {np.nanmax(fwet):.4f}\n"
        f"soil   {np.nanmin(soil):.4f} - {np.nanmax(soil):.4f}\n"
        f"canopy {np.nanmin(canopy):.4f} - {np.nanmax(canopy):.4f}"
        + coverage_note(len(fwet), fwet, soil, canopy)
        + "\n"
        + commutation,
    )

    below = int(np.sum((fwet < soil - TOL_EXACT) | (fwet < canopy - TOL_EXACT)))
    report(
        "PASS" if below == 0 else "FAIL",
        "Task 8: the proxy is never below either ingredient",
        f"days below one of its ingredients: {below} of {len(fwet)}\n"
        "Unlike the identity above this one is structural: a sum of max(a_p, b_p) weighted "
        "by non-negative areas is at least the same sum of a_p, and at least the same sum "
        "of b_p, whatever each patch does. A FAIL here would mean a corrupt tape."
        + coverage_note(len(fwet), fwet, soil, canopy),
    )

    canopy_binds = int(np.sum(canopy > soil))
    canopy_max = float(np.nanmax(canopy))
    soil_lo, soil_hi = float(np.nanmin(soil)), float(np.nanmax(soil))
    at_max = int(np.sum(np.isclose(canopy, canopy_max)))
    lines = [
        f"canopy sets the proxy (canopy > soil) on {canopy_binds} of {len(fwet)} days",
        f"canopy is nonzero on {100 * np.mean(canopy > 0):.0f}% of days and sits at its own "
        f"maximum ({canopy_max:.4f}) on {at_max} of them",
    ]
    if veg_frac is not None:
        lines.append(
            f"in patch units that maximum is {canopy_max / float(np.mean(veg_frac)):.4f}; "
            f"the site value is that times the non-bareground area fraction "
            f"{float(np.mean(veg_frac)):.4f}"
        )
    canopy_spike, soil_spike = spikiness(canopy), spikiness(soil)
    lines.append(
        f"day-to-day |delta| max/mean: canopy {canopy_spike:.1f}, soil {soil_spike:.1f}"
        if np.isfinite(canopy_spike) and np.isfinite(soil_spike)
        else "day-to-day |delta| max/mean: not defined on this tape -- there are no "
        "day-to-day steps to take a ratio of"
    )

    # Task 8 Step 4 asks for a correlation between the canopy ingredient and rain events.
    # Whether that is worth computing is a question about THIS run, not about the model: it
    # turns on whether the canopy ingredient ever wins, which turns on where CTSM's
    # maximum_leaf_wetted_fraction sits relative to this site's soil saturation. That
    # parameter is a global scalar on the host parameter file and a tuning candidate on this
    # branch, so the conclusion is stated against the value the run actually used.
    cap_phrase = (
        f"CTSM's maximum_leaf_wetted_fraction, {leaf_cap:g} ({leaf_cap_source})"
        if leaf_cap is not None
        else "CTSM's maximum_leaf_wetted_fraction, which could not be read from this run"
    )
    if canopy_binds == 0:
        # Whether RAIN is on the tape is a fact about this tape, so it is read off the tape
        # rather than asserted from what a FATES-SP field list usually carries.
        rain_note = (
            "Nothing is blocking the correlation itself -- RAIN is on this tape."
            if "RAIN" in data
            else "RAIN is not on this tape either, so the correlation could not have been "
            "computed here in any case; put RAIN in hist_fincl1 if the ceiling below is "
            "ever raised."
        )
        lines.append(
            f"RAIN EVENTS (Task 8 Step 4): the canopy ingredient tops out at "
            f"{canopy_max:.4f} against a soil ingredient spanning {soil_lo:.4f} - "
            f"{soil_hi:.4f}, so it never "
            "sets the proxy in this run and a correlation between it and rain would say "
            f"nothing about the proxy here. {rain_note} What makes it "
            f"pointless is the ceiling, which is {cap_phrase}. Raise that above this site's "
            "soil saturation floor and the limitation dissolves, so this is a statement "
            "about the run in front of you and not one about the design."
        )
    else:
        rain = (
            f" corr(RAIN, canopy ingredient) = {correlation(data['RAIN'], canopy):+.3f}."
            if "RAIN" in data
            else " RAIN is not on this tape, so it is not computed here."
        )
        lines.append(
            f"RAIN EVENTS (Task 8 Step 4): the canopy ingredient DOES set the proxy, on "
            f"{canopy_binds} of {len(fwet)} days, so unlike a run in which it is pinned "
            f"below the soil ingredient by {cap_phrase}, the rain-event correlation this "
            "step asks for is meaningful on this tape and worth computing." + rain
        )
    report(
        "INFO",
        "Task 8: is the canopy ingredient event-driven, and does it ever matter?",
        "\n".join(lines) + coverage_note(len(fwet), fwet, soil, canopy),
    )

    # An ingredient that never wins is exactly the class of thing the WARN channel exists
    # for: a path this run never exercised, which no PASS above can carry, and which is a
    # property of the run rather than of the design. Raised after the INFO so the numbers it
    # refers to are already on the screen.
    if canopy_binds == 0:
        report.warn(
            "The canopy ingredient never sets the moss wetness proxy in this run",
            f"FATES_MOSS_FWET_CANOPY tops out at {canopy_max:.4f} while "
            f"FATES_MOSS_FWET_SOIL spans {soil_lo:.4f} - {soil_hi:.4f}, so on all "
            f"{len(fwet)} days of this run the proxy is the soil ingredient and nothing "
            "else.\n"
            "The Task 8 identity above therefore PASSes on max(a, b) == a: the canopy branch "
            "of UpdateMossFwet was never taken, and neither the canopy ingredient's own "
            "arithmetic nor its effect on anything downstream of the proxy -- the Task 10 "
            "scaler, moss GPP -- is under test here at all. Task 8 Step 4's rain-event "
            "correlation is untestable for the same reason.\n"
            f"The ceiling that does it is {cap_phrase}. That is a property of THIS run: "
            "raise it above this site's soil saturation floor, or run a drier site, and the "
            "canopy branch starts being exercised with nothing else changed.",
        )


def check_task10_scaler(
    report, data, veg_frac, threshold, threshold_source, commutation, no_veg_frac_reason
):
    """Task 10: the wetness scaler is the shipped wetness map, in its two halves.

    The area weighting is the whole subtlety here. Per patch the scaler is
    min(1, fwet_patch/threshold). Both the scaler and the proxy reach history as
    sums of patch values weighted by patch area, with bareground contributing zero
    to each, so each site value is its patch value times `veg_frac`, the non-bareground
    area fraction. Pushing that weight through the min gives

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
        for label in (
            "Task 10: below the plateau the scaler is FATES_MOSS_FWET / threshold",
            "Task 10: on the plateau the scaler is the non-bareground area fraction",
        ):
            report("SKIP", label, "FATES_MOSS_WETNESS_SCALER is not on this tape.")
        return

    scaler = data["FATES_MOSS_WETNESS_SCALER"]
    fwet = data["FATES_MOSS_FWET"]
    nday = len(fwet)
    ratio = fwet / threshold

    if veg_frac is None:
        bound = float(np.nanmax(scaler)) if np.any(np.isfinite(scaler)) else 0.0
        if bound <= 0.0:
            # The lower bound on the area fraction is the largest scaler the run reached, so
            # a scaler that never leaves zero leaves no bound and no day that can be called
            # sub-plateau. That is a check that could not be made, not one that failed.
            for label in (
                "Task 10: below the plateau the scaler is FATES_MOSS_FWET / threshold",
                "Task 10: on the plateau the scaler is the non-bareground area fraction",
            ):
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
            f"below-the-kink days are the {{n}} on which fwet/{threshold} falls under "
            f"{bound:.4f}, the largest scaler this run reached, which is a lower bound on "
            "the non-bareground area fraction (the scaler is at most that fraction every "
            "day). The area fraction itself is not on this tape"
        )
        sub = ratio < bound * (1.0 - TOL_RELATIVE)
    else:
        bound_note = (
            f"below-the-kink days are the {{n}} on which fwet/{threshold} falls under the "
            f"non-bareground area fraction, {np.mean(veg_frac):.4f}"
        )
        sub = ratio < veg_frac * (1.0 - TOL_RELATIVE)

    if not sub.any():
        report(
            "SKIP",
            "Task 10: below the plateau the scaler is FATES_MOSS_FWET / threshold",
            "This run never leaves the plateau of the wetness map: FATES_MOSS_FWET is at or "
            f"above threshold x the area fraction on all {nday} days, so there is no day on "
            "which the sub-plateau branch of min(1, fwet/threshold) was taken and nothing "
            "here pins the threshold. A drier run would.",
        )
    else:
        deviation = relative_deviation(scaler[sub], ratio[sub])
        ok = deviation < TOL_RELATIVE
        report(
            "PASS" if ok else "FAIL",
            "Task 10: below the plateau the scaler is FATES_MOSS_FWET / threshold",
            ("" if ok else DIVERGENCE_FIRST_SUSPECT + "\n")
            + f"identity: scaler == FATES_MOSS_FWET/{threshold} on the days below the "
            "kink, where the area weighting cancels out of both sides\n"
            f"max relative deviation = {deviation:.3e} over {int(sub.sum())} of {nday} days\n"
            + bound_note.format(n=int(sub.sum()))
            + "\n"
            f"threshold from {threshold_source}\n"
            "This is the half that pins the threshold: it is the only quantity in it, and "
            "it holds whether or not the area fraction is known and whether or not it "
            "varies in time."
            + coverage_note(nday, fwet, scaler)
            + "\n"
            + commutation,
        )

    if veg_frac is None:
        report(
            "SKIP",
            "Task 10: on the plateau the scaler is the non-bareground area fraction",
            f"{no_veg_frac_reason}\n"
            "On the plateau the scaler IS the area fraction -- min(veg_frac, "
            "fwet/threshold) picks the first branch -- so this half is the area weighting "
            "and nothing else, and there is no weaker version of it left to test. It is "
            "also the only place the naive unweighted min(1, fwet/threshold) differs: on "
            "the plateau it is wrong by exactly the missing factor, while below the kink it "
            "agrees with the identity, which is why the half above still runs.",
        )
        return

    plateau = ratio > veg_frac * (1.0 + TOL_RELATIVE)
    naive = float(np.nanmax(np.abs(scaler - np.minimum(1.0, ratio))))
    if not plateau.any():
        report(
            "SKIP",
            "Task 10: on the plateau the scaler is the non-bareground area fraction",
            f"FATES_MOSS_FWET never reaches threshold x the area fraction "
            f"({threshold} x {np.mean(veg_frac):.4f}) on any of the {nday} days of this "
            "run, so the plateau branch of the map was never taken and there is nothing "
            "here to test it on. A wetter run would.",
        )
        return
    deviation = relative_deviation(scaler[plateau], veg_frac[plateau])
    ok = deviation < TOL_RELATIVE
    report(
        "PASS" if ok else "FAIL",
        "Task 10: on the plateau the scaler is the non-bareground area fraction",
        ("" if ok else DIVERGENCE_FIRST_SUSPECT + "\n")
        + f"identity: scaler == veg_frac = {np.mean(veg_frac):.4f} on the plateau days\n"
        f"max relative deviation = {deviation:.3e} over {int(plateau.sum())} of {nday} days "
        f"({100.0 * plateau.mean():.1f}% of the run)\n"
        f"scaler {np.nanmin(scaler):.4f} - {np.nanmax(scaler):.4f}\n"
        f"for contrast, the unweighted min(1, fwet/{threshold}) form misses by "
        f"{naive:.3e} -- that is the area weighting, and this half is where it shows"
        + coverage_note(nday, fwet, scaler, veg_frac)
        + "\n"
        + commutation,
    )


def check_task6_livemoss(report, data, fuel_amount, miner_total, miner_source):
    """Task 6: the live-moss fuel class carries the live-moss biomass.

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
        "Task 6: live-moss fuel loading agrees with FATES_LIVEMOSS_FUEL",
        f"identity: FATES_FUEL_AMOUNT_FC[live_moss] == "
        f"(1 - fates_fire_miner_total) * FATES_LIVEMOSS_FUEL\n"
        f"          = {damping:.6f} * FATES_LIVEMOSS_FUEL   "
        f"(miner_total {miner_total} from {miner_source})\n"
        f"max relative deviation = {deviation:.3e}\n"
        f"FATES_LIVEMOSS_FUEL {np.nanmin(reference):.4e} - {np.nanmax(reference):.4e} "
        f"kg m-2, nonzero on {int(np.sum(reference > 0))} of {len(reference)} days\n"
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
        + coverage_note(len(reference), reference, live_moss),
    )

    live_grass = fuel_amount[:, FUEL_CLASSES["live_grass"] - 1]
    report(
        "INFO",
        "Task 6: live-grass and live-moss fuel loading side by side",
        f"live grass  {np.nanmin(live_grass):.4e} - {np.nanmax(live_grass):.4e} kg m-2 "
        f"(mean {np.nanmean(live_grass):.4e})\n"
        f"live moss   {np.nanmin(live_moss):.4e} - {np.nanmax(live_moss):.4e} kg m-2 "
        f"(mean {np.nanmean(live_moss):.4e})\n"
        "Confirming that moss loading MOVED out of the live-grass class rather than being "
        "double-counted alongside it requires the pre-Task-6 baseline. One run cannot "
        "supply it, and nothing on this tape stands in for it.",
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
        "Task 7: FATES_MOSS_FINES carries the FATES-SP unset-litter sentinel",
        f"FATES_MOSS_FINES is {np.nanmax(fines):.4e} kg m-2 on {n_unset} of {len(fines)} "
        "days, which is ndcmpy x fates_unset_r8 (3 x -1e36) showing through rather than a "
        "physical value.\n"
        "Under FATES-SP, EDInitMod.F90:863-868 initializes the litter and seed pools to "
        "fates_unset_r8 rather than to zero, so this is the same convention "
        "FATES_SEEDLING_POOL and FATES_UNGERM_SEED_BANK already follow on an SP tape -- "
        "not moss-specific, and not a netCDF fill value. There is no litter state in SP "
        "mode for the Task 7 checks to test.",
    )
    return True


def check_task7_mossfines(report, data, fuel_amount, miner_total):
    """Task 7: the dead-moss fuel class carries the dead-moss litter, one day stale.

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
            "Task 7: dead-moss fuel loading agrees with FATES_MOSS_FINES",
            f"this tape holds {nday} day, and the identity compares "
            "FATES_FUEL_AMOUNT_FC[dead_moss] on one day against FATES_MOSS_FINES on the "
            "day before it. Two days of output would be enough.",
        )
    else:
        report(
            "PASS" if deviation < TOL_RELATIVE and nonzero else "FAIL",
            "Task 7: dead-moss fuel loading agrees with FATES_MOSS_FINES",
            f"identity: FATES_FUEL_AMOUNT_FC[dead_moss](t) == {damping:.6f} * "
            f"FATES_MOSS_FINES(t-1)\n"
            f"max relative deviation = {deviation:.3e}\n"
            f"FATES_MOSS_FINES {np.nanmin(fines):.4e} - {np.nanmax(fines):.4e} kg m-2, "
            f"nonzero on {int(np.sum(fines > 0))} of {nday} days\n"
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
            "Task 7: FATES_MOSS_FINES is nonzero and accumulates over the run",
            f"this tape holds {nday} day, so there is no first half and second half to "
            "compare and no trend over the run to read.",
        )
        return
    half = nday // 2
    first, second = np.nanmean(fines[:half]), np.nanmean(fines[half:])
    grew = np.nanmax(fines) > 0 and second > first
    report(
        "PASS" if grew else "FAIL",
        "Task 7: FATES_MOSS_FINES is nonzero and accumulates over the run",
        f"first-half mean {first:.4e}, second-half mean {second:.4e} kg m-2\n"
        f"day 1 {fines[0]:.4e} -> day {nday} {fines[-1]:.4e} kg m-2 "
        f"(peak {np.nanmax(fines):.4e})" + coverage_note(nday, fines),
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
            "Whether Task 9's moisture of extinction separates moss from the other fuel "
            "classes could not be examined",
            "fates_fire_SAV could not be read from this run's FATES parameter file, so the "
            "moss classes' surface-area-to-volume ratios were never compared against the "
            "other classes'.\n"
            "Where the moss classes share an SAV with a non-moss class they share a moisture "
            "of extinction, and the Task 9 slope check then cannot tell that FATES reached "
            "for a moss entry rather than that class's. Whether this run is in that position "
            "is unknown here, not ruled out. It is settled by giving this script a readable "
            "fates_paramfile, and nothing about the run has to change.",
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
                f"fates_fire_SAV[{FUEL_CLASSES[moss_name]}] ({moss_name}) = "
                f"{known[moss_name]:g}, which is also its value for " + ", ".join(twins)
            )
    if not lines:
        return
    report.warn(
        "Task 9's moisture of extinction does not separate moss from the other fuel classes",
        "\n".join(lines) + f"\n(fates_fire_SAV from {sav_source})\n"
        "The MEF this script rebuilds for a moss class is therefore the same number it "
        "would rebuild for those non-moss classes, and the Task 9 slope check "
        + (
            "would have passed just as well had FATES indexed one of them. What that check "
            "does establish here is that the shipped moss map was applied to the moss proxy "
            "with the shipped coefficients; what it CANNOT establish in this run is that "
            "FATES reached for a moss SAV entry at all rather than a neighbouring class's."
            if task9_ran
            else "could not have separated them either -- though it did not run in this "
            "case at all, so nothing above rests on this. It is recorded because it is a "
            "property of the parameter file this run was given, and it would bite on the "
            "next run that does reach Task 9."
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
    report, namelist, namelist_source, fuel_moisture, sav, task9_ran
):
    """Warn if the dead-moss moisture map is indistinguishable from the live-moss one.

    Live and dead moss are separate fuel classes fed by separate pools, and Tasks 6 and 7
    do separate them -- livemoss is patch biomass, moss_fines is litter. What can collapse
    is the Task 9 MOISTURE map: it is the same function of the same proxy for both classes
    whenever the two shipped coefficient sets agree and the two classes share an SAV, and
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
        f"shipped map, live moss: slope {live[0]}, intercept {live[1]}",
        f"shipped map, dead moss: slope {dead[0]}, intercept {dead[1]}   "
        f"({namelist_source})",
    ]
    if same_sav is not None:
        lines.append(
            f"fates_fire_SAV[{live_index}] and [{dead_index}] "
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
            f"FATES_FUEL_MOISTURE_FC[:, {live_index - 1}] and [:, {dead_index - 1}] differ "
            f"by at most {columns:.3e} over the whole run"
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
            "bite on the next run that does reach Task 9."
        )
    report.warn(
        "The dead-moss half of Task 9 adds no coverage in this run",
        "\n".join(lines) + "\n" + verdict + "\n"
        "Tasks 6 and 7 are NOT affected: they check the two classes against different pools, "
        "livemoss and moss_fines, and those are genuinely separate. It is the moisture check "
        "alone that is duplicated, and it earns its place the day the two coefficient sets "
        "diverge.",
    )


def check_task9_moisture(
    report,
    data,
    fuel_moisture,
    veg_frac,
    namelist,
    namelist_source,
    sav,
    sav_source,
    no_veg_frac_reason,
    fire_status,
):
    """Task 9: moss fuel moisture is an exact linear map of the proxy; others are not.

    Three properties of the fit have to be pinned, not merely described:

      * the SLOPE. FATES_FUEL_MOISTURE_FC reports EFFECTIVE moisture, moisture/MEF, so the
        fitted slope is the shipped slope divided by the moss classes' moisture of
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
        shipped intercept is nonzero. At a shipped intercept of zero, which is the shipped
        default for both moss classes, the expected crossing is zero for EVERY value of
        veg_frac, so the area fraction drops out and the check runs unchanged on a tape that
        has none. It is then still worth running -- a model that offset every moss moisture
        by a constant fails it -- but it is not pinning the intercept against the area
        weighting, because at zero there is nothing to pin. Both facts are said at runtime,
        and a run in that position is not counted as having lost a constraint.

      * the FLOOR. The map is wrapped in max(0, ...) (fire/FatesFuelMod.F90:274-277), so a
        negative shipped intercept makes it piecewise and it is linear only above the kink.
        Days on the floor are excluded from the fit and counted, rather than being left to
        drag R^2 below 1 for a legitimate reason.
    """
    fwet = data["FATES_MOSS_FWET"]
    veg = None if veg_frac is None else float(np.mean(veg_frac))

    for name, prefix in (("live_moss", "live"), ("dead_moss", "dead")):
        index = FUEL_CLASSES[name]
        moisture = fuel_moisture[:, index - 1]
        shipped_slope = namelist[f"fates_moss_fuel_moisture_{prefix}_slope"]
        shipped_intercept = namelist[f"fates_moss_fuel_moisture_{prefix}_intercept"]

        if veg is None:
            # Where the kink sits cannot be predicted without the area fraction, but it can
            # be seen: max(0, ...) makes the effective moisture exactly zero on the floor
            # and positive above it, so the reported value locates the kink itself.
            above_floor = moisture > 0
        else:
            above_floor = shipped_intercept + shipped_slope * (fwet / veg) > 0
        floored = int(np.sum(~above_floor))
        obstacle = fit_obstacle(fwet[above_floor], moisture[above_floor], len(fwet))
        if obstacle is not None:
            # A fit that could not be computed is not a fit that failed. Reporting it as a
            # FAIL printing `nan` puts a short or flat run's shape on the model's account.
            report(
                "SKIP",
                f"Task 9: fuel class {index} ({name}) moisture is an exact linear "
                "function of FATES_MOSS_FWET",
                f"the linear fit could not be computed: {obstacle}.\n"
                + (
                    f"{floored} of {len(fwet)} days sit at or below the max(0, ...) floor "
                    "of the shipped map and are excluded from the fit before this is "
                    "counted.\n"
                    if floored
                    else ""
                )
                + "Nothing here says the map is wrong -- it says this run does not contain "
                "the days it would take to test it. A longer run, or one that samples a "
                "range of FATES_MOSS_FWET, would.",
            )
            continue
        slope, intercept, r2 = linear_fit(fwet[above_floor], moisture[above_floor])
        span = float(np.ptp(fwet[above_floor])) if above_floor.any() else 0.0

        mef = (
            float(moisture_of_extinction(sav[index - 1]))
            if sav is not None and len(sav) >= index and sav[index - 1] > 0
            else np.nan
        )
        implied_mef = shipped_slope / slope if slope else np.nan

        # A shipped intercept of zero puts the crossing point at zero whatever veg_frac is,
        # so the area fraction cancels out of this half and it runs on any tape. It is not
        # then pinning the area weighting -- there is nothing at zero for the weighting to
        # scale -- which is why it is not counted as a constraint lost when the fraction is
        # missing. It still catches an offset, so it still runs.
        degenerate_crossing = abs(shipped_intercept) <= TOL_EXACT
        crossing = -intercept / slope if slope else np.nan
        expected_crossing = (
            0.0
            if degenerate_crossing and shipped_slope
            else -veg * shipped_intercept / shipped_slope
            if veg is not None and shipped_slope
            else np.nan
        )
        ok_crossing = (
            np.isfinite(crossing)
            and np.isfinite(expected_crossing)
            and abs(crossing - expected_crossing)
            <= TOL_RELATIVE * max(abs(expected_crossing), span)
        )
        expected_slope = shipped_slope / mef if np.isfinite(mef) else np.nan
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

        if np.isfinite(expected_crossing) and degenerate_crossing:
            crossing_note = (
                f"crossing point: expected 0 exactly, fitted {crossing:+.6e}. The shipped "
                f"intercept is {shipped_intercept}, so -veg_frac * intercept / slope is "
                "zero for EVERY value of the non-bareground area fraction and this half "
                + (
                    "needs none"
                    if veg is None
                    else f"would be zero at the {veg:.4f} on this tape as at any other"
                )
                + ". What it catches at these parameters is a moss moisture offset from "
                "zero; what it is NOT doing is pinning the area weighting, since at an "
                "intercept of zero there is nothing for the weighting to scale. Give the "
                "moss classes a nonzero shipped intercept and this half starts constraining "
                "the area fraction as well.\n"
            )
        elif np.isfinite(expected_crossing):
            crossing_note = (
                f"crossing point: expected veg_frac * intercept / slope = {veg:.4f} * "
                f"{shipped_intercept} / {shipped_slope} = {expected_crossing:+.6e} in site "
                f"units, fitted {crossing:+.6e}\n"
                f"        (the veg_frac factor is there because the area weighting cancels "
                f"out of the slope but not out of the intercept)\n"
            )
        else:
            crossing_note = (
                f"crossing point: NOT CONSTRAINED. {no_veg_frac_reason} The fitted "
                f"intercept is veg_frac * shipped intercept / MEF, so without the area "
                f"fraction there is no number to check the fitted {crossing:+.6e} against. "
                "The SLOPE reported above is unaffected: the weighting cancels out of it "
                "exactly. The R^2 is not quite unaffected -- the days entering the fit are "
                "the days whose reported moisture is positive rather than the days the "
                "shipped map predicts above its kink, so a day the model wrongly floored "
                "drops out of the fit instead of pulling R^2 down, and the survivors still "
                "fit a perfect line. Read the floored-day count below against what the "
                "shipped map would predict.\n"
            )

        report(
            "PASS" if ok else "FAIL",
            f"Task 9: fuel class {index} ({name}) moisture is an exact linear "
            "function of FATES_MOSS_FWET",
            f"fit: effective_moisture = {slope:.6f} * fwet {intercept:+.3e}, "
            f"R^2 = {r2:.10f}\n"
            f"shipped map is max(0, intercept {shipped_intercept} + slope {shipped_slope} "
            f"* fwet) ({namelist_source})\n"
            + (
                f"slope: expected shipped slope / MEF = {shipped_slope} / {mef:.6f} = "
                f"{expected_slope:.6f}, fitted {slope:.6f}, relative deviation "
                f"{abs(slope - expected_slope) / abs(expected_slope):.3e}\n"
                f"       MEF is rebuilt from fates_fire_SAV[{index}] = {sav[index - 1]:g} "
                f"({sav_source}), not from this fit\n"
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
                    else "the shipped intercept could not be checked: it survives the area "
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
            "Task 9: non-moss fuel classes track the Nesterov index, not the moss proxy",
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
                ("FATES_MOSS_FWET", fwet),
                ("FATES_NESTEROV_INDEX", nesterov),
            ):
                why = fit_obstacle(predictor, column, nday, both=True)
                if why:
                    obstacles.append(f"class {c} against {label}: {why}")
        if obstacles:
            report(
                "SKIP",
                "Task 9: non-moss fuel classes track the Nesterov index, not the moss proxy",
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
                "Task 9: non-moss fuel classes track the Nesterov index, not the moss proxy",
                "classes " + ", ".join(str(c) for c in NESTEROV_DRIVEN) + "\n"
                "corr with FATES_MOSS_FWET:      "
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
            "Task 9 / Task 12 Step 4: how often live moss cannot carry fire",
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
        "Task 9 / Task 12 Step 4: how often live moss cannot carry fire",
        f"patch effective moisture {np.nanmin(patch):.4f} - {np.nanmax(patch):.4f}; "
        f">= 1 (at or past extinction) on {100 * np.mean(patch >= 1.0):.1f}% of days\n"
        f"the site-level FATES_FUEL_MOISTURE_FC value is this times the non-bareground "
        f"area fraction {np.mean(veg_frac):.4f}, i.e. "
        f"{np.nanmin(site):.4f} - {np.nanmax(site):.4f}, and reads >= 1 on "
        f"{100 * np.mean(site >= 1.0):.1f}% of days -- comparing the site value against 1 "
        "understates the moss's wetness and is not the right test"
        + coverage_note(len(site), site, patch),
    )


def check_moss_productivity(report, data, moss, grass, fwet):
    """Task 10 / Task 12 Step 3b: is moss productive, and is the productive window visited?"""
    gone = absent(data, "FATES_GPP_PF")
    if gone:
        report(
            "SKIP",
            "Task 10 / Task 12 Step 3b: moss productivity",
            f"{', '.join(gone)} is not on this tape.",
        )
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
    report(
        "INFO",
        "Task 10: is moss FATES_GPP_PF positive, and how large is it?",
        f"moss  mean {np.nanmean(gpp):.4e}, max {np.nanmax(gpp):.4e} kg m-2 s-1\n"
        f"grass mean {np.nanmean(grass_gpp):.4e}, max {np.nanmax(grass_gpp):.4e} kg m-2 s-1"
        + (
            f"   (moss peaks {np.nanmax(grass_gpp) / np.nanmax(gpp):.3g}x below grass)"
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
    rows, means = [], []
    if edges.size < 2:
        rows.append(
            f"FATES_MOSS_FWET does not vary over this run -- it reads {edges[0]:.6f} on "
            f"all {len(fwet)} days -- so there are no deciles to bin by. Over the whole "
            f"run, mean moss GPP = {float(np.nanmean(gpp)):.4e} and GPP > 0 on "
            f"{100 * np.mean(gpp > 0):.1f}% of days."
        )
    for low, high in zip(edges[:-1], edges[1:]):
        sel = (fwet >= low) & (fwet < high)
        if not sel.sum():
            continue
        mean = float(np.nanmean(gpp[sel]))
        means.append((mean, low, high))
        rows.append(
            f"fwet {low:.3f} - {high:.3f}:  n = {int(sel.sum()):4d}   "
            f"mean GPP = {mean:.4e}   GPP > 0 on {100 * np.mean(gpp[sel] > 0):5.1f}% of days"
        )
    peak = max(means) if means else None
    report(
        "INFO",
        "Task 12 Step 3b: moss GPP binned by FATES_MOSS_FWET decile",
        "\n".join(rows)
        + (
            f"\npeak bin: fwet {peak[1]:.3f} - {peak[2]:.3f}, mean GPP {peak[0]:.4e}"
            if peak
            else ""
        )
        + (
            f"\noverall corr(fwet, moss GPP) = {correlation(fwet, gpp):+.3f}\n"
            if fit_obstacle(fwet, gpp, len(fwet), both=True) is None
            else "\noverall corr(fwet, moss GPP): not computed -- "
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

    parts = []
    if recruit is not None:
        parts.append(f"recruit height is {recruit:g} m (fates_recruit_height_min)")
    if None not in (d2h1, d2h2, dbh_max) and dbh_max > 0:
        ceiling = float(d2h1) * float(dbh_max) ** float(d2h2)
        parts.append(
            f"the height power law the moss allometry borrows saturates at {ceiling:.2f} m "
            f"(fates_allom_d2h1 x fates_allom_dbh_maxheight ** fates_allom_d2h2 = "
            f"{d2h1:g} x {dbh_max:g} ** {d2h2:g})"
        )
    height_line = (
        "\nFor reference, from this run's own FATES parameter file at PFT "
        f"{moss + 1}: " + "; and ".join(parts) + "."
        if parts
        else "\nNo reference heights: fates_recruit_height_min and the height allometry "
        "coefficients could not be read from this run's FATES parameter file, so there is "
        "nothing here to read the diagnosed height against."
    )

    if treelai_mismatch is None:
        leaf_line = (
            f"   Step 3d predicts {TREELAI_AT_RECRUIT} at recruit size and "
            f"{TREELAI_AT_MAX} at maximum ({TREELAI_PREDICTION_SOURCE}; this run's "
            "parameter file still carries every value at the moss index that those two "
            "were derived from, so they are restated here)\n"
        )
    else:
        leaf_line = (
            "   No prediction to read these against: the Task 12 Step 3d figures of "
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


def check_moss_structure(
    report,
    data,
    moss,
    grass,
    pft_moss,
    pft_grass,
    sp_mode,
    patch_area,
    moss_params,
    treelai_valid,
):
    """Task 10b / Task 12 Steps 3c, 3d: moss leaf area, crown area and height."""
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
        report(
            "SKIP",
            "Task 10b / Task 12 Step 3d: moss leaf and stem area",
            f"{', '.join(gone)} not on this tape.",
        )
    else:
        lai = data["FATES_LAI_PF"][:, moss]
        sai = data["FATES_SAI_PF"][:, moss]
        crown = data["FATES_CROWNAREA_PF"][:, moss]

        # FATES_LAI_PF is per m2 of LAND; the allometry is reasoned about per m2 of CROWN,
        # which is what FATES calls treelai. Dividing recovers it, and Step 3d's predictions
        # are in those units.
        with np.errstate(invalid="ignore", divide="ignore"):
            treelai = np.where(crown > 0, lai / np.where(crown > 0, crown, 1.0), np.nan)

        # Everything above is per unit land area or per unit crown area, and neither needs
        # the prescribed patch area. Only the last line does. Whether that variable is usable
        # was decided once, in non_bareground_fraction, and handed here -- so that a patch
        # area present but identically zero cannot come out reported in one place and
        # skipped in another, with a division by zero between them.
        moss_patch = None if patch_area is None else float(np.nanmax(patch_area[:, moss]))
        if moss_patch is not None and moss_patch > 0:
            against_patch = (
                f"moss crown area {np.nanmin(crown):.4e} - {np.nanmax(crown):.4e} m2 m-2, "
                f"against a prescribed nocomp patch area of {moss_patch:.4f}\n"
                f"   moss fills at most {100 * np.nanmax(crown) / moss_patch:.4f}% of the "
                "patch it was given"
            )
        elif moss_patch is not None:
            against_patch = (
                f"moss crown area {np.nanmin(crown):.4e} - {np.nanmax(crown):.4e} m2 m-2; "
                "the prescribed nocomp patch area for moss is zero on every day of this "
                "run, so there is no patch for the crown to fill a fraction of"
            )
        else:
            against_patch = (
                f"moss crown area {np.nanmin(crown):.4e} - {np.nanmax(crown):.4e} m2 m-2; "
                "there is no usable prescribed patch area on this tape to read it against"
            )

        report(
            "INFO",
            "Task 10b / Task 12 Step 3d: moss leaf and stem area",
            f"FATES_LAI_PF (per m2 land)  {np.nanmin(lai):.4e} - {np.nanmax(lai):.4e}\n"
            f"FATES_SAI_PF (per m2 land)  {np.nanmin(sai):.4e} - {np.nanmax(sai):.4e}\n"
            f"VAI = LAI + SAI             {np.nanmin(lai + sai):.4e} - "
            f"{np.nanmax(lai + sai):.4e}\n"
            f"LAI / FATES_CROWNAREA_PF (= treelai, per m2 crown)  "
            + span(treelai, "{:.6f}")
            + "\n"
            + leaf_line
            + against_patch
            + sp_note
            + coverage_note(len(lai), lai, sai, crown),
        )

    if absent(data, "FATES_MOSS_HEIGHT"):
        report(
            "SKIP",
            "Task 12 Step 3c: diagnosed moss height",
            "FATES_MOSS_HEIGHT is not on this tape.",
        )
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
        "Task 12 Step 3c: diagnosed moss height",
        f"FATES_MOSS_HEIGHT {np.nanmin(height):.5f} - {np.nanmax(height):.5f} m "
        f"({len(np.unique(np.round(height, 8)))} distinct values)\n"
        "This one is normalized by moss crown area rather than by land area, so unlike "
        "every other moss diagnostic here it carries no non-bareground area factor."
        + height_line
        + (
            f"\nEvery day moss is present it stands at exactly {recruit_height:g} m, so "
            "the cohort never grew past recruit size."
            if pinned
            else ""
        )
        + sp_note
        + coverage_note(len(height), height),
    )

    check_nocomp_cover(report, patch_area, moss, grass, pft_moss, pft_grass)


def check_nocomp_cover(report, patch_area, moss, grass, pft_moss, pft_grass):
    """Task 12 Step 3: the prescribed cover the rest of the run is read against.

    Gated on the same decision non_bareground_fraction made, not on a second look at the
    tape: whether that variable is usable is one question, and answering it twice produced a
    run that reported prescribed cover here while the WARN inventory said the report had been
    skipped.
    """
    if patch_area is None:
        report(
            "SKIP",
            "Task 12 Step 3: prescribed nocomp cover",
            "There is no usable FATES_NOCOMP_PATCHAREA_PF on this tape -- see the reason "
            "given with the area-fraction WARN above.\n"
            "A run with no prescribed cover has none for this step to report: what each PFT "
            "holds is then an outcome of the run rather than something it was given.",
        )
        return
    area = patch_area
    report(
        "INFO",
        "Task 12 Step 3: prescribed nocomp cover",
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
            "the "
            "moisture of extinction, and every burn-side quantity. The moss checks that do "
            "run here are the wetness proxy, the photosynthetic scaler, and moss structure "
            "and population -- none of which goes near the burn path.",
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
        "SPITFIRE ran and nothing burned, so the moss burn path is untested here too",
        f"{config.settings_phrase()}, and FATES_BURNFRAC is identically zero on "
        f"all {len(burn)} days of the run." + gate_note + "\n"
        "This is not the same as fire being off, and it is the more surprising of the two: "
        "the fire model ran, and the fuel loadings and moistures the Task 6, 7 and 9 checks "
        "above test are real quantities it produced. What never happened is combustion.\n"
        "So every burn-side diagnostic in this run, FATES_FUEL_BURNT_BURNFRAC_FC included, "
        "is structurally zero, and no PASS or number below establishes anything whatever "
        "about how moss burns. To test that, this site has to be driven to ignite.",
    )


def check_fuel_burnt(report, data, fire_status):
    """Task 12: report FATES_FUEL_BURNT_BURNFRAC_FC, which the moss testmod asks for.

    It has no check because there is nothing to check it against on one tape, and because
    it is structurally zero unless something burned. It is reported so that a reader can
    see it was looked at, and told plainly what it is worth.
    """
    burnt = data["FATES_FUEL_BURNT_BURNFRAC_FC"]
    moss_burnt = burnt[:, [FUEL_CLASSES["live_moss"] - 1, FUEL_CLASSES["dead_moss"] - 1]]
    burn = data.get("FATES_BURNFRAC")
    if burn is None:
        # Not "fire is off": FATES_BURNFRAC is registered unconditionally, so its absence is
        # a hist_fincl1 omission. What fire did is taken from the namelist instead.
        tail = (
            "FATES_BURNFRAC is not on this tape, so whether anything actually burned cannot "
            "be read here. " + fire_status
        )
    elif float(np.nanmax(burn)) <= 0.0:
        tail = (
            "FATES_BURNFRAC is zero on every day of this run, so these are structurally "
            "zero and establish nothing whatever about the moss burn path -- see the WARN "
            "that says so in full."
        )
    else:
        tail = (
            "There is no second run to check these against, so they are reported rather "
            "than tested."
        )
    report(
        "INFO",
        "Task 12: moss fuel burnt fractions (FATES_FUEL_BURNT_BURNFRAC_FC)",
        f"live moss {np.nanmin(moss_burnt[:, 0]):.4e} - {np.nanmax(moss_burnt[:, 0]):.4e}, "
        f"dead moss {np.nanmin(moss_burnt[:, 1]):.4e} - {np.nanmax(moss_burnt[:, 1]):.4e}\n"
        f"nonzero on {int(np.sum(np.any(moss_burnt != 0.0, axis=1)))} of {len(burnt)} days\n"
        + tail
        + coverage_note(len(burnt), moss_burnt),
    )


def check_moss_population(report, data, moss, when, fire_status):
    """Task 12 Step 3: mortality, fire, and what the moss population actually did.

    This is the check most likely to say something the plan did not anticipate, so it
    reports the trajectory in enough detail to tell slow decline from seasonality from
    outright loss, rather than only a first-half/second-half mean.
    """
    gone = absent(data, "FATES_MORTALITY_HYDRAULIC_PF", "FATES_MORTALITY_TERMINATION_PF")
    if gone:
        report(
            "SKIP",
            "Task 12 Step 3: moss mortality rates",
            f"{', '.join(gone)} not on this tape.",
        )
    else:
        hydraulic = data["FATES_MORTALITY_HYDRAULIC_PF"][:, moss]
        termination = data["FATES_MORTALITY_TERMINATION_PF"][:, moss]
        report(
            "INFO",
            "Task 12 Step 3: moss mortality rates",
            f"hydraulic   mean {np.nanmean(hydraulic):.4e} m-2 yr-1, max "
            f"{np.nanmax(hydraulic):.4e}, nonzero on {int(np.sum(hydraulic > 0))} days\n"
            f"termination mean {np.nanmean(termination):.4e} m-2 yr-1, max "
            f"{np.nanmax(termination):.4e}, nonzero on {int(np.sum(termination > 0))} days",
        )

    if "FATES_BURNFRAC" not in data:
        report(
            "SKIP",
            "Task 12 Step 3: did any fire occur?",
            "FATES_BURNFRAC is not on this tape. That says nothing about whether fire ran: "
            "FATES registers it unconditionally with use_default='active' "
            "(main/FatesHistoryInterfaceMod.F90:6839), so it is on any tape whose "
            "hist_fincl1 does not exclude it.\n" + fire_status,
        )
    else:
        burn = data["FATES_BURNFRAC"]
        report(
            "INFO",
            "Task 12 Step 3: did any fire occur?",
            f"FATES_BURNFRAC mean {np.nanmean(burn):.3e} s-1, max {np.nanmax(burn):.3e}, "
            f"nonzero on {int(np.sum(burn > 0))} of {len(burn)} days"
            + (
                ""
                if np.nanmax(burn) > 0
                else "\nNo fire occurred, so every burn-side diagnostic in this run is "
                "structurally zero and says nothing about the moss burn path."
            ),
        )

    if absent(data, "FATES_LEAFC_PF"):
        report(
            "SKIP",
            "Task 12 Step 3: moss population trajectory over the run",
            "FATES_LEAFC_PF is not on this tape.",
        )
        return

    leafc = data["FATES_LEAFC_PF"][:, moss]
    nday = len(leafc)
    half = nday // 2
    day = np.arange(1, nday + 1, dtype=float)
    alive = leafc > 0
    peak = float(np.nanmax(leafc))
    lines = [
        "moss FATES_LEAFC_PF " + span(leafc, "{:.4e}") + " kg m-2",
        # A first half and a second half need two days to divide between them.
        f"first-half mean {np.nanmean(leafc[:half]):.4e} -> second-half mean "
        f"{np.nanmean(leafc[half:]):.4e} kg m-2"
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
                f"({when[last + 1]}) reads {leafc[last + 1]:.4e} kg m-2"
            )
            lines.append(
                f"that final step is {ratio:.0f}x the median daily step over the "
                f"{last + 1} days moss is present ({median_step:.4e} kg m-2)"
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
        "Task 12 Step 3: moss population trajectory over the run",
        "\n".join(lines) + closing + coverage_note(nday, leafc),
    )


# ---------------------------------------------------------------------------------------
# Plots
# ---------------------------------------------------------------------------------------


def make_plots(data, moss, fwet, gpp, out_dir, tag):
    """Moss GPP against the wetness proxy, the proxy's distribution, and moss biomass."""
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
    axes[0].set_xlabel("FATES_MOSS_FWET [1]", color=COLOR_MUTED, fontsize=9)
    axes[0].set_ylabel("moss FATES_GPP_PF [kg m-2 s-1]", color=COLOR_MUTED, fontsize=9)
    axes[0].set_title(
        "Moss GPP against the wetness proxy", color=COLOR_TEXT, fontsize=11, loc="left"
    )

    axes[1].hist(fwet, bins=40, color=COLOR_SERIES[1], edgecolor=COLOR_SURFACE, zorder=3)
    axes[1].set_xlabel("FATES_MOSS_FWET [1]", color=COLOR_MUTED, fontsize=9)
    axes[1].set_ylabel("days", color=COLOR_MUTED, fontsize=9)
    axes[1].set_title(
        "Distribution of the wetness proxy", color=COLOR_TEXT, fontsize=11, loc="left"
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


def default_tag(run_dir):
    """A short, filesystem-safe name for this run's outputs.

    CIME test names run to nearly 200 characters, which makes an unwieldy and
    near-length-limit filename, so the tag is a readable prefix of the case name plus a
    hash. The hash is of the run directory's full PATH, not of the case name: hashing the
    case name would add nothing the truncated prefix does not already carry, and two runs of
    the same case in different scratch directories would then overwrite each other's PNG.
    """
    run_path = os.path.abspath(run_dir)
    case = os.path.basename(os.path.dirname(run_path))
    digest = hashlib.md5(run_path.encode()).hexdigest()[:8]
    safe = re.sub(r"[^A-Za-z0-9]+", "-", case)[:60].strip("-")
    return f"{safe}_{digest}"


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
        help="1-based grass PFT index on the fates_levpft axis. Default: 12, which is a "
        "property of the ALP2 moss testmods' surface datasets rather than a general one. "
        "Confirmed against the run's parameter file where that can be read, and WARNed "
        "about where it cannot; nothing PASSes or FAILs on it.",
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

    # These three are the ones the script cannot run at all without: they are indexed
    # unconditionally. Everything else a check indexes directly is looked for by the check
    # itself, which SKIPs rather than raising KeyError -- a tape written by an older testmod,
    # or a tape from a configuration that never registers a variable, should not stop the
    # run. FATES_NOCOMP_PATCHAREA_PF used to be a fourth entry here and is not one any more,
    # because a run may legitimately have none and the checks that need it now SKIP;
    # FATES_MOSS_WETNESS_SCALER came off the list for the same reason, its only consumer
    # being a check that SKIPs.
    for name in ("FATES_MOSS_FWET", "FATES_MOSS_FWET_SOIL", "FATES_MOSS_FWET_CANOPY"):
        if name not in data:
            raise HistoryContentError(
                f"{name} is not on this tape. This script expects a moss run with the moss "
                "history variables in hist_fincl1."
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
    namelist_source = "shipped namelist defaults (lnd_in not readable)"
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
        miner_total, miner_source = DEFAULT_MINER_TOTAL, "the shipped FATES default"
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

    case = os.path.basename(os.path.dirname(os.path.abspath(args.run_dir)))
    when = dates(data, nday, files)
    print(f"{nday} daily history files from")
    print(f"  {case}")
    print(f"  first {when[0]}, last {when[-1]}")
    print(f"  moss PFT {args.pft_moss}, grass PFT {args.pft_grass}, "
          + (f"non-bareground area fraction {np.mean(veg_frac):.4f}"
             if veg_frac is not None
             else "no non-bareground area fraction available"))
    if config.readable:
        print(f"  {config.settings_phrase()}")
    else:
        print("  this run's lnd_in could not be read, so nothing here comes from its "
              "namelist")
    if veg_frac is not None:
        print(f"  area fraction from {veg_frac_source}")
    for line in validation:
        print(f"  {line}")
    print(f"  {grass_line}")
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
            "What rests on it: the grass column of the Task 10 GPP comparison, which is "
            "there to give moss GPP a scale, and the grass line of the Task 12 Step 3 "
            "prescribed-cover report. Nothing else, and no PASS or FAIL anywhere.",
        )
    fwet = data["FATES_MOSS_FWET"]

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
            "plateau half of the Task 10 wetness-scaler identity; the crossing-point half "
            "of each Task 9 moss moisture check, where the shipped intercept is nonzero; "
            "the patch-level reading of how often moss sits past its moisture of "
            "extinction; and the prescribed-cover report.\n"
            "STILL RUN, because the weighting cancels out of them: Task 8's two proxy "
            "identities, Tasks 6 and 7's fuel-loading identities, the sub-plateau half of "
            "Task 10, which is what pins the threshold, the slope and R^2 halves of Task 9, "
            "the Nesterov contrast, Task 10b's leaf and stem area, and all of Task 12 "
            "except the cover report.",
        )
    elif veg_frac_source is not None and "FATES_NOCOMP_PATCHAREA_PF" not in data:
        report(
            "INFO",
            "The non-bareground area fraction this run's area-weighted checks use",
            f"veg_frac = {veg_frac_source} ({config.settings_phrase()}). FATES makes a "
            "bareground patch only under nocomp AND fixed biogeography "
            "(main/EDInitMod.F90:841), so on this run the patch areas sum to AREA and each "
            "site value IS the patch value.\n"
            "FATES_NOCOMP_PATCHAREA_PF is not on this tape and does not need to be: every "
            "area-weighted check below runs in full, with the same arithmetic a nocomp tape "
            "gets and the factor equal to one. Nothing is degraded and nothing is skipped "
            "for want of a patch area.",
        )

    commutation, commutation_warning = commutation_watch(
        data, veg_frac, leaf_cap, leaf_cap_source
    )
    if commutation_warning:
        report.warn(
            "The max()/min() commutation preconditions of Tasks 8 and 10 are no longer safe",
            commutation_warning,
        )
    check_task8_proxy(report, data, veg_frac, commutation, leaf_cap, leaf_cap_source)
    check_task10_scaler(
        report,
        data,
        veg_frac,
        namelist["fates_moss_vcmax_fwet_thresh"],
        namelist_source,
        commutation,
        no_veg_frac_reason,
    )

    litter_unset = check_mossfines_sentinel(report, data)

    if fuel_amount is None or fuel_moisture is None:
        reason = "FATES_FUEL_AMOUNT_FC or FATES_FUEL_MOISTURE_FC is not on this tape."
    elif not spitfire_on:
        reason = (
            f"SPITFIRE did not run in this case ({config.settings_phrase()}), so there is "
            "no fuel state to test." + gate_note
        )
    else:
        reason = None
    task9_ran = reason is None

    if reason is not None:
        report("SKIP", "Task 6: live-moss fuel loading agrees with FATES_LIVEMOSS_FUEL", reason)
        report("SKIP", "Task 7: dead-moss fuel loading agrees with FATES_MOSS_FINES", reason)
        report("SKIP", "Task 9: moss fuel moisture is a linear function of the proxy", reason)
    else:
        if absent(data, "FATES_LIVEMOSS_FUEL"):
            report(
                "SKIP",
                "Task 6: live-moss fuel loading agrees with FATES_LIVEMOSS_FUEL",
                "FATES_LIVEMOSS_FUEL is not on this tape.",
            )
        else:
            check_task6_livemoss(report, data, fuel_amount, miner_total, miner_source)
        if litter_unset or absent(data, "FATES_MOSS_FINES"):
            # Two checks go, so two SKIPs are printed. Folding them into one would drop the
            # accumulation check off the tally with no line of its own saying it was not
            # made, which reads as a check that never existed.
            why = (
                "FATES_MOSS_FINES is the unset-litter sentinel; see the INFO above."
                if litter_unset
                else "FATES_MOSS_FINES is not on this tape."
            )
            report("SKIP", "Task 7: dead-moss fuel loading agrees with FATES_MOSS_FINES", why)
            report("SKIP", "Task 7: FATES_MOSS_FINES is nonzero and accumulates over the "
                   "run", why)
        else:
            check_task7_mossfines(report, data, fuel_amount, miner_total)
        check_task9_moisture(
            report, data, fuel_moisture, veg_frac, namelist, namelist_source, sav,
            sav_source, no_veg_frac_reason, fire_status,
        )

    # What the Task 9 moisture checks were and were not able to distinguish in this run.
    # Both are properties of the parameters this run was given, so both are asked whether or
    # not the checks themselves ran; the tape columns only settle the second where SPITFIRE
    # actually produced them, and whether the checks ran changes only the wording, since a
    # warning about a fit that is not in the output points the reader at nothing.
    warn_sav_degeneracy(report, sav, sav_source, task9_ran)
    warn_live_dead_degeneracy(
        report,
        namelist,
        namelist_source,
        fuel_moisture if spitfire_on else None,
        sav,
        task9_ran,
    )

    gpp = check_moss_productivity(report, data, moss, grass, fwet)
    check_moss_structure(
        report, data, moss, grass, args.pft_moss, args.pft_grass,
        bool(config.use_sp), patch_area, moss_params, treelai_mismatch,
    )
    warn_fire_status(report, data, config, spitfire_on, gate_note)
    if absent(data, "FATES_FUEL_BURNT_BURNFRAC_FC"):
        report(
            "SKIP",
            "Task 12: moss fuel burnt fractions (FATES_FUEL_BURNT_BURNFRAC_FC)",
            "FATES_FUEL_BURNT_BURNFRAC_FC is not on this tape.",
        )
    else:
        check_fuel_burnt(report, data, fire_status)
    check_moss_population(report, data, moss, when, fire_status)

    if args.no_plots:
        pass
    elif gpp is None or absent(data, "FATES_LEAFC_PF"):
        print("Skipped the plots: FATES_GPP_PF or FATES_LEAFC_PF is not on this tape.\n")
    else:
        os.makedirs(args.out_dir, exist_ok=True)
        path = make_plots(data, moss, fwet, gpp, args.out_dir, default_tag(args.run_dir))
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
