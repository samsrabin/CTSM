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
import glob
import re
from pathlib import Path
import sys
from typing import List, Set, Tuple
import logging
import json


# Add the python directory to sys.path for direct script execution
_CTSM_PYTHON = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
if _CTSM_PYTHON not in sys.path:
    sys.path.insert(1, _CTSM_PYTHON)

from ctsm.no_nans_in_inputs.constants import (  # pylint: disable=wrong-import-position
    FILL_ATTR,
    DEFAULT_CTSM_ROOT,
    DIR_TO_SEARCH_FOR_XML_FILES,
    INDENT,
    INPUTDATA_PREFIX,
    KNOWN_GOOD_FILES_FILE,
    NEW_FILLVALUES_FILE,
    NO_HANDLED_NANS,
    SEP_LENGTH,
    USER_REQ_SKIP_FILE,
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
    file_has_mismatched_fill_missing,
    file_has_nan_ncks_chk_nan,
    file_has_nan_fill,
    file_has_nan_without_fill,
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


def _check_for_nans_in_netcdf(
    files_referencing_netcdfs: list,
    progress: NoNanFillValueProgress,
    netcdf_path: str,
    abs_path: str,
    warn_unhandled: bool,
    known_good_files_list: List[str],
) -> None:

    # Skip files already processed
    if abs_path in progress:
        return

    # Check that the file exists
    if not os.path.exists(abs_path):
        info(logger, f"netCDF file not found: '{netcdf_path}'")
        progress[abs_path] = {}
        progress.save()
        return
    # TODO: Check that the file is in CESM inputdata dir

    # Get path of netCDF file to display in messages
    msg_path = get_path_with_cesmdataroot(abs_path)

    # Skip files that we know to be unaffected
    path_rel_inputdata = os.path.relpath(abs_path, INPUTDATA_PREFIX)
    if path_rel_inputdata in known_good_files_list:
        info(logger, f"Skipping known-good file: '{abs_path}'")
        progress[abs_path] = NO_HANDLED_NANS
        progress.save()
        return

    # Check file for problems
    info(logger, f"{INDENT}Checking: '{msg_path}'")
    info(logger, f"{INDENT*2}Checking for NaN fill")
    any_nan_fill, vars_with_nan_fills = file_has_nan_fill(abs_path)
    info(logger, f"{INDENT*2}Checking for mismatched fill/missing")
    any_mismatched_fill_missing, mismatches = file_has_mismatched_fill_missing(abs_path)
    info(logger, f"{INDENT*2}Checking for NaNs without fill")
    any_nan_without_fill, vars_with_nan_without_fill = file_has_nan_without_fill(abs_path)

    # Return early if no problems found
    if not (any_nan_fill or any_mismatched_fill_missing or any_nan_without_fill):
        if warn_unhandled and file_has_nan_ncks_chk_nan(abs_path):
            info(logger, f"{INDENT*2}Checking for unhandled NaNs")
            error_type = FileNotFoundError if ctsm_logging.lte_debug(logger) else None
            msg = "WARNING: Skipping file with NaN that wasn't caught:" f" '{abs_path}'"
            error(logger, msg, error_type=error_type)
        if abs_path in progress:
            error(
                logger,
                f"Found no NaNs in file but it was in progress dict: {abs_path}",
                error_type=RuntimeError,
            )
        _print_msg(progress, abs_path)
        progress[abs_path] = NO_HANDLED_NANS
        progress.save()
        known_good_files_list.append(path_rel_inputdata)
        _save_known_good_files(known_good_files_list)
        return

    # Get information for this file
    fif_dict = progress[abs_path]["found_in_files"]
    for file_to_search in files_referencing_netcdfs:
        set_of_how_this_netcdf_appears = nlu.how_netcdf_is_referenced_in_file(
            file_to_search, netcdf_path
        )
        if set_of_how_this_netcdf_appears:
            if file_to_search not in fif_dict:
                fif_dict[file_to_search] = set()
            fif_dict[file_to_search] = fif_dict[file_to_search] | set_of_how_this_netcdf_appears

    # Get list of variables in this file with issues
    if any_nan_fill:
        progress[abs_path]["vars_with_nan_fills"] += vars_with_nan_fills
    if any_nan_without_fill:
        # That's right: We will reuse the existing list
        progress[abs_path]["vars_with_nan_fills"] += vars_with_nan_without_fill
    if any_mismatched_fill_missing:
        progress[abs_path]["vars_with_mismatched_fill_missing"] = [x.var_name for x in mismatches]

    # Get suffix for eventual new version of file
    progress[abs_path]["suffix"] = _get_output_suffix(progress, abs_path)

    # Save
    progress.save()
    _print_msg(progress, abs_path)


def _get_output_suffix(progress: NoNanFillValueProgress, file_path: str) -> str:
    # if not progress[file_path] or isinstance(progress[file_path], str):
    #     return ".SHOULD_SKIP"
    any_nan_fill = bool(progress[file_path]["vars_with_nan_fills"])
    any_mismatched_fill_missing = bool(progress[file_path]["vars_with_mismatched_fill_missing"])
    if any_nan_fill:
        if any_mismatched_fill_missing:
            suffix = ".no_nan_fill_same_missing"
        else:
            suffix = ".no_nan_fill"
    elif any_mismatched_fill_missing:
        suffix = ".same_fill_missing"
    else:
        raise RuntimeError("???")
    return suffix


def _print_msg(progress, abs_path):
    msg = f"NaN fill values: '{get_path_with_cesmdataroot(abs_path)}'"
    if abs_path in progress:
        info(logger, f"{INDENT}⚠️ {msg}")
    else:
        info(logger, f"{INDENT}✅ No {msg}")


def _get_netcdf_files_to_check(
    ctsm_root: str = DEFAULT_CTSM_ROOT,
) -> Tuple[Set[str], List[str]]:
    warn(logger, f"Searching namelist files in '{ctsm_root}' for netCDF paths...")

    # In production, we should only ever define these constants as paths relative to the CTSM
    # root! However, unit/system tests may mock them to be absolute paths instead.
    if os.path.isabs(DIR_TO_SEARCH_FOR_XML_FILES):
        dir_to_search_xml = DIR_TO_SEARCH_FOR_XML_FILES
    else:
        dir_to_search_xml = os.path.join(ctsm_root, DIR_TO_SEARCH_FOR_XML_FILES)
    if os.path.isabs(DIR_TO_SEARCH_FOR_USER_NL_FILES):
        dir_to_search_usernl_abs = DIR_TO_SEARCH_FOR_USER_NL_FILES
    else:
        dir_to_search_usernl_abs = os.path.join(ctsm_root, DIR_TO_SEARCH_FOR_USER_NL_FILES)

    # Make sure the requested locations exist
    if not os.path.isdir(dir_to_search_xml):
        error(logger, f"{dir_to_search_xml} not found", error_type=FileNotFoundError)
    if not os.path.isdir(dir_to_search_usernl_abs):
        error(logger, f"{dir_to_search_usernl_abs} not found", error_type=FileNotFoundError)

    # Get list of files to search for netCDF paths
    files_to_search = []
    files_to_search.extend(nlu.find_xml_files(dir_to_search_xml))
    files_to_search.extend(nlu.find_user_nl_files(dir_to_search_usernl_abs))

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


def _file_in_directory(my_file: Path | str, my_directory: Path | str) -> bool:
    my_file = Path(my_file).resolve()
    my_directory = Path(my_directory).resolve()
    return my_directory in my_file.parents


def _get_netcdfs_with_nan_fills(
    progress: NoNanFillValueProgress,
    netcdf_paths: Set[str] | str,
    files_referencing_netcdfs: List[str],
    warn_unhandled: bool,
    skippable_list: List[str],
    known_good_files_list: List[str],
) -> None:
    warn(logger, "\nChecking those netCDF files for NaNs...")

    if isinstance(netcdf_paths, str):
        netcdf_paths = {netcdf_paths}

    for netcdf_path in sorted(netcdf_paths):

        # Get the absolute path
        # TODO: REALPATH
        abs_path = convert_to_absolute_path(netcdf_path)

        # Did user request skipping this? If so, skip, unless it's already been processed.
        do_skip = False
        if abs_path not in progress or progress[abs_path] == USER_REQ_SKIP_FILE:
            for skippable in skippable_list:
                if os.path.isdir(skippable) and _file_in_directory(abs_path, skippable):
                    do_skip = True
                elif os.path.isfile(skippable) and abs_path == skippable:
                    do_skip = True
                if do_skip:
                    progress[abs_path] = USER_REQ_SKIP_FILE
                    progress.save()
                    break
        if do_skip:
            continue

        # User didn't request skipping, but it is marked as skipped in progress: Remove from
        # progress and process it now.
        if not do_skip and abs_path in progress and progress[abs_path] == USER_REQ_SKIP_FILE:
            del progress[abs_path]
            progress.save()

        # Continue if already processed
        if abs_path in progress:
            continue

        # Replace any shell vars with wildcards and search through matching files
        if "$" in netcdf_path:
            glob_pattern = re.sub(r"\$(\w+|\{[^}]+\})", "*", abs_path)
            matching_files = glob.glob(glob_pattern)
            matching_files.sort()
            if not matching_files:
                warn(logger, f"WARNING: No files found corresponding to '{glob_pattern}'")
                progress[abs_path] = {}
                continue
            progress_tmp = NoNanFillValueProgress()
            for globbed_abs_path in matching_files:
                # Check that the file actually has NaN _FillValue for at least one var
                _check_for_nans_in_netcdf(
                    files_referencing_netcdfs,
                    progress_tmp,
                    netcdf_path,
                    globbed_abs_path,
                    warn_unhandled,
                    known_good_files_list,
                )

            # No files need fixing
            if not progress_tmp.any_need_fixing():
                continue

            # If only SOME of the files matching the wildcards need fixing, you will need to make
            # copies of the other files with the same added suffix. This is currently not handled in
            # these scripts, so just skip such situations.
            n_to_fix = sum(isinstance(v, dict) for v in progress_tmp.values())
            n_matched = len(matching_files)
            if n_to_fix != n_matched:
                error_type = (
                    NotImplementedError if ctsm_logging.lte_debug(logger) else None
                )
                msg = (
                    f"Only {n_to_fix}/{n_matched} files matching pattern"
                    f" '{glob_pattern}' need fixing. This is currently not handled."
                )
                error(logger, msg, error_type=error_type)
                if not user_inputs.confirm_continue():
                    sys.exit("Exiting.")
                continue

            # A similar problem will arise if all the files need fixing but they wouldn't receive
            # the same suffix.
            # TODO: Avoid this by giving all new files the same suffix regardless of changes made
            if len({v["suffix"] for v in progress_tmp.values()}) > 1:
                error_type = RuntimeError if ctsm_logging.lte_debug(logger) else None
                msg = (
                    f"ERROR: Not all {len(progress_tmp)} files matching pattern '{glob_pattern}'"
                    " would get the same suffix, which would cause problems when using the"
                    " namelist. Will skip fixing these files."
                )
                error(logger, msg, error_type=error_type)
                if not user_inputs.confirm_continue():
                    sys.exit("Exiting.")
                continue

            # Save temporary progress dict to main one
            progress.update(progress_tmp)
            progress.save()

        # If no shell vars, just check the file directly
        else:
            # Check that the file actually has NaN _FillValue for at least one var
            _check_for_nans_in_netcdf(
                files_referencing_netcdfs,
                progress,
                netcdf_path,
                abs_path,
                warn_unhandled,
                known_good_files_list,
            )


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
    parser.add_argument(
        "--warn-unhandled",
        action="store_true",
        help=(
            "Warn if a file seems to have an unhandled NaN. Increases memory usage; may result in"
            " task getting killed."
        ),
    )
    parser.add_argument(
        "--skip",
        action="append",
        default=[],
        help="Mark a file or dir (and all files therein, recursive) as skippable",
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
            error_type = PermissionError if ctsm_logging.lte_debug(logger) else None
            error(logger, msg, error_type=error_type)
            sys.exit(1)
        info(logger, f"✓ Write access confirmed for {args.fillvalues_file}\n")

    # Load existing progress if available
    progress = NoNanFillValueProgress(progress_file=args.fillvalues_file)

    # Load list of known-good files
    if not os.path.exists(KNOWN_GOOD_FILES_FILE) and progress:
        known_good_files_list = [f for f in progress if progress[f] == NO_HANDLED_NANS]
        _save_known_good_files(known_good_files_list)
    if os.path.exists(KNOWN_GOOD_FILES_FILE):
        with open(KNOWN_GOOD_FILES_FILE, "r", encoding="utf8") as f:
            known_good_files_list = json.load(f)
    else:
        known_good_files_list = []

    netcdf_paths, files_referencing_netcdfs = _get_netcdf_files_to_check(args.ctsm_root)

    _get_netcdfs_with_nan_fills(
        progress,
        netcdf_paths,
        files_referencing_netcdfs,
        args.warn_unhandled,
        args.skip,
        known_good_files_list,
    )
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


def _save_known_good_files(known_good_files_list):
    known_good_files_list.sort()
    with open(KNOWN_GOOD_FILES_FILE, "w", encoding="utf8") as f:
        json.dump(known_good_files_list, f, indent=INDENT)


if __name__ == "__main__":
    sys.exit(main())
