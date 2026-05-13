#!/usr/bin/env python3

"""Tests of functions in aggregate_spatial_units.py"""

import xarray as xr
import pytest

import ctsm.postprocessing.aggregate_spatial_units as asp

# pylint: disable=protected-access


@pytest.fixture(name="test_ds", scope="function")
def fixture_test_ds():
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

    ds_land = xr.Dataset(
        {
            "land1d_gi": land1d_gi,
            "land1d_ixy": land1d_ixy,
            "land1d_jxy": land1d_jxy,
            "land1d_lat": land1d_lat,
            "land1d_lon": land1d_lon,
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

    ds_cols = xr.Dataset(
        {
            "cols1d_gi": cols1d_gi,
            "cols1d_li": cols1d_li,
            "cols1d_ixy": cols1d_ixy,
            "cols1d_jxy": cols1d_jxy,
            "cols1d_lat": cols1d_lat,
            "cols1d_lon": cols1d_lon,
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

    ds_pfts = xr.Dataset(
        {
            "pfts1d_gi": pfts1d_gi,
            "pfts1d_li": pfts1d_li,
            "pfts1d_ci": pfts1d_ci,
            "pfts1d_ixy": pfts1d_ixy,
            "pfts1d_jxy": pfts1d_jxy,
            "pfts1d_lat": pfts1d_lat,
            "pfts1d_lon": pfts1d_lon,
        }
    )
    assert ds_pfts.sizes["pft"] == 3 * n_gridcells + 2 * (n_gridcells - 1)

    ds = xr.merge([ds_grid, ds_land, ds_cols, ds_pfts])

    return ds


class TestCheckPftGridcellMapping:
    """Tests of _check_pft_gridcell_mapping()"""

    def test_pft_gridcell_ok(self, test_ds):
        """Make sure it doesn't error for known-good PFT-to-gridcell mapping"""
        asp._check_pft_gridcell_mapping(test_ds)

    def test_pft_gridcell_non_monotonic(self, test_ds):
        """Make sure it errors right if gridcell indices aren't monotonically increasing"""
        test_ds["pfts1d_gi"].values[-1] = 1
        with pytest.raises(AssertionError, match="pfts1d_gi not monotonically increasing"):
            asp._check_pft_gridcell_mapping(test_ds)

    def test_pft_gridcell_skipped(self, test_ds):
        """Make sure it errors right if a gridcell index is skipped"""
        test_ds["pfts1d_gi"].values[3] += 2
        with pytest.raises(AssertionError, match="pfts1d_gi skips at least one gridcell"):
            asp._check_pft_gridcell_mapping(test_ds)

    def test_pft_gridcell_missing_gridcell(self, test_ds):
        """Make sure it errors right if i,j indices are missing a gridcell"""
        test_ds["pfts1d_jxy"].values[-3:] = 1
        with pytest.raises(
            AssertionError, match="Not every gridcell is represented by at least one PFT"
        ):
            asp._check_pft_gridcell_mapping(test_ds)

    def test_pft_gridcell_unexpected_gridcell(self, test_ds):
        """Make sure it errors right if i,j indices reference an unexpected gridcell"""
        test_ds["pfts1d_ixy"].values[-2:] = 3
        with pytest.raises(
            AssertionError, match="Unexpected gridcell referenced by PFT i,j indices"
        ):
            asp._check_pft_gridcell_mapping(test_ds)

    def test_pft_gridcell_wrong_gridcell_order(self, test_ds):
        """Make sure it errors right if i,j indices are out of order"""
        test_ds["pfts1d_ixy"].values = [2, 2, 2, 2, 2, 2, 2, 2, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1]
        test_ds["pfts1d_jxy"].values = [1, 1, 1, 1, 1, 2, 2, 2, 1, 1, 1, 1, 1, 2, 2, 2, 2, 2]
        with pytest.raises(
            AssertionError, match="PFT list order does not correspond to gridcell list order"
        ):
            asp._check_pft_gridcell_mapping(test_ds)
