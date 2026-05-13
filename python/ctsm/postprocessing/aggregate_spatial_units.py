"""
This script allows users to take a CTSM history file (netCDF) and produce a new version with
aggregated spatial units. For example, the user might have outputs at PFT level and want to combine
them to gridcell level.
"""

import numpy as np
import xarray as xr


def ds_pft_to_gridcell(ds_in: xr.Dataset) -> xr.Dataset:
    """
    Aggregate pft-level variables in a Dataset to gridcell
    """

    # Get lists of pft-dimensioned variables to (1) drop and (2) aggregate
    pft_vars_to_aggregate = []
    pft_vars_to_drop = []
    var: str
    for var in ds_in:
        if "pft" in ds_in[var].dims:
            if var.startswith("pfts1d_"):
                pft_vars_to_drop.append(var)
            else:
                pft_vars_to_aggregate.append(var)

    # Create copy without pft-dimensioned variables
    ds_out = ds_in.drop_vars(pft_vars_to_drop + pft_vars_to_aggregate)

    # The following code depends on these assumptions:
    # 1. Every gridcell is represented by at least one pft.
    # 2. The PFTs in each gridcell are contiguous with each other.
    # 3. The PFTs are in the same order as the gridcells.
    _check_pft_gridcell_mapping(ds_in)

    # Aggregate and add to output Dataset
    for var in pft_vars_to_aggregate:
        da = da_pft_to_gridcell(ds_in, var)

        # Add to output Dataset
        ds_out[var] = da

    return ds_out


def da_pft_to_gridcell(ds_in: xr.Dataset, var: str) -> xr.DataArray:
    """
    Aggregate a pft-level variable in a Dataset to gridcell
    """
    # Area-weighted sum
    weights = ds_in["pfts1d_wtgcell"]
    da = (ds_in[var] * weights).groupby(ds_in["pfts1d_gi"]).sum()

    # It's now gridcell-dimensioned. Rename dimension and remove coordinate, which natively
    # gridcell-dimensioned variables do not have.
    da = da.swap_dims({"pfts1d_gi": "gridcell"})
    da = da.reset_coords(drop=True)

    return da


def _check_pft_gridcell_mapping(ds_in: xr.Dataset):
    unique_ordered_gi = []

    for i in np.arange(ds_in.sizes["pft"]):
        if i > 0:
            max_gi = max(unique_ordered_gi)
        else:
            max_gi = 0

        # Get gridcell index
        gi = int(ds_in["pfts1d_gi"].values[i])

        # Make sure PFT gridcell indices are monotonically increasing
        assert gi >= max_gi, "pfts1d_gi not monotonically increasing"

        # Make sure no gridcells are skipped
        assert gi <= max_gi + 1, "pfts1d_gi skips at least one gridcell"

        # Add to list of uniques
        if gi not in unique_ordered_gi:
            unique_ordered_gi.append(gi)

    # Get i, j pairs
    ij_pairs = []
    for i in np.arange(ds_in.sizes["pft"]):
        ixy = int(ds_in["pfts1d_ixy"].values[i])
        jxy = int(ds_in["pfts1d_jxy"].values[i])
        ij = (ixy, jxy)
        if ij not in ij_pairs:
            ij_pairs.append(ij)

    # Make sure every gridcell is represented and gridcells are ordered correctly
    ij_pairs_expected = []
    for i in np.arange(ds_in.sizes["gridcell"]):
        ixy = int(ds_in["grid1d_ixy"].values[i])
        jxy = int(ds_in["grid1d_jxy"].values[i])
        ij_pairs_expected.append((ixy, jxy))
    assert all(
        ij in ij_pairs for ij in ij_pairs_expected
    ), "Not every gridcell is represented by at least one PFT"
    assert all(
        ij in ij_pairs_expected for ij in ij_pairs
    ), "Unexpected gridcell referenced by PFT i,j indices"
    assert (
        ij_pairs == ij_pairs_expected
    ), "PFT list order does not correspond to gridcell list order"
