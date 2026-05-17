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

    # Check that our assumptions about child-parent mapping aren't violated
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
    # TODO: Check child-parent mapping here too, if not being called from ds_aggregate

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
    """Check child-parent mapping

    This function checks the assumptions in the aggregation functions as the latter are currently
    implemented:
    1. Every parent is represented by at least one child.
    2. The children are in the same order as the parents.
    3. There are no "unexpected parents" represented in the child.

    The functions could eventually be updated to resolve these:
    1. Fill unrepresented parents with NaN.
    2. Rearrange the output array to match the order of the parent.
    3. Warn the user and delete unexpected members of output array.

    Resolving 3 would probably need to use the lists of IDs in the "ijt" checks.
    """

    ###############################
    ### Check just with indices ###
    ###############################

    unique_ordered_parent_i = []

    child_to_parent_var = f"{childstrings.prefix}1d_{parentstrings.i}i"
    child_to_parent_values = ds_in[child_to_parent_var].values

    # Get list of parent indices in the order they appear in the child
    seen = set()
    unique_ordered_parent_i = [
        int(x) for x in child_to_parent_values if not (x in seen or seen.add(x))
    ]

    # Make sure no parents are skipped
    assert np.all(
        np.diff(unique_ordered_parent_i) == 1
    ), f"{child_to_parent_var} skips at least one {parentstrings.disp}"

    # Make sure length is correct
    n_in_child = len(unique_ordered_parent_i)
    n_parent = ds_in.sizes[parentstrings.dim]
    assert n_in_child == n_parent, (
        f"Expected {n_parent} {parentstrings.dim}s represented in"
        f" {child_to_parent_var}; got {n_in_child}"
    )

    ###############################################################
    ### Stricter check: Not just parent indices, but parent IDs ###
    ###############################################################

    # Get i,j,t triads
    ijt_ids = []
    for i in np.arange(ds_in.sizes[childstrings.dim]):
        ixy = int(ds_in[f"{childstrings.prefix}1d_ixy"].values[i])
        jxy = int(ds_in[f"{childstrings.prefix}1d_jxy"].values[i])
        t = tuple()
        if parentstrings.dim == "gridcell":
            pass
        else:
            if childstrings.dim == "column":
                t += (ds_in["cols1d_itype_lunit"].values[i],)
            elif childstrings.dim == "pft":
                t += (ds_in["pfts1d_itype_lunit"].values[i],)
                if parentstrings.dim == "column":
                    t += (ds_in["pfts1d_itype_col"].values[i],)
            else:
                raise ValueError(f"Unrecognized {childstrings.dim=}")
        ijt = (ixy, jxy)
        if t:
            ijt += t
        ijt = tuple([int(x) for x in ijt])

        if ijt not in ijt_ids:
            ijt_ids.append(ijt)

    # Make sure every parent is represented and parents are ordered correctly
    ijt_ids_expected = []
    for i in np.arange(ds_in.sizes[parentstrings.dim]):
        ixy = int(ds_in[f"{parentstrings.prefix}1d_ixy"].values[i])
        jxy = int(ds_in[f"{parentstrings.prefix}1d_jxy"].values[i])
        t = tuple()
        if parentstrings.dim == "gridcell":
            pass
        elif parentstrings.dim == "landunit":
            itype_lunit = ds_in["land1d_ityplunit"].values[i]
            t = (itype_lunit,)
        elif parentstrings.dim == "column":
            itype_lunit = ds_in["cols1d_itype_lunit"].values[i]
            itype_col = ds_in["cols1d_itype_col"].values[i]
            t = (itype_lunit, itype_col)
        else:
            raise ValueError(f"Unrecognized {parentstrings.dim=}")
        ijt = tuple([int(x) for x in (ixy, jxy) + t])
        if ijt not in ijt_ids_expected:
            ijt_ids_expected.append(ijt)
        else:
            raise NotImplementedError(
                f"This code depends on actual ijt IDs being unique; {ijt} appears at least twice (second time at index {i})"
            )
    if not all(ijt in ijt_ids for ijt in ijt_ids_expected):
        for ijt in ijt_ids_expected:
            if ijt not in ijt_ids:
                print(" ")
                print(f"{ijt_ids_expected[0:5]=}")
                print(f"{ijt_ids[0:5]=}")
                raise AssertionError(
                    f"Not every {parentstrings.disp} is represented by at least one {childstrings.disp}; {ijt} missing"
                )
    assert all(
        ijt in ijt_ids_expected for ijt in ijt_ids
    ), f"Unexpected {parentstrings.disp} referenced by {childstrings.disp} i,j,t indices"
    assert (
        ijt_ids == ijt_ids_expected
    ), f"{childstrings.disp} list order does not correspond to {parentstrings.disp} list order"
