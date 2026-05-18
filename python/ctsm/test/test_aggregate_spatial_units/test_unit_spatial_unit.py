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
