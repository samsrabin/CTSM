#!/usr/bin/env python3

"""Unit tests of _check_child_parent_mapping()"""

import numpy as np
import pytest

import ctsm.postprocessing.aggregate_spatial_units as asp

# pylint: disable=protected-access

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
def test_check_child_parent_mapping_ok(ds_all, childstrings, parentstrings):
    """Make sure it doesn't error for known-good mapping"""
    asp._check_child_parent_mapping(ds_all, childstrings, parentstrings)

@pytest.mark.parametrize(
    "childstrings, parentstrings",
    VALID_PARENT_CHILD_COMBOS,
)
def test_check_child_parent_mapping_skipped(ds_all, childstrings, parentstrings):
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
def test_check_child_gridcell_mapping_unexpected_gridcell(ds_all, childstrings):
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
def test_check_child_missing_parent_itype(ds_all, childstrings, parentstrings):
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
def test_check_child_missing_gridcell(ds_all, childstrings):
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
def test_child_wrong_gridcell_order(ds_all, childstrings):
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
