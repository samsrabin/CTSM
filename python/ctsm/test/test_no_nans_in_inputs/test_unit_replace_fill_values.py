#!/usr/bin/env python3
"""
System tests for replace_fill_values.py script.

Tests the functionality of replacing NaN fill values in NetCDF files.
"""
# pylint: disable=protected-access,too-many-arguments,too-many-positional-arguments,

from unittest.mock import MagicMock
import pytest
import numpy as np

from ctsm.no_nans_in_inputs.replace_fill_values import _check_ok_to_process, get_output_filename
from ctsm.no_nans_in_inputs import netcdf_utils


class TestGetOutputFilename:
    """Test the get_output_filename function."""

    def test_simple_nc_file(self):
        """Test with simple .nc file."""
        result = get_output_filename("/path/to/file.nc")
        assert result == "/path/to/file.no_nan_fill.nc"

    def test_double_extension(self):
        """Test with double extension like .tar.gz."""
        result = get_output_filename("/path/to/file.tar.gz")
        assert result == "/path/to/file.tar.no_nan_fill.gz"

    def test_no_extension(self):
        """Test with file without extension."""
        result = get_output_filename("/path/to/file")
        assert result == "/path/to/file.no_nan_fill"

    def test_no_directory(self):
        """Test with filename only (no directory)."""
        result = get_output_filename("file.nc")
        assert result == "file.no_nan_fill.nc"


class TestGetNcattedTypeCode:
    """Test the _get_ncatted_type_code function."""

    def test_float64(self):
        """Test float64 dtype."""
        assert netcdf_utils._get_ncatted_type_code(np.dtype("float64")) == "d"

    def test_float32(self):
        """Test float32 dtype."""
        assert netcdf_utils._get_ncatted_type_code(np.dtype("float32")) == "f"

    def test_int64(self):
        """Test int64 dtype raises error."""
        with pytest.raises(ValueError, match="Integer dtype detected"):
            netcdf_utils._get_ncatted_type_code(np.dtype("int64"))

    def test_int32(self):
        """Test int32 dtype raises error."""
        with pytest.raises(ValueError, match="Integer dtype detected"):
            netcdf_utils._get_ncatted_type_code(np.dtype("int32"))

    def test_int16(self):
        """Test int16 dtype raises error."""
        with pytest.raises(ValueError, match="Integer dtype detected"):
            netcdf_utils._get_ncatted_type_code(np.dtype("int16"))

    def test_int8(self):
        """Test int8 dtype raises error."""
        with pytest.raises(ValueError, match="Integer dtype detected"):
            netcdf_utils._get_ncatted_type_code(np.dtype("int8"))

    def test_unknown_dtype(self):
        """Test that unknown dtype raises ValueError."""
        with pytest.raises(ValueError, match="Unknown dtype"):
            netcdf_utils._get_ncatted_type_code(np.dtype("complex128"))


class TestCheckOkToProcess:
    """Unit tests for _check_ok_to_process in replace_fill_values.py."""

    @pytest.mark.parametrize(
        "exists, writable, user_continues, expected",
        [
            (True, True, None, True),  # file exists and writable -> True
            (False, True, True, False),  # missing, user continues -> False
            (False, True, False, SystemExit),  # missing, user aborts -> SystemExit
            (True, False, True, False),  # exists but not writable, user continues -> False
            (True, False, False, SystemExit),  # exists but not writable, user aborts -> SystemExit
        ],
    )
    def test_check_ok_to_process_parametrized(
        self, monkeypatch, exists, writable, user_continues, expected
    ):
        """Parametrized tests for the various outcomes of _check_ok_to_process."""

        # Prevent error() from raising exceptions during tests
        monkeypatch.setattr(
            "ctsm.no_nans_in_inputs.replace_fill_values.error",
            lambda logger, msg, error_type=None: None,
        )

        monkeypatch.setattr("os.path.exists", lambda p: exists)
        monkeypatch.setattr(
            "ctsm.no_nans_in_inputs.replace_fill_values.check_write_access", lambda d: writable
        )

        # If user_continues is None, confirm_continue should not be called; otherwise set its return
        if user_continues is None:
            # Provide a dummy that would raise if called unexpectedly
            monkeypatch.setattr(
                "ctsm.no_nans_in_inputs.replace_fill_values.confirm_continue",
                lambda: (_ for _ in ()).throw(
                    AssertionError("confirm_continue should not be called")
                ),
            )
        else:
            monkeypatch.setattr(
                "ctsm.no_nans_in_inputs.replace_fill_values.confirm_continue",
                lambda: user_continues,
            )

        if expected is SystemExit:
            with pytest.raises(SystemExit):
                _check_ok_to_process("/some/path/file.nc")
        else:
            assert _check_ok_to_process("/some/path/file.nc") is expected

    @pytest.mark.parametrize(
        "level,expected_err_type",
        [
            (pytest.importorskip("logging").DEBUG, FileNotFoundError),
            (pytest.importorskip("logging").INFO, None),
        ],
    )
    def test_error_called_with_correct_err_type_missing(
        self, monkeypatch, level, expected_err_type
    ):
        """
        Given a missing file, ensure error() is called with the right error_type depending on log
        level.
        """

        mock_error = MagicMock()
        monkeypatch.setattr("ctsm.no_nans_in_inputs.replace_fill_values.error", mock_error)

        # monkeypatch logger.getEffectiveLevel to return desired level
        monkeypatch.setattr(
            "ctsm.no_nans_in_inputs.replace_fill_values.logger.getEffectiveLevel", lambda: level
        )

        monkeypatch.setattr("os.path.exists", lambda p: False)
        monkeypatch.setattr(
            "ctsm.no_nans_in_inputs.replace_fill_values.check_write_access", lambda d: True
        )
        # ensure confirm_continue returns True to avoid SystemExit
        monkeypatch.setattr(
            "ctsm.no_nans_in_inputs.replace_fill_values.confirm_continue", lambda: True
        )

        # Call function
        _check_ok_to_process("/some/path/missing.nc")

        # Ensure error was called at least once
        assert mock_error.call_count >= 1
        # Grab the last call's kwargs
        _, kwargs = mock_error.call_args
        # The error_type kwarg should match expected_err_type
        assert kwargs.get("error_type") is expected_err_type

    @pytest.mark.parametrize(
        "level,expected_err_type",
        [
            (pytest.importorskip("logging").DEBUG, PermissionError),
            (pytest.importorskip("logging").INFO, None),
        ],
    )
    def test_error_called_with_correct_err_type_perms(self, monkeypatch, level, expected_err_type):
        """
        Given a file in directory without write perms, ensure error() is called with the right
        error_type depending on log level.
        """

        mock_error = MagicMock()
        monkeypatch.setattr("ctsm.no_nans_in_inputs.replace_fill_values.error", mock_error)

        # monkeypatch logger.getEffectiveLevel to return desired level
        monkeypatch.setattr(
            "ctsm.no_nans_in_inputs.replace_fill_values.logger.getEffectiveLevel", lambda: level
        )

        monkeypatch.setattr("os.path.exists", lambda p: True)
        monkeypatch.setattr(
            "ctsm.no_nans_in_inputs.replace_fill_values.check_write_access", lambda d: False
        )
        monkeypatch.setattr(
            "ctsm.no_nans_in_inputs.replace_fill_values.confirm_continue", lambda: True
        )

        _check_ok_to_process("/some/path/file.nc")

        # Ensure error was called at least once
        assert mock_error.call_count >= 1
        # Grab the last call's kwargs
        _, kwargs = mock_error.call_args
        # The error_type kwarg should match expected_err_type
        assert kwargs.get("error_type") is expected_err_type
