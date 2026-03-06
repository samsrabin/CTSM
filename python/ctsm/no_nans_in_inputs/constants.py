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

# JSON file with list of known-good files
KNOWN_GOOD_FILES_FILE = Path(__file__).parent / "known_good.json"

# Filename suffix after fixing NaN fills
NONANFILL_SUFFIX = "no_nan_fill"

# NetCDF attribute names
FILL_ATTR = "_FillValue"
MISSING_ATTR = "missing_value"

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

# String to save as key for netCDF path if no handled NaNs were detected
NO_HANDLED_NANS = "NO HANDLED NANS DETECTED"
