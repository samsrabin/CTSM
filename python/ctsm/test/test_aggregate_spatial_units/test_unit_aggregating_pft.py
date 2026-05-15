#!/usr/bin/env python3

"""Unit tests of aggregating PFT to gridcell, landunit, and column"""

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


@pytest.fixture(name="ds_p2g", scope="function")
def fixture_ds_p2g(ds_all):
    """Make an xarray Dataset to test pft-to-gridcell"""
    ds = drop_unneeded_subunits(ds_all, asp.PFTSTRINGS, asp.GRIDSTRINGS)
    ds["pfts1d_wtgcell"].values = (
        # Gridcell sums:       1,            15,             0,           0.8
        [0.2, 0.2, 0.2, 0.2, 0.2, 1, 2, 3, 4, 5, 0, 0, 0, 0, 0, 0.1, 0.2, 0.5]
    )

    # Add our test variable
    da = xr.DataArray(
        # Gridcell:         1,             2,                         3,         4
        data=[3, 7, 9, 17, 19, 5, 4, 3, 2, 3, 325, 1986, 724, 1987, 200, 0, 16, 24],
        dims=["pft"],
    )
    ds[VAR_NAME] = da

    return ds


class TestPftToGridcell:
    """Tests of aggregating pft to gridcell"""

    EXPECTED_DA = xr.DataArray(
        data=[
            get_expected_weighted_mean(weights=[0.2, 0.2, 0.2, 0.2, 0.2], values=[3, 7, 9, 17, 19]),
            get_expected_weighted_mean(weights=[1, 2, 3, 4, 5], values=[5, 4, 3, 2, 3]),
            get_expected_weighted_mean(weights=[0, 0, 0, 0, 0], values=[325, 1986, 724, 1987, 200]),
            get_expected_weighted_mean(weights=[0.1, 0.2, 0.5], values=[0, 16, 24]),
        ],
        dims=["gridcell"],
    )

    def test_da_p2g(self, ds_p2g):
        """Test da_aggregate() for pft to gridcell"""
        result = asp.da_aggregate(ds_p2g, VAR_NAME, asp.PFTSTRINGS, asp.GRIDSTRINGS)
        are_dataarrays_close(result, self.EXPECTED_DA, "gridcell")

    def test_ds_p2g(self, ds_p2g):
        """Test ds_aggregate() for pft to gridcell"""

        # Build expected Dataset
        expected: xr.Dataset
        expected = ds_p2g.drop_vars([x for x in ds_p2g if x.startswith("pfts1d_")] + [VAR_NAME])
        expected[VAR_NAME] = self.EXPECTED_DA

        # Get result Dataset
        result = asp.ds_aggregate(ds_p2g, "pft", "gridcell")

        # Compare the affected variable
        are_dataarrays_close(result[VAR_NAME], expected[VAR_NAME], "gridcell")

        # Now drop it and compare the rest of the Datasets
        expected = expected.drop_vars([VAR_NAME])
        result = result.drop_vars([VAR_NAME])
        assert result.equals(expected)

    def test_ds_p2g_novar(self, ds_p2g):
        """ds_aggregate() without any relevant variable should return the original Dataset"""
        ds_p2g_novar = ds_p2g.drop_vars(VAR_NAME)
        result = asp.ds_aggregate(ds_p2g_novar, "pft", "gridcell")
        assert result.equals(ds_p2g_novar)


@pytest.fixture(name="ds_p2l", scope="function")
def fixture_ds_p2l(ds_all):
    """Make an xarray Dataset to test pft-to-landunit"""
    childstrings = asp.PFTSTRINGS
    parentstrings = asp.LANDSTRINGS

    ds = drop_unneeded_subunits(ds_all, childstrings, parentstrings)
    ds["pfts1d_wtlunit"].values = (
        # Landunit sums (lots of zeros b/c we can test what we need w/o filling out all landunits):
        #                  1,      0.5,      14,    0,           0.8,    0,       0
        [1 / 3, 1 / 3, 1 / 3, 0.2, 0.3, 8, 4, 2, 0, 0, 0.1, 0.2, 0.5, 0, 0, 0, 0, 0]
    )

    # Add our test variable
    da = xr.DataArray(
        # Landunits:
        #           1,        2,       3,      4,        5,         6,          7
        data=[9, 9, 3, 87, -1.5, 7, 4, 6, 86, 24, 1, 10, 5, 100, -999, 84, 91, 55],
        dims=[childstrings.dim],
    )
    ds[VAR_NAME] = da

    return ds


class TestPftToLandunit:
    """Tests of aggregating pft to landunit"""

    CHILDSTRINGS = asp.PFTSTRINGS
    PARENTSTRINGS = asp.LANDSTRINGS

    EXPECTED_DA = xr.DataArray(
        data=[
            get_expected_weighted_mean(weights=[1 / 3, 1 / 3, 1 / 3], values=[9, 9, 3]),
            get_expected_weighted_mean(weights=[0.2, 0.3], values=[87, -1.5]),
            get_expected_weighted_mean(weights=[8, 4, 2], values=[7, 4, 6]),
            get_expected_weighted_mean(weights=[0, 0], values=[86, 24]),
            get_expected_weighted_mean(weights=[0.1, 0.2, 0.5], values=[1, 10, 5]),
            get_expected_weighted_mean(weights=[0, 0], values=[100, -999]),
            get_expected_weighted_mean(weights=[0, 0, 0], values=[84, 91, 55]),
        ],
        dims=[PARENTSTRINGS.dim],
    )

    def test_da_p2l(self, ds_p2l):
        """Test da_aggregate() for pft to landunit"""
        result = asp.da_aggregate(ds_p2l, VAR_NAME, self.CHILDSTRINGS, self.PARENTSTRINGS)
        assert result.sizes == self.EXPECTED_DA.sizes
        are_dataarrays_close(result, self.EXPECTED_DA, self.PARENTSTRINGS.dim)

    def test_ds_p2l(self, ds_p2l):
        """Test ds_aggregate() for pft to landunit"""

        # Build expected Dataset
        expected: xr.Dataset
        expected = ds_p2l.drop_vars(
            [x for x in ds_p2l if x.startswith(f"{self.CHILDSTRINGS.prefix}1d_")] + [VAR_NAME]
        )
        expected[VAR_NAME] = self.EXPECTED_DA

        # Get result Dataset
        result = asp.ds_aggregate(ds_p2l, self.CHILDSTRINGS.dim, self.PARENTSTRINGS.dim)

        # Compare the affected variable
        are_dataarrays_close(result[VAR_NAME], expected[VAR_NAME], self.PARENTSTRINGS.dim)

        # Now drop it and compare the rest of the Datasets
        expected = expected.drop_vars([VAR_NAME])
        result = result.drop_vars([VAR_NAME])
        assert result.equals(expected)


@pytest.fixture(name="ds_p2c", scope="function")
def fixture_ds_p2c(ds_all):
    """Make an xarray Dataset to test pft-to-column"""
    ds = drop_unneeded_subunits(ds_all, asp.PFTSTRINGS, asp.COLSSTRINGS)
    ds["pfts1d_wtcol"].values = (
        # Column sums (lots of zeros because we can test what we need without filling out all cols):
        #                  1, 1, 0.5,      14, 0, 0,           0.8, 0, 0,       0
        [1 / 3, 1 / 3, 1 / 3, 1, 0.5, 8, 4, 2, 0, 0, 0.1, 0.2, 0.5, 0, 0, 0, 0, 0]
    )

    # Add our test variable
    da = xr.DataArray(
        # Columns:
        #           1,  2,    3,       4,  5,  6,        7,   8,    9,         10
        data=[9, 9, 3, 87, -1.5, 7, 4, 6, 86, 24, 1, 10, 5, 100, -999, 84, 91, 55],
        dims=[asp.PFTSTRINGS.dim],
    )
    ds[VAR_NAME] = da

    return ds


class TestPftToColumn:
    """Tests of aggregating pft to column"""

    CHILDSTRINGS = asp.PFTSTRINGS
    PARENTSTRINGS = asp.COLSSTRINGS

    EXPECTED_DA = xr.DataArray(
        data=[
            get_expected_weighted_mean(weights=[1 / 3, 1 / 3, 1 / 3], values=[9, 9, 3]),
            get_expected_weighted_mean(weights=[1], values=[87]),
            get_expected_weighted_mean(weights=[0.5], values=[-1.5]),
            get_expected_weighted_mean(weights=[8, 4, 2], values=[7, 4, 6]),
            get_expected_weighted_mean(weights=[0], values=[86]),
            get_expected_weighted_mean(weights=[0], values=[24]),
            get_expected_weighted_mean(weights=[0.1, 0.2, 0.5], values=[1, 10, 5]),
            get_expected_weighted_mean(weights=[0], values=[100]),
            get_expected_weighted_mean(weights=[0], values=[-999]),
            get_expected_weighted_mean(weights=[0, 0, 0], values=[84, 91, 55]),
        ],
        dims=[PARENTSTRINGS.dim],
    )

    def test_da_p2c(self, ds_p2c):
        """Test da_aggregate() for pft to column"""
        result = asp.da_aggregate(ds_p2c, VAR_NAME, self.CHILDSTRINGS, self.PARENTSTRINGS)
        assert result.sizes == self.EXPECTED_DA.sizes
        are_dataarrays_close(result, self.EXPECTED_DA, self.PARENTSTRINGS.dim)

    def test_ds_p2c(self, ds_p2c):
        """Test ds_aggregate() for pft to column"""

        # Build expected Dataset
        expected: xr.Dataset
        expected = ds_p2c.drop_vars(
            [x for x in ds_p2c if x.startswith(f"{self.CHILDSTRINGS.prefix}1d_")] + [VAR_NAME]
        )
        expected[VAR_NAME] = self.EXPECTED_DA

        # Get result Dataset
        result = asp.ds_aggregate(ds_p2c, self.CHILDSTRINGS.dim, self.PARENTSTRINGS.dim)

        # Compare the affected variable
        are_dataarrays_close(result[VAR_NAME], expected[VAR_NAME], self.PARENTSTRINGS.dim)

        # Now drop it and compare the rest of the Datasets
        expected = expected.drop_vars([VAR_NAME])
        result = result.drop_vars([VAR_NAME])
        assert result.equals(expected)
