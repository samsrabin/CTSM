"""
Module handling the JSON file we use for saving progress and passing info between scripts
"""

from pathlib import Path
import os
import sys
from copy import deepcopy
from typing import List, Set, Tuple, Type
import json
from collections import defaultdict
import logging

# Add the python directory to sys.path for direct script execution
_CTSM_PYTHON = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
if _CTSM_PYTHON not in sys.path:
    sys.path.insert(1, _CTSM_PYTHON)

from ctsm.no_nans_in_inputs.constants import (  # pylint: disable=wrong-import-position
    ATTR,
    INDENT,
    NO_HANDLED_NANS,
    USER_REQ_SKIP_VAR,
)
from ctsm.no_nans_in_inputs.shared import (  # pylint: disable=wrong-import-position
    get_path_with_cesmdataroot,
)

from ctsm.ctsm_logging import (  # pylint: disable=wrong-import-position
    error,
    info,
    warn,
)

# Set up logging
logger = logging.getLogger(__name__)


def create_empty_progress_dict_onefile():
    """Return a dictionary for one netCDF file"""
    return {
        "found_in_files": {},
        "new_fill_values": {},
        "vars_with_nan_fills": [],
        "new_fill_missing": {},
        "vars_with_mismatched_fill_missing": [],
    }


class NoNanFillValueProgress(defaultdict):
    """Defaultdict-like for tracking progress in getting/replacing NaN fill values"""

    def __init__(
        self,
        default_factory=create_empty_progress_dict_onefile,
        progress_file: str | None = None,
        load_without_asking: bool = False,
    ):
        """
        Initialize our progress file: Either load an existing one or start a new one
        """
        super().__init__(default_factory)

        if isinstance(progress_file, Path):
            progress_file = str(progress_file)
        self.progress_file = progress_file

        if progress_file and os.path.exists(progress_file):
            try:
                with open(progress_file, "r", encoding="utf-8") as f:
                    progress = json.load(f)

                    # This is serialized as a list, but the code needs it as a set
                    progress = _convert_fif_dict_sets(progress, set)

                    warn(logger, f"\nLoaded progress from {progress_file}:")
                    self.update(progress)
                    self.print_summary()
                    total_vars = _get_n_vars_in_progress(self)
                    if total_vars:
                        # TODO: Also print progress so far for vars with mismatched fill/missing
                        warn(
                            logger,
                            f"Already decided {total_vars} new fill values in {len(self)} file(s)",
                        )
                    else:
                        warn(logger, "No new fill values decided so far")
                    if not load_without_asking:
                        response = (
                            input("Continue from where you left off? [Y/n]: ").strip().lower()
                        )
                        if response and response not in ("y", "yes"):
                            warn(logger, "Starting fresh...")
                            self.clear()
            except (IOError, OSError, json.JSONDecodeError) as e:
                error(logger, f"Warning: Could not load progress file: {e}", error_type=type(e))

    def __setitem__(self, key, value):
        """Ensure all keys are strings"""
        super().__setitem__(str(key), value)

    def update(self, *args, **kwargs):
        """Convert keys to str for update operations (i.e., ensuring no keys are Path)"""
        # Handle dict or iterable of key/value pairs
        if args:
            other = args[0]
            if hasattr(other, "items"):
                for k, v in other.items():
                    self[str(k)] = v
            else:  # iterable of (k, v)
                for k, v in other:
                    self[str(k)] = v
        for k, v in kwargs.items():
            self[str(k)] = v

    def append(self, new_dict):
        """Append another dict to this one"""
        self.update(dict(self, **new_dict))

    def save(self) -> None:
        """
        Save progress to a JSON file.
        """
        if not self.progress_file:
            return

        # Can't serialize sets. deepcopy() is needed so that caller's progress isn't affected
        # .copy() isn't sufficient since we have nested mutables.
        progress_out = _convert_fif_dict_sets(deepcopy(self), list)

        try:
            with open(self.progress_file, "w", encoding="utf-8") as f:
                json.dump(progress_out, f, indent=2)
            info(logger, f"{INDENT}[Progress saved to {self.progress_file}]")
        except (IOError, OSError) as e:
            warn(logger, f"{INDENT}Warning: Could not save progress: {e}", file=sys.stderr)

    def done_with_file(self, netcdf_path: str) -> None:
        """After we're done with a netCDF file, mark for removal from progress object/file"""
        if netcdf_path not in self:
            error(
                logger,
                f"{netcdf_path} not a key in NoNanFillValueProgress object",
                error_type=KeyError,
            )
        self[netcdf_path] = None

    def cleanup(self) -> None:
        """Remove keys marked for deletion, then update progress file"""
        keys_to_remove = [k for k in self if not self[k]]
        for key in keys_to_remove:
            self.pop(key)
        self.save()

    def get_nc_paths_and_files_referencing(self) -> Tuple[Set[str], List[str]]:
        """
        Get netCDF paths in this dict, as well as all the namelist files that reference netCDFs
        """
        netcdf_paths = set(self.keys())
        files_referencing_netcdfs = set()
        for k in self:
            if "found_in_files" not in self[k]:
                # netCDF file k wasn't found
                continue
            fif: dict = self[k]["found_in_files"]
            files_referencing_netcdfs = files_referencing_netcdfs | set(fif.keys())
        files_referencing_netcdfs = list(files_referencing_netcdfs)
        return netcdf_paths, files_referencing_netcdfs

    def print_summary(self, n_netcdfs_checked: int | None = None) -> None:
        """Print summary of progress so far"""
        if n_netcdfs_checked is not None:
            warn(
                logger,
                f"{n_netcdfs_checked}" "\tTotal netCDF files referenced in XML and user_nl_ files",
            )
        n_files_with_nans = 0
        for k in self:
            n_files_with_nans += int(
                (self[k] != NO_HANDLED_NANS) and (self[k] != USER_REQ_SKIP_VAR)
            )
        warn(logger, f"{n_files_with_nans}\tFiles with NaNs")
        files_not_found = [k for k in self if not self[k]]
        warn(logger, f"{len(files_not_found)}\tFiles not found")
        if files_not_found:
            for f in files_not_found:
                warn(logger, f"\t* '{get_path_with_cesmdataroot(f)}'")


def _convert_fif_dict_sets(
    progress: NoNanFillValueProgress, dest_type: Type
) -> NoNanFillValueProgress:
    """
    The code needs the "found_in_files" dictionary to contain sets, but the JSON serializer can only
    handle lists. This function allows the conversion of items in that dictionary between lists and
    sets.

    Args:
        progress: Dictionary of found locations and collected fill values
        dest_type: Type to convert to
    """
    for abs_path in progress:
        if "found_in_files" not in progress[abs_path]:
            # abs_path wasn't found
            continue
        fif_dict = progress[abs_path]["found_in_files"]
        for file_containing in fif_dict:
            fif_dict[file_containing] = dest_type(fif_dict[file_containing])
    return progress


def _get_n_vars_in_progress(progress: NoNanFillValueProgress) -> int:
    n_vars = 0
    for file in progress.keys():
        if "new_fill_values" in progress[file]:
            n_vars += len(progress[file]["new_fill_values"].keys())
    return n_vars
