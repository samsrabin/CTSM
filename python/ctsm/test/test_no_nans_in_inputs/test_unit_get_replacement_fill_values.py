#!/usr/bin/env python3
"""
Unit tests for get_replacement_fill_values.py script.
"""
# pylint: disable=too-many-arguments,too-many-positional-arguments,too-few-public-methods

import os
from unittest.mock import MagicMock, patch

import pytest

from ctsm.no_nans_in_inputs import namelist_utils
from ctsm.no_nans_in_inputs.get_replacement_fill_values import main, _get_netcdf_files_to_check
from ctsm.no_nans_in_inputs import get_replacement_fill_values


class TestCtsmRoot:
    """Test the --ctsm-root argument"""

    @patch(
        "ctsm.no_nans_in_inputs.get_replacement_fill_values._get_netcdf_files_to_check",
        wraps=_get_netcdf_files_to_check,
    )
    @patch("ctsm.no_nans_in_inputs.get_replacement_fill_values._get_netcdfs_with_nan_fills")
    @patch("ctsm.no_nans_in_inputs.json_io.NoNanFillValueProgress.print_summary")
    @patch("ctsm.no_nans_in_inputs.shared.confirm_continue")
    @patch("ctsm.no_nans_in_inputs.user_inputs.collect_new_fill_values")
    def test_ctsm_root_arg(
        self,
        mock_collect_new_fill_values,
        mock_confirm_continue,
        mock_print_summary_before_collecting,
        mock_get_netcdfs_with_nan_fills,
        mock_get_netcdf_files_to_check,
        monkeypatch,
    ):
        """
        Test that --ctsm-root is used where we expect (i.e., _get_netcdf_files_to_check()) by
        ensuring that that function throws an error if given nonexistent --ctsm-root.
        """
        nonexistent_ctsm_root = "/mwernerberbun"
        assert os.path.isabs(nonexistent_ctsm_root)
        assert not os.path.exists(nonexistent_ctsm_root)

        # Make sure we have a relative XML path so that ctsm_root will be prepended
        monkeypatch.setattr(get_replacement_fill_values, "DIR_TO_SEARCH_FOR_XML_FILES", "rel/path")

        # Make sure a FileNotFoundError is thrown given that nonexistent --ctsm-root
        with patch(
            "sys.argv", ["get_replacement_fill_values", "--ctsm-root", nonexistent_ctsm_root]
        ):
            with pytest.raises(FileNotFoundError, match=nonexistent_ctsm_root):
                main()

        # Make sure _get_netcdf_files_to_check() was called with our nonexistent ctsm_root as either
        # a positional or a keyword argument.
        args, kwargs = mock_get_netcdf_files_to_check.call_args
        try:
            assert nonexistent_ctsm_root in args
        except Exception:  # pylint: disable=broad-exception-caught
            assert ("ctsm_root", nonexistent_ctsm_root) in kwargs.items()

        # Make sure that the functions following _get_netcdf_files_to_check() weren't called
        mock_collect_new_fill_values.assert_not_called()
        mock_confirm_continue.assert_not_called()
        mock_print_summary_before_collecting.assert_not_called()
        mock_get_netcdfs_with_nan_fills.assert_not_called()


class TestHowNetcdfIsReferencedInFile:
    """Tests of how_netcdf_is_referenced_in_file()."""

    def return_input(self, x):
        """Take one input argument and return it"""
        return x

    @pytest.fixture(autouse=True)
    def mock_convert_to_absolute_path(self, monkeypatch):
        """Mock convert_to_absolute_path() to just return what it was given"""
        mock = MagicMock(side_effect=lambda x, *args, **kwargs: x)
        monkeypatch.setattr(namelist_utils, "convert_to_absolute_path", mock)
        return mock

    @pytest.fixture(autouse=True)
    def mock_replace_env_vars_in_netcdf_paths(self, monkeypatch):
        """Mock _replace_env_vars_in_netcdf_paths() to just return what it was given"""
        mock = MagicMock(side_effect=lambda x, *args, **kwargs: x)
        monkeypatch.setattr(namelist_utils, "_replace_env_vars_in_netcdf_paths", mock)
        return mock

    def test_how_netcdf_is_referenced_in_file_1found_once(
        self, monkeypatch, mock_convert_to_absolute_path, mock_replace_env_vars_in_netcdf_paths
    ):
        """Test how_netcdf_is_referenced_in_file() for one netCDF file present once in text file"""
        nc_file = "file.nc"
        monkeypatch.setattr(
            namelist_utils,
            "extract_file_paths_from_file",
            lambda *args, **kwargs: [nc_file],
        )
        set_of_how_this_netcdf_appears = namelist_utils.how_netcdf_is_referenced_in_file(
            "dummy", nc_file
        )
        assert mock_convert_to_absolute_path.call_count == 2
        assert mock_replace_env_vars_in_netcdf_paths.call_count == 1
        assert set_of_how_this_netcdf_appears == {nc_file}

    def test_how_netcdf_is_referenced_in_file_1found_twice_same(
        self, monkeypatch, mock_convert_to_absolute_path, mock_replace_env_vars_in_netcdf_paths
    ):
        """
        Test how_netcdf_is_referenced_in_file() for one netCDF file present twice in text file in
        the exact same way
        """
        nc_file = "file.nc"
        monkeypatch.setattr(
            namelist_utils,
            "extract_file_paths_from_file",
            lambda *args, **kwargs: [nc_file, nc_file],
        )
        set_of_how_this_netcdf_appears = namelist_utils.how_netcdf_is_referenced_in_file(
            "dummy", nc_file
        )
        assert mock_convert_to_absolute_path.call_count == 3
        assert mock_replace_env_vars_in_netcdf_paths.call_count == 2
        assert set_of_how_this_netcdf_appears == {nc_file}

    def test_how_netcdf_is_referenced_in_file_1found_twice_diff(
        self, monkeypatch, mock_convert_to_absolute_path, mock_replace_env_vars_in_netcdf_paths
    ):
        """
        Test how_netcdf_is_referenced_in_file() for one netCDF file present twice in text file in
        different ways
        """
        nc_file = "file.nc"
        nc_file2 = "abc123" + nc_file
        monkeypatch.setattr(
            namelist_utils,
            "extract_file_paths_from_file",
            lambda *args, **kwargs: [nc_file, nc_file2],
        )
        set_of_how_this_netcdf_appears = namelist_utils.how_netcdf_is_referenced_in_file(
            "dummy", nc_file
        )
        assert mock_convert_to_absolute_path.call_count == 3
        assert mock_replace_env_vars_in_netcdf_paths.call_count == 2
        assert set_of_how_this_netcdf_appears == {nc_file}

    def test_how_netcdf_is_referenced_in_file_2found(
        self, monkeypatch, mock_convert_to_absolute_path, mock_replace_env_vars_in_netcdf_paths
    ):
        """Test how_netcdf_is_referenced_in_file() for two netCDF files present in text file"""
        nc_file = "file.nc"
        nc_files = [nc_file, "file2.nc"]
        monkeypatch.setattr(
            namelist_utils,
            "extract_file_paths_from_file",
            lambda *args, **kwargs: nc_files,
        )
        set_of_how_this_netcdf_appears = namelist_utils.how_netcdf_is_referenced_in_file(
            "dummy", nc_file
        )
        assert mock_convert_to_absolute_path.call_count == 3
        assert mock_replace_env_vars_in_netcdf_paths.call_count == 2
        assert set_of_how_this_netcdf_appears == {nc_file}
