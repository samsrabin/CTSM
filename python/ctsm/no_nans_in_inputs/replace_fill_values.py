#!/usr/bin/env python3
"""
Replace NaN fill values in NetCDF files based on new_fillvalues.json.

This script:
1. Reads the new_fillvalues.json file created by get_replacement_fill_values.py
2. For each file, creates an output filename with .no_nan_fill before the extension
3. Uses ncatted to modify or delete _FillValue attributes
4. Creates modified copies of the input files
"""

import argparse
import os
import sys
from pathlib import Path
import logging
from subprocess import CalledProcessError
import warnings

# Add the python directory to sys.path for direct script execution
_CTSM_PYTHON = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
if _CTSM_PYTHON not in sys.path:
    sys.path.insert(1, _CTSM_PYTHON)

from ctsm.no_nans_in_inputs.json_io import (  # pylint: disable=wrong-import-position
    NoNanFillValueProgress,
)

from ctsm.no_nans_in_inputs.constants import (  # pylint: disable=wrong-import-position
    DEFAULT_CTSM_ROOT,
    DIR_TO_SEARCH_FOR_XML_FILES,
    INDENT,
    NEW_FILLVALUES_FILE,
    NO_HANDLED_NANS,
    SEP_LENGTH,
    USER_REQ_DELETE,
    USER_REQ_SKIP_FILE,
)
import ctsm.no_nans_in_inputs.namelist_utils as nlu  # pylint: disable=wrong-import-position
from ctsm.no_nans_in_inputs import netcdf_utils  # pylint: disable=wrong-import-position
from ctsm.no_nans_in_inputs.user_inputs import (  # pylint: disable=wrong-import-position
    confirm_continue,
)
from ctsm.no_nans_in_inputs.shared import (  # pylint: disable=wrong-import-position
    get_path_with_cesmdataroot,
)
from ctsm.ctsm_logging import (  # pylint: disable=wrong-import-position
    add_logging_args,
    error,
    info,
    process_logging_args,
    setup_logging_pre_config,
    warn,
)
from ctsm import ctsm_logging
from ctsm.git_utils import get_git_diff, get_git_toplevel
from ctsm.os_utils import check_write_access  # pylint: disable=wrong-import-position

# Set up logging
logging.basicConfig(format="%(message)s", level=logging.DEBUG)
ctsm_logging.skip_compose = True
logger = logging.getLogger()

# Maximum number of vars to list in message for each new fill value
MAX_LISTED_VARS = 5


def get_output_filename(input_file: str, suffix: str = ".no_nan_fill") -> str:
    """
    Generate output filename by adding .no_nan_fill before the extension.

    Args:
        input_file: Path to the input file

    Returns:
        Path to the output file

    Examples:
        /path/to/file.nc -> /path/to/file.no_nan_fill.nc
        /path/to/file.tar.gz -> /path/to/file.no_nan_fill.tar.gz
    """
    # Split the path into directory, basename, and extension
    directory = os.path.dirname(input_file)
    basename = os.path.basename(input_file)

    # Find the last dot to split extension
    if "." in basename:
        name, ext = basename.rsplit(".", 1)
        output_basename = f"{name}{suffix}.{ext}"
    else:
        # No extension
        output_basename = f"{basename}{suffix}"

    # Reconstruct the full path
    return os.path.join(directory, output_basename)


def _process_one_file(
    progress: NoNanFillValueProgress,
    input_file_abs: str,
    output_file: str,
    files_processed: list,
    dry_run: bool,
):

    # Check whether we can process the file
    print("\n")
    ok = _check_ok_to_process(progress, input_file_abs)
    print("\n")
    if not ok:
        return files_processed

    # Print things to do for this file
    var_fillvalues = progress[input_file_abs]["new_fill_values"]
    var_fillmissing = progress[input_file_abs]["new_fill_missing"]
    info(logger, f"\nInput:  {input_file_abs}")
    info(logger, f"Output: {output_file}")

    # Build and print the ncatted command
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message=".*has multiple fill values.*")
        cmd_list = netcdf_utils.build_nco_commands(
            input_file_abs, output_file, var_fillvalues, var_fillmissing
        )
    info(logger, "\nCommands:")
    for cmd in cmd_list:
        info(logger, INDENT + " ".join(cmd))

    # Execute the command if not in dry-run mode
    if not dry_run:
        try:
            files_processed += netcdf_utils.execute_nco_commands(cmd_list)
        except Exception:  # pylint: disable=broad-exception-caught
            if not confirm_continue():
                sys.exit("Exiting.")
            return files_processed
        # Update the XML file(s) with the new output path
        files_containing = []
        for file_containing_netcdf, set_of_how_this_netcdf_appears in progress[input_file_abs][
            "found_in_files"
        ].items():
            files_containing.append(file_containing_netcdf)
            for netcdf_path_in in set_of_how_this_netcdf_appears:
                netcdf_path_out = get_output_filename(
                    netcdf_path_in, progress[input_file_abs]["suffix"]
                )
                nlu.update_text_file_referencing_netcdf(
                    file_containing_netcdf, netcdf_path_in, netcdf_path_out
                )

        # Print message and wait for user to approve before continuing
        _print_and_wait(
            input_file_abs, output_file, var_fillvalues, var_fillmissing, files_containing
        )

        # Update progress object and file
        progress.done_with_file(input_file_abs)
        progress.cleanup()
    return files_processed


def _check_ok_to_process(progress: NoNanFillValueProgress, input_file_abs: str) -> bool:
    """Check whether it's okay to process a netCDF file"""

    # get_replacement_fill_values.py result was to NOT process
    if isinstance(progress[input_file_abs], str):
        return False

    # File doesn't exist
    if not os.path.exists(input_file_abs):
        err_type = FileNotFoundError if logger.getEffectiveLevel() <= logging.DEBUG else None
        error(logger, f"File not found: '{input_file_abs}'", error_type=err_type)
        if not confirm_continue():
            sys.exit("Exiting.")
        return False

    # User doesn't have write access in directory
    dirname, basename = os.path.split(input_file_abs)
    if not check_write_access(input_file_abs):
        err_type = PermissionError if logger.getEffectiveLevel() <= logging.DEBUG else None
        error(
            logger,
            f"User can't replace '{basename}': No write perms in '{dirname}'",
            error_type=err_type,
        )
        if not confirm_continue():
            sys.exit("Exiting.")
        return False

    return True


def _print_and_wait(
    input_file_abs: str,
    output_file: str,
    var_fillvalues: dict,
    var_fillmissing: dict,
    files_containing: list,
) -> None:
    """Print info and a message useful for a git commit, then wait for user to continue"""

    print("\n")
    ctsm_root = None
    try:
        ctsm_root = os.path.commonpath(files_containing)
        ctsm_root = get_git_toplevel(ctsm_root)
        msg = f"== git diff {ctsm_root} "
        warn(logger, msg + "=" * max(0, SEP_LENGTH - len(msg)))
        get_git_diff(repo_root=ctsm_root, capture_output=False)

    except CalledProcessError as e:
        if logger.getEffectiveLevel() <= logging.DEBUG:
            error(logger, str(e), error_type=CalledProcessError)
        else:
            warn(logger, "[git diff failed]")
    except Exception as e:  # pylint:disable=broad-exception-caught
        exc_type = type(e)
        if logger.getEffectiveLevel() <= logging.DEBUG:
            error(logger, str(e), error_type=exc_type)
        else:
            warn(logger, f"[unable to do git diff due to {exc_type}]")
    warn(logger, "=" * SEP_LENGTH)

    warn(logger, "-" * SEP_LENGTH)

    # Which netCDF file did we replace?
    input_file_msg = get_path_with_cesmdataroot(input_file_abs)
    warn(logger, f"Handled NaN fill values in '{input_file_msg}'.\n")
    output_file_msg = get_path_with_cesmdataroot(output_file)
    warn(logger, f"New file '{output_file_msg}'.")

    # Which new fill values did we give it?
    if var_fillvalues:
        warn(logger, "Replaced NaN or missing fill values with:")
        vars_with_deleted_fill = []
        new_fill_dict = {}
        for var, fill_val in var_fillvalues.items():
            if fill_val == USER_REQ_DELETE:
                vars_with_deleted_fill.append(var)
            else:
                if fill_val in new_fill_dict:
                    new_fill_dict[fill_val].append(var)
                else:
                    new_fill_dict[fill_val] = [var]
        new_fill_dict = dict(sorted(new_fill_dict.items()))  # Sort by key ascending
        for fill_val, var_list in new_fill_dict.items():
            n_vars = len(var_list)
            if n_vars > MAX_LISTED_VARS:
                n_others = n_vars - MAX_LISTED_VARS
                var_list_txt = ", ".join(var_list[:MAX_LISTED_VARS]) + f", and {n_others} others"
                if n_others == 1:
                    var_list_txt = var_list_txt[:-1]
            else:
                var_list_txt = ", ".join(var_list)
            warn(logger, f"{INDENT}{fill_val}: {var_list_txt}")
        if vars_with_deleted_fill:
            if len(vars_with_deleted_fill) <= MAX_LISTED_VARS:
                warn(logger, f"{INDENT}Deleted fill: {', '.join(vars_with_deleted_fill)}")
            else:
                warn(
                    logger,
                    f"{INDENT}Deleted unused fill from {len(vars_with_deleted_fill)} variables",
                )

    # Which variables got their _FillValue and missing_value harmonized?
    if var_fillmissing:
        warn(logger, "Harmonized _FillValue and missing_value to:")
        new_fillmiss_dict = {}
        for var, var_dict in var_fillmissing.items():
            assert len(set(var_dict.values())) == 1
            harmonized_val = list(var_dict.values())[0]
            if harmonized_val in new_fillmiss_dict:
                new_fillmiss_dict[harmonized_val].append(var)
            else:
                new_fillmiss_dict[harmonized_val] = [var]
        new_fillmiss_dict = dict(sorted(new_fillmiss_dict.items()))  # Sort by key ascending
        for harmonized_val, var_list in new_fillmiss_dict.items():
            n_vars = len(var_list)
            if n_vars > MAX_LISTED_VARS:
                n_others = n_vars - MAX_LISTED_VARS
                var_list_txt = ", ".join(var_list[:MAX_LISTED_VARS]) + f", and {n_others} others"
                if n_others == 1:
                    var_list_txt = var_list_txt[:-1]
            else:
                var_list_txt = ", ".join(var_list)
            warn(logger, f"{INDENT}{harmonized_val}: {var_list_txt}")

    # Which files did we update the path in?
    warn(logger, "\nPath updated in:")
    for f in files_containing:
        if os.path.exists(f) and not os.path.isabs(f):
            f = os.path.realpath(f)
        if ctsm_root:
            f_rel = Path(f).relative_to(ctsm_root)
        else:
            f_rel = f
        warn(logger, f"{INDENT}{f_rel}")

    warn(logger, "-" * SEP_LENGTH)

    # Wait for user to confirm or not
    if not confirm_continue():
        sys.exit("Exiting.")


def process_files(
    fillvalues_file: str,
    dry_run: bool = False,
    overwrite: bool = False,
) -> int:
    """
    Process files to replace fill values.

    Args:
        fillvalues_file: Path to JSON file with new fill values
        dry_run: If True, show commands without executing (default: False)
        overwrite: If True, overwrite existing output files (default: False)

    Returns:
        Number of files successfully processed
    """
    # Load the new fill values
    warn(logger, f"Loading new fill values from {fillvalues_file}...")
    progress = NoNanFillValueProgress(progress_file=fillvalues_file, load_without_asking=True)

    total_files = len(progress)
    total_vars = sum(len(vars_dict) for vars_dict in progress.values())
    warn(logger, f"Found {total_vars} variable(s) in {total_files} file(s)\n")

    # Process each file
    files_processed = 0
    files_to_process = list(progress.keys()).copy()
    for input_file_abs in files_to_process:

        # Skip file if the user requested skipping it or there were no handled NaNs
        if progress[input_file_abs] in [USER_REQ_SKIP_FILE, NO_HANDLED_NANS]:
            continue

        # Get output filename
        output_file = get_output_filename(input_file_abs, suffix=progress[input_file_abs]["suffix"])

        # Check whether we're skipping this file
        if skip_this_file(input_file_abs, output_file, overwrite):
            continue

        files_processed = _process_one_file(
            progress=progress,
            input_file_abs=input_file_abs,
            output_file=output_file,
            files_processed=files_processed,
            dry_run=dry_run,
        )

    # Only print summary in dry-run mode
    if dry_run:
        print_dry_run_summary(total_files, total_vars)

    return files_processed


def skip_this_file(input_file: str, output_file: str, overwrite: bool) -> bool:
    """
    Determine whether to skip processing a file.

    Files are skipped if the output is a symlink (always) or if the output
    exists and overwrite is False.

    Args:
        input_file: Path to input file
        output_file: Path to output file
        overwrite: Whether to overwrite existing files

    Returns:
        True if file should be skipped, False otherwise
    """
    # Check if output is a symlink - never overwrite symlinks
    if os.path.islink(output_file):
        warn(logger, f"\n{'!' * SEP_LENGTH}")
        warn(logger, "WARNING: Output file is a symlink - SKIPPING")
        warn(logger, f"  Input:  {input_file}")
        warn(logger, f"  Output: {output_file} -> {os.readlink(output_file)}")
        warn(logger, "  Symlinks will never be overwritten for safety")
        warn(logger, f"{'!' * SEP_LENGTH}")
        return True

    # Skip if output file already exists and overwrite is not enabled
    if os.path.exists(output_file) and not overwrite:
        warn(logger, f"\nSkipping (output exists): {input_file}")
        warn(logger, f"  Output: {output_file}")
        warn(logger, "  Use --overwrite to replace existing files")
        return True

    return False


def print_dry_run_summary(total_files: int, total_vars: int) -> None:
    """
    Print summary information about files to be processed.

    Only called in dry-run mode to show what would be done.

    Args:
        total_files: Total number of files to process
        total_vars: Total number of variables to modify
    """
    warn(logger, "\n" + "=" * SEP_LENGTH)
    warn(logger, "\nSummary:")
    warn(logger, f"  {total_files} file(s) will be processed")
    warn(logger, f"  {total_vars} variable(s) will be modified")


def main() -> int:
    """
    Main function to replace fill values.

    Parses command-line arguments and processes files to replace NaN fill values.

    Returns:
        Exit code (0 for success)
    """

    # Parse command-line arguments
    parser = argparse.ArgumentParser(
        description="Replace NaN fill values in NetCDF files using ncatted"
    )
    parser.add_argument(
        "--fillvalues-file",
        default=NEW_FILLVALUES_FILE,
        help=f"Path to JSON file with new fill values (default: {NEW_FILLVALUES_FILE})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without actually modifying files",
    )
    parser.add_argument(
        "-o",
        "--overwrite",
        action="store_true",
        help="Overwrite existing output files (default: skip if output exists)",
    )
    parser.add_argument(
        "--xml-dir",
        default=DIR_TO_SEARCH_FOR_XML_FILES,
        help=(
            "Path to directory to find XML files to update with new paths, relative to CTSM root"
            f" (default: {DIR_TO_SEARCH_FOR_XML_FILES})"
        ),
    )
    add_logging_args(parser)
    args = parser.parse_args()
    process_logging_args(args)

    # Process the files
    process_files(
        args.fillvalues_file,
        dry_run=args.dry_run,
        overwrite=args.overwrite,
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
