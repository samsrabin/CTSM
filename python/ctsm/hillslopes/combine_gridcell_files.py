"""
Combine gridcell files into single file
"""
import sys
import os
import subprocess
import argparse
import netCDF4 as netcdf4
import numpy as np
from ctsm.hillslopes.hillslope_utils import create_variables as shared_create_variables


def parse_arguments(argv):
    """
    Parse arguments to script
    """
    parser = argparse.ArgumentParser(description="Combine gridcell files into single file")

    parser.add_argument(
        "-i",
        "--input-file",
        help="Input surface dataset with grid information",
        required=True,
    )
    parser.add_argument(
        "-d",
        "--input-dir",
        help="Directory containing chunk files",
        required=True,
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        help="Directory where output file should be saved (default: current dir)",
        default=os.getcwd(),
    )
    dem_source_default = "MERIT"
    parser.add_argument(
        "--dem-source",
        help=f"DEM to use (default: {dem_source_default})",
        type=str,
        default=dem_source_default,
    )
    parser.add_argument("cndx", help="chunk", nargs="?", type=int, default=0)
    parser.add_argument("--overwrite", help="overwrite", action="store_true", default=False)
    parser.add_argument("-v", "--verbose", help="print info", action="store_true", default=False)

    args = parser.parse_args(argv)

    # Check arguments
    if not os.path.exists(args.input_file):
        raise FileNotFoundError(f"Input file not found: {args.input_file}")
    if not os.path.exists(args.input_dir):
        raise FileNotFoundError(f"Input directory not found: {args.input_dir}")
    if not os.path.exists(args.output_dir):
        os.makedirs(args.output_dir)

    return args


def main():
    """
    See module description
    """

    args = parse_arguments(sys.argv[1:])
    cndx = args.cndx
    verbose = args.verbose

    totalChunks = 36
    if cndx < 1 or cndx > totalChunks:
        raise RuntimeError("cndx must be 1-{:d}".format(totalChunks))

    printFlush = True

    # Gridcell file directory
    cfile = os.path.join(
        args.input_dir,
        "chunk_{:02d}_HAND_4_col_hillslope_geo_params_section_quad_{}.nc".format(
            cndx, args.dem_source
        ),
    )

    # Output file
    outfile = os.path.join(
        args.output_dir, cfile.split("/")[-1].replace("chunk_", "combined_chunk_")
    )

    # Read output file coordinates
    f = netcdf4.Dataset(args.input_file, "r")
    sjm = len(f.dimensions["lsmlat"])
    sim = len(f.dimensions["lsmlon"])
    f.close()

    # Check for output file existence
    command = ["ls", outfile]
    file_exists = subprocess.run(command, capture_output=True).returncode
    # if file_exists !=0, file not found
    if file_exists == 0:
        if args.overwrite:
            if verbose:
                print(outfile, " exists; overwriting", flush=printFlush)
        else:
            raise FileExistsError(outfile, " exists; stopping", flush=printFlush)

    # Locate gridcell files
    gfile = cfile.replace(".nc", "*.nc")

    command = "ls " + gfile
    gfiles = (
        subprocess.run(command, capture_output=True, shell="True")
        .stdout.decode("utf-8")
        .split("\n")[:-1]
    )

    if len(gfiles) == 0:
        raise FileNotFoundError("No files found")

    # Read hillslope data dimensions
    f = netcdf4.Dataset(gfiles[0], "r")
    nhillslope = len(f.dimensions["nhillslope"])
    nmaxhillcol = len(f.dimensions["nmaxhillcol"])

    if "hillslope_bedrock_depth" in f.variables.keys():
        addBedrock = True
    else:
        addBedrock = False

    if "hillslope_stream_depth" in f.variables.keys():
        addStreamChannelVariables = True
    else:
        addStreamChannelVariables = False
    f.close()

    # initialize outfile
    command = 'date "+%y%m%d"'
    timetag = (
        subprocess.Popen(command, stdout=subprocess.PIPE, shell="True")
        .communicate()[0]
        .strip()
        .decode()
    )

    write_to_file(
        outfile,
        sjm,
        sim,
        gfiles,
        nhillslope,
        nmaxhillcol,
        addBedrock,
        addStreamChannelVariables,
        timetag,
    )


def write_to_file(
    outfile,
    sjm,
    sim,
    gfiles,
    nhillslope,
    nmaxhillcol,
    addBedrock,
    addStreamChannelVariables,
    timetag,
):
    """
    Write to file
    """
    w = netcdf4.Dataset(outfile, "w")
    w.creation_date = timetag

    w.createDimension("lsmlon", sim)
    w.createDimension("lsmlat", sjm)
    w.createDimension("nhillslope", nhillslope)
    w.createDimension("nmaxhillcol", nmaxhillcol)

    (
        olon,
        olat,
        olon2d,
        olat2d,
        ohand,
        odtnd,
        owidth,
        oarea,
        oslop,
        oasp,
        obed,
        onhill,
        opcthill,
        ohillndx,
        ocolndx,
        odcolndx,
        ocmask,
        osdepth,
        oswidth,
        osslope,
    ) = create_variables(addStreamChannelVariables, w)

    # loop over gridcell files
    for gfile in gfiles:
        y1, x1 = gfile.index("j_"), gfile.index("i_")
        j, i = int(gfile[y1 + 2 : y1 + 5]), int(gfile[x1 + 2 : x1 + 5])

        f = netcdf4.Dataset(gfile, "r")
        lon = f.variables["longitude"][
            :,
        ]
        lat = f.variables["latitude"][
            :,
        ]
        lon2d = f.variables["LONGXY"][
            :,
        ]
        lat2d = f.variables["LATIXY"][
            :,
        ]
        chunk_mask = f.variables["chunk_mask"][
            :,
        ]

        hillslope_elev = np.asarray(
            f.variables["hillslope_elevation"][
                :,
            ]
        )
        hillslope_dist = np.asarray(
            f.variables["hillslope_distance"][
                :,
            ]
        )
        hillslope_width = np.asarray(
            f.variables["hillslope_width"][
                :,
            ]
        )
        hillslope_area = np.asarray(
            f.variables["hillslope_area"][
                :,
            ]
        )
        hillslope_slope = np.asarray(
            f.variables["hillslope_slope"][
                :,
            ]
        )
        hillslope_aspect = np.asarray(
            f.variables["hillslope_aspect"][
                :,
            ]
        )
        if addBedrock:
            hillslope_bedrock = np.asarray(
                f.variables["hillslope_bedrock_depth"][
                    :,
                ]
            )
        if addStreamChannelVariables:
            hillslope_stream_depth = np.asarray(
                f.variables["hillslope_stream_depth"][
                    :,
                ]
            )
            hillslope_stream_width = np.asarray(
                f.variables["hillslope_stream_width"][
                    :,
                ]
            )
            hillslope_stream_slope = np.asarray(
                f.variables["hillslope_stream_slope"][
                    :,
                ]
            )

        nhillcolumns = f.variables["nhillcolumns"][
            :,
        ].astype(int)
        pct_hillslope = f.variables["pct_hillslope"][
            :,
        ]
        hillslope_index = f.variables["hillslope_index"][
            :,
        ].astype(int)
        column_index = f.variables["column_index"][
            :,
        ].astype(int)
        downhill_column_index = f.variables["downhill_column_index"][
            :,
        ].astype(int)
        f.close()

        olon[i] = lon
        olat[j] = lat
        olon2d[j, i] = lon2d
        olat2d[j, i] = lat2d

        ohand[:, j, i] = hillslope_elev
        odtnd[:, j, i] = hillslope_dist
        oarea[:, j, i] = hillslope_area
        owidth[:, j, i] = hillslope_width
        oslop[:, j, i] = hillslope_slope
        oasp[:, j, i] = hillslope_aspect
        opcthill[:, j, i] = pct_hillslope
        onhill[j, i] = np.int32(nhillcolumns)
        ohillndx[:, j, i] = hillslope_index.astype(np.int32)
        ocolndx[:, j, i] = column_index.astype(np.int32)
        odcolndx[:, j, i] = downhill_column_index.astype(np.int32)
        ocmask[j, i] = np.int32(chunk_mask)
        if addBedrock:
            obed[:, j, i] = hillslope_bedrock

        if addStreamChannelVariables:
            osdepth[j, i] = hillslope_stream_depth
            oswidth[j, i] = hillslope_stream_width
            osslope[j, i] = hillslope_stream_slope

    w.close()
    print(outfile + " created")


def create_variables(addStreamChannelVariables, w):
    olon = w.createVariable("longitude", float, ("lsmlon",))
    olon.units = "degrees"
    olon.long_name = "longitude"

    olat = w.createVariable("latitude", float, ("lsmlat",))
    olat.units = "degrees"
    olat.long_name = "latitude"

    olon2d = w.createVariable(
        "LONGXY",
        float,
        (
            "lsmlat",
            "lsmlon",
        ),
    )
    olon2d.units = "degrees"
    olon2d.long_name = "longitude - 2d"

    olat2d = w.createVariable(
        "LATIXY",
        float,
        (
            "lsmlat",
            "lsmlon",
        ),
    )
    olat2d.units = "degrees"
    olat2d.long_name = "latitude - 2d"

    (
        ohand,
        odtnd,
        owidth,
        oarea,
        oslop,
        oasp,
        onhill,
        opcthill,
        ohillndx,
        ocolndx,
        odcolndx,
        obed,
    ) = shared_create_variables(w)

    ocmask = w.createVariable(
        "chunk_mask",
        np.int32,
        (
            "lsmlat",
            "lsmlon",
        ),
    )
    ocmask.units = "unitless"
    ocmask.long_name = "chunk mask"

    if addStreamChannelVariables:
        wdims = w["LONGXY"].dimensions
        osdepth = w.createVariable("hillslope_stream_depth", float, wdims)
        oswidth = w.createVariable("hillslope_stream_width", float, wdims)
        osslope = w.createVariable("hillslope_stream_slope", float, wdims)

        osdepth.long_name = "stream channel bankfull depth"
        osdepth.units = "m"

        oswidth.long_name = "stream channel bankfull width"
        oswidth.units = "m"

        osslope.long_name = "stream channel slope"
        osslope.units = "m/m"

    # Initialize arrays
    olon[
        :,
    ] = 0
    olat[
        :,
    ] = 0
    olon2d[
        :,
    ] = 0
    olat2d[
        :,
    ] = 0

    ohand[
        :,
    ] = 0
    odtnd[
        :,
    ] = 0
    oarea[
        :,
    ] = 0
    owidth[
        :,
    ] = 0
    oslop[
        :,
    ] = 0
    obed[
        :,
    ] = 0
    oasp[
        :,
    ] = 0
    opcthill[
        :,
    ] = 0
    onhill[
        :,
    ] = 0
    ohillndx[
        :,
    ] = 0
    ocolndx[
        :,
    ] = 0
    odcolndx[
        :,
    ] = 0
    ocmask[
        :,
    ] = 0

    if addStreamChannelVariables:
        osdepth[
            :,
        ] = 0
        oswidth[
            :,
        ] = 0
        osslope[
            :,
        ] = 0

    return (
        olon,
        olat,
        olon2d,
        olat2d,
        ohand,
        odtnd,
        owidth,
        oarea,
        oslop,
        oasp,
        obed,
        onhill,
        opcthill,
        ohillndx,
        ocolndx,
        odcolndx,
        ocmask,
        osdepth,
        oswidth,
        osslope,
    )
