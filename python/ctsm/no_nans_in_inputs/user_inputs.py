"""
Functions handling user inputs
"""

import os
import sys
from typing import Any
import logging
import warnings

warnings.simplefilter("error")  # Treat all warnings as errors


import numpy as np
import xarray as xr

# Add the python directory to sys.path for direct script execution
_CTSM_PYTHON = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
if _CTSM_PYTHON not in sys.path:
    sys.path.insert(1, _CTSM_PYTHON)

from ctsm.no_nans_in_inputs.constants import (  # pylint: disable=wrong-import-position
    ATTR,
    ERR_STR_SKIP_FILE,
    ERR_STR_SKIP_VAR,
    INDENT,
    OPEN_DS_KWARGS,
    SEP_LENGTH,
    USER_REQ_DELETE,
    USER_REQ_QUIT,
    USER_REQ_SKIP_FILE,
    USER_REQ_SKIP_VAR,
)
from ctsm.no_nans_in_inputs.shared import (  # pylint: disable=wrong-import-position
    FillValueConfig,
    VarContext,
)
from ctsm.no_nans_in_inputs.netcdf_utils import (  # pylint: disable=wrong-import-position
    get_var_info,
    show_ncdump_for_variable,
)
from ctsm.no_nans_in_inputs.json_io import (  # pylint: disable=wrong-import-position
    NoNanFillValueProgress,
)

from ctsm.ctsm_logging import (  # pylint: disable=wrong-import-position
    error,
    info,
    warn,
)

# Set up logging
logger = logging.getLogger(__name__)


def confirm_continue(prompt: str = "Continue? [Y/n]: "):
    """
    Prompt the user for confirmation to continue, defaulting to 'Yes'.

    Parameters
    ----------
    prompt : str
        The message displayed to the user. Default is "Continue? [Y/n]: ".

    Returns
    -------
    bool
        True if the user confirms (Yes), False if the user declines (No).

    Behavior
    --------
    - Pressing Enter defaults to Yes.
    - Accepts 'y', 'yes' (case-insensitive) as Yes.
    - Accepts 'n', 'no' (case-insensitive) as No.
    - Any other input will reprompt until a valid response is given.
    """
    while True:
        response = input(prompt).strip().lower()

        if response in ("", "y", "yes"):
            return True
        if response in ("n", "no"):
            return False

        error(logger, f"Please enter 'y' or 'n', not {response}.", error_type=None)


def _convert_and_validate_input(user_input: str, target_type: type) -> Any | None:
    """
    Convert user input to the target type and validate it's not NaN.

    Args:
        user_input: The user's input string (already stripped)
        target_type: Type to convert the input to

    Returns:
        Converted value, or None if conversion failed (error message already printed)
    """
    try:
        converted_value = target_type(user_input)

        # Make sure it's not NaN
        try:
            converted_value_is_nan = np.isnan(converted_value)
        except TypeError:
            converted_value_is_nan = False
        if converted_value_is_nan:
            error(logger, f"Input '{user_input}' would produce a NaN {ATTR}", error_type=ValueError)

        return converted_value
    except (ValueError, TypeError) as e:
        error(
            logger,
            f"{INDENT}Invalid input: {e}. Please enter a valid {target_type.__name__}.",
            error_type=None,
        )
        return None


def _get_fill_value_from_user(var_context: VarContext, config: FillValueConfig) -> Any:
    """
    Prompt user for a new fill value and convert it to the target type.

    Args:
        var_context: Context about the variable (name, type, file path)
        config: Configuration for prompt behavior (default, allow_delete, auto-delete)

    Returns:
        Converted fill value of the specified type, or USER_REQ_DELETE string

    Raises:
        KeyboardInterrupt: If user presses Ctrl-C twice or types 'quit'
        ValueError: If user types 'skip' or 'skipfile'
    """
    # If delete_if_none_filled is enabled and default is delete, use it automatically
    if config.delete_if_none_filled and config.default_value == USER_REQ_DELETE:
        if var_context.dry_run:
            prefix = "Would auto-delete"
        else:
            prefix = "Auto-deleting"
        warn(logger, f"{INDENT}{prefix} {ATTR} attribute, since no elements are filled")
        return USER_REQ_DELETE

    # TODO:  WARN AND ASK FOR CONFIRMATION IF TRYING TO SET FILL VALUE TO SOMETHING ALREADY PRESENT
    # IN DATA

    ctrl_c_count = 0

    while True:
        user_input = None
        try:
            # Build prompt with default value if available
            prompt = f"    New fill value for '{var_context.var_name}'"
            if config.default_value is not None:
                prompt += f" [default: {config.default_value}]"
            if not var_context.dry_run:
                prompt += ": "
            elif config.delete_if_none_filled:
                prompt += "; would automatically mark for deletion"

            # Skip variable if dry run
            if var_context.dry_run:
                info(logger, prompt)
                return USER_REQ_SKIP_VAR

            user_input = input(prompt).strip()

            if user_input:
                # Check for special commands first
                special_result = _handle_special_command(user_input, config.allow_delete)
                if special_result is not None:
                    return special_result

                # Try to convert to the target type
                converted = _convert_and_validate_input(user_input, var_context.target_type)
                if converted is not None:
                    return converted
            else:
                # Empty input - use default or show help
                empty_result = _handle_empty_input(config.default_value, config.allow_delete)
                if empty_result is not None:
                    return empty_result

        except KeyboardInterrupt:
            ctrl_c_count = _handle_ctrl_c(ctrl_c_count, user_input, var_context)


def _handle_ctrl_c(ctrl_c_count: int, user_input: str | None, var_context: VarContext) -> int:
    """
    Handle a KeyboardInterrupt (Ctrl-C) during user input.

    On the first Ctrl-C, shows ncdump output for the variable.
    On the second Ctrl-C (or if user had typed 'quit'), re-raises.

    Args:
        ctrl_c_count: Number of times Ctrl-C has been pressed (before incrementing)
        user_input: The user's input before Ctrl-C (may be None)
        var_context: Context about the variable being processed

    Returns:
        Updated ctrl_c_count

    Raises:
        KeyboardInterrupt: If this is the second Ctrl-C or user typed 'quit'
    """
    ctrl_c_count += 1

    # If this is the second Ctrl-C or the user requested quit or dry run, exit
    if ctrl_c_count >= 2 or user_input == USER_REQ_QUIT or var_context.dry_run:
        if ctrl_c_count >= 2:
            warn(logger, f"\n{INDENT}[Ctrl-C pressed again - exiting]")
        else:
            warn(logger, f"\n{INDENT}User requested quit")
        raise KeyboardInterrupt

    # First Ctrl-C: show ncdump output for this variable
    warn(logger, f"\n{INDENT}[Ctrl-C detected - press again to exit]")
    show_ncdump_for_variable(var_context.file_path, var_context.var_name)
    return ctrl_c_count


def _handle_empty_input(default_value: Any, allow_delete: bool) -> Any | None:
    """
    Handle empty user input by returning the default or printing help.

    Args:
        default_value: Default value to use, or None if no default
        allow_delete: Whether deleting the fill value is allowed (for help message)

    Returns:
        The default value if one exists, or None if no default (help message already printed)
    """
    if default_value is not None:
        warn(logger, f"{INDENT}Using default: {default_value}")
        return default_value

    # Build help message based on what's allowed
    options = []
    if allow_delete:
        options.append(f"'{USER_REQ_DELETE}' to delete attribute")
    options.extend(
        [
            f"'{USER_REQ_SKIP_VAR}' to skip variable",
            f"'{USER_REQ_SKIP_FILE}' to skip file",
            f"'{USER_REQ_QUIT}' to save and exit",
        ]
    )
    error(logger, f"{INDENT}Please enter a value (or {', '.join(options)}).", error_type=None)
    return None


def _handle_special_command(input_str: str, allow_delete: bool) -> Any | None:
    """
    Check if user input is a special command and handle it.

    Args:
        input_str: The user's input string (already stripped)
        allow_delete: Whether deleting the fill value is allowed

    Returns:
        USER_REQ_DELETE if delete was requested and allowed, or None if not a special command

    Raises:
        KeyboardInterrupt: If user typed 'quit'
        ValueError: If user typed 'skip' or 'skipfile'
    """
    lower_input = input_str.lower()
    # Do not use error() for raising special codes; those will be caught and handled by a try-except
    # block and thus should not be printed to log file
    if lower_input == USER_REQ_QUIT:
        raise KeyboardInterrupt("User requested quit")
    if lower_input == USER_REQ_SKIP_VAR:
        raise ValueError(ERR_STR_SKIP_VAR)
    if lower_input == USER_REQ_SKIP_FILE:
        raise ValueError(ERR_STR_SKIP_FILE)
    if lower_input == USER_REQ_DELETE:
        if not allow_delete:
            error(
                logger,
                f"{INDENT}Error: Cannot delete {ATTR} - variable contains NaN values",
                error_type=None,
            )
            return None
        warn(logger, f"{INDENT}Will delete {ATTR} attribute")
        return USER_REQ_DELETE
    return None


def _collect_fill_values_one_path(
    progress: NoNanFillValueProgress,
    delete_if_none_filled: bool,
    abs_path: str,
    dry_run: bool,
    accept_all_defaults: bool = False,
) -> NoNanFillValueProgress:
    """
    Interactively collect new fill values for variables in one file with NaN fill values.

    Opens the file, identifies variables with NaN fill values, displays their properties, and
    prompts the user to enter new fill values.

    Progress is automatically saved after each variable. User can type 'quit' to save and exit,
    or 'skip' to skip a variable.

    Args:
        progress_file: Path to save/load progress
        progress: Dictionary of found locations and collected fill values (from progress_file)
        delete_if_none_filled: If True, automatically use delete when it's the default
        abs_path: Absolute path to the file.
        dry_run: If true, just print vars to process (and defaults, if any).

    Returns:
        Dictionary mapping absolute file paths to dictionaries of {variable_name: new_fill_value}
    """
    if "new_fill_values" not in progress[abs_path]:
        return progress

    warn(logger, f"\n{'=' * SEP_LENGTH}")
    warn(logger, f"Processing: {abs_path}")
    warn(logger, f"{'=' * SEP_LENGTH}")

    # Get dictionary for this file's fill values
    new_fill_values = progress[abs_path]["new_fill_values"]
    n_fv_before = len(new_fill_values)

    # Process all variables with mismatched fill vs. missing values
    _process_vars_with_mismatched_fill_missing(progress, abs_path, accept_all_defaults, dry_run)

    # Process all variables with NaN fill values
    _process_vars_with_nan_fills(
        progress, delete_if_none_filled, abs_path, dry_run, accept_all_defaults, new_fill_values
    )

    # Print summary for this file
    if not dry_run:
        n_fv_after = len(new_fill_values)
        n_new_fv = n_fv_after - n_fv_before
        info(
            logger,
            f"\n{INDENT}Collected {n_new_fv} new fill value(s) for this file; {n_fv_after} total:",
        )
        for var, fill_val in new_fill_values.items():
            info(logger, f"{INDENT*2}{var}: {fill_val}")

    return progress


def _process_vars_with_mismatched_fill_missing(
    progress: NoNanFillValueProgress, abs_path: str, accept_all_defaults: bool, dry_run: bool
) -> None:
    vars_with_mismatched_fill_missing = progress[abs_path]["vars_with_mismatched_fill_missing"]
    if not vars_with_mismatched_fill_missing:
        return
    new_fill_missing = progress[abs_path]["new_fill_missing"]

    ds = xr.open_dataset(abs_path, **OPEN_DS_KWARGS, mask_and_scale=False)

    for var in vars_with_mismatched_fill_missing:
        # Skip variables we've already processed
        if var in new_fill_missing:
            info(logger, f"\n{INDENT}Variable: {var} [already processed, skipping]")
            continue

        da = ds[var]
        fill = da.attrs["_FillValue"]
        missing = da.attrs["missing_value"]

        # Do any values match missing_value?
        if np.isnan(missing):
            any_missing = da.isnull().any()
        else:
            any_missing = (da == missing).any()

        # Do any values match _FillValue?
        if np.isnan(fill):
            raise RuntimeError(
                "Not sure how this will interact with _process_vars_with_nan_fills()"
            )
        any_fill = (da == fill).any()

        if any_missing and any_fill:
            msg = (
                f"Variable {var} has elements with both fill value ({fill}) "
                f"and missing value ({missing})"
            )
            error_type = (
                NotImplementedError if logger.getEffectiveLevel() <= logging.DEBUG else None
            )
            error(logger, msg, error_type=error_type)
            if not accept_all_defaults and not confirm_continue():
                raise KeyboardInterrupt
            continue

        new_missing = None
        new_fill = None
        # TODO: Replace these with proper prompts rather than just asking whether to continue
        if not any_missing:
            msg = f"{INDENT}{var}: Setting missing_value ({missing}) to match _FillValue ({fill})"
            warn(logger, msg)
            new_missing = fill
            new_fill = fill
        elif not any_fill:
            msg = f"{INDENT}{var}: Setting _FillValue ({fill}) to match missing_value ({missing})"
            warn(logger, msg)
            new_fill = missing
            new_missing = missing

        fixing = new_missing is not None
        if not fixing:
            msg = (
                f"{INDENT}WARNING: variable {var} has both _FillValue ({fill}) "
                f"and missing_value ({missing}); skipping",
            )
            error_type = (
                NotImplementedError if logger.getEffectiveLevel() <= logging.DEBUG else None
            )
            error(logger, msg, error_type=error_type)

        user_ok = accept_all_defaults or dry_run or confirm_continue()
        if not user_ok:
            raise KeyboardInterrupt

        # Save
        if fixing and not dry_run:
            # This dict will be saved as progress[abs_path]["new_fill_missing"][var]
            d = {
                "_FillValue": new_fill,
                "missing_value": new_missing,
            }

            # Handle types that aren't JSON-serializable
            for k, v in d.items():
                if isinstance(v, np.int32):
                    d[k] = int(v)

            new_fill_missing[var] = d
            try:
                progress.save()
            except TypeError as e:
                if "not JSON serializable" in str(e):
                    if logger.getEffectiveLevel() <= logging.DEBUG:
                        raise e
                    msg = (
                        f"{INDENT}WARNING: Variable {var} had fill or missing value not JSON "
                        "serializable; skipping."
                    )
                    warn(logger, msg)
                else:
                    raise e
    ds.close()


def _process_vars_with_nan_fills(
    progress: NoNanFillValueProgress,
    delete_if_none_filled: bool,
    abs_path: str,
    dry_run: bool,
    accept_all_defaults: bool,
    new_fill_values: dict,
):
    vars_with_nan_fills = progress[abs_path]["vars_with_nan_fills"]
    if not vars_with_nan_fills:
        return

    ds = xr.open_dataset(abs_path, **OPEN_DS_KWARGS)
    for var in vars_with_nan_fills:
        # Skip variables we've already processed
        if var in new_fill_values:
            info(logger, f"\n{INDENT}Variable: {var} [already processed, skipping]")
            continue

        # Process this variable to get new fill value
        var_context, config = get_var_info(var, ds, abs_path, delete_if_none_filled, dry_run)

        # If accept_all_defaults is set and a default exists, accept it automatically.
        # If no default exists, still prompt the user (don't skip).
        if accept_all_defaults and config.default_value is not None:
            new_fill_value = config.default_value
            warn(logger, f"{INDENT}Accepting default for '{var}': {new_fill_value}")
        else:
            try:
                new_fill_value = _get_fill_value_from_user(var_context, config)
            except ValueError as e:
                # Check if this is the skip variable signal
                if str(e) == ERR_STR_SKIP_VAR:
                    warn(logger, f"{INDENT}Skipping variable '{var}'")
                    continue
                # Check if this is the skip file signal
                if str(e) == ERR_STR_SKIP_FILE:
                    warn(logger, f"{INDENT}Skipping rest of file")
                    break
                # Otherwise re-raise
                error(logger, str(e), error_type=ValueError)

        if dry_run:
            continue

        # Handle new fill value (or other user input)
        new_fill_values[var] = new_fill_value

        # Save progress after each variable
        progress.save()
        progress[abs_path]["new_fill_values"] = new_fill_values
    ds.close()


def collect_new_fill_values(
    progress: NoNanFillValueProgress,
    delete_if_none_filled: bool = False,
    dry_run: bool = False,
    accept_all_defaults: bool = False,
) -> NoNanFillValueProgress:
    """
    Interactively collect new fill values for variables with NaN fill values, looping through files.

    See _collect_fill_values_one_path(), which processes individual files, for more information.

    Args:
        matches: List of tuples (relative_path, absolute_path) for files to process
        delete_if_none_filled: If True, automatically use delete when it's the default
        dry_run: If true, just print vars to process (and defaults, if any).

    Returns:
        Dictionary mapping absolute file paths to dictionaries of {variable_name: new_fill_value}
    """

    msg = (
        f"\nCommands: Type a number for fill value, '{USER_REQ_DELETE}' to delete attribute, "
        f"'{USER_REQ_SKIP_VAR}' to skip variable, '{USER_REQ_SKIP_FILE}' to skip file, "
        f"'{USER_REQ_QUIT}' to save and exit"
    )
    warn(logger, msg)

    try:
        for abs_path in progress:
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", message=".*has multiple fill values.*")
                progress = _collect_fill_values_one_path(
                    progress=progress,
                    delete_if_none_filled=delete_if_none_filled,
                    abs_path=abs_path,
                    dry_run=dry_run,
                    accept_all_defaults=accept_all_defaults,
                )

    except KeyboardInterrupt:
        warn(logger, "Exiting.")
        sys.exit(0)

    return progress
