"""Functions for working with netCDF files"""

import os
import sys
import re
import subprocess
from typing import Any, List, NamedTuple, Tuple
import logging

import numpy as np
import xarray as xr
from netCDF4 import Dataset, Variable  # pylint: disable=no-name-in-module

# Add the python directory to sys.path for direct script execution
_CTSM_PYTHON = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
if _CTSM_PYTHON not in sys.path:
    sys.path.insert(1, _CTSM_PYTHON)

from ctsm.no_nans_in_inputs.constants import (  # pylint: disable=wrong-import-position
    ATTR,
    INDENT,
    INPUTDATA_PREFIX,
    KNOWN_GOOD_FILES,
    OPEN_DS_KWARGS,
    USER_REQ_DELETE,
)

from ctsm.no_nans_in_inputs.shared import (  # pylint: disable=wrong-import-position
    FillValueConfig,
    VarContext,
)
from ctsm.no_nans_in_inputs.constants import (  # pylint: disable=wrong-import-position
    VARSTARTS_TO_DEFAULT_NEG999,
)

from ctsm.ctsm_logging import (  # pylint: disable=wrong-import-position
    error,
    info,
    warn,
)

# Set up logging
logger = logging.getLogger(__name__)


def build_ncatted_command(
    input_file: str,
    output_file: str,
    var_fillvalues: dict[str, Any],
    var_fillmissing: dict[str, dict[str:Any]],
) -> list[str]:
    """
    Build ncatted command to modify or delete fill values.

    Args:
        input_file: Path to input NetCDF file
        output_file: Path to output NetCDF file
        var_fillvalues: Dictionary mapping variable names to new fill values
                        (or USER_REQ_DELETE to delete the attribute)
        var_fillmissing: Dictionary mapping variable names to new fill/missing values

    Returns:
        Command as list of arguments for subprocess

    Raises:
        ValueError: If input and output files are the same, or if variable not found
    """
    # Ensure input and output files are different (resolve symlinks)
    input_real = os.path.realpath(input_file)
    output_real = os.path.realpath(output_file)

    if input_real == output_real:
        error(
            logger,
            f"Input and output files are the same: {input_file} -> {input_real}",
            error_type=ValueError,
        )

    # ncatted command will probably fail if any variable is in both these dicts
    for var in var_fillvalues:
        if var in var_fillmissing:
            error(
                logger,
                f"Variable {var} is in both var_fillvalues and var_fillmissing",
                error_type=NotImplementedError,
            )

    cmd = ["ncatted", "-O"]  # -O flag to overwrite without prompting

    ds = xr.open_dataset(input_file, **OPEN_DS_KWARGS)
    for var, fill_val in var_fillvalues.items():
        if fill_val == USER_REQ_DELETE:
            # Delete the attribute: -a attr_name,var_name,d,,
            cmd.extend(["-a", f"{ATTR},{var},d,,"])
        else:
            type_code = _get_ncatted_dtype_and_type_code(input_file, var, ds)

            # Modify the attribute: -a attr_name,var_name,o,type,value
            cmd.extend(["-a", f"{ATTR},{var},o,{type_code},{fill_val}"])
    ds.close()

    ds = xr.open_dataset(input_file, **OPEN_DS_KWARGS, mask_and_scale=False)
    for var, fillmissing_dict in var_fillmissing.items():
        type_code = _get_ncatted_dtype_and_type_code(input_file, var, ds, allow_int=True)
        for attr, new_val in fillmissing_dict.items():
            cmd.extend(["-a", f"{attr},{var},o,{type_code},{new_val}"])
    ds.close()

    # Add input and output files
    cmd.extend([input_file, output_file])

    return cmd


def _get_ncatted_dtype_and_type_code(input_file, var, ds, allow_int=False):
    # Get the actual data type from the file
    dtype = None
    if var in ds.data_vars:
        dtype = ds[var].dtype
    elif var in ds.coords:
        dtype = ds[var].dtype
    else:
        # Variable not found - raise error
        ds.close()
        error(logger, f"Variable '{var}' not found in {input_file}", error_type=ValueError)

    # Get the appropriate type code for ncatted
    type_code = _get_ncatted_type_code(dtype, allow_int)
    return type_code


def execute_ncatted_command(cmd: list[str]) -> int:
    """
    Runs the ncatted command to create the output file with modified fill values.

    Args:
        cmd: ncatted command as list of arguments

    Returns:
        Number of files processed (1 on success, 0 on skip)

    Raises:
        SystemExit: If ncatted command fails or is not found
    """
    info(logger, "\nExecuting...")
    files_processed = 0
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        info(logger, f"{INDENT}✓ Success")
        if result.stdout:
            info(logger, f"{INDENT}stdout: {result.stdout}")
        if result.stderr:
            info(logger, f"{INDENT}stderr: {result.stderr}")
        files_processed = 1

    except subprocess.CalledProcessError as e:
        msg = f"  ✗ Error: ncatted failed with exit code {e.returncode}"
        if e.stdout:
            msg += f"\n{INDENT}stdout: {e.stdout}"
        if e.stderr:
            msg += f"\n{INDENT}stderr: {e.stderr}"
        error(logger, msg + f"\n{e}", error_type=subprocess.CalledProcessError)
        raise e
    except FileNotFoundError:
        msg = f"{INDENT}✗ Error: ncatted command not found\n"
        msg += f"{INDENT}Please ensure NCO (NetCDF Operators) is installed"
        error_type = INDENT if logger.getEffectiveLevel() <= logging.DEBUG else None
        error(logger, msg, error_type=error_type)
        sys.exit(7)
    return files_processed


class FillValueMismatch(NamedTuple):
    var_name: str
    fill_value: object
    missing_value: object


def file_has_mismatched_fill_missing(nc_path: str) -> Tuple[bool, List[FillValueMismatch]]:
    """
    Return list of (var_name, fill_value, missing_value, dtype)
    for variables where both attributes exist and do not match.
    """

    mismatches = []

    with Dataset(nc_path, "r") as ds:
        for name, var in ds.variables.items():
            mismatch = var_has_mismatched_fill_missing(name, var)
            if mismatch:
                mismatches.append(mismatch)
    return bool(mismatches), mismatches


def var_has_mismatched_fill_missing(name: str, var: Variable) -> FillValueMismatch | None:
    if not hasattr(var, "_FillValue") or not hasattr(var, "missing_value"):
        return None

    fill_val = var._FillValue  # pylint: disable=protected-access
    missing_val = var.missing_value

    # Convert both explicitly to the variable dtype
    dtype = var.dtype
    fill_cast = np.array(fill_val, dtype=dtype).item()
    missing_cast = np.array(missing_val, dtype=dtype).item()

    # Handle NaN safely
    if np.issubdtype(dtype, np.floating):
        equal = (np.isnan(fill_cast) and np.isnan(missing_cast)) or fill_cast == missing_cast
    else:
        equal = fill_cast == missing_cast

    if not equal:
        mismatch = FillValueMismatch(
            var_name=name, fill_value=fill_cast, missing_value=missing_cast
        )
    else:
        mismatch = None
    return mismatch


def file_has_nan_ncks_chk_nan(abs_path: str) -> bool:
    """
    Use ncks --chk_nan to determine whether a netCDF file has a NaN
    """
    cmd = ["ncks", "--chk_nan", str(abs_path)]
    if logger.getEffectiveLevel() <= logging.DEBUG:
        stdout = None
    else:
        stdout = subprocess.DEVNULL
    result = subprocess.run(cmd, check=False, stdout=stdout)

    # We expect returncode 1 if NaN is found, 0 if not. Anything else is an unhandled error.
    if result.returncode > 1:
        error(
            logger,
            f"Unexpected error code {result.returncode} during ncks --chk_nan of '{abs_path}'",
            error_type=NotImplementedError,
        )

    return bool(result.returncode)


def file_has_nan_fill(abs_path: str) -> Tuple[bool, List[str]]:
    """
    Check if a netCDF file has any variable with NaN fill value attribute.

    Args:
        abs_path: Absolute path to file

    Returns:
        bool: True if the file has any variable with NaN fill value attribute, False otherwise
        List[str]: Variables with NaN fill value attributes
    """
    vars_with_nan_fills = get_vars_with_nan_fills(abs_path)

    return bool(vars_with_nan_fills), vars_with_nan_fills


def _get_ncatted_type_code(dtype: np.dtype, allow_int=False) -> str:
    """
    Get ncatted type code from numpy dtype.

    Args:
        dtype: numpy dtype object

    Returns:
        ncatted type code (f, d, c)

    Raises:
        ValueError: If dtype is not recognized or is an integer type
                    (NetCDF doesn't allow NaN fill values for integers)
    """
    dtype_str = str(dtype)

    # Float types
    if "float64" in dtype_str or "float_" in dtype_str:
        return "d"  # double
    if "float32" in dtype_str:
        return "f"  # float

    # Integer types - not allowed (NetCDF doesn't support NaN for integers)
    if any(
        x in dtype_str for x in ["int64", "int32", "int16", "int8", "int_", "byte"]
    ):
        if not allow_int:
            msg = (
                f"Integer dtype detected: {dtype}. "
                "NetCDF does not allow NaN fill values for integer variables. So how'd this happen?"
            )
            error(logger, msg, error_type=ValueError)
        elif dtype_str == "int32":
            return "l"
        elif dtype_str == "int16":
            return "s"
        else:
            raise NotImplementedError(f"ncatted type code not known for type {dtype_str}")

    # String/char
    if "str" in dtype_str or "char" in dtype_str or "U" in dtype_str or "S" in dtype_str:
        return "c"  # char

    # Unknown type - raise error
    error(logger, f"Unknown dtype for ncatted: {dtype}", error_type=ValueError)


def get_var_info(
    var: str, ds: xr.Dataset, abs_path: str, delete_if_none_filled: bool, dry_run: bool
) -> Tuple[VarContext, FillValueConfig]:
    """
    Process a single variable to get information to be used as settings.

    Displays variable metadata and statistics and calculates a smart default.

    Args:
        var: Variable name
        da: xarray DataArray for the variable
        abs_path: Absolute path to the file (for context in defaults)
        delete_if_none_filled: If True, automatically use delete when it's the default
        dry_run: If true, just print vars to process (and defaults, if any).

    Returns:
        VarContext: Information about the variable
        FillValueConfig: Information about the fill value
    """
    da = ds[var]

    # Get variable metadata
    long_name = da.attrs.get("long_name", "N/A")
    units = da.attrs.get("units", "N/A")
    shape = da.shape

    # Get data statistics
    nanmin = float(np.nanmin(da.values))
    nanmax = float(np.nanmax(da.values))

    # Check if data contains any NaN values
    data_has_nan = var_data_has_nan(da)

    # Calculate default fill value
    default_fill = None
    # Suggest delete if data has no NaN values
    if not data_has_nan:
        default_fill = USER_REQ_DELETE
    elif (
        nanmin >= 0
        or nanmin == -1
        or any(var.startswith(x) for x in VARSTARTS_TO_DEFAULT_NEG999)
        or ("/surfdata_map/" in abs_path and bool(re.match(r"[a-z0-9]{5}_to_[a-z0-9]{5}", var)))
    ):
        default_fill = type(nanmin)(-999)

    # Print variable summary
    warn(logger, f"\n  Variable: {var}")
    warn(logger, f"{INDENT}long_name: {long_name}")
    warn(logger, f"{INDENT}shape:     {shape}")
    warn(logger, f"{INDENT}units:     {units}")
    warn(logger, f"{INDENT}nanmin:    {nanmin}")
    warn(logger, f"{INDENT}nanmax:    {nanmax}")
    if data_has_nan:
        warn(logger, f"{INDENT}WARNING: Data contains NaN values - cannot delete {ATTR}")

    # Save and return info
    var_context = VarContext(
        var_name=var, target_type=type(nanmin), file_path=abs_path, dry_run=dry_run
    )
    config = FillValueConfig(
        default_value=default_fill,
        allow_delete=not data_has_nan,
        delete_if_none_filled=delete_if_none_filled,
    )

    return var_context, config


def get_vars_with_nan_fills(abs_path: str) -> List[str]:
    """
    Given a file, get variables with NaN fill value attribute (if any).

    Args:
        abs_path: Absolute path to file

    Returns:
        bool: List of variables with NaN fill value attribute
    """
    ncdump_results = subprocess.check_output(["ncdump", "-h", abs_path], text=True)

    # Regex breakdown:
    # ^\s* : Start of line and any leading whitespace
    # (\S+)       : Capture one or more non-whitespace characters (the variable name)
    # :{ATTR}} : The attribute where fill value is stored
    # \s*=\s* : The equals sign with flexible surrounding whitespace
    # NaNf?\s*;    : The NaN/NaNf value and the closing semicolon
    regex_pattern = rf"^\s*(\S+):{ATTR}\s*=\s*NaNf?\s*;"

    # Use re.MULTILINE to treat each line in the string as a new start
    vars_with_nan_fills = re.findall(regex_pattern, ncdump_results, re.MULTILINE)
    vars_with_nan_fills.sort()
    return vars_with_nan_fills


def show_ncdump_for_variable(file_path: str | None, var_name: str) -> None:
    """
    Run ncdump -h on a file and display lines matching the variable name.

    Args:
        file_path: Path to the netCDF file (None to skip)
        var_name: Name of the variable to search for in ncdump output
    """
    if not file_path:
        warn(logger, f"{INDENT}No file path available for ncdump")
        warn(logger, "")
        return

    try:
        info(logger, f"{INDENT}Running: ncdump -h {file_path}")
        result = subprocess.run(
            ["ncdump", "-h", file_path], capture_output=True, text=True, check=True
        )
        # Filter lines containing the variable name
        matching_lines = [line for line in result.stdout.split("\n") if var_name in line]
        if matching_lines:
            info(logger, f"    Lines matching '{var_name}':")
            for line in matching_lines:
                info(logger, f"      {line}")
        else:
            info(logger, f"    No lines found matching '{var_name}'")
    except subprocess.CalledProcessError as e:
        error(logger, f"    Error running ncdump: {e}", error_type=None)
    except FileNotFoundError:
        error(logger, "    Error: ncdump command not found", error_type=None)

    error(logger, "", error_type=None)  # Empty line for readability


def var_data_has_nan(da: xr.DataArray) -> bool:
    """
    Check if a variable's data contains any NaN values.

    Args:
        da: xarray DataArray to check

    Returns:
        bool: True if the data contains any NaN values, False otherwise
    """
    try:
        return bool(da.isnull().any())
    except TypeError:
        # If isnan fails (e.g., for string data), assume no NaN
        return False
