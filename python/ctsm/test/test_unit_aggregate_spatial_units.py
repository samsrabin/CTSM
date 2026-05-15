#!/usr/bin/env python3

"""Tests of functions in aggregate_spatial_units.py"""

import numpy as np
import xarray as xr
import pytest

import ctsm.postprocessing.aggregate_spatial_units as asp

# pylint: disable=protected-access

# TODO: Add testing for subgroups whose weights sum to zero (should get NaN)

VAR_NAME = "testvar"


def are_dataarrays_close(result: xr.DataArray, expected: xr.DataArray, dim: str):
    for i in range(expected.sizes[dim]):
        assert np.isclose(result.values[i], expected.values[i], equal_nan=True)
    assert result.dims == expected.dims
    assert result.sizes == expected.sizes
    assert result.coords == expected.coords


def _get_expected_weighted_mean(*, weights, values):
    """Keyword-only because order *really* matters"""

    assert len(weights) == len(values)
    weights = np.array(weights)
    values = np.array(values)

    if all(weights == 0.0):
        return np.nan

    # Weighted mean normalizes the sum of weights to 1.
    weights = weights / np.sum(weights)

    # np.dot() does elementwise multiplcation, then takes the sum
    return np.dot(values, weights)


@pytest.fixture(name="ds_all", scope="function")
def fixture_ds_all():
    """Make an xarray Dataset to test"""
    # pylint: disable=too-many-locals

    # Assume a 2x2 global grid
    lons = [90.0, 270.0]
    lats = [-45.0, 45.0]
    nx = len(lons)
    ny = len(lats)
    n_gridcells = nx * ny

    # TODO: Assert unique grid lon-lat pairs
    grid1d_lon = xr.DataArray(
        data=[lons[0]] * ny + [lons[1]] * ny,
        attrs={"units": "degrees_east"},
        dims=["gridcell"],
    )
    grid1d_lat = xr.DataArray(
        data=lats * nx,
        attrs={"units": "degrees_north"},
        dims=["gridcell"],
    )

    # TODO: Assert unique grid i-j pairs
    grid1d_ixy = xr.DataArray(
        data=[1, 1, 2, 2],  # 1-indexed to match Fortran outputs
        dims=["gridcell"],
    )
    grid1d_jxy = xr.DataArray(
        data=[1, 2, 1, 2],  # 1-indexed to match Fortran outputs
        dims=["gridcell"],
    )

    ds_grid = xr.Dataset(
        {
            "grid1d_lon": grid1d_lon,
            "grid1d_lat": grid1d_lat,
            "grid1d_ixy": grid1d_ixy,
            "grid1d_jxy": grid1d_jxy,
        }
    )
    assert ds_grid.sizes["gridcell"] == n_gridcells

    # Assume 2 landunits per gridcell (natural, crop), except no crop on last gridcell
    n_landunits_per_gridcell = 2
    n_landunits = n_gridcells * n_landunits_per_gridcell - 1

    # TODO: Assert all land1d variables have length n_landunits

    land1d_gi = xr.DataArray(
        data=[1, 1, 2, 2, 3, 3, 4],
        dims=["landunit"],
    )
    land1d_lon = xr.DataArray(
        data=[grid1d_lon.values[i - 1] for i in land1d_gi.values],
        attrs=grid1d_lon.attrs,
        dims=["landunit"],
    )
    land1d_lat = xr.DataArray(
        data=[grid1d_lat.values[i - 1] for i in land1d_gi.values],
        attrs=grid1d_lat.attrs,
        dims=["landunit"],
    )
    land1d_ixy = xr.DataArray(
        data=[grid1d_ixy.values[i - 1] for i in land1d_gi.values],
        attrs=grid1d_ixy.attrs,
        dims=["landunit"],
    )
    land1d_jxy = xr.DataArray(
        data=[grid1d_jxy.values[i - 1] for i in land1d_gi.values],
        attrs=grid1d_jxy.attrs,
        dims=["landunit"],
    )
    land1d_wtgcell = xr.DataArray(
        # Sums:      1,    1,      0.9, 1.0,
        data=[0.5, 0.5, 0, 1, 0.1, 0.8, 1.0],
        dims=["landunit"],
    )
    land1d_ityplunit = xr.DataArray(
        data=[1, 2, 1, 2, 1, 2, 1],
        dims=["landunit"],
    )

    ds_land = xr.Dataset(
        {
            "land1d_gi": land1d_gi,
            "land1d_ixy": land1d_ixy,
            "land1d_jxy": land1d_jxy,
            "land1d_lat": land1d_lat,
            "land1d_lon": land1d_lon,
            "land1d_wtgcell": land1d_wtgcell,
            "land1d_ityplunit": land1d_ityplunit,
        }
    )
    assert ds_land.sizes["landunit"] == n_landunits

    # Assume 1 column on natural landunit and 2 columns on crop (1 per crop PFT)
    cols1d_gi = xr.DataArray(
        data=[1, 1, 1, 2, 2, 2, 3, 3, 3, 4],
        dims=["column"],
    )
    cols1d_li = xr.DataArray(
        data=[1, 2, 2, 3, 4, 4, 5, 6, 6, 7],
        dims=["column"],
    )
    cols1d_lon = xr.DataArray(
        data=[grid1d_lon.values[i - 1] for i in cols1d_gi.values],
        attrs=grid1d_lon.attrs,
        dims=["column"],
    )
    cols1d_lat = xr.DataArray(
        data=[grid1d_lat.values[i - 1] for i in cols1d_gi.values],
        attrs=grid1d_lat.attrs,
        dims=["column"],
    )
    cols1d_ixy = xr.DataArray(
        data=[grid1d_ixy.values[i - 1] for i in cols1d_gi.values],
        attrs=grid1d_ixy.attrs,
        dims=["column"],
    )
    cols1d_jxy = xr.DataArray(
        data=[grid1d_jxy.values[i - 1] for i in cols1d_gi.values],
        attrs=grid1d_jxy.attrs,
        dims=["column"],
    )
    cols1d_wtlunit = xr.DataArray(
        # Sums: 1,        1, 0.9,          1,   1,    100, 0.1
        data=[1.0, 0.5, 0.5, 0.9, 0.75, 0.25, 1.0, 50, 50, 0.1],
        dims=["column"],
    )
    data = []
    for ci in np.arange(cols1d_gi.sizes["column"]):
        col_wtlunit = cols1d_wtlunit.values[ci]
        li = cols1d_li.values[ci]
        lunit_wtgcell = land1d_wtgcell.values[li - 1]
        data.append(col_wtlunit * lunit_wtgcell)
    cols1d_wtgcell = xr.DataArray(
        data=data,
        dims=["column"],
    )
    cols1d_itype_lunit = xr.DataArray(
        data=[1, 2, 2, 1, 2, 2, 1, 2, 2, 1],
        dims=["column"],
    )
    cols1d_itype_col = xr.DataArray(
        data=[1, 201, 202, 1, 201, 202, 1, 201, 202, 1],
        dims=["column"],
    )

    ds_cols = xr.Dataset(
        {
            "cols1d_gi": cols1d_gi,
            "cols1d_li": cols1d_li,
            "cols1d_ixy": cols1d_ixy,
            "cols1d_jxy": cols1d_jxy,
            "cols1d_lat": cols1d_lat,
            "cols1d_lon": cols1d_lon,
            "cols1d_wtlunit": cols1d_wtlunit,
            "cols1d_wtgcell": cols1d_wtgcell,
            "cols1d_itype_lunit": cols1d_itype_lunit,
            "cols1d_itype_col": cols1d_itype_col,
        }
    )
    assert ds_cols.sizes["column"] == n_gridcells + 2 * (n_gridcells - 1)

    # Assume 3 natural and, as above, 2 crop PFTs
    pfts1d_gi = xr.DataArray(
        data=[1, 1, 1, 1, 1, 2, 2, 2, 2, 2, 3, 3, 3, 3, 3, 4, 4, 4],
        dims=["pft"],
    )
    pfts1d_li = xr.DataArray(
        data=[1, 1, 1, 2, 2, 3, 3, 3, 4, 4, 5, 5, 5, 6, 6, 7, 7, 7],
        dims=["pft"],
    )
    pfts1d_ci = xr.DataArray(
        data=[1, 1, 1, 2, 3, 4, 4, 4, 5, 6, 7, 7, 7, 8, 9, 10, 10, 10],
        dims=["pft"],
    )
    pfts1d_lon = xr.DataArray(
        data=[grid1d_lon.values[i - 1] for i in pfts1d_gi.values],
        attrs=grid1d_lon.attrs,
        dims=["pft"],
    )
    pfts1d_lat = xr.DataArray(
        data=[grid1d_lat.values[i - 1] for i in pfts1d_gi.values],
        attrs=grid1d_lat.attrs,
        dims=["pft"],
    )
    pfts1d_ixy = xr.DataArray(
        data=[grid1d_ixy.values[i - 1] for i in pfts1d_gi.values],
        attrs=grid1d_ixy.attrs,
        dims=["pft"],
    )
    pfts1d_jxy = xr.DataArray(
        data=[grid1d_jxy.values[i - 1] for i in pfts1d_gi.values],
        attrs=grid1d_jxy.attrs,
        dims=["pft"],
    )
    pfts1d_wtcol = xr.DataArray(
        # Sums:                 1, 1, 1,             1, 0.5, 1        0, 1, 9,           0.6
        data=[1 / 3, 1 / 3, 1 / 3, 1, 1, 0.1, 0.4, 0.5, 0.5, 1, 0, 0, 0, 1, 9, 0.1, 0.2, 0.3],
        dims=["pft"],
    )
    data = []
    for pi in np.arange(pfts1d_gi.sizes["pft"]):
        pft_wtcol = pfts1d_wtcol.values[pi]
        ci = pfts1d_ci.values[pi]
        col_wtlunit = cols1d_wtlunit.values[ci - 1]
        data.append(pft_wtcol * col_wtlunit)
    pfts1d_wtlunit = xr.DataArray(
        data=data,
        dims=["pft"],
    )
    data = []
    for pi in np.arange(pfts1d_gi.sizes["pft"]):
        pft_wtlunit = pfts1d_wtlunit.values[pi]
        li = pfts1d_li.values[pi]
        land_wtgcell = land1d_wtgcell.values[li - 1]
        data.append(pft_wtlunit * land_wtgcell)
    pfts1d_wtgcell = xr.DataArray(
        data=data,
        dims=["pft"],
    )
    pfts1d_itype_lunit = xr.DataArray(
        data=[1, 1, 1, 2, 2, 1, 1, 1, 2, 2, 1, 1, 1, 2, 2, 1, 1, 1],
        dims=["pft"],
    )
    pfts1d_itype_col = xr.DataArray(
        data=[1, 1, 1, 201, 202, 1, 1, 1, 201, 202, 1, 1, 1, 201, 202, 1, 1, 1],
        dims=["pft"],
    )

    ds_pfts = xr.Dataset(
        {
            "pfts1d_gi": pfts1d_gi,
            "pfts1d_li": pfts1d_li,
            "pfts1d_ci": pfts1d_ci,
            "pfts1d_ixy": pfts1d_ixy,
            "pfts1d_jxy": pfts1d_jxy,
            "pfts1d_lat": pfts1d_lat,
            "pfts1d_lon": pfts1d_lon,
            "pfts1d_wtcol": pfts1d_wtcol,
            "pfts1d_wtlunit": pfts1d_wtlunit,
            "pfts1d_wtgcell": pfts1d_wtgcell,
            "pfts1d_itype_lunit": pfts1d_itype_lunit,
            "pfts1d_itype_col": pfts1d_itype_col,
        }
    )
    assert ds_pfts.sizes["pft"] == 3 * n_gridcells + 2 * (n_gridcells - 1)

    ds = xr.merge([ds_grid, ds_land, ds_cols, ds_pfts])

    return ds


def _drop_unneeded_subunits(
    ds: xr.Dataset, childstrings: asp.SpatialUnitStrings, parentstrings: asp.SpatialUnitStrings
):
    """
    Drop subunits that aren't the child or parent. Not strictly necessary, but would make debugging
    cleaner.
    """
    unneeded_vars = []
    for k, v in asp.DIMSTRINGS_DICT.items():
        if k in [childstrings.dim, parentstrings.dim]:
            continue
        for var in ds:
            if var.startswith(f"{v.prefix}_1d"):
                unneeded_vars.append(var)
    return ds.drop_vars(unneeded_vars)


class TestCheckChildParentMapping:
    """Tests of _check_child_parent_mapping() that exercise all child-parent combos"""

    # Child, parent
    VALID_PARENT_CHILD_COMBOS = [
        (asp.PFTSTRINGS, asp.COLSSTRINGS),
        (asp.PFTSTRINGS, asp.LANDSTRINGS),
        (asp.PFTSTRINGS, asp.GRIDSTRINGS),
        (asp.COLSSTRINGS, asp.LANDSTRINGS),
        (asp.COLSSTRINGS, asp.GRIDSTRINGS),
        (asp.LANDSTRINGS, asp.GRIDSTRINGS),
    ]

    @pytest.mark.parametrize(
        "childstrings, parentstrings",
        VALID_PARENT_CHILD_COMBOS,
    )
    def test_check_child_parent_mapping_ok(self, ds_all, childstrings, parentstrings):
        """Make sure it doesn't error for known-good mapping"""
        asp._check_child_parent_mapping(ds_all, childstrings, parentstrings)

    @pytest.mark.parametrize(
        "childstrings, parentstrings",
        VALID_PARENT_CHILD_COMBOS,
    )
    def test_check_child_parent_mapping_non_monotonic(self, ds_all, childstrings, parentstrings):
        """Make sure it errors right if child's parent indices aren't monotonically increasing"""
        child1d_parenti_var = f"{childstrings.prefix}1d_{parentstrings.i}i"
        ds_all[child1d_parenti_var].values[-1] = 1
        with pytest.raises(
            AssertionError, match=f"{child1d_parenti_var} not monotonically increasing"
        ):
            asp._check_child_parent_mapping(ds_all, childstrings, parentstrings)

    @pytest.mark.parametrize(
        "childstrings, parentstrings",
        VALID_PARENT_CHILD_COMBOS,
    )
    def test_check_child_parent_mapping_skipped(self, ds_all, childstrings, parentstrings):
        """Make sure it errors right if a child's parent index is skipped"""
        child1d_parenti_var = f"{childstrings.prefix}1d_{parentstrings.i}i"
        ds_all[child1d_parenti_var].values[3] += 2
        with pytest.raises(
            AssertionError, match=f"{child1d_parenti_var} skips at least one {parentstrings.disp}"
        ):
            asp._check_child_parent_mapping(ds_all, childstrings, parentstrings)

    @pytest.mark.parametrize(
        "childstrings",
        [asp.PFTSTRINGS, asp.COLSSTRINGS, asp.LANDSTRINGS],
    )
    def test_check_child_gridcell_mapping_unexpected_gridcell(self, ds_all, childstrings):
        """Make sure it errors right if i,j indices reference an unexpected gridcell"""
        ds_all[f"{childstrings.prefix}1d_ixy"].values[0] = 0
        with pytest.raises(
            AssertionError,
            match=f"Unexpected gridcell referenced by {childstrings.disp} i,j,t indices",
        ):
            asp._check_child_parent_mapping(ds_all, childstrings, asp.GRIDSTRINGS)

    @pytest.mark.parametrize(
        "childstrings, parentstrings",
        [
            (asp.PFTSTRINGS, asp.COLSSTRINGS),
            (asp.PFTSTRINGS, asp.LANDSTRINGS),
            (asp.COLSSTRINGS, asp.LANDSTRINGS),
        ],
    )
    def test_check_child_missing_parent_itype(self, ds_all, childstrings, parentstrings):
        """
        Make sure it errors right if some i,j,t index is missing because of bad parent t (itype).
        Gridcells have no itype, so they don't need to be tested as parent. Gridcells are the
        highest level, so they can't be tested as child.
        """
        var = f"{childstrings.prefix}1d_itype_{parentstrings.wt}"
        ds_all[var].values[3:] = 999
        with pytest.raises(
            AssertionError,
            match=(
                f"Not every {parentstrings.disp} is represented by at least one {childstrings.disp}"
            ),
        ):
            asp._check_child_parent_mapping(ds_all, childstrings, parentstrings)

    @pytest.mark.parametrize(
        "childstrings",
        [asp.PFTSTRINGS, asp.COLSSTRINGS, asp.LANDSTRINGS],
    )
    def test_check_child_missing_gridcell(self, ds_all, childstrings):
        """Make sure it errors right if i,j indices are missing a gridcell"""
        ds_all[f"{childstrings.prefix}1d_jxy"].values[-3:] = 1
        with pytest.raises(
            AssertionError,
            match=f"Not every gridcell is represented by at least one {childstrings.disp}",
        ):
            asp._check_child_parent_mapping(ds_all, childstrings, asp.GRIDSTRINGS)

    @pytest.mark.parametrize(
        "childstrings",
        [asp.PFTSTRINGS, asp.COLSSTRINGS, asp.LANDSTRINGS],
    )
    def test_child_wrong_gridcell_order(self, ds_all, childstrings):
        """Make sure it errors right if i,j indices are out of order"""
        child1d_ixy_var = f"{childstrings.prefix}1d_ixy"
        child1d_jxy_var = f"{childstrings.prefix}1d_jxy"
        ds_all[child1d_ixy_var].values = np.flip(ds_all[child1d_ixy_var].values)
        ds_all[child1d_jxy_var].values = np.flip(ds_all[child1d_jxy_var].values)
        with pytest.raises(
            AssertionError,
            match=f"{childstrings.disp} list order does not correspond to gridcell list order",
        ):
            asp._check_child_parent_mapping(ds_all, childstrings, asp.GRIDSTRINGS)


@pytest.fixture(name="ds_p2g", scope="function")
def fixture_ds_p2g(ds_all):
    """Make an xarray Dataset to test pft-to-gridcell"""
    ds = _drop_unneeded_subunits(ds_all, asp.PFTSTRINGS, asp.GRIDSTRINGS)
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
            _get_expected_weighted_mean(
                weights=[0.2, 0.2, 0.2, 0.2, 0.2], values=[3, 7, 9, 17, 19]
            ),
            _get_expected_weighted_mean(weights=[1, 2, 3, 4, 5], values=[5, 4, 3, 2, 3]),
            _get_expected_weighted_mean(
                weights=[0, 0, 0, 0, 0], values=[325, 1986, 724, 1987, 200]
            ),
            _get_expected_weighted_mean(weights=[0.1, 0.2, 0.5], values=[0, 16, 24]),
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

    ds = _drop_unneeded_subunits(ds_all, childstrings, parentstrings)
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
            _get_expected_weighted_mean(weights=[1 / 3, 1 / 3, 1 / 3], values=[9, 9, 3]),
            _get_expected_weighted_mean(weights=[0.2, 0.3], values=[87, -1.5]),
            _get_expected_weighted_mean(weights=[8, 4, 2], values=[7, 4, 6]),
            _get_expected_weighted_mean(weights=[0, 0], values=[86, 24]),
            _get_expected_weighted_mean(weights=[0.1, 0.2, 0.5], values=[1, 10, 5]),
            _get_expected_weighted_mean(weights=[0, 0], values=[100, -999]),
            _get_expected_weighted_mean(weights=[0, 0, 0], values=[84, 91, 55]),
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
    ds = _drop_unneeded_subunits(ds_all, asp.PFTSTRINGS, asp.COLSSTRINGS)
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
            _get_expected_weighted_mean(weights=[1 / 3, 1 / 3, 1 / 3], values=[9, 9, 3]),
            _get_expected_weighted_mean(weights=[1], values=[87]),
            _get_expected_weighted_mean(weights=[0.5], values=[-1.5]),
            _get_expected_weighted_mean(weights=[8, 4, 2], values=[7, 4, 6]),
            _get_expected_weighted_mean(weights=[0], values=[86]),
            _get_expected_weighted_mean(weights=[0], values=[24]),
            _get_expected_weighted_mean(weights=[0.1, 0.2, 0.5], values=[1, 10, 5]),
            _get_expected_weighted_mean(weights=[0], values=[100]),
            _get_expected_weighted_mean(weights=[0], values=[-999]),
            _get_expected_weighted_mean(weights=[0, 0, 0], values=[84, 91, 55]),
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


@pytest.fixture(name="ds_c2g", scope="function")
def fixture_ds_c2g(ds_all):
    """Make an xarray Dataset to test column-to-gridcell"""
    ds = _drop_unneeded_subunits(ds_all, asp.COLSSTRINGS, asp.GRIDSTRINGS)
    ds["cols1d_wtgcell"].values = (
        # Gridcell sums:
        #            1,           0.6,       16, 0
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
            _get_expected_weighted_mean(weights=[1 / 3, 1 / 3, 1 / 3], values=[3, 25, 86]),
            _get_expected_weighted_mean(weights=[0.1, 0.2, 0.3], values=[7, 24, 87]),
            _get_expected_weighted_mean(weights=[4, 10, 2], values=[0, -55, 18]),
            _get_expected_weighted_mean(weights=[0], values=[7.4]),
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

    ds = _drop_unneeded_subunits(ds_all, childstrings, parentstrings)
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
            _get_expected_weighted_mean(weights=[1], values=[1.58]),
            _get_expected_weighted_mean(weights=[0.5, 0.5], values=[880, 22]),
            _get_expected_weighted_mean(weights=[0.25], values=[10.53]),
            _get_expected_weighted_mean(weights=[3, 7], values=[33e7, 41e7]),
            _get_expected_weighted_mean(weights=[0], values=[27.6]),
            _get_expected_weighted_mean(weights=[0, 0], values=[41, 14]),
            _get_expected_weighted_mean(weights=[0], values=[87]),
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


@pytest.fixture(name="ds_l2g", scope="function")
def fixture_ds_l2g(ds_all):
    """Make an xarray Dataset to test landunit-to-gridcell"""
    ds = _drop_unneeded_subunits(ds_all, asp.LANDSTRINGS, asp.GRIDSTRINGS)
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
            _get_expected_weighted_mean(weights=[0.5, 0.5], values=[4.8e-9, 8.0e-7]),
            _get_expected_weighted_mean(weights=[4.8e-9, 8.0e-7], values=[19, 87]),
            _get_expected_weighted_mean(weights=[0, 0], values=[0, 0]),
            _get_expected_weighted_mean(weights=[66], values=[5]),
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
