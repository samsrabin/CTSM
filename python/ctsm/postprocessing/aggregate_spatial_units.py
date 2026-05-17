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

    _check_child_parent_mapping_indices(ds_in, childstrings, parentstrings)

    ###############################################################
    ### Stricter check: Not just parent indices, but parent IDs ###
    ###############################################################

    _check_child_parent_mapping_ids(ds_in, childstrings, parentstrings)


def _check_child_parent_mapping_indices(ds_in, childstrings, parentstrings):
    """Check child-parent mapping using parent indices

    Checks the child1d_parenti variable for two conditions:
    1. The parent indices are monotonically increasing *if* you look at just their first
       appearances.
    2. No parent indices are skipped.

    This would be sufficient to prove that all parents are represented, in the correct order, by at
    least one child... if we were to trust that the children and parents about what the parents look
    like. But we don't, so we will follow up this function with _check_child_parent_mapping_ids().
    """
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


def _check_child_parent_mapping_ids(ds_in, childstrings, parentstrings):
    """Check child-parent mapping using parent IDs

    Checks that the parent types referenced by the child1d_itype_* variables actually match (in both
    order and value) the parent1d_itype_* values. It does this by constructing a list of tuples for
    each:
    - If child is landunit: (ixy, jxy)
    - If child is column: (ixy, jxy, itype_lunit)
    - If child is pft: (ixy, jxy, itype_lunit, itype_col)

    This "ijt tuple" can be considered a unique identifier for the parent.
    """
    # Get list of where parent indices first appear in the child
    seen = set()
    idx = [
        i
        for i, x in enumerate(ds_in[f"{childstrings.prefix}1d_{parentstrings.i}i"].values)
        if not (x in seen or seen.add(x))
    ]

    # Get i,j,t IDs of parents as they appear in child
    ixy = ds_in[f"{childstrings.prefix}1d_ixy"].values[idx].astype(int)
    jxy = ds_in[f"{childstrings.prefix}1d_jxy"].values[idx].astype(int)
    if parentstrings.dim == "gridcell":
        ijt_ids = list(map(tuple, zip(ixy, jxy)))
    elif childstrings.dim == "column":
        itype_lunit = ds_in["cols1d_itype_lunit"].values[idx].astype(int)
        ijt_ids = list(map(tuple, zip(ixy, jxy, itype_lunit)))
    elif childstrings.dim == "pft":
        itype_lunit = ds_in["pfts1d_itype_lunit"].values[idx].astype(int)
        if parentstrings.dim == "column":
            itype_col = ds_in["pfts1d_itype_col"].values[idx].astype(int)
            ijt_ids = list(map(tuple, zip(ixy, jxy, itype_lunit, itype_col)))
        elif parentstrings.dim == "landunit":
            ijt_ids = list(map(tuple, zip(ixy, jxy, itype_lunit)))
        else:
            raise ValueError(f"Unrecognized {parentstrings.dim=}")
    else:
        raise ValueError(f"Unrecognized {childstrings.dim=}")

    # Get i,j,t IDs of parents themselves
    ixy = ds_in[f"{parentstrings.prefix}1d_ixy"].values.astype(int)
    jxy = ds_in[f"{parentstrings.prefix}1d_jxy"].values.astype(int)
    if parentstrings.dim == "gridcell":
        ijt_ids_expected = list(map(tuple, zip(ixy, jxy)))
    elif parentstrings.dim == "landunit":
        itype_landunit_var = "land1d_ityplunit"
        if itype_landunit_var not in ds_in:
            itype_landunit_var = "land1d_itype_lunit"
        itype_lunit = ds_in[itype_landunit_var].values.astype(int)
        ijt_ids_expected = list(map(tuple, zip(ixy, jxy, itype_lunit)))
    elif parentstrings.dim == "column":
        itype_lunit = ds_in["cols1d_itype_lunit"].values.astype(int)
        itype_col = ds_in["cols1d_itype_col"].values.astype(int)
        ijt_ids_expected = list(map(tuple, zip(ixy, jxy, itype_lunit, itype_col)))
    else:
        raise ValueError(f"Unrecognized {parentstrings.dim=}")

    # Make sure every parent is represented
    ijt_ids_set = set(ijt_ids)
    ijt_ids_expected_set = set(ijt_ids_expected)
    msg = f"Not every {parentstrings.disp} is represented by at least one {childstrings.disp}"
    assert ijt_ids_expected_set.issubset(ijt_ids_set), msg

    # Make sure there are no unexpected parents
    msg = f"Unexpected {parentstrings.disp} referenced by {childstrings.disp} i,j,t indices"
    assert ijt_ids_set.issubset(ijt_ids_expected_set), msg

    # Make sure order is correct
    assert (
        ijt_ids == ijt_ids_expected
    ), f"{childstrings.disp} list order does not correspond to {parentstrings.disp} list order"
