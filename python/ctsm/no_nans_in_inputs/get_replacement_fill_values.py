#!/usr/bin/env python3
"""
Find file paths from namelist_defaults_ctsm.xml that are also in inputdata_fillvalue.log.clm_bad.

This script:
1. Parses the XML file to extract all file paths
2. Converts relative paths (starting with lnd/clm2/) to absolute paths
3. Checks which of these paths appear in the bad files log
4. Prints the matching paths
"""

import argparse
import os
from pathlib import Path
import sys
from typing import List, Set, Tuple
import logging


# Add the python directory to sys.path for direct script execution
_CTSM_PYTHON = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
if _CTSM_PYTHON not in sys.path:
    sys.path.insert(1, _CTSM_PYTHON)

from ctsm.no_nans_in_inputs.constants import (  # pylint: disable=wrong-import-position
    ATTR,
    DEFAULT_CTSM_ROOT,
    INDENT,
    NEW_FILLVALUES_FILE,
    SEP_LENGTH,
    XML_FILE,
)
from ctsm.no_nans_in_inputs.json_io import (  # pylint: disable=wrong-import-position
    NoNanFillValueProgress,
)
import ctsm.no_nans_in_inputs.namelist_utils as nlu  # pylint: disable=wrong-import-position
from ctsm.no_nans_in_inputs.shared import (  # pylint: disable=wrong-import-position
    convert_to_absolute_path,
    get_path_with_cesmdataroot,
)
from ctsm.no_nans_in_inputs import user_inputs  # pylint: disable=wrong-import-position
from ctsm.no_nans_in_inputs.netcdf_utils import (  # pylint: disable=wrong-import-position
    file_has_nan_fill,
)
from ctsm.ctsm_logging import (  # pylint: disable=wrong-import-position
    add_logging_args,
    debug,
    error,
    info,
    process_logging_args,
    warn,
)
from ctsm import ctsm_logging  # pylint: disable=wrong-import-position
from ctsm.os_utils import check_write_access  # pylint: disable=wrong-import-position

# Set up logging
logging.basicConfig(format="%(message)s", level=logging.DEBUG)
ctsm_logging.skip_compose = True
logger = logging.getLogger()

# Directory to search for user_nl_ files. Must be relative to CTSM root.
DIR_TO_SEARCH_FOR_USER_NL_FILES = "cime_config"


def _check_for_nanfill_in_netcdf(
    files_referencing_netcdfs: list,
    progress: NoNanFillValueProgress,
    netcdf_path: str,
    abs_path: str,
):
    any_nan_fill, vars_with_nan_fills = file_has_nan_fill(abs_path)
    if any_nan_fill:
        fif_dict = progress[abs_path]["found_in_files"]
        for file_to_search in files_referencing_netcdfs:
            set_of_how_this_netcdf_appears = nlu.how_netcdf_is_referenced_in_file(
                file_to_search, netcdf_path
            )
            if set_of_how_this_netcdf_appears:
                if file_to_search not in fif_dict:
                    fif_dict[file_to_search] = set()
                fif_dict[file_to_search] = fif_dict[file_to_search] | set_of_how_this_netcdf_appears
        progress[abs_path]["vars_with_nan_fills"] = vars_with_nan_fills
        progress.save()
    else:
        if abs_path in progress:
            error(
                logger,
                f"Found no NaN fills in file but it was in progress dict: {abs_path}",
                error_type=RuntimeError,
            )
        info(logger, f"{INDENT}No variable in file has NaN {ATTR}; skipping")





def _get_netcdf_files_to_check(
    progress: NoNanFillValueProgress | None = None,
    ctsm_root: str = DEFAULT_CTSM_ROOT,
) -> Tuple[Set[str], List[str]]:
    if progress:
        netcdf_paths, files_referencing_netcdfs = progress.get_nc_paths_and_files_referencing()
    else:
        warn(logger, f"Searching namelist files in '{ctsm_root}' for netCDF paths...")

        # In production, we should only ever define these constants as paths relative to the CTSM
        # root! However, unit/system tests may mock them to be absolute paths instead.
        if os.path.isabs(XML_FILE):
            xml_file_abs = XML_FILE
        else:
            xml_file_abs = os.path.join(ctsm_root, XML_FILE)
        if os.path.isabs(DIR_TO_SEARCH_FOR_USER_NL_FILES):
            dir_to_search_abs = DIR_TO_SEARCH_FOR_USER_NL_FILES
        else:
            dir_to_search_abs = os.path.join(ctsm_root, DIR_TO_SEARCH_FOR_USER_NL_FILES)

        # Make sure the requested locations exist
        if not os.path.isfile(xml_file_abs):
            error(logger, f"{xml_file_abs} not found", error_type=FileNotFoundError)
        if not os.path.isdir(dir_to_search_abs):
            error(logger, f"{dir_to_search_abs} not found", error_type=FileNotFoundError)

        # Get list of files to search for netCDF paths
        files_to_search = [xml_file_abs]
        files_to_search.extend(nlu.find_user_nl_files(dir_to_search_abs))

        # Find all netCDF paths referenced in those files
        netcdf_paths = set()
        files_referencing_netcdfs = []
        for file_to_search in files_to_search:
            # replace_fill_values will read directly from the JSON file and will not get --cesm-root
            # option, so paths to namelist files need to be absolute
            assert os.path.isabs(file_to_search), f"Got rel but expected abs: {file_to_search}"

            netcdf_paths_thisfile = nlu.extract_file_paths_from_file(file_to_search)
            if netcdf_paths_thisfile:
                files_referencing_netcdfs.append(file_to_search)
            netcdf_paths = netcdf_paths | netcdf_paths_thisfile

            try:
                msg_path = Path(file_to_search).relative_to(ctsm_root)
            except Exception:  # pylint: disable=broad-exception-caught
                msg_path = file_to_search
            info(logger, f"{INDENT}Found {len(netcdf_paths_thisfile)} netCDF paths in '{msg_path}'")
    return netcdf_paths, files_referencing_netcdfs


def _get_netcdfs_with_nan_fills(progress, netcdf_paths, files_referencing_netcdfs):
    warn(logger, "\nChecking those netCDF files for NaN fill...")

    for netcdf_path in sorted(netcdf_paths):
        # Get the absolute path; continue if already processed
        abs_path = convert_to_absolute_path(netcdf_path)
        if abs_path in progress:
            continue

        # Check that the file exists
        if not os.path.exists(abs_path):
            info(logger, f"netCDF file not found: '{netcdf_path}'")
            # TODO: Actually handle files that weren't found, if possible.
            progress[abs_path] = {}
            continue
        # TODO: Check that the file is in CESM inputdata dir

        # Get path of netCDF file to display in messages
        msg_path = get_path_with_cesmdataroot(abs_path)

        # Check that the file actually has NaN _FillValue for at least one var
        info(logger, f"{INDENT}Checking for NaN fill: '{msg_path}'")
        _check_for_nanfill_in_netcdf(files_referencing_netcdfs, progress, netcdf_path, abs_path)

        # Print message
        msg = f"NaN fill values: '{msg_path}'"
        if abs_path in progress:
            info(logger, f"{INDENT}⚠️ {msg}")
        else:
            info(logger, f"{INDENT}✅ No {msg}")


def main() -> int:
    """
    Main function to find matching file paths and collect new fill values.

    Parses command-line arguments, finds files with NaN fill values, and
    interactively collects replacement values from the user.

    Returns:
        Exit code (0 for success)
    """

    # Parse command-line arguments
    parser = argparse.ArgumentParser(
        description="Find and fix files with NaN fill values in CTSM namelist defaults"
    )
    parser.add_argument(
        "--delete-if-none-filled",
        action="store_true",
        help="Automatically use 'delete' if variable has no filled elements (no prompt)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Print the variables that would be processed (and their defaults, if any), but don't"
            " request user input or save anything."
        ),
    )
    parser.add_argument(
        "--fillvalues-file",
        default=str(NEW_FILLVALUES_FILE),
        help=(f"JSON file where collected info will be saved. Default: '{NEW_FILLVALUES_FILE}'"),
    )
    # Hidden option to accept all suggested defaults without prompting the user
    parser.add_argument(
        "--accept-all-defaults",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--ctsm-root",
        type=str,
        default=DEFAULT_CTSM_ROOT,
        help=f"Path to root of CTSM directory with namelist files (default: {DEFAULT_CTSM_ROOT})",
    )
    add_logging_args(parser)
    args = parser.parse_args()
    process_logging_args(args)

    # Check write access to progress file before starting
    if not args.dry_run:
        debug(logger, "Checking write access for progress file...")
        if not check_write_access(args.fillvalues_file):
            msg = f"Error: No write access to create/update {args.fillvalues_file}\n"
            dir_str = os.path.dirname(args.fillvalues_file) or "."
            msg += f"Please check permissions in directory: {dir_str}"
            error_type = PermissionError if logger.getEffectiveLevel() <= logging.DEBUG else None
            error(logger, msg, error_type=error_type)
            sys.exit(1)
        info(logger, f"✓ Write access confirmed for {args.fillvalues_file}\n")

    # Load existing progress if available
    progress = NoNanFillValueProgress(progress_file=args.fillvalues_file)
    did_load_progress = bool(progress)

    netcdf_paths, files_referencing_netcdfs = _get_netcdf_files_to_check(progress, args.ctsm_root)

    if not did_load_progress:
        _get_netcdfs_with_nan_fills(progress, netcdf_paths, files_referencing_netcdfs)
        warn(logger, "\n" + "=" * SEP_LENGTH)
        progress.print_summary(len(netcdf_paths))
        warn(logger, "=" * SEP_LENGTH)

        # Ask if user wants to continue
        warn(logger, "")
        if not user_inputs.confirm_continue():
            sys.exit("Exiting.")

    # Collect new fill values from user
    user_inputs.collect_new_fill_values(
        progress,
        delete_if_none_filled=args.delete_if_none_filled,
        dry_run=args.dry_run,
        accept_all_defaults=args.accept_all_defaults,
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
