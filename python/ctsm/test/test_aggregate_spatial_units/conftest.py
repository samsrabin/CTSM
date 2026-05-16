"""
Fixtures used across multiple tests in test_aggregate_spatial_units/. pytest will automatically
make these available to all tests in that directory.
"""

import pytest
import numpy as np
import xarray as xr


@pytest.fixture(name="ds_all", scope="function")
def fixture_ds_all():
    """Make an xarray Dataset to test with.

    The idea here is to provide a simple Dataset that mimics a CTSM history file, but without any
    actual history outputs. We're only going to include the 1d variables related to spatial units:
    grid1d_*, land1d_*, cols1d_*, and pfts1d_*. This Dataset will be used as-is for testing the
    part of aggregate_spatial_units that ensures valid mapping of child spatial units to the
    target parent. It will also be subsetted and modified by various tests of mapping a child to a
    parent; e.g., tests of aggregating PFT to gridcell will drop the land1d_* and cols1d_*
    variables, which are not necessary.

    We'll be making a 2x2 "global" grid. The gridcells will have the following landunits:
    - 1: natural, crop, urban_hd, and urban_md
    - 2: natural, crop
    - 3: natural, crop
    - 4: natural

    There will be 3 natural and 2 crop PFTs. The urban landunits will each get the first natural
    PFT, and only that PFT. As in CTSM, the natural PFTs will share a column, while the crop PFTs
    will each get their own column.
    """
    # pylint: disable=too-many-locals,too-many-statements

    # Assume a 2x2 global grid
    lons = [90.0, 270.0]
    lats = [-45.0, 45.0]
    nx = len(lons)
    ny = len(lats)
    n_gridcells = nx * ny

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
    assert grid1d_lon.size == grid1d_lat.size
    unique_grid_lonlats = []
    for i in range(grid1d_lon.size):
        lonlat = (grid1d_lon.values[i], grid1d_lat.values[i])
        assert lonlat not in unique_grid_lonlats
        unique_grid_lonlats.append(lonlat)

    grid1d_ixy = xr.DataArray(
        data=[1, 1, 2, 2],  # 1-indexed to match Fortran outputs
        dims=["gridcell"],
    )
    grid1d_jxy = xr.DataArray(
        data=[1, 2, 1, 2],  # 1-indexed to match Fortran outputs
        dims=["gridcell"],
    )
    assert grid1d_ixy.size == grid1d_jxy.size
    unique_grid_ijs = []
    for i in range(grid1d_ixy.size):
        ij = (grid1d_ixy.values[i], grid1d_jxy.values[i])
        assert ij not in unique_grid_ijs
        unique_grid_ijs.append(ij)

    ds_grid = xr.Dataset(
        {
            "grid1d_lon": grid1d_lon,
            "grid1d_lat": grid1d_lat,
            "grid1d_ixy": grid1d_ixy,
            "grid1d_jxy": grid1d_jxy,
        }
    )
    assert ds_grid.sizes["gridcell"] == n_gridcells

    n_landunits = 4 + 2 + 2 + 1

    land1d_gi = xr.DataArray(
        data=[1, 1, 1, 1, 2, 2, 3, 3, 4],
        dims=["landunit"],
    )
    assert land1d_gi.size == n_landunits
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
        # Sums:                    1,    1,      0.9, 1.0,
        data=[0.25, 0.25, 0.25, 0.25, 0, 1, 0.1, 0.8, 1.0],
        dims=["landunit"],
    )
    land1d_ityplunit = xr.DataArray(
        data=[1, 2, 8, 9, 1, 2, 1, 2, 1],
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

    # Assume 1 column on natural and urban landunits, 2 columns on crop (1 per crop PFT)
    cols1d_gi = xr.DataArray(
        data=[1, 1, 1, 1, 1, 2, 2, 2, 3, 3, 3, 4],
        dims=["column"],
    )
    cols1d_li = xr.DataArray(
        data=[1, 2, 2, 3, 4, 5, 6, 6, 7, 8, 8, 9],
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
        # Sums: 1,        1, 1, 1, 0.9,          1,   1,    100, 0.1
        data=[1.0, 0.5, 0.5, 1, 1, 0.9, 0.75, 0.25, 1.0, 50, 50, 0.1],
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
        data=[1, 2, 2, 8, 9, 1, 2, 2, 1, 2, 2, 1],
        dims=["column"],
    )
    cols1d_itype_col = xr.DataArray(
        data=[1, 201, 202, 71, 71, 1, 201, 202, 1, 201, 202, 1],
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
    assert ds_cols.sizes["column"] == n_gridcells + 2 * (n_gridcells - 1) + 2

    # Assume 3 natural and, as above, 2 crop PFTs
    pfts1d_gi = xr.DataArray(
        data=[1, 1, 1, 1, 1, 1, 1, 2, 2, 2, 2, 2, 3, 3, 3, 3, 3, 4, 4, 4],
        dims=["pft"],
    )
    pfts1d_li = xr.DataArray(
        data=[1, 1, 1, 2, 2, 3, 4, 5, 5, 5, 6, 6, 7, 7, 7, 8, 8, 9, 9, 9],
        dims=["pft"],
    )
    pfts1d_ci = xr.DataArray(
        data=[1, 1, 1, 2, 3, 4, 5, 6, 6, 6, 7, 8, 9, 9, 9, 10, 11, 12, 12, 12],
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
        # Sums:                 1, 1, 1, 1, 1,             1, 0.5, 1        0, 1, 9,           0.6
        data=[1 / 3, 1 / 3, 1 / 3, 1, 1, 1, 1, 0.1, 0.4, 0.5, 0.5, 1, 0, 0, 0, 1, 9, 0.1, 0.2, 0.3],
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
        data=[1, 1, 1, 2, 2, 8, 9, 1, 1, 1, 2, 2, 1, 1, 1, 2, 2, 1, 1, 1],
        dims=["pft"],
    )
    pfts1d_itype_col = xr.DataArray(
        data=[1, 1, 1, 201, 202, 71, 71, 1, 1, 1, 201, 202, 1, 1, 1, 201, 202, 1, 1, 1],
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
    assert ds_pfts.sizes["pft"] == 3 * n_gridcells + 2 * (n_gridcells - 1) + 2

    ds = xr.merge([ds_grid, ds_land, ds_cols, ds_pfts])

    return ds
