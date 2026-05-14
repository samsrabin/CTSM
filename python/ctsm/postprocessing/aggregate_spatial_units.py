"""
This script allows users to take a CTSM history file (netCDF) and produce a new version with
aggregated spatial units. For example, the user might have outputs at PFT level and want to combine
them to gridcell level.
"""

from dataclasses import dataclass

import numpy as np
import xarray as xr


@dataclass
class SpatialUnitStrings:
    """Strings used in various places that are associated with spatial unit"""

    # Associated dimension name
    dim: str

    # Used when printing messages
    disp: str

    # Prefix for ..._*i variables
    i: str

    # Prefix for *1d_... variables
    prefix: str

    # Suffix for ...1d_wt* variables
    wt: None


PFTSTRINGS = SpatialUnitStrings(dim="pft", disp="PFT", i=None, prefix="pfts", wt=None)
GRIDSTRINGS = SpatialUnitStrings(dim="gridcell", disp="gridcell", i="g", prefix="grid", wt="gcell")


def ds_pft_to_gridcell(ds_in: xr.Dataset) -> xr.Dataset:
    """
    Aggregate pft-level variables in a Dataset to gridcell
    """

    # Get lists of pft-dimensioned variables to (1) drop and (2) aggregate
    pft_vars_to_aggregate = []
    pft_vars_to_drop = []
    var: str
    for var in ds_in:
        if PFTSTRINGS.dim in ds_in[var].dims:
            if var.startswith(f"{PFTSTRINGS.prefix}1d_"):
                pft_vars_to_drop.append(var)
            else:
                pft_vars_to_aggregate.append(var)

    # If there are no pft-dimensioned variables to aggregate, just return the input
    if not pft_vars_to_aggregate:
        return ds_in

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
    # Area-weighted mean
    weights = ds_in[f"{PFTSTRINGS.prefix}1d_wt{GRIDSTRINGS.wt}"]
    groups = ds_in[f"{PFTSTRINGS.prefix}1d_{GRIDSTRINGS.i}i"]
    weighted_sum = (ds_in[var] * weights).groupby(groups).sum(dim=PFTSTRINGS.dim)
    weight_totals = weights.groupby(groups).sum(dim=PFTSTRINGS.dim)
    da = weighted_sum / weight_totals

    # It's now gridcell-dimensioned. Rename dimension and remove coordinate, which natively
    # gridcell-dimensioned variables do not have.
    da = da.swap_dims({f"{PFTSTRINGS.prefix}1d_{GRIDSTRINGS.i}i": GRIDSTRINGS.dim})
    da = da.reset_coords(drop=True)

    return da


def _check_pft_gridcell_mapping(ds_in: xr.Dataset):
    unique_ordered_gi = []

    for i in np.arange(ds_in.sizes[PFTSTRINGS.dim]):
        if i > 0:
            max_gi = max(unique_ordered_gi)
        else:
            max_gi = 0

        # Get gridcell index
        child_to_parent_var = f"{PFTSTRINGS.prefix}1d_{GRIDSTRINGS.i}i"
        gi = int(ds_in[child_to_parent_var].values[i])

        # Make sure PFT gridcell indices are monotonically increasing
        assert gi >= max_gi, f"{child_to_parent_var} not monotonically increasing"

        # Make sure no gridcells are skipped
        assert gi <= max_gi + 1, f"{child_to_parent_var} skips at least one {GRIDSTRINGS.disp}"

        # Add to list of uniques
        if gi not in unique_ordered_gi:
            unique_ordered_gi.append(gi)

    # Get i,j,t triads
    ijt_triads = []
    for i in np.arange(ds_in.sizes[PFTSTRINGS.dim]):
        ixy = int(ds_in[f"{PFTSTRINGS.prefix}1d_ixy"].values[i])
        jxy = int(ds_in[f"{PFTSTRINGS.prefix}1d_jxy"].values[i])
        t = -999  # Because we're going to gridcell
        ijt = (ixy, jxy, t)
        if ijt not in ijt_triads:
            ijt_triads.append(ijt)

    # Make sure every gridcell is represented and gridcells are ordered correctly
    ijt_triads_expected = []
    for i in np.arange(ds_in.sizes[GRIDSTRINGS.dim]):
        ixy = int(ds_in[f"{GRIDSTRINGS.prefix}1d_ixy"].values[i])
        jxy = int(ds_in[f"{GRIDSTRINGS.prefix}1d_jxy"].values[i])
        t = -999
        ijt = (ixy, jxy, t)
        if ijt not in ijt_triads_expected:
            ijt_triads_expected.append(ijt)
        else:
            raise NotImplementedError("This code depends on actual ijt triads being unique")
    assert all(
        ijt in ijt_triads for ijt in ijt_triads_expected
    ), "Not every gridcell is represented by at least one PFT"
    assert all(
        ijt in ijt_triads_expected for ijt in ijt_triads
    ), "Unexpected gridcell referenced by PFT i,j,t indices"
    assert (
        ijt_triads == ijt_triads_expected
    ), "PFT list order does not correspond to gridcell list order"
