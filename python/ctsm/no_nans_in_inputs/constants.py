"""
Shared constants for the no_nans_in_inputs module.
"""

from pathlib import Path

# File paths
INPUTDATA_PREFIX = "/glade/campaign/cesm/cesmdata/cseg/inputdata/"
NEW_FILLVALUES_FILE = "new_fillvalues.json"  # File to save/load new fill values
DIR_TO_SEARCH_FOR_XML_FILES = "bld/namelist_files"
OUR_PATH = "lnd/clm2/"  # String to be found in files we're responsible for
try:
    DEFAULT_CTSM_ROOT = Path(__file__).resolve().parents[3]
except IndexError:
    DEFAULT_CTSM_ROOT = Path.cwd()

# Filename suffix after fixing NaN fills
NONANFILL_SUFFIX = "no_nan_fill"

# NetCDF attribute name
ATTR = "_FillValue"

# Special commands for user input
USER_REQ_QUIT = "quit"
USER_REQ_SKIP_VAR = "skip"
USER_REQ_SKIP_FILE = "skipfile"
USER_REQ_DELETE = "delete"

# Error strings corresponding to special user commands
ERR_STR_SKIP_VAR = "SKIP_VARIABLE"
ERR_STR_SKIP_FILE = "SKIP_FILE"

# Output formatting
SEP_LENGTH = 80  # Length of horizontal separators in stdout

# Keyword arguments we want to include in every xarray.open_dataset() call.
OPEN_DS_KWARGS = {"decode_timedelta": False, "decode_times": False}

# Pattern for extracting netCDF paths (third group) from user_nl_ files
ONE_OF_OUR_FILES = f"""[^'"]*{OUR_PATH}[^'"]"""
USERNL_NC_PATTERN = rf"""^(\s*\w+\s*=\s*)(['"])({ONE_OF_OUR_FILES}*)(['"])(.*)$"""

# netCDF variables that start with any of these strings should get a default fill value of -999
VARSTARTS_TO_DEFAULT_NEG999 = ["fertl_", "irrig_", "crpbf_", "fharv_"]

# Indentation for messages
INDENT = "    "

# Skip these huge files that we already know, via `ncks --chk_nan`, to be okay. Paths relative to
# INPUTDATA_PREFIX.
KNOWN_GOOD_FILES = [
    (
        "lnd/clm2/urbandata/"
        "CTSM52_tbuildmax_OlesonFeddema_2020_mpasa3p75_fromf09_simyr1849-2106_c20240502.nc"
    ),
    (
        "lnd/clm2/surfdata_esmf/ctsm5.4.0/"
        "landuse.timeseries_360x720cru_hist_1850-2023_78pfts_c251022.nc"
    ),
    (
        "lnd/clm2/surfdata_esmf/ctsm5.3.0/"
        "landuse.timeseries_360x720cru_SSP2-4.5_1850-2100_78pfts_c240908.nc"
    ),
    "lnd/clm2/surfdata_esmf/ctsm5.4.0/landuse.timeseries_0.9x1.25_hist_1850-2023_78pfts_c250428.nc"
]
