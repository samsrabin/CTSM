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

    # Suffix for ...1d_wt* variables (also ...itype_* variables)
    wt: None


PFTSTRINGS = SpatialUnitStrings(dim="pft", disp="PFT", i=None, prefix="pfts", wt=None)
LANDSTRINGS = SpatialUnitStrings(dim="landunit", disp="land unit", i="l", prefix="land", wt="lunit")
COLSSTRINGS = SpatialUnitStrings(dim="column", disp="column", i="c", prefix="cols", wt="col")
GRIDSTRINGS = SpatialUnitStrings(dim="gridcell", disp="gridcell", i="g", prefix="grid", wt="gcell")
DIMSTRINGS_DICT = {
    PFTSTRINGS.dim: PFTSTRINGS,
    COLSSTRINGS.dim: COLSSTRINGS,
    LANDSTRINGS.dim: LANDSTRINGS,
    GRIDSTRINGS.dim: GRIDSTRINGS,
}


def ds_aggregate(ds_in: xr.Dataset, child: str, parent: str) -> xr.Dataset:
    """
    Aggregate variables in a Dataset from one spatial unit to a higher-level one (e.g., pft to
    gridcell)
    """

    # TODO: Error if PFT requested as parent
    # TODO: Error if child == parent
    # TODO: Error if child is a higher level than parent
    childstrings = DIMSTRINGS_DICT[child]
    parentstrings = DIMSTRINGS_DICT[parent]

    # Get lists of child-dimensioned variables to (1) drop and (2) aggregate
    child_vars_to_aggregate = []
    child_vars_to_drop = []
    var: str
    for var in ds_in:
        if childstrings.dim in ds_in[var].dims:
            if var.startswith(f"{childstrings.prefix}1d_"):
                child_vars_to_drop.append(var)
            else:
                child_vars_to_aggregate.append(var)

    # If there are no child-dimensioned variables to aggregate, just return the input
    if not child_vars_to_aggregate:
        return ds_in

    # Create copy without child-dimensioned variables
    ds_out = ds_in.drop_vars(child_vars_to_drop + child_vars_to_aggregate)

    # The following code depends on these assumptions:
    # 1. Every parent is represented by at least one child.
    # 2. The children in each parent are contiguous with each other.
    # 3. The children are in the same order as the parents.
    _check_child_parent_mapping(ds_in, childstrings, parentstrings)

    # Aggregate and add to output Dataset
    for var in child_vars_to_aggregate:
        da = da_aggregate(ds_in, var, childstrings, parentstrings)

        # Add to output Dataset
        ds_out[var] = da

    return ds_out


def da_aggregate(
    ds_in: xr.Dataset, var: str, childstrings: SpatialUnitStrings, parentstrings: SpatialUnitStrings
) -> xr.DataArray:
    """
    Aggregate one variable in a Dataset from one spatial unit to a higher-level one (e.g., pft to
    gridcell)
    """
    # Area-weighted mean
    weights = ds_in[f"{childstrings.prefix}1d_wt{parentstrings.wt}"]
    groups = ds_in[f"{childstrings.prefix}1d_{parentstrings.i}i"]
    weighted_sum = (ds_in[var] * weights).groupby(groups).sum(dim=childstrings.dim)
    weight_totals = weights.groupby(groups).sum(dim=childstrings.dim)
    da = weighted_sum / weight_totals

    # It's now parent-dimensioned. Rename dimension and remove coordinate, which natively
    # parent-dimensioned variables do not have.
    da = da.swap_dims({f"{childstrings.prefix}1d_{parentstrings.i}i": parentstrings.dim})
    da = da.reset_coords(drop=True)

    return da


def _check_child_parent_mapping(
    ds_in: xr.Dataset, childstrings: SpatialUnitStrings, parentstrings: SpatialUnitStrings
):
    unique_ordered_parent_i = []

    for i in np.arange(ds_in.sizes[childstrings.dim]):
        if i > 0:
            max_parent_i = max(unique_ordered_parent_i)
        else:
            max_parent_i = 0

        # Get parent index
        child_to_parent_var = f"{childstrings.prefix}1d_{parentstrings.i}i"
        parent_i = int(ds_in[child_to_parent_var].values[i])

        # Make sure child's parent indices are monotonically increasing
        assert parent_i >= max_parent_i, f"{child_to_parent_var} not monotonically increasing"

        # Make sure no parents are skipped
        assert (
            parent_i <= max_parent_i + 1
        ), f"{child_to_parent_var} skips at least one {parentstrings.disp}"

        # Add to list of uniques
        if parent_i not in unique_ordered_parent_i:
            unique_ordered_parent_i.append(parent_i)

    # Get i,j,t triads
    ijt_triads = []
    for i in np.arange(ds_in.sizes[childstrings.dim]):
        ixy = int(ds_in[f"{childstrings.prefix}1d_ixy"].values[i])
        jxy = int(ds_in[f"{childstrings.prefix}1d_jxy"].values[i])
        if parentstrings.dim == "gridcell":
            t = -999  # Because we're going to gridcell
        else:
            t = int(ds_in[f"{childstrings.prefix}1d_itype_{parentstrings.wt}"].values[i])
        ijt = (ixy, jxy, t)
        if ijt not in ijt_triads:
            ijt_triads.append(ijt)

    # Make sure every parent is represented and parents are ordered correctly
    ijt_triads_expected = []
    for i in np.arange(ds_in.sizes[parentstrings.dim]):
        ixy = int(ds_in[f"{parentstrings.prefix}1d_ixy"].values[i])
        jxy = int(ds_in[f"{parentstrings.prefix}1d_jxy"].values[i])
        if parentstrings.dim == "gridcell":
            t = -999
        else:
            itype_var = f"{parentstrings.prefix}1d_itype_{parentstrings.wt}"
            if itype_var == "land1d_itype_lunit":
                itype_var = "land1d_ityplunit"
            t = int(ds_in[itype_var].values[i])
        ijt = (ixy, jxy, t)
        if ijt not in ijt_triads_expected:
            ijt_triads_expected.append(ijt)
        else:
            raise NotImplementedError("This code depends on actual ijt triads being unique")
    assert all(
        ijt in ijt_triads for ijt in ijt_triads_expected
    ), f"Not every {parentstrings.disp} is represented by at least one {childstrings.disp}"
    assert all(
        ijt in ijt_triads_expected for ijt in ijt_triads
    ), f"Unexpected {parentstrings.disp} referenced by {childstrings.disp} i,j,t indices"
    assert (
        ijt_triads == ijt_triads_expected
    ), f"{childstrings.disp} list order does not correspond to {parentstrings.disp} list order"
