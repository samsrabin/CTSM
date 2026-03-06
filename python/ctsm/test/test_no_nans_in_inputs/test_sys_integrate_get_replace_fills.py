"""
Tests of the integrated get_replacement_fill_values.py -> replace_fill_values.py pipeline
"""

import os
from unittest.mock import patch
import xml.etree.ElementTree as ET

import pytest
import numpy as np
import xarray as xr

from ctsm.netcdf_utils import get_netcdf_format
from ctsm.no_nans_in_inputs.constants import (
    FILL_ATTR,
    OPEN_DS_KWARGS,
    USER_REQ_DELETE,
)
from ctsm.no_nans_in_inputs import get_replacement_fill_values
from ctsm.no_nans_in_inputs.replace_fill_values import main as replace_fill_values
from ctsm.no_nans_in_inputs.replace_fill_values import get_output_filename
from ctsm.no_nans_in_inputs.json_io import NoNanFillValueProgress

# Test constants
TEST_VAR_TEMP = "temp"
TEST_VAR_PRESSURE = "pressure"
TEST_OUTPUT_FILE = "output.nc"
TEST_FILL_VALUE = -123.4


@pytest.fixture(name="test_netcdf_file_nan_nanfill")
def fixture_test_netcdf_file_nan_nanfill(tmp_path):
    """Create a temporary NetCDF file with filled values, NaN fill"""

    def _create(nc_format: str):
        test_file = tmp_path / "lnd" / "clm2" / "test.nc"
        os.makedirs(os.path.dirname(str(test_file)))

        # Create a simple NetCDF file with float variables that have NaN fill values
        # (NetCDF doesn't allow NaN for integer types, and our scripts only work on
        # variables that already have NaN fill values)
        ds = xr.Dataset(
            {
                TEST_VAR_TEMP: xr.DataArray(
                    np.array([np.nan, 2.0, 3.0], dtype=np.float32),
                    dims=["time"],
                ),
                TEST_VAR_PRESSURE: xr.DataArray(
                    np.array([1000.0, 1010.0, 1020.0], dtype=np.float64),
                    dims=["time"],
                ),
            }
        )
        encoding = {}
        for v in ds:
            encoding[v] = {FILL_ATTR: type(ds[v].values[0])(np.nan)}
        ds.to_netcdf(str(test_file), format=nc_format, encoding=encoding)
        ds.close()
        return str(test_file)

    return _create


@pytest.fixture(name="test_netcdf_file_nan_nofill")
def fixture_test_netcdf_file_nan_nofill(tmp_path):
    """Create a temporary NetCDF file with NaN values, no fill"""

    def _create(nc_format: str):
        test_file = tmp_path / "lnd" / "clm2" / "test.nc"
        os.makedirs(os.path.dirname(str(test_file)))

        # Create a simple NetCDF file with float variables that have NaN fill values
        # (NetCDF doesn't allow NaN for integer types, and our scripts only work on
        # variables that already have NaN fill values)
        ds = xr.Dataset(
            {
                TEST_VAR_TEMP: xr.DataArray(
                    np.array([np.nan, 2.0, 3.0], dtype=np.float32),
                    dims=["time"],
                ),
                TEST_VAR_PRESSURE: xr.DataArray(
                    np.array([1000.0, 1010.0, 1020.0], dtype=np.float64),
                    dims=["time"],
                ),
            }
        )
        encoding = {}
        for v in ds:
            encoding[v] = {FILL_ATTR: None}
        ds.to_netcdf(str(test_file), encoding=encoding, format=nc_format)
        ds.close()

        return str(test_file)

    return _create


@pytest.mark.parametrize(
    "abs_or_rel, nc_format",
    [
        ("abs", "NETCDF4"),
        ("rel", "NETCDF4"),
        ("abs", "NETCDF4_CLASSIC"),
        ("abs", "NETCDF3_64BIT_OFFSET"),
        ("abs", "NETCDF3_64BIT_DATA"),
        ("abs", "NETCDF3_CLASSIC"),
    ],
)
def test_integrate_getreplace_nan_nanfill(
    tmp_path, test_netcdf_file_nan_nanfill, create_mock_xml_file, abs_or_rel, nc_format
):
    """Test the integrated get -> replace pipeline for a file with NaN fill and filled values"""

    # Get the path to put in the XML
    netcdf_path = test_netcdf_file_nan_nanfill(nc_format)
    assert os.path.exists(netcdf_path)
    if abs_or_rel == "abs":
        netcdf_path_for_xml = netcdf_path
    elif abs_or_rel == "rel":
        netcdf_path_for_xml = os.path.relpath(netcdf_path, start=tmp_path)
    else:
        raise RuntimeError(f"Unrecognized {abs_or_rel=}")

    # Write the XML file
    xml_content = f"""<?xml version="1.0"?>
<namelist_defaults>
    <paramfile>{netcdf_path_for_xml}</paramfile>
</namelist_defaults>
"""
    xml_file = create_mock_xml_file(xml_content)

    # Call get_replacement_fill_values.py
    progress_file = str(tmp_path / "progress.json")
    assert not os.path.exists(progress_file)
    with patch("sys.argv", ["get_replacement_fill_values.py", "--fillvalues-file", progress_file]):
        with patch(
            "builtins.input",
            side_effect=[
                "y",  # continue after printing summary
                USER_REQ_DELETE,  # alphabetically 1st var
                str(TEST_FILL_VALUE),  # alphabetically 2nd var
            ],
        ):
            get_replacement_fill_values.main()

    # Call replace_fill_values.py
    with patch("sys.argv", ["replace_fill_values.py", "--fillvalues-file", progress_file]):
        with patch(
            "builtins.input",
            side_effect=[
                # "y",  # load progress without asking
                "y",  # continue after replacing
            ],
        ):
            replace_fill_values()

    # Check the output file
    output_file = get_output_filename(str(netcdf_path))
    assert os.path.exists(output_file)
    ds = xr.open_dataset(output_file, **OPEN_DS_KWARGS)
    assert FILL_ATTR in ds["temp"].encoding
    assert ds["temp"].encoding[FILL_ATTR] == TEST_FILL_VALUE
    assert np.isnan(ds["temp"].values[0])
    assert FILL_ATTR not in ds["pressure"].encoding
    assert get_netcdf_format(output_file) == nc_format

    # Check that the XML points to the output file
    tree = ET.parse(xml_file)
    root = tree.getroot()
    paramfile = root.find("paramfile")
    assert paramfile is not None
    assert paramfile.text == get_output_filename(netcdf_path_for_xml)

    # Make sure the progress file is now empty
    assert not NoNanFillValueProgress(progress_file=progress_file, load_without_asking=True)

@pytest.mark.parametrize(
    "nc_format",
    [
        "NETCDF4",
        "NETCDF4_CLASSIC",
        "NETCDF3_64BIT_OFFSET",
        "NETCDF3_64BIT_DATA",
        "NETCDF3_CLASSIC",
    ],
)
def test_integrate_getreplace_nan_nofill(
    tmp_path, test_netcdf_file_nan_nofill, create_mock_xml_file, nc_format
):
    """Test the integrated get -> replace pipeline given a file with NaN values but no fill value"""

    # Write the XML file
    netcdf_path = test_netcdf_file_nan_nofill(nc_format)
    xml_content = f"""<?xml version="1.0"?>
<namelist_defaults>
    <paramfile>{netcdf_path}</paramfile>
</namelist_defaults>
"""
    xml_file = create_mock_xml_file(xml_content)

    # Call get_replacement_fill_values.py
    progress_file = str(tmp_path / "progress.json")
    assert not os.path.exists(progress_file)
    with patch("sys.argv", ["get_replacement_fill_values.py", "--fillvalues-file", progress_file]):
        with patch(
            "builtins.input",
            side_effect=[
                "y",  # continue after printing summary
                USER_REQ_DELETE,  # alphabetically 1st var
                str(TEST_FILL_VALUE),  # alphabetically 2nd var
            ],
        ):
            get_replacement_fill_values.main()

    # Call replace_fill_values.py
    with patch("sys.argv", ["replace_fill_values.py", "--fillvalues-file", progress_file]):
        with patch(
            "builtins.input",
            side_effect=[
                # "y",  # load progress without asking
                "y",  # continue after replacing
            ],
        ):
            replace_fill_values()

    # Check the output file
    output_file = get_output_filename(str(netcdf_path))
    assert os.path.exists(output_file)
    ds = xr.open_dataset(output_file, **OPEN_DS_KWARGS)
    assert np.isnan(ds["temp"].values[0])
    assert FILL_ATTR in ds["temp"].encoding
    assert ds["temp"].encoding[FILL_ATTR] == TEST_FILL_VALUE
    assert np.isnan(ds["temp"].values[0])
    assert FILL_ATTR not in ds["pressure"].encoding
    assert get_netcdf_format(output_file) == nc_format

    # Check that the XML points to the output file
    tree = ET.parse(xml_file)
    root = tree.getroot()
    paramfile = root.find("paramfile")
    assert paramfile is not None
    assert paramfile.text == get_output_filename(netcdf_path)

    # Make sure the progress file is now empty
    assert not NoNanFillValueProgress(progress_file=progress_file, load_without_asking=True)
