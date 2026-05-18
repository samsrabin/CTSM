#!/usr/bin/env python3

"""Unit tests of _check_child_parent_mapping()"""

import numpy as np
import xarray as xr
import pytest

import ctsm.postprocessing.aggregate_spatial_units as asp
from ctsm.postprocessing.spatial_unit import SU_GRID, SU_LAND, SU_COLS, SU_PFT

# pylint: disable=protected-access

# Child, parent
VALID_PARENT_CHILD_COMBOS = [
    (SU_PFT, SU_COLS),
    (SU_PFT, SU_LAND),
    (SU_PFT, SU_GRID),
    (SU_COLS, SU_LAND),
    (SU_COLS, SU_GRID),
    (SU_LAND, SU_GRID),
]

@pytest.mark.parametrize(
    "su_child, su_parent",
    VALID_PARENT_CHILD_COMBOS,
)
def test_check_child_parent_mapping_ok(ds_all, su_child, su_parent):
    """Make sure it doesn't error for known-good mapping"""
    asp._check_child_parent_mapping(ds_all, su_child, su_parent)

@pytest.mark.parametrize(
    "su_child, su_parent",
    VALID_PARENT_CHILD_COMBOS,
)
def test_check_child_parent_mapping_skipped(ds_all, su_child, su_parent):
    """Make sure it errors right if a child's parent index is skipped"""
    child1d_parenti_var = f"{su_child.prefix}1d_{su_parent.i}i"
    ds_all[child1d_parenti_var].values[3] += 2
    with pytest.raises(
        AssertionError, match=f"{child1d_parenti_var} skips at least one {su_parent}"
    ):
        asp._check_child_parent_mapping(ds_all, su_child, su_parent)

@pytest.mark.parametrize(
    "su_child",
    [SU_PFT, SU_COLS, SU_LAND],
)
def test_check_child_gridcell_mapping_unexpected_gridcell(ds_all, su_child):
    """
    Make sure it errors right if i,j indices reference an unexpected gridcell. This needs to be done
    with _check_child_parent_mapping_ids() instead of its caller, _check_child_parent_mapping(),
    because otherwise the "Make sure length is correct" check in
    _check_child_parent_mapping_indices() would fail.
    """
    ds_all[f"{su_child.prefix}1d_gi"].values[0] = 0
    ds_all[f"{su_child.prefix}1d_ixy"].values[0] = 0
    with pytest.raises(
        AssertionError,
        match=f"Unexpected gridcell referenced by {su_child} i,j,t indices",
    ):
        asp._check_child_parent_mapping_ids(ds_all, su_child, SU_GRID)

@pytest.mark.parametrize(
    "su_child, su_parent",
    [
        (SU_PFT, SU_COLS),
        (SU_PFT, SU_LAND),
        (SU_COLS, SU_LAND),
    ],
)
def test_check_child_missing_parent_itype(ds_all, su_child, su_parent):
    """
    Make sure it errors right if some i,j,t index is missing because of bad parent t (itype).
    Gridcells have no itype, so they don't need to be tested as parent. Gridcells are the
    highest level, so they can't be tested as child.
    """
    var = f"{su_child.prefix}1d_itype_{su_parent.wt}"
    ds_all[var].values[3:] = 999
    with pytest.raises(
        AssertionError,
        match=(
            f"Not every {su_parent} is represented by at least one {su_child}"
        ),
    ):
        asp._check_child_parent_mapping(ds_all, su_child, su_parent)

@pytest.mark.parametrize(
    "su_child",
    [SU_PFT, SU_COLS, SU_LAND],
)
def test_check_child_missing_gridcell(ds_all, su_child):
    """Make sure it errors right if i,j indices are missing a gridcell"""
    ds_all[f"{su_child.prefix}1d_jxy"].values[-3:] = 1
    with pytest.raises(
        AssertionError,
        match=f"Not every gridcell is represented by at least one {su_child}",
    ):
        asp._check_child_parent_mapping(ds_all, su_child, SU_GRID)

@pytest.mark.parametrize(
    "su_child",
    [SU_PFT, SU_COLS, SU_LAND],
)
def test_child_wrong_gridcell_order(ds_all, su_child):
    """
    Make sure it errors right if i,j indices are out of order. This needs to be done with
    _check_child_parent_mapping_ids() instead of its caller, _check_child_parent_mapping(), because
    otherwise a check in _check_child_parent_mapping_indices() would fail.
    """
    su_parent = SU_GRID
    child1d_ixy_var = f"{su_child.prefix}1d_ixy"
    child1d_jxy_var = f"{su_child.prefix}1d_jxy"
    child1d_parenti_var = f"{su_child.prefix}1d_{su_parent.i}i"
    ds_all[child1d_ixy_var].values = np.flip(ds_all[child1d_ixy_var].values)
    ds_all[child1d_jxy_var].values = np.flip(ds_all[child1d_jxy_var].values)
    ds_all[child1d_parenti_var].values = np.flip(ds_all[child1d_parenti_var].values)
    with pytest.raises(
        AssertionError,
        match=f"{su_child} list order does not correspond to gridcell list order",
    ):
        asp._check_child_parent_mapping_ids(ds_all, su_child, su_parent)

def test_error_child_eq_parent():
    """
    Make sure error is thrown if child level == parent level
    """
    su = SU_COLS

    with pytest.raises(RuntimeError, match=f"Attempting to aggregate {su.dim} to itself"):
        asp._check_child_parent_mapping(xr.Dataset(), su, su)

def test_error_child_gt_parent():
    """
    Make sure error is thrown if child level > parent level
    """
    su_child = SU_COLS
    su_parent = SU_PFT

    with pytest.raises(
        RuntimeError, match=f"Can't aggregate {su_child.dim} to lower-level {su_parent.dim}"
    ):
        asp._check_child_parent_mapping(xr.Dataset(), su_child, su_parent)
