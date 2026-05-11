"""
Functions helping to handle CFTs and crop types in CTSM outputs
"""

from typing import List, Tuple
import xarray as xr

FIRST_UNMGD_CROP_INT = 15
N_UNMGD_CROPS = 2


def get_mgd_cft_lists(ds: xr.Dataset) -> Tuple[List[str], List[int]]:
    """Get names of and integers corresponding to managed crop functional types"""
    cft_list_str = []
    cft_list_int = []
    k: str
    v: int
    cft_attr_dict = {k: v for k, v in ds.attrs.items() if k.startswith("cft_")}
    for k, v in cft_attr_dict.items():
        # Skip unmanaged crops (grasses)
        if v <= N_UNMGD_CROPS:
            continue

        cft_list_str.append(k)
        cft_list_int.append(FIRST_UNMGD_CROP_INT + v - 1)
    return cft_list_str, cft_list_int


def extract_mgd_crops(ds: xr.Dataset) -> xr.Dataset:
    """Remove non-managed-crop PFTs from a Dataset"""

    # Return early if no variables have pft dimension
    if "pft" not in ds.dims:
        print("PFT dimension not found on dataset")
        return ds
    any_var_has_pft = False
    for var in ds:
        if "pft" in ds[var].dims:
            any_var_has_pft = True
            break
    if not any_var_has_pft:
        print("No variable on dataset has PFT dimension")
        return ds

    # Get CFT list (string and integer), returning early if no managed CFTs found
    cft_list_str, cft_list_int = get_mgd_cft_lists(ds)
    if not cft_list_str:
        print("No managed CFTs found in cft_* attributes")
        return ds

    # Restrict dataset's PFT-dimensioned variables to crops
    is_crop = [i for i, x in enumerate(ds["pfts1d_itype_veg"].values) if x in cft_list_int]
    ds_out = ds.copy().isel(pft=is_crop)
    # TODO: Test that original Dataset is not touched!

    # Save as attributes
    ds_out.attrs["cft_list_str"] = " ".join(cft_list_str)
    ds_out.attrs["cft_list_int"] = " ".join([str(x) for x in cft_list_int])

    return ds_out
