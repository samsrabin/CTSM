#!/usr/bin/env python3

"""Tests of get_mgd_cft_lists and extract_mgd_crops"""

import numpy as np
import xarray as xr

from ctsm.crop_postprocessing.cfts_and_crops import (
    FIRST_UNMGD_CROP_INT,
    N_UNMGD_CROPS,
    get_mgd_cft_lists,
    extract_mgd_crops,
)

# Allow test names that pylint doesn't like; otherwise hard to make them
# readable
# pylint: disable=invalid-name

# pylint: disable=protected-access,too-many-public-methods
# pylint: disable=use-implicit-booleaness-not-comparison


# Attribute dictionary representing a typical CTSM history-file layout: two
# unmanaged crop entries (values <= N_UNMGD_CROPS, to be skipped) followed by
# several managed CFTs.
CFT_ATTRS = {
    "cft_c3_crop": 1,
    "cft_c3_irrigated": 2,
    "cft_corn": 3,
    "cft_irrigated_corn": 4,
    "cft_spring_wheat": 5,
    "cft_irrigated_spring_wheat": 6,
}


def _make_ds_with_cft_attrs(extra_attrs=None):
    """Build a tiny Dataset whose attrs include the CFT_ATTRS mapping"""
    ds = xr.Dataset()
    ds.attrs.update(CFT_ATTRS)
    if extra_attrs:
        ds.attrs.update(extra_attrs)
    return ds


class TestGetCftLists:
    """Tests of get_mgd_cft_lists function"""

    def test_returns_only_managed_crops(self):
        """Unmanaged crops (value <= N_UNMGD_CROPS) should be skipped"""
        ds = _make_ds_with_cft_attrs()
        cft_list_str, cft_list_int = get_mgd_cft_lists(ds)

        assert cft_list_str == [
            "cft_corn",
            "cft_irrigated_corn",
            "cft_spring_wheat",
            "cft_irrigated_spring_wheat",
        ]
        # integer = FIRST_UNMGD_CROP_INT + v - 1
        assert cft_list_int == [
            FIRST_UNMGD_CROP_INT + 3 - 1,
            FIRST_UNMGD_CROP_INT + 4 - 1,
            FIRST_UNMGD_CROP_INT + 5 - 1,
            FIRST_UNMGD_CROP_INT + 6 - 1,
        ]

    def test_no_cft_attrs_returns_empty(self):
        """A Dataset with no cft_ attrs should produce empty lists"""
        ds = xr.Dataset()
        ds.attrs.update({"history": "made-up", "title": "no crops here"})

        cft_list_str, cft_list_int = get_mgd_cft_lists(ds)

        assert cft_list_str == []
        assert cft_list_int == []

    def test_only_unmanaged_returns_empty(self):
        """If every cft_ attr is unmanaged, the result should be empty"""
        ds = xr.Dataset()
        ds.attrs.update({"cft_c3_crop": 1, "cft_c3_irrigated": 2})

        cft_list_str, cft_list_int = get_mgd_cft_lists(ds)

        assert cft_list_str == []
        assert cft_list_int == []

    def test_non_cft_attrs_ignored(self):
        """Attrs that don't start with 'cft_' should not show up in the output"""
        ds = _make_ds_with_cft_attrs(extra_attrs={"title": "ignored", "source": "ignored"})

        cft_list_str, _ = get_mgd_cft_lists(ds)

        assert "title" not in cft_list_str
        assert "source" not in cft_list_str
        # The cft_ entries we expect are still there
        assert "cft_corn" in cft_list_str

    def test_boundary_value(self):
        """A cft_ attr with value exactly equal to N_UNMGD_CROPS should be skipped"""
        ds = xr.Dataset()
        ds.attrs.update(
            {
                "cft_boundary": N_UNMGD_CROPS,
                "cft_first_managed": N_UNMGD_CROPS + 1,
            }
        )

        cft_list_str, cft_list_int = get_mgd_cft_lists(ds)

        assert cft_list_str == ["cft_first_managed"]
        assert cft_list_int == [FIRST_UNMGD_CROP_INT + N_UNMGD_CROPS]

    def test_lists_have_same_length(self):
        """String and integer lists should always have matching lengths"""
        ds = _make_ds_with_cft_attrs()
        cft_list_str, cft_list_int = get_mgd_cft_lists(ds)
        assert len(cft_list_str) == len(cft_list_int)


class TestExtractMgdCrops:
    """Tests of extract_mgd_crops function"""

    N_GRIDCELLS = 2

    def _make_ds_with_pft_dim(self):
        """
        Build a small Dataset containing a mix of natural PFTs, unmanaged crops, and managed crops
        over a few gridcells.
        """
        # itype_veg integers for each pft slot. The managed-crop integers
        # produced by get_mgd_cft_lists for CFT_ATTRS are 17, 18, 19, 20.
        pft_list_int = [1, 5, 17, 18, 19, 20, 99]
        pfts1d_itype_veg = np.array(pft_list_int * self.N_GRIDCELLS, dtype=np.int32)
        n_pft = len(pft_list_int)

        ds = xr.Dataset(
            data_vars={
                "pfts1d_itype_veg": (("pft",), pfts1d_itype_veg),
                "some_pft_var": (("pft",), np.arange(n_pft * self.N_GRIDCELLS, dtype=np.float64)),
                # A variable without the pft dim, to make sure it's preserved untouched
                "scalar_var": ((), np.float64(42.0)),
            },
            # CTSM output files don't have a pft coordinate, so don't add one.
        )
        ds.attrs.update(CFT_ATTRS)
        return ds

    def test_no_pft_dim_returns_input(self, capsys):
        """If there's no 'pft' dim, the Dataset should be returned unchanged"""
        ds = xr.Dataset(data_vars={"foo": (("x",), np.arange(3))})
        ds.attrs.update(CFT_ATTRS)

        result = extract_mgd_crops(ds)

        assert result is ds
        captured = capsys.readouterr()
        assert "PFT dimension not found" in captured.out

    def test_pft_dim_but_no_var_uses_it_returns_input(self, capsys):
        """If 'pft' is in dims but no variable uses it, return unchanged"""
        # Create a pft dim via a coord, with no data var that has the pft dim
        ds = xr.Dataset(
            data_vars={"scalar_var": ((), np.float64(1.0))},
            coords={"pft": np.arange(4)},
        )
        ds.attrs.update(CFT_ATTRS)

        # Correctness check on the fixture: pft is in dims but no variable uses it
        assert "pft" in ds.dims
        assert all("pft" not in ds[v].dims for v in ds.data_vars)

        result = extract_mgd_crops(ds)

        assert result is ds
        captured = capsys.readouterr()
        assert "No variable on dataset has PFT dimension" in captured.out

    def test_filters_to_managed_crops(self):
        """Output should keep only PFT slots whose itype_veg is a managed CFT integer"""
        ds = self._make_ds_with_pft_dim()

        result = extract_mgd_crops(ds)

        # Managed CFT integers in CFT_ATTRS are 17, 18, 19, 20 (FIRST_UNMGD_CROP_INT + v - 1
        # for v in {3, 4, 5, 6}). The fixture has those at pft indices 2..5 (gridcell 0) and 9..12
        # (gridcell 1).
        expected_itype = np.array([17, 18, 19, 20] * self.N_GRIDCELLS, dtype=np.int32)
        np.testing.assert_array_equal(result["pfts1d_itype_veg"].values, expected_itype)
        np.testing.assert_array_equal(
            result["some_pft_var"].values, np.array([2, 3, 4, 5, 9, 10, 11, 12])
        )

    def test_preserves_non_pft_variables(self):
        """Variables without the pft dim should be carried through untouched"""
        ds = self._make_ds_with_pft_dim()

        result = extract_mgd_crops(ds)

        assert "scalar_var" in result
        assert float(result["scalar_var"].values) == 42.0

    def test_sets_cft_list_attrs(self):
        """Output should record the managed CFT lists in its attrs"""
        ds = self._make_ds_with_pft_dim()

        result = extract_mgd_crops(ds)

        assert (
            result.attrs["cft_list_str"]
            == "cft_corn cft_irrigated_corn cft_spring_wheat cft_irrigated_spring_wheat"
        )
        assert result.attrs["cft_list_int"] == "17 18 19 20"

    def test_does_not_mutate_input(self):
        """The original Dataset should not be modified by extract_mgd_crops"""
        ds = self._make_ds_with_pft_dim()
        orig_pft_size = ds.sizes["pft"]
        orig_itype = ds["pfts1d_itype_veg"].values.copy()
        orig_attr_keys = set(ds.attrs.keys())

        _ = extract_mgd_crops(ds)

        assert ds.sizes["pft"] == orig_pft_size
        np.testing.assert_array_equal(ds["pfts1d_itype_veg"].values, orig_itype)
        # The output-only attrs should not have been written onto the input
        assert "cft_list_str" not in ds.attrs
        assert "cft_list_int" not in ds.attrs
        assert set(ds.attrs.keys()) == orig_attr_keys

    def test_no_managed_crops_returns_input(self, capsys):
        """If no managed CFTs are defined in attrs, the Dataset should be returned unchanged"""
        pfts1d_itype_veg = np.array([1, 5, 99], dtype=np.int32)
        n_pft = pfts1d_itype_veg.size
        ds = xr.Dataset(
            data_vars={
                "pfts1d_itype_veg": (("pft",), pfts1d_itype_veg),
                "some_pft_var": (("pft",), np.arange(n_pft, dtype=np.float64)),
            },
            coords={"pft": np.arange(n_pft)},
        )
        # Only unmanaged crop attrs — get_mgd_cft_lists returns empty lists
        ds.attrs.update({"cft_c3_crop": 1, "cft_c3_irrigated": 2})

        result = extract_mgd_crops(ds)

        assert result is ds
        assert "cft_list_str" not in result.attrs
        assert "cft_list_int" not in result.attrs
        captured = capsys.readouterr()
        assert "No managed CFTs found" in captured.out
