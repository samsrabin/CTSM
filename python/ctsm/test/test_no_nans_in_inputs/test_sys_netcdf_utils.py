"""System tests of netcdf_utils (anything touching filesystem)"""

# pylint: disable=too-few-public-methods

import os
from unittest import mock
import logging

import pytest
import numpy as np
import xarray as xr
from netCDF4 import Dataset  # pylint: disable=no-name-in-module

from ctsm.no_nans_in_inputs.constants import (
    ATTR,
    OPEN_DS_KWARGS,
    USER_REQ_DELETE,
    VARSTARTS_TO_DEFAULT_NEG999,
)
from ctsm.no_nans_in_inputs.netcdf_utils import (
    _build_ncatted_command,
    build_nco_commands,
    _execute_nco_command,
    get_var_info,
    get_vars_with_nan_fills,
    show_ncdump_for_variable,
    var_data_has_nan,
    var_has_nan_without_fill,
)

# Test constants
TEST_VAR_TEMP = "temp"
TEST_VAR_PRESSURE = "pressure"
TEST_OUTPUT_FILE = "output.nc"
TEST_FILL_VALUE = -123.4
NCATTED_CMD = "ncatted"
NCATTED_FLAG = "-a"
TEST_VAR_NAME = "test_var"


class TestGetVarsWithNanFills:
    """Test the get_vars_with_nan_fills function."""

    @pytest.mark.parametrize(
        "fill_value, expected",
        [
            (np.float32(np.nan), True),
            (np.float64(np.nan), True),
            (np.float32(-999.0), False),
            (np.int32(-999), False),
            (None, False),
        ],
    )
    def test_fill_value_detection(self, tmp_path, fill_value, expected):
        """Test that get_vars_with_nan_fills correctly detects NaN/non-NaN/absent fill values."""
        test_file = tmp_path / "test.nc"
        var_name = "temp"
        dtype = np.float32 if fill_value is None else type(fill_value)
        ds = xr.Dataset(
            {
                var_name: xr.DataArray(
                    np.array([1, 2], dtype=dtype),
                    dims=["time"],
                ),
            }
        )
        # Use encoding to set (or suppress) the _FillValue
        encoding = {var_name: {ATTR: fill_value}}
        ds.to_netcdf(str(test_file), encoding=encoding)
        vars_with_nan_fills = get_vars_with_nan_fills(str(test_file))
        assert (var_name in vars_with_nan_fills) == expected


class TestShowNcdumpForVariable:
    """Test the show_ncdump_for_variable function."""

    TEST_VAR = "temp"

    @pytest.fixture
    def test_netcdf_file(self, tmp_path):
        """Create a temporary NetCDF file for testing."""
        test_file = tmp_path / "test.nc"
        ds = xr.Dataset(
            {
                self.TEST_VAR: xr.DataArray(
                    np.array([1.0, 2.0, 3.0], dtype=np.float32),
                    dims=["time"],
                    attrs={ATTR: np.float32(np.nan), "long_name": "temperature"},
                ),
            }
        )
        ds.to_netcdf(str(test_file))
        ds.close()
        return str(test_file)

    def test_prints_matching_lines(self, test_netcdf_file, caplog):
        """Test that matching lines from ncdump are printed."""
        with caplog.at_level(logging.DEBUG):
            show_ncdump_for_variable(test_netcdf_file, self.TEST_VAR)
        assert self.TEST_VAR in caplog.text
        assert "Lines matching" in caplog.text

    def test_prints_no_match_message(self, test_netcdf_file, caplog):
        """Test that a message is printed when no lines match."""
        with caplog.at_level(logging.DEBUG):
            show_ncdump_for_variable(test_netcdf_file, "nonexistent_var")
        assert "No lines found matching" in caplog.text

    def test_none_file_path(self, caplog):
        """Test that None file path prints a message and returns."""
        with caplog.at_level(logging.DEBUG):
            show_ncdump_for_variable(None, self.TEST_VAR)
        assert "No file path available" in caplog.text

    def test_nonexistent_file(self, caplog):
        """Test that a nonexistent file prints an error."""
        with caplog.at_level(logging.DEBUG):
            show_ncdump_for_variable("/nonexistent/file.nc", self.TEST_VAR)
        assert "Error running ncdump" in caplog.text


class TestGetVarInfo:
    """Test the get_var_info function."""

    @staticmethod
    def _create_test_dataset(data, var_name, long_name, units):
        """Helper to create a test dataset."""
        return xr.Dataset(
            {var_name: (("y", "x"), data)},
            attrs={"long_name": long_name, "units": units},
        )

    @pytest.mark.parametrize("dry_run", [False, True])
    def test_no_nan_in_data_suggests_delete(self, dry_run):
        """If data has no NaNs, default suggestion should be to delete the attribute."""
        data = np.array([[1.0, 2.0], [3.0, 4.0]])
        ds = self._create_test_dataset(data, TEST_VAR_NAME, "Test Variable", "test_units")
        _, config = get_var_info(
            TEST_VAR_NAME, ds, "/path/to/file", delete_if_none_filled=False, dry_run=dry_run
        )
        assert config.default_value == USER_REQ_DELETE
        assert config.allow_delete is True

    @pytest.mark.parametrize("dry_run", [False, True])
    def test_nan_in_data_prevents_delete(self, dry_run):
        """If data has NaNs, deleting the attribute should not be allowed."""
        data = np.array([[1.0, 2.0], [np.nan, 4.0]])
        ds = self._create_test_dataset(data, TEST_VAR_NAME, "Test Variable", "test_units")
        _, config = get_var_info(
            TEST_VAR_NAME, ds, "/path/to/file", delete_if_none_filled=False, dry_run=dry_run
        )
        assert config.default_value != USER_REQ_DELETE
        assert config.allow_delete is False

    @pytest.mark.parametrize("data_min", [10.0, 0.0, -1.0])
    def test_defaults_to_neg999_due_to_min(self, data_min):
        """For some minimum values, default should be -999."""
        data = np.array([[data_min, 20.0], [np.nan, 40.0]])
        ds = self._create_test_dataset(data, TEST_VAR_NAME, "Test Variable", "test_units")
        _, config = get_var_info(
            TEST_VAR_NAME, ds, "/path/to/file", delete_if_none_filled=False, dry_run=False
        )
        assert config.default_value == -999

    def test_special_varname_prefix_defaults_to_neg999(self):
        """Test if var name starts with special prefix like 'fertl_', default is -999."""
        var_name = VARSTARTS_TO_DEFAULT_NEG999[0] + "weuuewriebr"
        data = np.array([[-50.0, 20.0], [np.nan, 40.0]])
        ds = self._create_test_dataset(data, var_name, "Fertilizer", "g/m2")
        _, config = get_var_info(
            var_name, ds, "/path/to/file", delete_if_none_filled=False, dry_run=False
        )
        assert config.default_value == -999

    @pytest.mark.parametrize(
        "abs_path, expected",
        [
            ("/some/path/surfdata_map/file.nc", -999),
            ("/some/path/surfdata_map.nc", None),
        ],
    )
    def test_surfdata_map_defaults_to_neg999(self, abs_path, expected):
        """Test that a variable in a surfdata_map dir defaults to -999."""
        var_name = "grid1_to_grid2"
        data = np.array([[-50.0, 20.0], [np.nan, 40.0]])
        ds = self._create_test_dataset(data, var_name, "Mapping", "none")
        _, config = get_var_info(var_name, ds, abs_path, delete_if_none_filled=False, dry_run=False)
        assert config.default_value == expected

    @pytest.mark.parametrize("dry_run", [False, True])
    def test_no_special_case_no_default(self, dry_run):
        """If no special condition is met, there should be no default value."""
        data = np.array([[-50.0, -20.0], [np.nan, -10.0]])
        ds = self._create_test_dataset(data, TEST_VAR_NAME, "Test Variable", "test_units")
        _, config = get_var_info(
            TEST_VAR_NAME, ds, "/path/to/file", delete_if_none_filled=False, dry_run=dry_run
        )
        assert config.default_value is None

    def test_returns_correct_var_context(self):
        """Ensure VarContext is returned with correct info."""
        data = np.array([[1.0, 2.0]], dtype=np.float32)
        ds = self._create_test_dataset(data, TEST_VAR_NAME, "Test Variable", "test_units")
        file_path = "/path/to/file.nc"
        var_context, _ = get_var_info(
            TEST_VAR_NAME, ds, file_path, delete_if_none_filled=False, dry_run=False
        )
        assert var_context.var_name == TEST_VAR_NAME
        assert var_context.target_type == float
        assert var_context.file_path == file_path


class TestVarDataHasNan:
    """Test the var_data_has_nan function."""

    def test_true_when_nan_present(self):
        """Test detection of NaN values."""
        da = xr.DataArray([[1.0, 2.0], [np.nan, 4.0]])
        assert var_data_has_nan(da)

    def test_false_when_no_nan(self):
        """Test correct response for arrays without NaN values."""
        da = xr.DataArray([1.0, 2.0, 3.0, 4.0])
        assert not var_data_has_nan(da)

    def test_true_when_all_nan(self):
        """Test that arrays with all NaN values are detected."""
        da = xr.DataArray([np.nan, np.nan, np.nan])
        assert var_data_has_nan(da)

    def test_false_for_empty_array(self):
        """Test that empty arrays return False (no NaNs)."""
        da = xr.DataArray([])
        assert not var_data_has_nan(da)


class TestVarHasNanWithoutFill:
    """Tests for var_has_nan_without_fill covering simple and slicing branches."""

    def test_simple_detects_nan_and_no_nan(self):
        """Small xarray DataArray: detect NaN and no-NaN correctly"""
        da_with_nan = xr.DataArray(np.array([1.0, np.nan]))
        assert var_has_nan_without_fill(da_with_nan, dims_to_slice_over=None)

        da_no_nan = xr.DataArray(np.array([0.0, 2.0, 3.0]))
        assert not var_has_nan_without_fill(da_no_nan, dims_to_slice_over=None)

    def test_returns_false_nan_fillvalue_but_no_filled(self):
        """Returns False if variable has NaN _FillValue but no filled elements"""
        da = xr.DataArray(np.array([1.0, 2.0]), attrs={"_FillValue": np.nan})
        assert not var_has_nan_without_fill(da, dims_to_slice_over=None)

    def test_returns_false_nan_fillvalue_and_filled(self):
        """Returns False if variable has NaN _FillValue and some filled elements"""
        da = xr.DataArray(
            np.array([np.nan, 2.0, 3.0], dtype=np.float32),
            dims=["time"],
            attrs={ATTR: np.float32(np.nan)},
        )
        assert not var_has_nan_without_fill(da, dims_to_slice_over=None)

    class _SmallFakeDataArray:
        """Small fake DataArray used as the result of isel() on a big array.

        Implements the minimal interface used by var_has_nan_without_fill.
        """

        def __init__(self, has_null: bool):
            self.size = 1
            self.dims = ()
            self.sizes = {}
            self._has_null = bool(has_null)

        def isel(self, _indexers, drop=True):
            return self

        def isnull(self):
            class _Any:
                def __init__(self, val):
                    self._val = val

                def any(self):
                    return self._val

            return _Any(self._has_null)

    class _BigFakeDataArray:
        """Fake DataArray that simulates a very large array and slices into smaller
        pieces. The constructor takes a list of booleans indicating whether each
        slice contains a NaN.
        """

        def __init__(self, dim_name: str, sizes: dict, slice_nulls: list[bool]):
            self.dims = (dim_name,)
            self.sizes = dict(sizes)
            # Keep slice null indicators; size will be provided via a property
            self._slice_nulls = list(slice_nulls)

        @property
        def size(self):
            # Simulate a very large array by returning a large size when accessed
            return int(1e8) + 1

        def isel(self, indexers, drop=True):
            # indexers looks like {dim_name: idx}
            dim, idx = next(iter(indexers.items()))
            has_null = bool(self._slice_nulls[int(idx)])
            return TestVarHasNanWithoutFill._SmallFakeDataArray(has_null)

        def isnull(self):
            any_null = any(self._slice_nulls)

            class _Any:
                def __init__(self, val):
                    self._val = val

                def any(self):
                    return self._val

            return _Any(any_null)

    def test_slicing_branch_detects_nan_and_no_nan(self):
        """Simulate the large-size slicing path: one case where a slice contains a
        NaN (should return True), and one case where no slices have NaNs (should
        return False).
        """
        big_with_nan = self._BigFakeDataArray("x", {"x": 3}, [False, True, False])
        assert var_has_nan_without_fill(big_with_nan, dims_to_slice_over=["x"]) is True

        big_no_nan = self._BigFakeDataArray("x", {"x": 3}, [False, False, False])
        assert var_has_nan_without_fill(big_no_nan, dims_to_slice_over=["x"]) is False

    def test_multi_dims_slicing(self):
        """Test when dims_to_slice_over has multiple items and the first dim is
        present in the DataArray: the function should slice over the first dim
        and recursively evaluate the remaining dims (which for our fake slices
        reduces to checking the slice's isnull()).
        """
        # Two slices, second slice contains a NaN; dims_to_slice_over has two items
        big_multi_with_nan = self._BigFakeDataArray("x", {"x": 2}, [False, True])
        assert var_has_nan_without_fill(big_multi_with_nan, dims_to_slice_over=["x", "y"]) is True

        # Two slices, none have NaN
        big_multi_no_nan = self._BigFakeDataArray("x", {"x": 2}, [False, False])
        assert var_has_nan_without_fill(big_multi_no_nan, dims_to_slice_over=["x", "y"]) is False

    def test_break_stops_iteration(self):
        """If the first slice contains a NaN, the function should break and not
        call isel() for subsequent indices.
        """
        calls = []

        class TrackingBig:
            def __init__(self, dim_name: str, sizes: dict, slice_nulls: list[bool]):
                self.dims = (dim_name,)
                self.sizes = dict(sizes)
                self._slice_nulls = list(slice_nulls)

            @property
            def size(self):
                return int(1e8) + 1

            def isel(self, indexers, drop=True):
                dim, idx = next(iter(indexers.items()))
                idx = int(idx)
                calls.append(idx)
                # Return a small fake slice that reports True only for idx == 0.
                if idx == 0:
                    return TestVarHasNanWithoutFill._SmallFakeDataArray(True)
                # If we ever get here, the function didn't break as expected
                raise RuntimeError("isel called for idx>0; break did not occur")

            def isnull(self):
                # Fallback: report whether any slice would have a null
                return TestVarHasNanWithoutFill._SmallFakeDataArray(any(self._slice_nulls)).isnull()

        tb = TrackingBig("x", {"x": 3}, [True, True, True])
        res = var_has_nan_without_fill(tb, dims_to_slice_over=["x"])
        assert res is True
        assert calls == [0]

    def test_continues_until_true(self):
        """Ensure the function continues scanning when early slices are False and
        a later slice is True (i.e., it doesn't prematurely return False).
        """
        calls = []

        class ContinueBig:
            def __init__(self, dim_name: str, sizes: dict, slice_nulls: list[bool]):
                self.dims = (dim_name,)
                self.sizes = dict(sizes)
                self._slice_nulls = list(slice_nulls)

            @property
            def size(self):
                return int(1e8) + 1

            def isel(self, indexers, drop=True):
                dim, idx = next(iter(indexers.items()))
                idx = int(idx)
                calls.append(idx)
                # Return small fake slice: True only for idx == 2
                return TestVarHasNanWithoutFill._SmallFakeDataArray(idx == 2)

            def isnull(self):
                return TestVarHasNanWithoutFill._SmallFakeDataArray(any(self._slice_nulls)).isnull()

        cb = ContinueBig("x", {"x": 3}, [False, False, True])
        res = var_has_nan_without_fill(cb, dims_to_slice_over=["x"])
        assert res is True
        assert calls == [0, 1, 2]

    def test_multi_dims_first_missing_falls_back_to_isnull(self):
        """When the first dim in dims_to_slice_over is not present in da.dims,
        the function should fall back to da.isnull().any() rather than trying
        to slice or recurse.
        """

        class MissingDimBig:
            def __init__(self, dim_name: str, sizes: dict, has_null: bool):
                # Provide a different dim name so the first requested dim is missing
                self.dims = (dim_name,)
                self.sizes = dict(sizes)
                self._has_null = bool(has_null)

            @property
            def size(self):
                return int(1e8) + 1

            def isel(self, indexers, drop=True):
                # Should not be called in this path
                raise RuntimeError("isel should not be called when first dim is missing")

            def isnull(self):
                class _Any:
                    def __init__(self, val):
                        self._val = val

                    def any(self):
                        return self._val

                return _Any(self._has_null)

        # dims_to_slice_over asks to slice over 'missing_dim' then 'x'; our object
        # only has 'x' and reports True/False via isnull().any()
        mb_true = MissingDimBig("x", {"x": 3}, True)
        assert var_has_nan_without_fill(mb_true, dims_to_slice_over=["missing_dim", "x"]) is True

        mb_false = MissingDimBig("x", {"x": 3}, False)
        assert var_has_nan_without_fill(mb_false, dims_to_slice_over=["missing_dim", "x"]) is False


class TestBuildNcattedCommand:
    """Test the _build_ncatted_command function."""

    @pytest.fixture
    def test_netcdf_file(self, tmp_path):
        """Create a temporary NetCDF file for testing."""
        test_file = tmp_path / "test.nc"

        # Create a simple NetCDF file with float variables that have NaN fill values
        # (NetCDF doesn't allow NaN for integer types, and our scripts only work on
        # variables that already have NaN fill values)
        ds = xr.Dataset(
            {
                TEST_VAR_TEMP: xr.DataArray(
                    np.array([1.0, 2.0, 3.0], dtype=np.float32),
                    dims=["time"],
                    attrs={ATTR: np.float32(np.nan)},
                ),
                TEST_VAR_PRESSURE: xr.DataArray(
                    np.array([1000.0, 1010.0, 1020.0], dtype=np.float64),
                    dims=["time"],
                    attrs={ATTR: np.float64(np.nan)},
                ),
            }
        )
        ds.to_netcdf(str(test_file))
        ds.close()

        yield str(test_file)

    def test_delete_attribute(self, test_netcdf_file):
        """Test building command to delete an attribute."""
        var_fillvalues = {TEST_VAR_TEMP: USER_REQ_DELETE}
        cmd = _build_ncatted_command(test_netcdf_file, TEST_OUTPUT_FILE, var_fillvalues, var_fillmissing={})

        assert NCATTED_CMD in cmd
        assert NCATTED_FLAG in cmd
        assert f"{ATTR},{TEST_VAR_TEMP},d,," in cmd
        assert test_netcdf_file in cmd
        assert TEST_OUTPUT_FILE in cmd

    def test_modify_float_attribute(self, test_netcdf_file):
        """Test building command to modify a float attribute."""
        var_fillvalues = {TEST_VAR_TEMP: TEST_FILL_VALUE}
        cmd = _build_ncatted_command(test_netcdf_file, TEST_OUTPUT_FILE, var_fillvalues, var_fillmissing={})

        assert NCATTED_CMD in cmd
        assert NCATTED_FLAG in cmd
        # Should use 'f' for float32
        assert f"{ATTR},{TEST_VAR_TEMP},o,f,{TEST_FILL_VALUE}" in cmd

    def test_modify_double_attribute(self, test_netcdf_file):
        """Test building command to modify a double (float64) attribute."""
        var_fillvalues = {TEST_VAR_PRESSURE: TEST_FILL_VALUE}
        cmd = _build_ncatted_command(test_netcdf_file, TEST_OUTPUT_FILE, var_fillvalues, var_fillmissing={})

        assert NCATTED_CMD in cmd
        assert NCATTED_FLAG in cmd
        # Should use 'd' for float64
        assert f"{ATTR},{TEST_VAR_PRESSURE},o,d,{TEST_FILL_VALUE}" in cmd

    def test_multiple_variables(self, test_netcdf_file):
        """Test building command with multiple variables."""
        var_fillvalues = {TEST_VAR_TEMP: TEST_FILL_VALUE, TEST_VAR_PRESSURE: USER_REQ_DELETE}
        cmd = _build_ncatted_command(test_netcdf_file, TEST_OUTPUT_FILE, var_fillvalues, var_fillmissing={})

        # Should have two -a flags
        assert cmd.count(NCATTED_FLAG) == 2
        assert f"{ATTR},{TEST_VAR_TEMP},o,f,{TEST_FILL_VALUE}" in cmd
        assert f"{ATTR},{TEST_VAR_PRESSURE},d,," in cmd

    def test_variable_not_found(self, test_netcdf_file):
        """Test that missing variable raises ValueError."""
        var_fillvalues = {"nonexistent_var": TEST_FILL_VALUE}
        with pytest.raises(ValueError, match="not found"):
            _build_ncatted_command(test_netcdf_file, TEST_OUTPUT_FILE, var_fillvalues, var_fillmissing={})

    def test_same_input_output(self, test_netcdf_file):
        """Test that same input and output files raises ValueError."""
        var_fillvalues = {TEST_VAR_TEMP: TEST_FILL_VALUE}
        with pytest.raises(ValueError, match="Input and output files are the same"):
            build_nco_commands(test_netcdf_file, test_netcdf_file, var_fillvalues, var_fillmissing={})

    def test_output_already_exists(self, test_netcdf_file, tmp_path):
        """Test that existing output file is detected."""
        # Create an output file that already exists
        output_file = tmp_path / "output.nc"
        output_file.write_text("dummy content")

        # The function should still build the command (skip logic is in main())
        # but we can verify the output file exists
        assert os.path.exists(str(output_file))

        # Building command should still work - skip logic is in main()
        var_fillvalues = {TEST_VAR_TEMP: TEST_FILL_VALUE}
        cmd = _build_ncatted_command(test_netcdf_file, str(output_file), var_fillvalues, var_fillmissing={})
        assert NCATTED_CMD in cmd


class TestExecuteCommand:
    """Test the _execute_nco_command function."""

    @pytest.fixture(name="create_test_nc")
    def fixture_create_test_nc(self, tmp_path):
        """
        Factory fixture to create a test netCDF file with given or default parameters

        Returns:
            A function that creates the test netCDF file and returns its path.
        """

        def _create(
            *, netcdf_format: str = "NETCDF4_CLASSIC", first_value: np.float32 = 1.0
        ) -> str:
            test_nc = str(tmp_path / "test_input.nc")
            nan_fill = np.float32(np.nan)
            ds = xr.Dataset(
                {
                    TEST_VAR_TEMP: xr.DataArray(
                        np.array([first_value, 2.0, 3.0], dtype=np.float32),
                        dims=["time"],
                    ),
                }
            )
            ds.to_netcdf(test_nc, format=netcdf_format, encoding={TEST_VAR_TEMP: {ATTR: nan_fill}})
            ds.close()

            # Check fill value
            ds = xr.open_dataset(test_nc, mask_and_scale=True, **OPEN_DS_KWARGS)
            assert ATTR in ds[TEST_VAR_TEMP].encoding
            assert np.isnan(ds[TEST_VAR_TEMP].encoding[ATTR])
            ds.close()

            return test_nc

        return _create

    @pytest.fixture(name="mock_update_xml_file", autouse=True)
    def fixture_mock_update_xml_file(self):
        """Every test in this class will have _update_xml_file() mocked; that's tested elsewhere"""
        with mock.patch("ctsm.no_nans_in_inputs.namelist_utils._update_xml_file") as _fixture:
            yield _fixture

    @pytest.mark.parametrize(
        "netcdf_format",
        [
            "NETCDF4",
            "NETCDF4_CLASSIC",
            "NETCDF3_CLASSIC",
        ],
    )
    def test_execute_preserves_format(self, tmp_path, create_test_nc, netcdf_format):
        """Test _execute_nco_command preserves NetCDF format from input to output."""
        # Create input file with specified format
        input_file = create_test_nc(netcdf_format=netcdf_format)

        # Build and execute the command without XML update (because we're not testing that here)
        output_file = str(tmp_path / "test_output.nc")
        var_fillvalues = {TEST_VAR_TEMP: TEST_FILL_VALUE}
        cmd = _build_ncatted_command(input_file, output_file, var_fillvalues, var_fillmissing={})
        files_processed = _execute_nco_command(cmd)

        # Should have processed 1 file
        assert files_processed == 1

        # Output file should exist
        assert os.path.exists(output_file)

        # Verify the output file is valid NetCDF with correct fill value
        ds_out = xr.open_dataset(
            output_file,
            **OPEN_DS_KWARGS,
        )
        assert TEST_VAR_TEMP in ds_out
        assert ATTR in ds_out[TEST_VAR_TEMP].encoding
        assert ds_out[TEST_VAR_TEMP].encoding[ATTR] == TEST_FILL_VALUE
        ds_out.close()

        # Verify formats match
        with Dataset(input_file, "r") as nc_in:
            input_format = nc_in.data_model
        with Dataset(output_file, "r") as nc_out:
            output_format = nc_out.data_model
        assert output_format == input_format
        assert output_format == netcdf_format

    @pytest.mark.parametrize(
        "first_value, expect_filled",
        [
            (np.nan, True),
            (TEST_FILL_VALUE, True),
            (150, False),
            (7.24, False),
        ],
    )
    def test_execute_different_data(self, tmp_path, create_test_nc, first_value, expect_filled):
        """Test _execute_nco_command with different data values."""
        # Create input file with specified value first
        input_file = create_test_nc(first_value=first_value)

        # Build and execute the command without XML update (because we're not testing that here)
        output_file = str(tmp_path / "test_output.nc")
        var_fillvalues = {TEST_VAR_TEMP: TEST_FILL_VALUE}
        cmd = _build_ncatted_command(input_file, output_file, var_fillvalues, var_fillmissing={})
        _execute_nco_command(cmd)

        # Verify the output file is valid NetCDF with correct fill value. mask_and_scale True means
        # that the variable's DataArray's _FillValue attribute will be populated and any filled
        # values will be NaN.
        assert os.path.exists(output_file)
        ds_out = xr.open_dataset(output_file, mask_and_scale=True, **OPEN_DS_KWARGS)
        assert TEST_VAR_TEMP in ds_out
        assert ATTR in ds_out[TEST_VAR_TEMP].encoding
        assert ds_out[TEST_VAR_TEMP].encoding[ATTR] == TEST_FILL_VALUE

        # If we used a value we expect to be filled, then...
        if expect_filled:
            # It should be NaN after reading with mask_and_scale True
            assert np.isnan(ds_out[TEST_VAR_TEMP].values[0]), str(ds_out[TEST_VAR_TEMP].values)
            # It should be the fill value after reading with mask_and_scale False
            ds_out_no_ms = xr.open_dataset(output_file, mask_and_scale=False, **OPEN_DS_KWARGS)
            assert ds_out_no_ms[TEST_VAR_TEMP].values[0] == TEST_FILL_VALUE
            ds_out_no_ms.close()
        # Otherwise, we expect it to be unchanged
        else:
            assert ds_out[TEST_VAR_TEMP].values[0] == first_value

        ds_out.close()
