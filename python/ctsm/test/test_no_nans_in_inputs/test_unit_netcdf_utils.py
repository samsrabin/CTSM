#!/usr/bin/env python3
"""
Unit tests for netcdf_utils.py module.
"""
# pylint: disable=too-many-arguments,too-many-positional-arguments,too-few-public-methods
# pylint: disable=too-many-public-methods

import pytest
import numpy as np

from ctsm.no_nans_in_inputs.netcdf_utils import _get_negative_default


class TestGetNegativeDefault:
    """Test the _get_negative_default() function"""

    @pytest.mark.parametrize(
        "nanmin, expected",
        [
            # Floats
            (100.0, -999.0),
            (0, -999.0),
            (-1.0, -999.0),
            (-999.0, -9999.0),
            (-1000.0, -9999.0),
            (-9999.0, -99999.0),
            (-998.9, -999.0),
            # Integers
            (100, -999),
            (-999, -9999),
            # Infinity
            (-np.inf, None),
        ],
    )
    def test_general(self, nanmin, expected):
        """General test of many possibilities"""
        result = _get_negative_default(nanmin)
        if expected is None:
            assert result is None
        else:
            assert result == expected
            assert isinstance(result, type(nanmin))

    @pytest.mark.parametrize(
        "this_type", [np.float32, np.float64, np.int32, np.int64]
    )
    def test_specific_type_preserved(self, this_type):
        """Test that specific types are preserved"""
        result = _get_negative_default(this_type(0.0))
        assert isinstance(result, this_type)
