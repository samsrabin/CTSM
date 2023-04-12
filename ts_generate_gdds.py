# %%

import numpy as np
import xarray as xr
from python.ctsm.crop_calendars import utils
from glob import glob
import os

rundir = "/glade/scratch/samrabin/RXCROPMATURITY_Ld3.f10_f10_mg37.IHistClm50BgcCrop.cheyenne_intel.clm-default.G.20230412_153306_jn2z6t/run"

h1 = utils.import_ds(glob(os.path.join(rundir, "*h1*")))
h2 = utils.import_ds(glob(os.path.join(rundir, "*h2*")))

# %%

for thisYear in [1850, 1851, 1852, 1853, 1854]:
    print(thisYear)

    h2_filelist = glob(os.path.join(rundir, "*h2*"))
    dates_ds = utils.import_ds(h2_filelist, \
        myVars=["SDATES", "HDATES"], 
        myVegtypes=utils.define_mgdcrop_list(),
        timeSlice = slice(f"{thisYear}-01-01", f"{thisYear}-12-31"))
        
    if dates_ds.dims['time'] > 1:
        if dates_ds.dims['time'] == 365:
            if not incorrectly_daily:
                print("   ℹ️ You saved SDATES and HDATES daily, but you only needed annual. Fixing.")
            incorrectly_daily = True
            dates_ds = dates_ds.isel(time=-1)
    else:
        dates_ds = dates_ds.isel(time=0)

    # Make sure NaN masks match
    sdates_all_nan = np.sum(~np.isnan(dates_ds.SDATES.values), axis=dates_ds.SDATES.dims.index('mxsowings')) == 0
    hdates_all_nan = np.sum(~np.isnan(dates_ds.HDATES.values), axis=dates_ds.HDATES.dims.index('mxharvests')) == 0
    N_unmatched_nans = np.sum(sdates_all_nan != hdates_all_nan)
    if N_unmatched_nans > 0:
        print("Output SDATE and HDATE NaN masks do not match."); continue
    if np.sum(~np.isnan(dates_ds.SDATES.values)) == 0:
        print("All SDATES are NaN!"); continue

    # Just work with non-NaN patches for now
    skip_patches_for_isel_nan = np.where(sdates_all_nan)[0]
    incl_patches_for_isel_nan = np.where(~sdates_all_nan)[0]
    # different_nan_mask = y > 0 and not np.array_equal(skip_patches_for_isel_nan_lastyear, skip_patches_for_isel_nan)
    # if different_nan_mask:
    #     print('   Different NaN mask than last year')
    #     incl_thisyr_but_nan_lastyr = [dates_ds.patch.values[p] for p in incl_patches_for_isel_nan if p in skip_patches_for_isel_nan_lastyear]
    # else:
    #     incl_thisyr_but_nan_lastyr = []
    skipping_patches_for_isel_nan = len(skip_patches_for_isel_nan) > 0
    if skipping_patches_for_isel_nan:
        print(f'   Ignoring {len(skip_patches_for_isel_nan)} patches with all-NaN sowing and harvest dates.')
        dates_incl_ds = dates_ds.isel(patch=incl_patches_for_isel_nan)
    else:
        dates_incl_ds = dates_ds
    incl_patches1d_itype_veg = dates_incl_ds.patches1d_itype_veg

    # if y==0:
    incl_vegtypes_str = dates_incl_ds.vegtype_str.values
    # else:
    #     incl_vegtypes_str = incl_vegtypes_str_in
    #     if isinstance(incl_vegtypes_str, xr.DataArray):
    #         incl_vegtypes_str = incl_vegtypes_str.values
    #     if isinstance(incl_vegtypes_str, np.ndarray):
    #         incl_vegtypes_str = list(incl_vegtypes_str)
    #     if incl_vegtypes_str != list(dates_incl_ds.vegtype_str.values):
    #         raise RuntimeError(f'Included veg types differ. Previously {incl_vegtypes_str}, now {dates_incl_ds.vegtype_str.values}')
        
    if np.sum(~np.isnan(dates_incl_ds.SDATES.values)) == 0:
        print("All SDATES are NaN after ignoring those patches!"); continue

