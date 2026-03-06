"""
Tests of the integrated get_replacement_fill_values.py -> replace_fill_values.py pipeline
"""

import itertools
import os
from unittest.mock import patch
import xml.etree.ElementTree as ET
from typing import Any

import pytest
import numpy as np
import xarray as xr

from ctsm.netcdf_utils import get_netcdf_format
from ctsm.no_nans_in_inputs.constants import (
    FILL_ATTR,
    MISSING_ATTR,
    OPEN_DS_KWARGS,
    USER_REQ_DELETE,
)
from ctsm.no_nans_in_inputs import get_replacement_fill_values
from ctsm.no_nans_in_inputs.replace_fill_values import main as replace_fill_values
from ctsm.no_nans_in_inputs.replace_fill_values import get_output_filename
from ctsm.no_nans_in_inputs.json_io import NoNanFillValueProgress
from ctsm.no_nans_in_inputs.netcdf_utils import file_has_nan_ncks_chk_nan

# Test constants
TEST_VAR_TEMP = "temp"
TEST_VAR_PRESSURE = "pressure"
TEST_OUTPUT_FILE = "output.nc"
TEST_NEW_FILL = -123.4
TEST_ORIG_FILLS = [np.nan, None]
NETCDF_TYPES = [
    "NETCDF4",
    "NETCDF4_CLASSIC",
    "NETCDF3_64BIT_OFFSET",
    "NETCDF3_64BIT_DATA",
    "NETCDF3_CLASSIC",
]


param_combos = [("abs",) + combo for combo in itertools.product(NETCDF_TYPES, TEST_ORIG_FILLS)]
param_combos += [("rel", NETCDF_TYPES[0], TEST_ORIG_FILLS[0])]


@pytest.fixture(name="test_netcdf_file")
def fixture_test_netcdf_file(tmp_path):
    """Create a temporary NetCDF file with filled values, NaN fill"""

    def _create(*, fill_value: Any, missing_value: Any = None, nc_format: str = NETCDF_TYPES[0]):
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

        # Set missing_value, if doing so
        if missing_value is not None:
            for v in ds:
                ds[v].attrs[MISSING_ATTR] = missing_value

        # Get encoding to set fill value
        encoding = {}
        for v in ds:
            encoding[v] = {FILL_ATTR: type(ds[v].values[0])(fill_value)}

        # Save and close
        ds.to_netcdf(str(test_file), format=nc_format, encoding=encoding)
        ds.close()

        return str(test_file)

    return _create


@pytest.mark.parametrize("abs_or_rel, nc_format, orig_fill", param_combos)
def test_integrate_get_replace(
    tmp_path, test_netcdf_file, create_mock_xml_file, abs_or_rel, nc_format, orig_fill
):
    """Test the integrated get -> replace pipeline for a file with NaN fill and filled values"""
    # pylint: disable=too-many-arguments, too-many-positional-arguments

    # Write netCDF
    netcdf_path = test_netcdf_file(fill_value=orig_fill, nc_format=nc_format)

    # Write XML
    netcdf_path, netcdf_path_for_xml, xml_file = _create_xml_and_netcdf(
        tmp_path, create_mock_xml_file, abs_or_rel, netcdf_path
    )

    # Simulate user input
    inputs_get = [
        "y",  # continue after printing summary
        USER_REQ_DELETE,  # alphabetically 1st var
        str(TEST_NEW_FILL),  # alphabetically 2nd var
    ]
    inputs_replace = [
        "y",  # continue after replacing
    ]

    # Call get_replacement_fill_values.py and do standard checks
    output_file = _call_and_check(
        tmp_path, nc_format, netcdf_path, netcdf_path_for_xml, xml_file, inputs_get, inputs_replace
    )

    # Extra checks
    ds = xr.open_dataset(output_file, **OPEN_DS_KWARGS)
    assert ds["temp"].encoding[FILL_ATTR] == TEST_NEW_FILL


def _create_xml_and_netcdf(tmp_path, create_mock_xml_file, abs_or_rel, netcdf_path):
    # pylint: disable=too-many-arguments, too-many-positional-arguments

    # Get the path to put in the XML
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
    return netcdf_path, netcdf_path_for_xml, xml_file


def _call_and_check(
    tmp_path, nc_format, netcdf_path, netcdf_path_for_xml, xml_file, inputs_get, inputs_replace
):
    # pylint: disable=too-many-arguments, too-many-positional-arguments
    progress_file = str(tmp_path / "progress.json")
    assert not os.path.exists(progress_file)
    with patch("sys.argv", ["get_replacement_fill_values.py", "--fillvalues-file", progress_file]):
        with patch(
            "builtins.input",
            side_effect=inputs_get,
        ):
            get_replacement_fill_values.main()

    # Call replace_fill_values.py
    with patch("sys.argv", ["replace_fill_values.py", "--fillvalues-file", progress_file]):
        with patch("builtins.input", side_effect=inputs_replace):
            replace_fill_values()

    # Check the output file
    output_file = get_output_filename(str(netcdf_path))
    assert os.path.exists(output_file)
    ds = xr.open_dataset(output_file, **OPEN_DS_KWARGS)
    assert np.isnan(ds["temp"].values[0])
    assert FILL_ATTR in ds["temp"].encoding
    assert np.isnan(ds["temp"].values[0])
    assert FILL_ATTR not in ds["pressure"].encoding
    assert get_netcdf_format(output_file) == nc_format
    assert not file_has_nan_ncks_chk_nan(output_file)

    # Check that the XML points to the output file
    tree = ET.parse(xml_file)
    root = tree.getroot()
    paramfile = root.find("paramfile")
    assert paramfile is not None
    assert paramfile.text == get_output_filename(netcdf_path_for_xml)

    # Make sure the progress file is now empty
    assert not NoNanFillValueProgress(progress_file=progress_file, load_without_asking=True)

    return output_file
