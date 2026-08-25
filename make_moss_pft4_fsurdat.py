#!/usr/bin/env python
"""Build the two ALP2 moss fsurdats our single moss paramfile needs, moss on PFT index 4.

Why this script is needed
-------------------------
This project commits ONE moss FATES parameter file, `fates_params_moss.json`, which maps
moss onto HLM PFT index 4 (displacing broadleaf_evergreen_tropical_tree) and leaves
arctic_c3_grass on index 12. We deliberately do not port the NVP branch's second, HLM-12
variant.

The NVP branch shipped two ALP2 moss fsurdats, one per NVP paramfile, and neither is
usable as-is:

  ..._moss.nc        5.75% bare + 94.25% on natpft 12.  NVP paired this with its HLM-12
                     paramfile. Under OUR paramfile index 12 is still arctic_c3_grass, so
                     this file is a GRASS run, not a moss run.

  ..._grassmoss.nc   20% bare + 50% on natpft 4 + 30% on natpft 12. NVP paired this with
                     its `mossMapsBrEvTrTree` paramfile, which put moss on index 4 -- the
                     same choice we made -- so the AREA layout is already right for us.
                     But its moss canopy column is malformed: three of the four MONTHLY_*
                     columns were moved from 12 to 4 and MONTHLY_HEIGHT_BOT was not, so
                     index 4 carries a canopy bottom of 0.8386 m (the tropical tree's)
                     under a canopy top of 0.0338 m. Bottom above top, in all 12 months.

This script produces a corrected counterpart of each:

  --fout-moss        from ..._moss.nc:       relocate moss from index 12 to index 4.
  --fout-grassmoss   from ..._grassmoss.nc:  leave the area alone; overwrite index 4's
                     canopy column with the authoritative moss column.

The malformed MONTHLY_HEIGHT_BOT is inert in a FATES run -- it is read only by
`SatellitePhenology`, which aborts if `use_fates` is true, and FATES-SP ingests only
`hlm_sp_htop` -- so this is housekeeping, not a bug fix. Doing it anyway means neither
file has a nonsense column waiting for whoever reads it next.

The authoritative moss canopy column
------------------------------------
Index 12 of ..._moss.nc, which is the hand-tuned moss canopy:

  MONTHLY_LAI 2.0   MONTHLY_SAI 0.5   MONTHLY_HEIGHT_TOP 0.0338 m   MONTHLY_HEIGHT_BOT 1e-06 m

Both outputs get exactly this column at index 4, which is why the moss-only file is an input
to the grassmoss build too. For the grassmoss file, three of the four variables already match
it, so exactly one correction -- MONTHLY_HEIGHT_BOT -- should be needed. That is enforced in
both directions and is a hard error either way: another column differing means the input is
not the file this script was written for, and MONTHLY_HEIGHT_BOT *not* differing means the
file has already been through this script. Comparison is exact, not tolerance-based.

Scope: single-gridcell fsurdats only. Both inputs are checked and a multi-gridcell file is
refused rather than mishandled -- see require_single_gridcell.

What moves, and why the canopy columns matter
---------------------------------------------
  PCT_NAT_PFT         (natpft, lsmlat, lsmlon)          -- dim natpft = 15
  MONTHLY_LAI         (time, lsmpft, lsmlat, lsmlon)    -- dim lsmpft = 17
  MONTHLY_SAI                  "
  MONTHLY_HEIGHT_TOP           "
  MONTHLY_HEIGHT_BOT           "

Moving the MONTHLY_* columns is essential, not cosmetic. In ..._moss.nc index 12 has been
hand-tuned to a moss canopy while index 4 carries the stock tropical-tree values (LAI 4.39,
HEIGHT_TOP 29.35 m). Moving PCT_NAT_PFT alone would hand moss a 29 m canopy in any FATES-SP
run, where LAI/SAI/height are prescribed from these arrays rather than computed.

natpft and lsmpft are both 0-based and agree on PFT identity over 0..14 (index 0 = bare
ground), so "index 4" and "index 12" mean the same PFT in both.

Note on index 12 in the moss-only output: its area becomes 0, but its MONTHLY_* values are
left as-is (unused once the area is zero). The script reports this. In the grassmoss output
index 12 is untouched entirely -- it is real arctic grass with real area.

Usage
-----
Run in the ctsm_pylib conda env; uses only netCDF4, numpy, and the stdlib. Every path is
defaulted, so from the directory you want the outputs in:

  /glade/work/samrabin/conda-envs/ctsm_pylib/bin/python3 make_moss_pft4_fsurdat.py

That builds both files. Defaults:

  --fin-moss        $INPUTDATA/lnd/clm2/testdata/moss/fsurdat/
                        surfdata_ALP2_hist_2000_16pfts_c260427_moss.nc
  --fin-grassmoss   (same directory) ..._c260427_grassmoss.nc
  --fout-moss       ./<input basename, restamped, with Pft4 appended>, i.e. on 2026-08-24
                        ./surfdata_ALP2_hist_2000_16pfts_c260824_mossPft4.nc
  --fout-grassmoss  ./surfdata_ALP2_hist_2000_16pfts_c260824_grassmossPft4.nc

The default output names mint a **fresh** `cYYMMDD` creation stamp from today's date,
replacing the source file's, per CTSM convention for a newly created dataset. So the default
names change from day to day -- if you need a fixed name, pass --fout-moss /
--fout-grassmoss explicitly.

$INPUTDATA is used for the inputs, falling back to $DIN_LOC_ROOT; if neither is set, pass
the --fin paths explicitly. Outputs default to the directory you invoked the script from,
never to the input directory -- the script never writes near $INPUTDATA unless you point it
there. Inputs are only ever opened read-only.

Both outputs are always built. The script refuses to overwrite an existing output unless
--overwrite is given.

Add --dry-run to print the before/after tables without writing anything.

The exact command you invoked, interpreter included, is recorded in each output's `history`
attribute alongside a description of what was changed.
"""

import argparse
import datetime
import os
import re
import shlex
import shutil
import sys

import netCDF4
import numpy as np

MOSS_SRC_IDX = 12  # arctic_c3_grass slot, where ..._moss.nc parks its moss
MOSS_DST_IDX = 4   # broadleaf_evergreen_tropical_tree slot, which our paramfile gives to moss

# The one canopy column that ..._grassmoss.nc is known to have wrong at index 4: three of
# the four were moved from index 12 and MONTHLY_HEIGHT_BOT was not. Anything else differing
# from the authoritative moss column means the input is not the file this script expects,
# and check_grassmoss raises rather than overwriting it.
EXPECTED_GRASSMOSS_CORRECTIONS = {"MONTHLY_HEIGHT_BOT"}

AREA_VAR = "PCT_NAT_PFT"
CANOPY_VARS = ["MONTHLY_LAI", "MONTHLY_SAI", "MONTHLY_HEIGHT_TOP", "MONTHLY_HEIGHT_BOT"]
ALL_VARS = [AREA_VAR] + CANOPY_VARS

# Where the NVP-branch ALP2 moss fsurdats live under $INPUTDATA, and their names.
MOSS_TESTDATA_SUBDIR = "lnd/clm2/testdata/moss/fsurdat"
DEFAULT_MOSS_NAME = "surfdata_ALP2_hist_2000_16pfts_c260427_moss.nc"
DEFAULT_GRASSMOSS_NAME = "surfdata_ALP2_hist_2000_16pfts_c260427_grassmoss.nc"


class FsurdatContentError(ValueError):
    """An input fsurdat is not shaped the way this script requires."""


def inputdata_root():
    """$INPUTDATA, falling back to $DIN_LOC_ROOT. None if neither is set."""
    for var in ("INPUTDATA", "DIN_LOC_ROOT"):
        value = os.environ.get(var)
        if value:
            return value
    return None


def default_fin(name):
    """Default input path, or None if we cannot locate the inputdata root."""
    root = inputdata_root()
    return None if root is None else os.path.join(root, MOSS_TESTDATA_SUBDIR, name)


def default_fout(fin):
    """Input basename, restamped with today's cYYMMDD and Pft4 appended, in the invoking dir.

    CTSM convention is that a newly created dataset carries its own creation stamp, so the
    source file's is replaced rather than inherited.
    """
    stem = os.path.basename(fin)
    if stem.endswith(".nc"):
        stem = stem[: -len(".nc")]
    stamp = "c" + datetime.date.today().strftime("%y%m%d")
    stem, n_replaced = re.subn(r"c\d{6}", stamp, stem, count=1)
    if n_replaced == 0:
        stem = f"{stem}_{stamp}"
    return os.path.join(os.getcwd(), stem + "Pft4.nc")


def invocation():
    """The exact command line, interpreter included, quoted so it can be pasted back."""
    return " ".join(shlex.quote(a) for a in [sys.executable] + sys.argv)


def pft_axis(var):
    """Return the index of var's PFT axis. Fatal if it has none."""
    for axis, dim in enumerate(var.dimensions):
        if dim in ("natpft", "lsmpft"):
            return axis
    raise FsurdatContentError(
        f"{var.name} has no natpft/lsmpft dimension: {var.dimensions}"
    )


def column(data, axis, idx):
    """The idx'th slice along axis, with that axis dropped."""
    return np.take(data, idx, axis=axis)


def put_column(data, axis, idx, values):
    """Write values into the idx'th slice along axis, in place."""
    sel = [slice(None)] * data.ndim
    sel[axis] = idx
    data[tuple(sel)] = values


def require_single_gridcell(ds, path):
    """This script only handles single-gridcell fsurdats.

    Multi-gridcell support was deliberately not implemented (Sam, 2026-08-24): every
    reported quantity here -- the per-PFT areas, the sum-to-100 line, the column comparison
    -- would have to become per-gridcell, and fill-valued gridcells would need mask handling
    that this script does not do. Rather than pretend, it refuses.
    """
    nlat = len(ds.dimensions["lsmlat"])
    nlon = len(ds.dimensions["lsmlon"])
    if nlat * nlon != 1:
        raise FsurdatContentError(
            f"{path} has lsmlat={nlat} x lsmlon={nlon} = {nlat * nlon} gridcells. This "
            "script only handles single-gridcell fsurdats, such as the 1x1 ALP2 files it "
            "was written for."
        )


def require_vars(ds, path):
    for name in ALL_VARS:
        if name not in ds.variables:
            raise FsurdatContentError(f"expected variable {name} not found in {path}")


def area_by_index(ds):
    """PCT_NAT_PFT per PFT index, as a plain list.

    Exact, not a summary statistic: require_single_gridcell has already established that
    there is exactly one gridcell, so each index has exactly one value.
    """
    var = ds.variables[AREA_VAR]
    axis = pft_axis(var)
    data = np.asarray(var[:])
    return [float(np.ravel(column(data, axis, i))[0]) for i in range(data.shape[axis])]


def describe_area(ds, label):
    """Report which PFT indices carry area, and what they sum to.

    Single gridcell, so the sum below is the gridcell's total and should be 100. It is
    printed, not asserted -- the caller-level checks are the ones that refuse to proceed.
    """
    areas = area_by_index(ds)
    nz = [(i, round(a, 4)) for i, a in enumerate(areas) if a > 1e-9]
    print(f"    {label:12s} {AREA_VAR} nonzero: {nz}  (sums to {sum(areas):.4f})")


def summarize_canopy(ds, label):
    """Print index 4 and 12 of every canopy variable."""
    print(f"    {label}")
    for name in CANOPY_VARS:
        var = ds.variables[name]
        axis = pft_axis(var)
        data = np.asarray(var[:])
        dst = np.max(column(data, axis, MOSS_DST_IDX))
        src = np.max(column(data, axis, MOSS_SRC_IDX))
        print(
            f"      {name:20s} idx{MOSS_DST_IDX:<3d}max={dst:12.6f}"
            f"   idx{MOSS_SRC_IDX:<3d}max={src:12.6f}"
        )


def read_moss_column(path):
    """Lift the authoritative moss canopy column out of the moss-only file."""
    col = {}
    with netCDF4.Dataset(path) as ds:
        require_vars(ds, path)
        require_single_gridcell(ds, path)
        for name in CANOPY_VARS:
            var = ds.variables[name]
            col[name] = column(np.asarray(var[:]), pft_axis(var), MOSS_SRC_IDX)
    return col


def stamp_history(ds, note):
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    line = f"{stamp}: make_moss_pft4_fsurdat.py {note}\n  command: {invocation()}"
    existing = ds.history if hasattr(ds, "history") else ""
    ds.history = (line + "\n" + existing) if existing else line


def check_moss_only(path):
    """Confirm path is the moss-on-index-12 file, and report it."""
    with netCDF4.Dataset(path) as ds:
        require_vars(ds, path)
        require_single_gridcell(ds, path)
        n_natpft = len(ds.dimensions["natpft"])
        if max(MOSS_SRC_IDX, MOSS_DST_IDX) >= n_natpft:
            raise FsurdatContentError(
                f"index {max(MOSS_SRC_IDX, MOSS_DST_IDX)} out of range for "
                f"natpft={n_natpft} in {path}"
            )
        areas = area_by_index(ds)
        if not areas[MOSS_SRC_IDX] > 0:
            raise FsurdatContentError(
                f"{AREA_VAR}[{MOSS_SRC_IDX}] is zero in {path} -- this does not look "
                "like the moss-on-index-12 file --fin-moss expects."
            )
        if areas[MOSS_DST_IDX] > 0:
            raise FsurdatContentError(
                f"{AREA_VAR}[{MOSS_DST_IDX}] is nonzero (max={areas[MOSS_DST_IDX]:.4f}) "
                f"in {path}; moving index {MOSS_SRC_IDX} there would clobber real area. "
                "Did you pass the grassmoss file to --fin-moss?"
            )
        describe_area(ds, "BEFORE")
        summarize_canopy(ds, os.path.basename(path))


def check_grassmoss(path, moss_col):
    """Confirm path is the bare+grass+moss file, and report which columns need fixing."""
    with netCDF4.Dataset(path) as ds:
        require_vars(ds, path)
        require_single_gridcell(ds, path)
        areas = area_by_index(ds)
        if not areas[MOSS_DST_IDX] > 0:
            raise FsurdatContentError(
                f"{AREA_VAR}[{MOSS_DST_IDX}] is zero in {path} -- --fin-grassmoss "
                f"expects moss area already on index {MOSS_DST_IDX}. Did you pass the "
                "moss-only file here?"
            )
        if not areas[MOSS_SRC_IDX] > 0:
            raise FsurdatContentError(
                f"{AREA_VAR}[{MOSS_SRC_IDX}] is zero in {path} -- expected arctic "
                f"grass area on index {MOSS_SRC_IDX}. This does not look like the "
                "bare+grass+moss file."
            )
        describe_area(ds, "BEFORE")
        summarize_canopy(ds, os.path.basename(path))

        pending = []
        for name in CANOPY_VARS:
            var = ds.variables[name]
            have = column(np.asarray(var[:]), pft_axis(var), MOSS_DST_IDX)
            want = moss_col[name]
            if have.shape != want.shape:
                raise FsurdatContentError(
                    f"{name} shape mismatch between --fin-moss and --fin-grassmoss: "
                    f"{want.shape} vs {have.shape}. Are they the same grid?"
                )
            if np.array_equal(have, want):
                print(f"      {name:20s} idx{MOSS_DST_IDX} already matches moss column")
            else:
                pending.append(name)
                print(
                    f"      {name:20s} idx{MOSS_DST_IDX} NEEDS CORRECTION: "
                    f"max {np.max(have):.6f} -> {np.max(want):.6f}"
                )
        if set(pending) != EXPECTED_GRASSMOSS_CORRECTIONS:
            expected = ", ".join(sorted(EXPECTED_GRASSMOSS_CORRECTIONS))
            problems = []
            extra = sorted(set(pending) - EXPECTED_GRASSMOSS_CORRECTIONS)
            if extra:
                problems.append(
                    f"{', '.join(extra)} differs from the moss column but should already "
                    "match it -- so this is not the file this script was written for, and "
                    f"overwriting index {MOSS_DST_IDX} would destroy something real"
                )
            missing = sorted(EXPECTED_GRASSMOSS_CORRECTIONS - set(pending))
            if missing:
                problems.append(
                    f"{', '.join(missing)} already matches the moss column but should have "
                    "needed correcting -- so either this file has already been through this "
                    "script, or it is not the one this script was written for"
                )
            raise FsurdatContentError(
                f"at index {MOSS_DST_IDX} of {os.path.basename(path)}, exactly "
                f"[{expected}] was expected to need correcting. Instead: "
                + "; ".join(problems)
                + ". Check the input before rerunning."
            )
        return pending


def build_moss_only(fin, fout):
    shutil.copyfile(fin, fout)
    with netCDF4.Dataset(fout, "a") as ds:
        for name in ALL_VARS:
            var = ds.variables[name]
            axis = pft_axis(var)
            data = np.asarray(var[:])
            put_column(data, axis, MOSS_DST_IDX, column(data, axis, MOSS_SRC_IDX))
            if name == AREA_VAR:
                # Only the area is vacated; MONTHLY_* at index 12 become unused, not wrong.
                put_column(data, axis, MOSS_SRC_IDX, 0.0)
            var[:] = data

        stamp_history(
            ds,
            f"moved PFT index {MOSS_SRC_IDX} -> {MOSS_DST_IDX} for {AREA_VAR} (area zeroed "
            f"at {MOSS_SRC_IDX}) and for {', '.join(CANOPY_VARS)} (values left in place at "
            f"{MOSS_SRC_IDX}, now unused). Source: {os.path.basename(fin)}. Purpose: match "
            f"fates_params_moss.json, which maps moss onto HLM PFT {MOSS_DST_IDX}.",
        )
        print("\n  AFTER:")
        describe_area(ds, "AFTER")
        summarize_canopy(ds, os.path.basename(fout))


def build_grassmoss(fin, fout, moss_col, fin_moss, pending):
    shutil.copyfile(fin, fout)
    with netCDF4.Dataset(fout, "a") as ds:
        for name in CANOPY_VARS:
            var = ds.variables[name]
            data = np.asarray(var[:])
            put_column(data, pft_axis(var), MOSS_DST_IDX, moss_col[name])
            var[:] = data

        stamp_history(
            ds,
            f"replaced PFT index {MOSS_DST_IDX} of {', '.join(CANOPY_VARS)} with the "
            f"authoritative moss canopy column (index {MOSS_SRC_IDX} of "
            f"{os.path.basename(fin_moss)}); corrected: "
            f"{', '.join(pending) if pending else 'none'}. {AREA_VAR} untouched. "
            f"Source: {os.path.basename(fin)}. Purpose: match fates_params_moss.json, "
            f"which maps moss onto HLM PFT {MOSS_DST_IDX}.",
        )
        print("\n  AFTER:")
        describe_area(ds, "AFTER")
        summarize_canopy(ds, os.path.basename(fout))


def check_output_path(path, args, label):
    if os.path.exists(path) and not (args.overwrite or args.dry_run):
        raise FileExistsError(f"{label} exists (pass --overwrite to replace): {path}")
    for fin in (args.fin_moss, args.fin_grassmoss):
        if fin and os.path.abspath(fin) == os.path.abspath(path):
            raise ValueError(f"{label} is the same file as an input: {path}")


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--fin-moss",
        default=default_fin(DEFAULT_MOSS_NAME),
        help="Input ..._moss.nc (read-only). Also supplies the authoritative moss canopy "
        "column used to build the grassmoss output. "
        f"Default: $INPUTDATA/{MOSS_TESTDATA_SUBDIR}/{DEFAULT_MOSS_NAME}",
    )
    parser.add_argument(
        "--fin-grassmoss",
        default=default_fin(DEFAULT_GRASSMOSS_NAME),
        help="Input ..._grassmoss.nc (read-only). "
        f"Default: $INPUTDATA/{MOSS_TESTDATA_SUBDIR}/{DEFAULT_GRASSMOSS_NAME}",
    )
    parser.add_argument(
        "--fout-moss",
        help="Moss-only output to create. Default: the --fin-moss basename restamped with "
        "today's cYYMMDD and Pft4 appended, in the directory you invoked the script from.",
    )
    parser.add_argument(
        "--fout-grassmoss",
        help="Bare+grass+moss output to create. Default: the --fin-grassmoss basename "
        "restamped with today's cYYMMDD and Pft4 appended, in the directory you invoked the "
        "script from.",
    )
    parser.add_argument(
        "--overwrite", action="store_true", help="Permit overwriting an existing output."
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Report what would change; write nothing."
    )
    args = parser.parse_args()

    no_root = (
        "{0} not given, and neither $INPUTDATA nor $DIN_LOC_ROOT is set, so it "
        "cannot be defaulted. Pass {0} explicitly."
    )
    for label, path in (("--fin-moss", args.fin_moss), ("--fin-grassmoss", args.fin_grassmoss)):
        if path is None:
            raise ValueError(no_root.format(label))
        if not os.path.exists(path):
            raise FileNotFoundError(f"{label} does not exist: {path}")

    if args.fout_moss is None:
        args.fout_moss = default_fout(args.fin_moss)
    if args.fout_grassmoss is None:
        args.fout_grassmoss = default_fout(args.fin_grassmoss)

    check_output_path(args.fout_moss, args, "--fout-moss")
    check_output_path(args.fout_grassmoss, args, "--fout-grassmoss")
    if os.path.abspath(args.fout_moss) == os.path.abspath(args.fout_grassmoss):
        raise ValueError("--fout-moss and --fout-grassmoss are the same file.")

    moss_col = read_moss_column(args.fin_moss)
    print(f"Authoritative moss column: {args.fin_moss} index {MOSS_SRC_IDX}")
    for name in CANOPY_VARS:
        print(f"    {name:20s} max={np.max(moss_col[name]):12.6f}")

    # Validate BOTH inputs before writing EITHER output. Otherwise a bad --fin-grassmoss
    # only surfaces after the moss-only file has already been written, leaving a half-built
    # set behind -- and the retry then trips FileExistsError on that leftover.
    print(f"\n=== validating moss-only: {args.fin_moss}")
    check_moss_only(args.fin_moss)
    print(f"\n=== validating bare+grass+moss: {args.fin_grassmoss}")
    pending = check_grassmoss(args.fin_grassmoss, moss_col)

    if args.dry_run:
        print(
            f"\n--dry-run: would move index {MOSS_SRC_IDX} -> {MOSS_DST_IDX} for "
            f"{AREA_VAR} and {', '.join(CANOPY_VARS)}, into\n    {args.fout_moss}"
        )
        print(
            f"--dry-run: would overwrite index {MOSS_DST_IDX} of "
            f"{', '.join(CANOPY_VARS)} with the moss column "
            f"(corrections: {', '.join(pending) if pending else 'none'}), "
            f"{AREA_VAR} untouched, into\n    {args.fout_grassmoss}"
        )
        print("--dry-run: nothing written.")
        return

    print(f"\n=== writing moss-only: {args.fout_moss}")
    build_moss_only(args.fin_moss, args.fout_moss)
    print(f"  Wrote {args.fout_moss}")

    print(f"\n=== writing bare+grass+moss: {args.fout_grassmoss}")
    build_grassmoss(args.fin_grassmoss, args.fout_grassmoss, moss_col, args.fin_moss, pending)
    print(f"  Wrote {args.fout_grassmoss}")

    print("\nDone. Inputs were opened read-only; nothing outside the --fout paths was modified.")


if __name__ == "__main__":
    main()
