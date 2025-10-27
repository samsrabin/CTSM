"""
Script to make a version of a paramfile with all GGCMI crops activated
"""

import os
import sys
import argparse

_CTSM_PYTHON = os.path.join(
    os.path.dirname(os.path.realpath(__file__)), os.pardir, os.pardir, "python"
)
sys.path.insert(1, _CTSM_PYTHON)

from ctsm.param_utils.paramfile_shared import open_paramfile, get_pft_names  # pylint: disable=import-error,wrong-import-position,no-name-in-module
from ctsm.param_utils.set_paramfile import main as set_paramfile  # pylint: disable=import-error,wrong-import-position,no-name-in-module

# For GGCMI phase 3. List members are CLM names, comments are GGCMI names.
# GGCMI's bea and rap are being ignored because CLM has nothing that fits. We could choose arbitrary
# crops for these, but their growing degree-day base temperatures might not end up corresponding to
# what they "should" be. (That applies more generally to all the untested CFTs we're enabling here,
# but at least those were based on something originally.)
GGCMI_CROP_LIST = [
    "barley",  # bar
    # "",  # bea; CLM has nothing else (except pulses, which are being used for pea)
    "cassava",  # cas
    "cotton",  # cot
    "corn",  # mai,
    "millet",  # mil
    "nut",  # nut
    "pulses",  # pea; based on suggested mapping to 15crop pulses
    "potato",  # pot
    # "",  # rap; CLM has no rapeseed/canola
    "rice",  # ric/ri1/ri2
    "rye",  # rye
    "sugarbeet",  # sgb
    "sugarcane",  # sgc
    "sorghum",  # sor
    "soybean",  # soy
    "sunflower",  # sun
    "spring_wheat",  # swh
    "winter_wheat",  # wwh
]


def main(input_file, output_file):
    # Open parameter file
    ds_in = open_paramfile(input_file)

    pft_names = get_pft_names(ds_in)

    pft_arg_list = []
    mergetoclmpft_arg_list = []
    for crop in GGCMI_CROP_LIST:
        matching_pft_names = [pft for pft in pft_names if crop in pft]

        # Exclude CLM's winter barley and rye, since GGCMI doesn't have equivalents
        if "winter" not in crop:
            matching_pft_names = [
                pft for pft in matching_pft_names if "winter" not in pft
            ]

        # We expect a nonzero, even number of matches (because of rainfed+irrigataed)
        n_matches = len(matching_pft_names)
        assert n_matches > 0 and int(n_matches / 2) == n_matches / 2

        for pft_name in matching_pft_names:
            pft_arg_list.append(pft_name)
            mergetoclmpft_arg_list.append(pft_names.index(pft_name))

    pft_arg = ",".join(pft_arg_list)
    mergetoclmpft_arg = ",".join(str(x) for x in mergetoclmpft_arg_list)

    set_paramfile_args = [
        "set_paramfile",
        "-i",
        input_file,
        "-o",
        output_file,
        "-p",
        pft_arg,
        "mergetoclmpft=" + mergetoclmpft_arg,
    ]
    argv_orig = sys.argv
    sys.argv = set_paramfile_args
    set_paramfile()
    sys.argv = argv_orig


if __name__ == "__main__":
    ###############################
    ### Process input arguments ###
    ###############################
    parser = argparse.ArgumentParser(
        description="Activate all (well, most) GGCMI crops in a CLM run",
    )

    # Required
    parser.add_argument(
        "input_file",
        help="Input paramfile",
    )
    parser.add_argument(
        "output_file",
        help="Output paramfile",
    )

    # Get arguments
    args = parser.parse_args(sys.argv[1:])

    main(args.input_file, args.output_file)
