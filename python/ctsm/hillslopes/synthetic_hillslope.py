"""
 specify a synthetic hillslope profile
"""

import argparse
import os
import shutil
import sys
import numpy as np
from netCDF4 import Dataset  # pylint: disable=no-name-in-module

# The above "pylint: disable" is because pylint complains that netCDF4 has no member Dataset, even
# though it does.
from ctsm.hillslopes.hillslope_utils import create_variables as shared_create_variables


def parse_arguments(argv):
    """
    Parse arguments to script
    """
    parser = argparse.ArgumentParser(description="Specify a synthetic hillslope profile")

    # Input and output file settings
    parser.add_argument(
        "-i",
        "--input-file",
        help="Input surface dataset",
        required=True,
    )
    parser.add_argument(
        "-o",
        "--output-file",
        help="Output surface dataset",
        default=None,
    )
    parser.add_argument(
        "--overwrite",
        help="Overwrite existing output file",
        dest="overwrite",
        action="store_true",
    )

    # Synthetic hillslope settings
    parser.add_argument(
        "--delx",
        help="increments to use in numerical integration of mean elevation (m)",
        type=float,
        default=1.0,
    )
    parser.add_argument(
        "--hcase",
        help="hcase",
        type=str,
        default="slope_aspect",
        choices=["slope_aspect"],
    )
    parser.add_argument(
        "--hillslope-distance",
        help="distance from channel to ridge (m)",
        type=float,
        default=500.0,
    )
    parser.add_argument(
        "--nmaxhillcol",
        help="max. number of hillslope columns",
        type=int,
        default=16,
    )
    parser.add_argument(
        "--num-hillslopes",
        help="number of hillslopes",
        type=int,
        default=4,
    )
    parser.add_argument(
        "--phill",
        help="shape parameter (power law exponent)",
        type=float,
        default=1.0,
    )
    parser.add_argument(
        "--thresh",
        help="threshold for freating specified fractional bins",
        type=float,
        default=2.0,
    )
    parser.add_argument(
        "--width-reach",
        help="uniform width of reach (m)",
        type=float,
        default=500.0,
    )

    args = parser.parse_args(argv)

    if args.output_file is None:
        stem, ext = os.path.splitext(args.input_file)
        args.output_file = stem + ".synth_hillslopes" + ext

    if os.path.exists(args.output_file) and not args.overwrite:
        raise FileExistsError(f"Output file already exists: {args.output_file}")

    return args


def write_to_file(
    args,
    lmask,
    max_columns_per_landunit,
    pct_landunit,
    distance,
    area,
    width,
    elevation,
    slope,
    aspect,
    col_ndx,
    col_dndx,
    hill_ndx,
):
    """
    Write to file
    """
    shutil.copyfile(args.input_file, args.output_file)

    outfile = Dataset(args.output_file, "a")
    outfile.createDimension("nhillslope", args.num_hillslopes)
    outfile.createDimension("nmaxhillcol", max_columns_per_landunit)

    create_variables(outfile)

    outfile.variables["nhillcolumns"][:, :] = max_columns_per_landunit * lmask
    outfile.variables["pct_hillslope"][
        :,
    ] = pct_landunit
    outfile.variables["hillslope_index"][
        :,
    ] = hill_ndx
    outfile.variables["column_index"][
        :,
    ] = col_ndx
    outfile.variables["downhill_column_index"][
        :,
    ] = col_dndx
    outfile.variables["hillslope_distance"][
        :,
    ] = distance
    outfile.variables["hillslope_width"][
        :,
    ] = width
    outfile.variables["hillslope_elevation"][
        :,
    ] = elevation
    outfile.variables["hillslope_slope"][
        :,
    ] = slope
    outfile.variables["hillslope_aspect"][
        :,
    ] = aspect
    outfile.variables["hillslope_area"][
        :,
    ] = area
    outfile.variables["hillslope_bedrock_depth"][
        :,
    ] = 2

    # add stream variables
    wdepth = outfile.createVariable("hillslope_stream_depth", np.float64, ("lsmlat", "lsmlon"))
    wwidth = outfile.createVariable("hillslope_stream_width", np.float64, ("lsmlat", "lsmlon"))
    wslope = outfile.createVariable("hillslope_stream_slope", np.float64, ("lsmlat", "lsmlon"))

    wdepth.long_name = "stream channel bankfull depth"
    wdepth.units = "m"

    wwidth.long_name = "stream channel bankfull width"
    wwidth.units = "m"

    wslope.long_name = "stream channel slope"
    wslope.units = "m/m"

    # Calculate stream geometry from hillslope parameters
    uharea = np.sum(area, axis=0)
    adepth, bdepth = 1e-3, 0.4
    wdepth[
        :,
    ] = adepth * (uharea**bdepth)
    awidth, bwidth = 1e-3, 0.6
    wwidth[
        :,
    ] = awidth * (uharea**bwidth)
    wslope[
        :,
    ] = 1e-2

    # Save settings as global attributes
    outfile.synth_hillslopes_delx = args.delx
    outfile.synth_hillslopes_hcase = args.hcase
    outfile.synth_hillslopes_hillslope_distance = args.hillslope_distance
    outfile.synth_hillslopes_nmaxhillcol = args.nmaxhillcol
    outfile.synth_hillslopes_num_hillslopes = args.num_hillslopes
    outfile.synth_hillslopes_phill = args.phill
    outfile.synth_hillslopes_thresh = args.thresh
    outfile.synth_hillslopes_width_reach = args.width_reach

    print("created ", args.output_file)

    # --  Close output file
    outfile.close()


def create_variables(outfile):
    """
    Create variables in output file
    """

    shared_create_variables(outfile)

    opft = outfile.createVariable(
        "hillslope_pftndx",
        np.int32,
        (
            "nmaxhillcol",
            "lsmlat",
            "lsmlon",
        ),
    )
    opft.units = "unitless"
    opft.long_name = "hillslope pft indices"

    outfile.variables["hillslope_pftndx"][
        :,
    ] = 13


"""
---------------------------------------------------
#cosine - power law hillslope
create bins of equal height
this form ensures a near-zero slope at the hill top
---------------------------------------------------
"""  # pylint: disable=pointless-string-statement


def cosp_height(x, hlen, hhgt, phill):
    """
    Get elevation
    """
    fx = 0.5 * (1.0 + np.cos(np.pi * (1.0 + (x / hlen))))
    h = hhgt * np.power(fx, phill)
    return h


def icosp_height(h, hlen, hhgt, phill):
    """
    Fill lbins
    """
    if hhgt <= 0.0:
        x = 0.0
    else:
        fh = np.arccos(2.0 * np.power((h / hhgt), (1.0 / phill)) - 1)
        # np.arccos returns [0,pi]
        # want [pi,2pi] based on cosp_height definition
        fh = 2.0 * np.pi - fh
        x = hlen * ((1.0 / np.pi) * fh - 1.0)
    return x


def calc_mean_elevation(args, hhgt, uedge, ledge):
    """
    numerically integrate to calculate mean elevation
    """
    nx = int(uedge - ledge)
    mean_elev = 0.0
    for k in range(nx):
        x1 = uedge - (k + 0.5) * args.delx
        mean_elev += cosp_height(x1, args.hillslope_distance, hhgt, args.phill)
    mean_elev = mean_elev / float(nx)
    return mean_elev


def create_bins(args, max_columns_per_hillslope, bin_fractions, hhgt):
    """
    create specified fractional bins
    """

    # create height bins
    hbins = np.zeros(max_columns_per_hillslope + 1)
    hbins[1] = args.thresh
    # array needs to be length max_columns_per_hillslope-1
    hbins[2 : max_columns_per_hillslope + 1] = hbins[1] + (hhgt - args.thresh) * bin_fractions

    # create length bins from height bins
    lbins = np.zeros(max_columns_per_hillslope + 1)
    for n in range(max_columns_per_hillslope + 1):
        if hhgt > 0.0:
            lbins[n] = icosp_height(hbins[n], args.hillslope_distance, hhgt, args.phill)
    return hbins, lbins


def define_hillslope_geom_arrays(args, n_lon, n_lat, max_columns_per_landunit):
    """
    Define arrays governing hillslope geometry
    """
    # percentage of landunit occupied by each hillslope (must sum to 100)
    pct_landunit = np.zeros((args.num_hillslopes, n_lat, n_lon))
    # distance of column midpoint from stream channel
    distance = np.zeros((max_columns_per_landunit, n_lat, n_lon), dtype=float)
    # area of column
    area = np.zeros((max_columns_per_landunit, n_lat, n_lon), dtype=float)
    # width of interface with downstream column (or channel)
    width = np.zeros((max_columns_per_landunit, n_lat, n_lon), dtype=float)
    # elevation of column midpoint
    elevation = np.zeros((max_columns_per_landunit, n_lat, n_lon), dtype=float)
    # mean slope of column
    slope = np.zeros((max_columns_per_landunit, n_lat, n_lon), dtype=float)
    # azimuth angle of column
    aspect = np.zeros((max_columns_per_landunit, n_lat, n_lon), dtype=float)
    # column identifier index
    col_ndx = np.zeros((max_columns_per_landunit, n_lat, n_lon), dtype=np.int32)
    # index of downhill column
    col_dndx = np.zeros((max_columns_per_landunit, n_lat, n_lon), dtype=np.int32)
    # index of hillslope type
    hill_ndx = np.zeros((max_columns_per_landunit, n_lat, n_lon), dtype=np.int32)
    return (
        pct_landunit,
        distance,
        area,
        width,
        elevation,
        slope,
        aspect,
        col_ndx,
        col_dndx,
        hill_ndx,
    )


def main():
    """
    See module description
    """

    args = parse_arguments(sys.argv[1:])

    infile = Dataset(args.input_file, "r")
    n_lon = len(infile.dimensions["lsmlon"])
    n_lat = len(infile.dimensions["lsmlat"])
    std_elev = np.asarray(infile.variables["STD_ELEV"][:, :])
    lmask = np.asarray(infile.variables["PFTDATA_MASK"][:, :])
    pct_natveg = np.asarray(infile.variables["PCT_NATVEG"][:, :])
    infile.close()

    # are any points in land mask but have zero % natveg?
    print("zero natveg pts ", np.sum(np.where(np.logical_and(lmask == 1, pct_natveg == 0), 1, 0)))
    lmask = np.where(np.logical_and(lmask == 1, pct_natveg > 0), 1, 0).astype(int)

    max_columns_per_hillslope = args.nmaxhillcol // args.num_hillslopes

    if max_columns_per_hillslope == 4:
        bin_fractions = np.array((0.25, 0.75, 1.0))
    elif max_columns_per_hillslope == 5:
        bin_fractions = np.array((0.25, 0.50, 0.75, 1.0))
    elif max_columns_per_hillslope == 6:
        bin_fractions = np.array((0.20, 0.40, 0.60, 0.80, 1.0))
    else:
        raise RuntimeError(f"Unhandled max_columns_per_hillslope: {max_columns_per_hillslope}")

    max_columns_per_landunit = args.num_hillslopes * max_columns_per_hillslope

    # --  define geometry of hillslopes
    (
        pct_landunit,
        distance,
        area,
        width,
        elevation,
        slope,
        aspect,
        col_ndx,
        col_dndx,
        hill_ndx,
    ) = define_hillslope_geom_arrays(args, n_lon, n_lat, max_columns_per_landunit)

    cndx = 0
    for i in range(n_lon):
        for j in range(n_lat):
            if lmask[j, i] != 1:
                continue

            # slope tangent (y/x)
            beta = np.min((std_elev[j, i], 200.0)) / args.hillslope_distance

            # specify hill height from slope and length
            hhgt = beta * args.hillslope_distance
            hhgt = np.max([hhgt, 4.0])

            # create specified fractional bins
            hbins, lbins = create_bins(args, max_columns_per_hillslope, bin_fractions, hhgt)

            # loop over aspect bins
            for naspect in range(args.num_hillslopes):
                pct_landunit[naspect, j, i] = 100 / float(args.num_hillslopes)
                # index from ridge to channel (i.e. downhill)
                for n in range(max_columns_per_hillslope):
                    ncol = n + naspect * max_columns_per_hillslope

                    cndx += 1  # start at 1 not zero (oceans are 0)
                    col_ndx[ncol, j, i] = cndx
                    hill_ndx[ncol, j, i] = naspect + 1

                    uedge = lbins[n + 1]
                    ledge = lbins[n]
                    #      lowland column
                    if n == 0:
                        col_dndx[ncol, j, i] = -999
                    else:  # upland columns
                        col_dndx[ncol, j, i] = col_ndx[ncol, j, i] - 1

                    distance[ncol, j, i] = 0.5 * (uedge + ledge)
                    area[ncol, j, i] = args.width_reach * (uedge - ledge)
                    width[ncol, j, i] = args.width_reach

                    # numerically integrate to calculate mean elevation
                    elevation[ncol, j, i] = calc_mean_elevation(args, hhgt, uedge, ledge)

                    slope[ncol, j, i] = (hbins[n + 1] - hbins[n]) / (lbins[n + 1] - lbins[n])
                    if 0 <= naspect <= 3:
                        # 0 = north
                        # 1 = east
                        # 2 = south
                        # 3 = west
                        aspect[ncol, j, i] = naspect * np.pi / 2
                    else:
                        raise RuntimeError(f"Unhandled naspect: {naspect}")

    # write to file  --------------------------------------------
    write_to_file(
        args,
        lmask,
        max_columns_per_landunit,
        pct_landunit,
        distance,
        area,
        width,
        elevation,
        slope,
        aspect,
        col_ndx,
        col_dndx,
        hill_ndx,
    )
