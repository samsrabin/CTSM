# %% Setup

import sys, argparse
import cropcal_module as cc
import glob, os

def main(argv):
    
    # Set arguments
    parser = argparse.ArgumentParser(description="ADD DESCRIPTION HERE")
    parser.add_argument("-d", "--directory",
                        help="Directory with CLM output history files",
                        required=True)
    parser.add_argument("--rx_sdates_file", "--rx-sdates-file",
                        help="Prescribed sowing dates file",
                        required=True)
    parser.add_argument("--rx_gdds_file", "--rx-gdds-file",
                        help="Prescribed maturity requirements file",
                        required=True)
    parser.add_argument("-y1", "--first_usable_year", "--first-usable-year", 
                        type=int,
                        help="First usable year in the outputs",
                        required=True)
    parser.add_argument("-yN", "--last_usable_year", "--last-usable-year", 
                        type=int,
                        help="Last usable year in the outputs",
                        required=True)
    args = parser.parse_args(argv)

    # Note that _PERHARV will be stripped off upon import
    myVars = ['GRAINC_TO_FOOD_PERHARV', 'GRAINC_TO_FOOD_ANN', 'SDATES', 'SDATES_PERHARV',
            'SYEARS_PERHARV', 'HDATES', 'HYEARS', 'GDDHARV_PERHARV', 'GDDACCUM_PERHARV',
            'HUI_PERHARV', 'SOWING_REASON_PERHARV', 'HARVEST_REASON_PERHARV']
    
    h2files = glob.glob(os.path.join(args.directory, "*.clm2.h2.*.nc.rxboth"))
    
    this_ds = cc.import_output(h2files, myVars=myVars,
                               y1=args.first_usable_year,
                               yN=args.last_usable_year,
                               incl_irrig=False)

    # These should be constant in a Prescribed Calendars (rxboth) run, as long as the inputs were
    # static.
    case = {
        'constantVars': ["SDATES", "GDDHARV"],
        'rx_sdates_file': args.rx_sdates_file,
        'rx_gdds_file': args.rx_gdds_file,
        }
    
    cc.check_constant_vars(this_ds, case, ignore_nan=True, verbose=True, throw_error=True)

if __name__ == "__main__":
    main(sys.argv[1:])
