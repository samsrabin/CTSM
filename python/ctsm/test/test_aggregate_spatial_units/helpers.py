"""
Functions used across multiple tests in test_aggregate_spatial_units/.
"""

import numpy as np
import xarray as xr

import ctsm.postprocessing.aggregate_spatial_units as asp
from ctsm.postprocessing.spatial_unit import SpatialUnit


def are_dataarrays_close(result: xr.DataArray, expected: xr.DataArray, dim: str):
    """
    Check whether two DataArrays are equal, aside from their values, which can be *close to* equal.
    """
    for i in range(expected.sizes[dim]):
        assert np.isclose(result.values[i], expected.values[i], equal_nan=True)
    assert result.dims == expected.dims
    assert result.sizes == expected.sizes
    assert result.coords == expected.coords


def drop_unneeded_subunits(ds: xr.Dataset, su_child: SpatialUnit, su_parent: SpatialUnit):
    """
    Drop subunits that aren't the child or parent. Not strictly necessary, but would make debugging
    cleaner.
    """
    unneeded_vars = []
    for k, v in asp.SUDICT.items():
        if k in [su_child.dim, su_parent.dim]:
            continue
        for var in ds:
            if var.startswith(f"{v.prefix}_1d"):
                unneeded_vars.append(var)
    return ds.drop_vars(unneeded_vars)


def get_expected_weighted_mean(*, weights, values):
    """Keyword-only because order *really* matters"""

    assert len(weights) == len(values)
    weights = np.array(weights)
    values = np.array(values)

    if all(weights == 0.0):
        return np.nan

    # Our weighted mean normalizes the sum of weights to 1.
    weights = weights / np.sum(weights)

    # np.dot() does elementwise multiplcation, then takes the sum
    return np.dot(values, weights)
