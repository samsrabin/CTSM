"""
Module handling the JSON file we use for saving progress and passing info between scripts
"""

from pathlib import Path
import os
import sys
from copy import deepcopy
from typing import Any, Callable, List, Set, Tuple, Type
import json
from collections import defaultdict
import logging

import numpy as np

# Add the python directory to sys.path for direct script execution
_CTSM_PYTHON = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
if _CTSM_PYTHON not in sys.path:
    sys.path.insert(1, _CTSM_PYTHON)

from ctsm.no_nans_in_inputs.constants import (  # pylint: disable=wrong-import-position
    FILL_ATTR,
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


def create_empty_progress_dict_onefile() -> dict:
    """Return a dictionary for one netCDF file"""
    return {
        "found_in_files": {},
        "new_fill_values": {},
        "vars_to_give_fills": [],
        "vars_with_rawnan_nofill": [],
        "vars_with_rawnan_yesfill": {},
    }


class NoNanFillValueProgress(defaultdict):
    """Defaultdict-like for tracking progress in getting/replacing NaN fill values"""

    def __init__(
        self,
        default_factory: Callable = create_empty_progress_dict_onefile,
        progress_file: str | None = None,
        load_without_asking: bool = False,
    ) -> None:
        """Initialize the progress tracker, loading from an existing file if present.

        Args:
            default_factory (Callable): Factory for default dict values.
                Default: create_empty_progress_dict_onefile.
            progress_file (str | None): Path to JSON progress file to load/save. Default: None.
            load_without_asking (bool): If True, load existing progress without prompting the
                user to confirm. Default: False.
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

    def __setitem__(self, key: Any, value: Any) -> None:
        """Ensure all keys are stored as strings.

        Args:
            key (Any): Key to set; will be coerced to str.
            value (Any): Value to associate with the key.
        """
        super().__setitem__(str(key), value)

    def update(self, *args: Any, **kwargs: Any) -> None:
        """Update the dict, converting all keys to str (ensuring no keys are Path objects).

        Args:
            *args (Any): Positional arguments; first may be a dict or iterable of (key, value) pairs.
            **kwargs (Any): Keyword arguments to merge in.
        """
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

    def append(self, new_dict: dict) -> None:
        """Merge another dict into this one.

        Args:
            new_dict (dict): Dictionary to merge in; its keys take precedence over existing ones.
        """
        self.update(dict(self, **new_dict))

    def save(self) -> None:
        """Save progress to a JSON file."""
        if not self.progress_file:
            return

        # Can't serialize sets. deepcopy() is needed so that caller's progress isn't affected
        # .copy() isn't sufficient since we have nested mutables.
        progress_out = _convert_fif_dict_sets(deepcopy(self), list)

        # Handle types that aren't JSON-serializable
        _handle_non_serializable_types(progress_out)

        try:
            with open(self.progress_file, "w", encoding="utf-8") as f:
                json.dump(progress_out, f, indent=2)
            info(logger, f"{INDENT}[Progress saved to {self.progress_file}]")
        except (IOError, OSError) as e:
            warn(logger, f"{INDENT}Warning: Could not save progress: {e}", file=sys.stderr)

    def done_with_file(self, netcdf_path: str) -> None:
        """Mark a netCDF file as done, flagging it for removal from the progress object and file.

        Args:
            netcdf_path (str): Absolute path to the netCDF file that has been processed.
        """
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
        """Get netCDF paths in this dict and all namelist files that reference them.

        Returns:
            Tuple[Set[str], List[str]]: Tuple of (netcdf_paths, files_referencing_netcdfs), where
                netcdf_paths is the set of all netCDF file paths tracked in this dict, and
                files_referencing_netcdfs is the list of namelist/XML files that reference them.
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
        """Print a summary of progress: files with NaNs, files not found, and optionally total checked.

        Args:
            n_netcdfs_checked (int | None): Total number of netCDF files checked, printed if provided.
                Default: None.
        """
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

    def any_need_fixing(self) -> bool:
        """Do any of the processed files need fixing?"""
        return any(isinstance(v, dict) and bool(v) for v in self.values())


def _convert_fif_dict_sets(
    progress: NoNanFillValueProgress, dest_type: Type
) -> NoNanFillValueProgress:
    """Convert the "found_in_files" dict values between lists and sets.

    The code needs "found_in_files" to contain sets, but the JSON serializer can only
    handle lists. This function converts between the two representations.

    Args:
        progress (NoNanFillValueProgress): Progress dict whose "found_in_files" values will
            be converted.
        dest_type (Type): Type to convert to (e.g., set or list).

    Returns:
        NoNanFillValueProgress: The modified progress dict (same object, modified in-place).
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
    """Count the total number of new fill values decided across all files in a progress dict.

    Args:
        progress (NoNanFillValueProgress): Progress dict to count variables in.

    Returns:
        int: Total number of variables with decided fill values.
    """
    n_vars = 0
    for file in progress.keys():
        if "new_fill_values" in progress[file]:
            n_vars += len(progress[file]["new_fill_values"].keys())
    return n_vars


def _handle_non_serializable_types(progress_out: NoNanFillValueProgress) -> None:
    """Convert non-JSON-serializable numpy numeric types to native Python types, in-place.

    Converts numpy integers and float32 values to Python int or float so the
    progress dict can be serialized with json.dump.

    Args:
        progress_out (NoNanFillValueProgress): Progress dict to modify in-place.
    """
    for progress_1file in progress_out.values():
        if not isinstance(progress_1file, dict):
            continue
        # Loop through all dicts in this file's dict
        for d in progress_1file.values():
            if not isinstance(d, dict):
                continue
            for k, v in d.items():
                if isinstance(v, np.integer):
                    d[k] = int(v)
                elif isinstance(v, np.float32):
                    if np.round(v) == v:
                        d[k] = int(v)
                    else:
                        d[k] = float(v)
