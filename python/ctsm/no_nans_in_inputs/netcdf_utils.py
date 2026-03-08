"""Functions for working with netCDF files"""

import os
import sys
from pathlib import Path
import re
import subprocess
from typing import Any, Dict, List, NamedTuple, Tuple
import logging
import warnings
from shutil import copyfile

import numpy as np
import xarray as xr
from netCDF4 import Dataset, Variable  # pylint: disable=no-name-in-module

# Add the python directory to sys.path for direct script execution
_CTSM_PYTHON = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
if _CTSM_PYTHON not in sys.path:
    sys.path.insert(1, _CTSM_PYTHON)

from ctsm.no_nans_in_inputs.constants import (  # pylint: disable=wrong-import-position
    FILL_ATTR,
    INDENT,
    INPUTDATA_PREFIX,
    OPEN_DS_KWARGS,
    USER_REQ_DELETE,
)

from ctsm.netcdf_utils import get_netcdf_format  # pylint: disable-wrong-import-position
from ctsm.no_nans_in_inputs.shared import (  # pylint: disable=wrong-import-position
    confirm_continue,
    FillValueConfig,
    VarContext,
)
from ctsm.no_nans_in_inputs.constants import (  # pylint: disable=wrong-import-position
    VARSTARTS_TO_DEFAULT_NEG999,
)
from ctsm.no_nans_in_inputs.json_io import (  # pylint: disable=wrong-import-position
    NoNanFillValueProgress,
)

from ctsm.ctsm_logging import (  # pylint: disable=wrong-import-position
    error,
    info,
    warn,
)
from ctsm import ctsm_logging

# Set up logging
logger = logging.getLogger(__name__)


def _build_nccopy_command(
    input_file: str,
    output_file: str,
    nccopy_kind: str,
) -> list[str]:
    """
    Build nccopy command to convert netCDF type.
    """

    cmd = ["nccopy", "-k", nccopy_kind, input_file, output_file]

    return cmd


def _build_ncatted_command(
    input_file: str,
    output_file: str,
    var_fillvalues: dict[str, Any],
) -> list[str]:
    """
    Build ncatted command to modify or delete fill values.

    Args:
        input_file: Path to input NetCDF file
        output_file: Path to output NetCDF file
        var_fillvalues: Dictionary mapping variable names to new fill values
                        (or USER_REQ_DELETE to delete the attribute)

    Returns:
        Command as list of arguments for subprocess

    Raises:
        ValueError: If input and output files are the same, or if variable not found
    """

    cmd = ["ncatted", "-O"]  # -O flag to overwrite without prompting

    ds = xr.open_dataset(input_file, **OPEN_DS_KWARGS)
    for var, fill_val in var_fillvalues.items():
        if fill_val == USER_REQ_DELETE:
            # Delete the attribute: -a attr_name,var_name,d,,
            cmd.extend(["-a", f"{FILL_ATTR},{var},d,,"])
        else:
            type_code = _get_ncatted_dtype_and_type_code(input_file, var, ds)

            # Modify the attribute: -a attr_name,var_name,o,type,value
            cmd.extend(["-a", f"{FILL_ATTR},{var},o,{type_code},{fill_val}"])
    ds.close()

    # Add input and output files
    cmd.extend([input_file, output_file])

    return cmd


def _build_ncap2_command(
    input_file: str,
    output_file: str,
    var_fillvalues: dict[str, Any],
    vars_with_rawnan_nofill: List[str],
) -> list[str]:
    """ncap2 command to set raw NaNs equal to the fill value"""

    cmd = ["ncap2", "-O", "-s"]
    ncap2_script_expr = ""
    for var in vars_with_rawnan_nofill:
        new_fill = var_fillvalues[var]
        # ncap2's isnan() is available in older nco versions, so we take advantage of the IEEE
        # rule that NaN is the only value not equal to itself.
        ncap2_script_expr += f"where({var}!={var}) {var}={new_fill}; "
    cmd.append(ncap2_script_expr)
    cmd += [input_file, output_file]
    return cmd


def build_nco_commands(
    input_file: str,
    output_file: str,
    var_fillvalues: dict[str, Any],
    tmpdir: str,
    progress: NoNanFillValueProgress,
) -> List[list[str]]:

    # Ensure we're working with strings
    if isinstance(input_file, Path):
        input_file = str(input_file)
    if isinstance(output_file, Path):
        output_file = str(output_file)

    # Ensure input and output files are different (resolve symlinks)
    input_real = os.path.realpath(input_file)
    output_real = os.path.realpath(output_file)
    if input_real == output_real:
        error(
            logger,
            f"Input and output files are the same: {input_file} -> {input_real}",
            error_type=ValueError,
        )

    # Some file types need special handling because they store data and metadata contiguously.
    # Instead of working on them directly, we'll convert to netCDF4, then do our nco commands,
    # then convert back. If we don't do this, our nco commands will take a LONG time, as they will
    # need to rewrite the entire file for every changed variable.
    match get_netcdf_format(input_file):
        case "NETCDF3_64BIT_DATA":
            nccopy_kind = "cdf5"
        case _:
            nccopy_kind = None
    if nccopy_kind:
        input_file_nc4 = _get_tmp_nc4_path(input_file, tmpdir)
    else:
        input_file_nc4 = input_file

    # Coerce type, if needed
    if isinstance(tmpdir, Path):
        tmpdir = str(tmpdir)

    # nccopy to convert to netCDF4, if needed (see above). This has to actually get called before
    # _build_ncatted_command() because that function will try to open the resulting netCDF4 file.
    if nccopy_kind:
        execute_nco_commands([_build_nccopy_command(input_file, input_file_nc4, "netCDF-4")])

    # Always work on a temporary file so we don't pollute inputdata if a command fails. This will
    # require a move operation after we're all done, but as long as the eventual output is on the
    # same file system as our temporary file, it will be instantaneous.
    nc_tmp = os.path.join(tmpdir, "tmp.nc")

    # Now we'll start building (the other) commands
    cmd_list = []

    # ncatted to replace NaN fill values
    if var_fillvalues:
        cmd_list.append(_build_ncatted_command(input_file_nc4, nc_tmp, var_fillvalues))
    elif not os.path.exists(nc_tmp):
        copyfile(input_file_nc4, nc_tmp, follow_symlinks=True)

    # Only needed for vars with raw NaNs originally
    vars_with_rawnan_nofill = progress[input_file]["vars_with_rawnan_nofill"]
    vars_with_rawnan_yesfill = progress[input_file]["vars_with_rawnan_yesfill"]
    vars_with_rawnan = vars_with_rawnan_nofill + list(vars_with_rawnan_yesfill.keys())
    any_rawnan = bool(vars_with_rawnan)
    if any_rawnan:
        # Get combined list of fill values, making sure no variable is in both the dicts
        if vars_in_both := set(vars_with_rawnan_nofill) & set(vars_with_rawnan_yesfill.keys()):
            msg = (
                "Unexpected variable(s) in both var_fillvalues and vars_with_rawnan_yesfill: "
                + ", ".join(vars_in_both)
            )
            error(logger, msg, error_type=AssertionError)

        # Build dict of variables and their fill values for the ncap2 command, which sets raw NaNs
        # in a variable to its fill value
        var_fillvalues_for_ncap2 = {}
        for k, v in var_fillvalues.items():
            if k in vars_with_rawnan_nofill:
                var_fillvalues_for_ncap2[k] = v
        var_fillvalues_for_ncap2 = var_fillvalues_for_ncap2 | vars_with_rawnan_yesfill
        assert len(var_fillvalues_for_ncap2) == len(vars_with_rawnan)
        # ncap2 writes a temporary file by default, so we don't need to worry about slowdowns when
        # we call it with the same input and output
        cmd_list.append(
            _build_ncap2_command(nc_tmp, nc_tmp, var_fillvalues_for_ncap2, vars_with_rawnan)
        )

    # nccopy to convert back, if needed (see above)
    if nccopy_kind:
        cmd_list.append(_build_nccopy_command(nc_tmp, output_file, nccopy_kind))
        result_file = output_file
    else:
        result_file = nc_tmp

    # We must be doing SOMETHING
    if not cmd_list:
        error_type = RuntimeError if ctsm_logging.lte_debug(logger) else None
        error(logger, "Empty command list", error_type=error_type)
        if not confirm_continue():
            sys.exit("Exiting.")

    return cmd_list, result_file


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


def _get_tmp_nc4_path(file_abs: str, tmpdir: str):
    file_basename = os.path.basename(file_abs)
    root, _ = os.path.splitext(file_basename)
    ext = ".nc4"
    file_tmp = os.path.join(tmpdir, root + ext)
    # Make sure our temporary path doesn't match our original
    while file_tmp == file_abs:
        root, ext = os.path.splitext(file_tmp)
        file_tmp = root + ".tmp" + ext
    return file_tmp


def _execute_nco_command(cmd: list[str]) -> int:
    """
    Runs the nco command to create the output file with modified fill values.

    Args:
        cmd: nco command as list of arguments

    Returns:
        Number of files processed (1 on success, 0 on skip)

    Raises:
        SystemExit: If nco command fails or is not found
    """
    info(logger, f"\nExecuting: {' '.join([str(x) for x in cmd])}")
    nco_util = cmd[0]
    files_processed = 0
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        info(logger, f"{INDENT}✓ Successful {nco_util}")
        if result.stdout:
            info(logger, f"{INDENT}stdout: {result.stdout}")
        if result.stderr:
            info(logger, f"{INDENT}stderr: {result.stderr}")
        files_processed = 1

    except subprocess.CalledProcessError as e:
        msg = f"  ✗ Error: {nco_util} failed with exit code {e.returncode}"
        if e.stdout:
            msg += f"\n{INDENT}stdout: {e.stdout}"
        if e.stderr:
            msg += f"\n{INDENT}stderr: {e.stderr}"
        error(logger, msg + f"\n{e}", error_type=subprocess.CalledProcessError)
        raise e
    except FileNotFoundError:
        msg = f"{INDENT}✗ Error: {nco_util} command not found\n"
        msg += f"{INDENT}Please ensure NCO (NetCDF Operators) is installed"
        error_type = INDENT if ctsm_logging.lte_debug(logger) else None
        error(logger, msg, error_type=error_type)
        sys.exit(7)
    return files_processed


def execute_nco_commands(cmd_list: List[list[str]]) -> int:
    for cmd in cmd_list:
        result = _execute_nco_command(cmd)
        if not result:
            error(logger, "Unhandled nco command failure", error_type=NotImplementedError)
    return result


def var_has_rawnan(
    da: xr.DataArray,
    dims_to_slice_over: list,
):
    """
    Best to sort dims_to_slice_over smallest -> largest so that we're always working with the
    largest possible slice, for efficiency
    """
    # Get fill value, if any
    try:
        fill_value = da.attrs[FILL_ATTR]
    except KeyError:
        fill_value = None

    # Check one slice at a time for some dimensions in order to reduce RAM usage
    if (dims_to_slice_over is not None) and da.size > 1e8:
        dim = dims_to_slice_over[0]
        if len(dims_to_slice_over) > 1:
            dims_to_slice_over = dims_to_slice_over[1:]
        else:
            dims_to_slice_over = None
        if dim in da.dims:
            for i in range(da.sizes[dim]):
                da_i = da.isel({dim: i}, drop=True)
                info(
                    logger, f"{INDENT*4}Slicing over {dim} {i+1}/{da.sizes[dim]}; size {da_i.size}"
                )
                any_raw_null, fill_value = var_has_rawnan(
                    da_i, dims_to_slice_over=dims_to_slice_over
                )
                if any_raw_null:
                    break
            return any_raw_null, fill_value
        if dims_to_slice_over and len(dims_to_slice_over) > 1:
            any_raw_null, fill_value = var_has_rawnan(da, dims_to_slice_over=dims_to_slice_over)
            return any_raw_null, fill_value
        any_raw_null = da.isnull().any()
    else:
        any_raw_null = da.isnull().any()
    return any_raw_null, fill_value


def file_has_rawnan(nc_path: str) -> Tuple[bool, List[str], dict[str, Any]]:
    vars_with_rawnan_nofill = []
    vars_with_rawnan_yesfill = {}
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message=".*has multiple fill values.*")
        ds = xr.open_dataset(nc_path, **OPEN_DS_KWARGS, mask_and_scale=False)

        # # Best to sort dims_to_slice_over smallest -> largest so that we're always working with the
        # # largest possible slice, for efficiency.
        # dims_sorted = sorted(ds.sizes.items(), key=lambda kv: kv[1])
        # dims_to_slice_over = [dim for dim, size in dims_sorted]
        dims_to_slice_over = ["time"] if "time" in ds.dims else None

        for v in ds:
            info(logger, f"{INDENT*3}Checking {v}")
            has_rawnan, fill_value = var_has_rawnan(ds[v], dims_to_slice_over=dims_to_slice_over)
            if has_rawnan:
                if fill_value is None:
                    vars_with_rawnan_nofill.append(v)
                else:
                    vars_with_rawnan_yesfill[v] = fill_value
        ds.close()
    any_var_has_rawnan = bool(vars_with_rawnan_nofill) or bool(vars_with_rawnan_yesfill)
    return any_var_has_rawnan, vars_with_rawnan_nofill, vars_with_rawnan_yesfill


def file_has_nan_ncks_chk_nan(abs_path: str) -> bool:
    """
    Use ncks --chk_nan to determine whether a netCDF file has a NaN
    """
    # We'll check one variable at a time to reduce RAM usage
    ds = xr.open_dataset(abs_path, **OPEN_DS_KWARGS)
    var_list = list(ds)
    ds.close()

    for v in var_list:
        cmd = ["ncks", "--chk_nan", "-v", v, str(abs_path)]
        if ctsm_logging.lte_debug(logger):
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
        elif result.returncode == 1:
            break

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
    vars_to_give_fills = get_vars_with_nan_fills(abs_path)

    return bool(vars_to_give_fills), vars_to_give_fills


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
    if any(x in dtype_str for x in ["int64", "int32", "int16", "int8", "int_", "byte"]):
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
    elif np.isnan(nanmin):
        # The data is all filled anyway
        default_fill = -999
    elif nanmin >= 0 or nanmin == -1 or any(var.startswith(x) for x in VARSTARTS_TO_DEFAULT_NEG999):
        default_fill = _get_negative_default(nanmin)
    else:
        default_fill = -(10 ** (np.ceil(np.log10(max(np.abs([nanmin, nanmax])))) + 1) - 1)

    # Checks of numeric defaults
    if not isinstance(default_fill, str):
        # Ensure default is the right type
        default_fill = type(nanmin)(default_fill)

        # Ensure default is less than minimum
        if not np.isnan(nanmin) and default_fill >= nanmin:
            error(logger, f"Failed to get default < {nanmin=}", error_type=RuntimeError)

    # Print variable summary
    warn(logger, f"\n  Variable: {var}")
    warn(logger, f"{INDENT}long_name: {long_name}")
    warn(logger, f"{INDENT}shape:     {shape}")
    warn(logger, f"{INDENT}units:     {units}")
    warn(logger, f"{INDENT}nanmin:    {nanmin}")
    warn(logger, f"{INDENT}nanmax:    {nanmax}")
    if data_has_nan:
        warn(logger, f"{INDENT}WARNING: Data contains NaN values - cannot delete {FILL_ATTR}")

    # Save and return info
    var_context = VarContext(
        var_name=var, target_type=type(nanmin), file_path=abs_path, dry_run=dry_run
    )
    config = FillValueConfig(
        _default_value=default_fill,
        allow_delete=not data_has_nan,
        delete_if_none_filled=delete_if_none_filled,
    )

    return var_context, config


def _get_negative_default(nanmin):
    default_fill = None
    if not np.isneginf(nanmin):
        default_fill = type(nanmin)(-999)
        while default_fill >= nanmin:
            default_fill = (default_fill - 1) * 10 + 1
    return default_fill


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
    # :{FILL_ATTR}} : The attribute where fill value is stored
    # \s*=\s* : The equals sign with flexible surrounding whitespace
    # NaNf?\s*;    : The NaN/NaNf value and the closing semicolon
    regex_pattern = rf"^\s*(\S+):{FILL_ATTR}\s*=\s*NaNf?\s*;"

    # Use re.MULTILINE to treat each line in the string as a new start
    vars_to_give_fills = re.findall(regex_pattern, ncdump_results, re.MULTILINE)
    vars_to_give_fills.sort()
    return vars_to_give_fills


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
