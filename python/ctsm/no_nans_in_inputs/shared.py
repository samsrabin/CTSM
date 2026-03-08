"""Misc. shared utilities"""

import os
import sys
from dataclasses import dataclass
from typing import Any
import logging

# Add the python directory to sys.path for direct script execution
_CTSM_PYTHON = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
if _CTSM_PYTHON not in sys.path:
    sys.path.insert(1, _CTSM_PYTHON)

from ctsm.ctsm_logging import (  # pylint: disable=wrong-import-position
    error,
    info,
)
from ctsm.no_nans_in_inputs.constants import (  # pylint: disable=wrong-import-position
    INPUTDATA_PREFIX,
)

# Set up logging
logger = logging.getLogger(__name__)


@dataclass
class FillValueConfig:
    """Configuration for how the fill value prompt should behave.

    Attributes:
        _default_value: Optional default value to use if user presses enter
        allow_delete: Whether to allow deleting the fill value attribute
        delete_if_none_filled: If True, automatically use delete when it's the default
    """

    _default_value: Any = None
    allow_delete: bool = True
    delete_if_none_filled: bool = False

    def get_default_value(self):
        """Get the default value. Functionized so we can mock it in testing."""
        return self._default_value


@dataclass
class VarContext:
    """Context about the variable being processed.

    Attributes:
        var_name: Name of the variable
        target_type: Type to convert user input to (e.g., float, int)
        file_path: Optional path to the netCDF file (for ncdump on Ctrl-C)
        dry_run: If true, just print vars to process (and defaults, if any).
    """

    var_name: str
    target_type: type
    file_path: str | None = None
    dry_run: bool = False


def convert_to_absolute_path(relative_path: str) -> str:
    """
    Convert a relative path to an absolute path.

    Args:
        relative_path: Relative path starting with OUR_PATH, or already absolute path

    Returns:
        Absolute path
    """
    # If the path is already absolute, return it as-is
    if os.path.isabs(relative_path):
        return relative_path

    # Otherwise, convert relative path to absolute
    return os.path.join(INPUTDATA_PREFIX, relative_path)


def get_path_with_cesmdataroot(abs_path):
    """Given a path, replace the env var CESMDATAROOT in the string with '$CESMDATAROOT'"""
    if os.getenv("CESMDATAROOT"):
        return abs_path.replace(os.getenv("CESMDATAROOT"), "$CESMDATAROOT").replace("//", "/")
    return abs_path


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
        info(logger, f"Prompt: {prompt}")
        response = input(prompt).strip().lower()
        info(logger, f"Input: {response}")

        if response in ("", "y", "yes"):
            return True
        if response in ("n", "no"):
            return False

        error(logger, f"Please enter 'y' or 'n', not {response}.", error_type=None)
