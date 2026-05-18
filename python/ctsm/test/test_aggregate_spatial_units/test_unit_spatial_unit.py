"""
Tests of SpatialUnit
"""

import pytest

import ctsm.postprocessing.spatial_unit as su


def test_no_setattr():
    """Check that changing an attribute is not allowed"""
    with pytest.raises(AttributeError, match="'SpatialUnit' object is immutable"):
        su.SU_COLS.dim = "abc123"


def test_no_delattr():
    """Check that changing an attribute is not allowed"""
    with pytest.raises(AttributeError, match="'SpatialUnit' object is immutable"):
        delattr(su.SU_COLS, "dim")


def test_lt():
    """Test < operator"""
    assert su.SU_PFT < su.SU_COLS < su.SU_LAND < su.SU_GRID


def test_le():
    """Test <= operator"""
    assert su.SU_PFT <= su.SU_COLS <= su.SU_LAND <= su.SU_GRID


def test_gt():
    """Test > operator"""
    assert su.SU_GRID > su.SU_LAND > su.SU_COLS > su.SU_PFT


def test_ge():
    """Test >= operator"""
    assert su.SU_GRID >= su.SU_LAND >= su.SU_COLS >= su.SU_PFT


def test_eq():
    """Test == operator"""
    assert su.SU_PFT == su.SU_PFT
    assert su.SU_COLS == su.SU_COLS
    assert su.SU_LAND == su.SU_LAND
    assert su.SU_GRID == su.SU_GRID


def test_ne():
    """Test != operator"""
    assert su.SU_PFT != su.SU_COLS
    assert su.SU_PFT != su.SU_LAND
    assert su.SU_PFT != su.SU_GRID
    assert su.SU_COLS != su.SU_LAND
    assert su.SU_COLS != su.SU_GRID
    assert su.SU_LAND != su.SU_GRID
