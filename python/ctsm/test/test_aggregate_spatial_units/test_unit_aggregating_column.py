#!/usr/bin/env python3

"""Unit tests of aggregating column to gridcell and landunit"""

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


@pytest.fixture(name="ds_c2g", scope="function")
def fixture_ds_c2g(ds_all):
    """Make an xarray Dataset to test column-to-gridcell"""
    ds = drop_unneeded_subunits(ds_all, asp.COLSSTRINGS, asp.GRIDSTRINGS)
    ds["cols1d_wtgcell"].values = (
        # Gridcell sums:
        #                  1,           0.6,       16, 0
        [1 / 3, 1 / 3, 1 / 3, 0.1, 0.2, 0.3, 4, 10, 2, 0]
    )

    # Add our test variable
    da = xr.DataArray(
        # Gridcell:   1,         2,          3,   4
        data=[3, 25, 86, 7, 24, 87, 0, -55, 18, 7.4],
        dims=["column"],
    )
    ds[VAR_NAME] = da

    return ds


class TestColumnToGridcell:
    """Tests of aggregating column to gridcell"""

    CHILDSTRINGS = asp.COLSSTRINGS
    PARENTSTRINGS = asp.GRIDSTRINGS

    EXPECTED_DA = xr.DataArray(
        data=[
            get_expected_weighted_mean(weights=[1 / 3, 1 / 3, 1 / 3], values=[3, 25, 86]),
            get_expected_weighted_mean(weights=[0.1, 0.2, 0.3], values=[7, 24, 87]),
            get_expected_weighted_mean(weights=[4, 10, 2], values=[0, -55, 18]),
            get_expected_weighted_mean(weights=[0], values=[7.4]),
        ],
        dims=[PARENTSTRINGS.dim],
    )

    def test_da_c2g(self, ds_c2g):
        """Test da_aggregate() for column to gridcell"""
        result = asp.da_aggregate(ds_c2g, VAR_NAME, self.CHILDSTRINGS, self.PARENTSTRINGS)
        are_dataarrays_close(result, self.EXPECTED_DA, self.PARENTSTRINGS.dim)

    def test_ds_c2g(self, ds_c2g):
        """Test ds_aggregate() for column to gridcell"""

        # Build expected Dataset
        expected: xr.Dataset
        expected = ds_c2g.drop_vars(
            [x for x in ds_c2g if x.startswith(f"{self.CHILDSTRINGS.prefix}1d_")] + [VAR_NAME]
        )
        expected[VAR_NAME] = self.EXPECTED_DA

        # Get result Dataset
        result = asp.ds_aggregate(ds_c2g, self.CHILDSTRINGS.dim, self.PARENTSTRINGS.dim)

        # Compare the affected variable
        are_dataarrays_close(result[VAR_NAME], expected[VAR_NAME], self.PARENTSTRINGS.dim)

        # Now drop it and compare the rest of the Datasets
        expected = expected.drop_vars([VAR_NAME])
        result = result.drop_vars([VAR_NAME])
        assert result.equals(expected)


@pytest.fixture(name="ds_c2l", scope="function")
def fixture_ds_c2l(ds_all):
    """Make an xarray Dataset to test column-to-landunit"""
    childstrings = asp.COLSSTRINGS
    parentstrings = asp.LANDSTRINGS

    ds = drop_unneeded_subunits(ds_all, childstrings, parentstrings)
    ds[f"{childstrings.prefix}1d_wt{parentstrings.wt}"].values = (
        # Landunit sums (lots of zeros b/c we can test what we need w/o filling out all landunits):
        # 1,       1, 0.25,   10, 0,    0, 0
        [1, 0.5, 0.5, 0.25, 3, 7, 0, 0, 0, 0]
    )

    # Add our test variable
    da = xr.DataArray(
        # Landunits:
        #        1,       2,     3,          4,    5,      6,  7
        data=[1.58, 880, 22, 10.53, 33e7, 41e7, 27.6, 41, 14, 87],
        dims=[childstrings.dim],
    )
    ds[VAR_NAME] = da

    return ds


class TestColumnToLandunit:
    """Tests of aggregating column to landunit"""

    CHILDSTRINGS = asp.COLSSTRINGS
    PARENTSTRINGS = asp.LANDSTRINGS

    EXPECTED_DA = xr.DataArray(
        data=[
            get_expected_weighted_mean(weights=[1], values=[1.58]),
            get_expected_weighted_mean(weights=[0.5, 0.5], values=[880, 22]),
            get_expected_weighted_mean(weights=[0.25], values=[10.53]),
            get_expected_weighted_mean(weights=[3, 7], values=[33e7, 41e7]),
            get_expected_weighted_mean(weights=[0], values=[27.6]),
            get_expected_weighted_mean(weights=[0, 0], values=[41, 14]),
            get_expected_weighted_mean(weights=[0], values=[87]),
        ],
        dims=[PARENTSTRINGS.dim],
    )

    def test_da_c2l(self, ds_c2l):
        """Test da_aggregate() for column to landunit"""
        result = asp.da_aggregate(ds_c2l, VAR_NAME, self.CHILDSTRINGS, self.PARENTSTRINGS)
        assert result.sizes == self.EXPECTED_DA.sizes
        are_dataarrays_close(result, self.EXPECTED_DA, self.PARENTSTRINGS.dim)

    def test_ds_c2l(self, ds_c2l):
        """Test ds_aggregate() for column to landunit"""

        # Build expected Dataset
        expected: xr.Dataset
        expected = ds_c2l.drop_vars(
            [x for x in ds_c2l if x.startswith(f"{self.CHILDSTRINGS.prefix}1d_")] + [VAR_NAME]
        )
        expected[VAR_NAME] = self.EXPECTED_DA

        # Get result Dataset
        result = asp.ds_aggregate(ds_c2l, self.CHILDSTRINGS.dim, self.PARENTSTRINGS.dim)

        # Compare the affected variable
        are_dataarrays_close(result[VAR_NAME], expected[VAR_NAME], self.PARENTSTRINGS.dim)

        # Now drop it and compare the rest of the Datasets
        expected = expected.drop_vars([VAR_NAME])
        result = result.drop_vars([VAR_NAME])
        assert result.equals(expected)
