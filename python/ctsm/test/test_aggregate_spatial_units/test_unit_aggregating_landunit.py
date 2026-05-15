#!/usr/bin/env python3

"""Unit tests of aggregating landunit to gridcell"""

import xarray as xr
import pytest

import ctsm.postprocessing.aggregate_spatial_units as asp
from ctsm.test.test_aggregate_spatial_units.helpers import (
    are_dataarrays_close,
    drop_unneeded_subunits,
    get_expected_weighted_mean,
)

# pylint: disable=protected-access

VAR_NAME = "testvar"


@pytest.fixture(name="ds_l2g", scope="function")
def fixture_ds_l2g(ds_all):
    """Make an xarray Dataset to test landunit-to-gridcell"""
    ds = drop_unneeded_subunits(ds_all, asp.LANDSTRINGS, asp.GRIDSTRINGS)
    ds["land1d_wtgcell"].values = (
        # Gridcell:
        #       1,              2,    3,  4
        [0.5, 0.5, 4.8e-9, 8.0e-7, 0, 0, 66]
    )

    # Add our test variable
    da = xr.DataArray(
        # Gridcell:        1,      2,    3, 4
        data=[4.8e-9, 8.0e-7, 19, 87, 0, 0, 5],
        dims=["landunit"],
    )
    ds[VAR_NAME] = da

    return ds


class TestLandunitToGridcell:
    """Tests of aggregating landunit to gridcell"""

    CHILDSTRINGS = asp.LANDSTRINGS
    PARENTSTRINGS = asp.GRIDSTRINGS

    EXPECTED_DA = xr.DataArray(
        data=[
            get_expected_weighted_mean(weights=[0.5, 0.5], values=[4.8e-9, 8.0e-7]),
            get_expected_weighted_mean(weights=[4.8e-9, 8.0e-7], values=[19, 87]),
            get_expected_weighted_mean(weights=[0, 0], values=[0, 0]),
            get_expected_weighted_mean(weights=[66], values=[5]),
        ],
        dims=[PARENTSTRINGS.dim],
    )

    def test_da_l2g(self, ds_l2g):
        """Test da_aggregate() for landunit to gridcell"""
        result = asp.da_aggregate(ds_l2g, VAR_NAME, self.CHILDSTRINGS, self.PARENTSTRINGS)
        are_dataarrays_close(result, self.EXPECTED_DA, self.PARENTSTRINGS.dim)

    def test_ds_l2g(self, ds_l2g):
        """Test ds_aggregate() for landunit to gridcell"""

        # Build expected Dataset
        expected: xr.Dataset
        expected = ds_l2g.drop_vars(
            [x for x in ds_l2g if x.startswith(f"{self.CHILDSTRINGS.prefix}1d_")] + [VAR_NAME]
        )
        expected[VAR_NAME] = self.EXPECTED_DA

        # Get result Dataset
        result = asp.ds_aggregate(ds_l2g, self.CHILDSTRINGS.dim, self.PARENTSTRINGS.dim)

        # Compare the affected variable
        are_dataarrays_close(result[VAR_NAME], expected[VAR_NAME], self.PARENTSTRINGS.dim)

        # Now drop it and compare the rest of the Datasets
        expected = expected.drop_vars([VAR_NAME])
        result = result.drop_vars([VAR_NAME])
        assert result.equals(expected)
