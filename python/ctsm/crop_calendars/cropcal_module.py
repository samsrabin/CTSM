import numpy as np
import xarray as xr
import warnings
import sys
import os
import glob

# Import the CTSM Python utilities.
# sys.path.insert() is necessary for RXCROPMATURITY to work. The fact that it's calling this script in the RUN phase seems to require the python/ directory to be manually added to path.
_CTSM_PYTHON = os.path.join(
    os.path.dirname(os.path.realpath(__file__)), os.pardir, os.pardir, os.pardir, "python"
)
sys.path.insert(1, _CTSM_PYTHON)
import ctsm.crop_calendars.cropcal_utils as utils

try:
    import pandas as pd
except:
    pass


# Define conversion multipliers, {from: {to1, to2, ...}, ...}
multiplier_dict = {
    # Mass
    "g": {
        "Mt": 1e-12,
    },
    "t": {
        "Mt": 1e-6,
    },
    # Volume
    "m3": {
        "km3": 1e-9,
    },
    # Yield
    "g/m2": {
        "t/ha": 1e-6 * 1e4,
    },
}


# After importing a file, restrict it to years of interest.
def check_and_trim_years(y1, yN, ds_in):
    ### In annual outputs, file with name Y is actually results from year Y-1.
    ### Note that time values refer to when it was SAVED. So 1981-01-01 is for year 1980.

    def get_year_from_cftime(cftime_date):
        # Subtract 1 because the date for annual files is when it was SAVED
        return cftime_date.year - 1

    # Check that all desired years are included
    if get_year_from_cftime(ds_in.time.values[0]) > y1:
        print(f"Requested y1 is {y1} but first year in outputs is {get_year_from_cftime(ds_in.time.values[0])}")
        stop
    elif get_year_from_cftime(ds_in.time.values[-1]) < y1:
        print(f"Requested yN is {yN} but last year in outputs is {get_year_from_cftime(ds_in.time.values[-1])}")
        stop

    # Remove years outside range of interest
    ### Include an extra year at the end to finish out final seasons.
    ds_in = utils.safer_timeslice(ds_in, slice(f"{y1+1}-01-01", f"{yN+2}-01-01"))

    # Make sure you have the expected number of timesteps (including extra year)
    Nyears_expected = yN - y1 + 2
    if ds_in.dims["time"] != Nyears_expected:
        print(f"Expected {Nyears_expected} timesteps in output but got {ds_in.dims['time']}")
        stop

    return ds_in


def open_lu_ds(filename, y1, yN, existing_ds, ungrid=True):
    # Open and trim to years of interest
    dsg = xr.open_dataset(filename).sel(time=slice(y1, yN))

    # Assign actual lon/lat coordinates
    dsg = dsg.assign_coords(
        lon=("lsmlon", existing_ds.lon.values), lat=("lsmlat", existing_ds.lat.values)
    )
    dsg = dsg.swap_dims({"lsmlon": "lon", "lsmlat": "lat"})

    if "AREA" in dsg:
        dsg["AREA_CFT"] = dsg.AREA * 1e6 * dsg.LANDFRAC_PFT * dsg.PCT_CROP / 100 * dsg.PCT_CFT / 100
        dsg["AREA_CFT"].attrs = {"units": "m2"}
        dsg["AREA_CFT"].load()
    else:
        print("Warning: AREA missing from Dataset, so AREA_CFT will not be created")

    if not ungrid:
        return dsg

    # Un-grid
    query_ilons = [int(x) - 1 for x in existing_ds["patches1d_ixy"].values]
    query_ilats = [int(x) - 1 for x in existing_ds["patches1d_jxy"].values]
    query_ivts = [list(dsg.cft.values).index(x) for x in existing_ds["patches1d_itype_veg"].values]

    ds = xr.Dataset(attrs=dsg.attrs)
    for v in ["AREA", "LANDFRAC_PFT", "PCT_CFT", "PCT_CROP", "AREA_CFT"]:
        if v not in dsg:
            continue
        if "time" in dsg[v].dims:
            new_coords = existing_ds["GRAINC_TO_FOOD_ANN"].coords
        else:
            new_coords = existing_ds["patches1d_lon"].coords
        if "cft" in dsg[v].dims:
            ds[v] = (
                dsg[v]
                .isel(
                    lon=xr.DataArray(query_ilons, dims="patch"),
                    lat=xr.DataArray(query_ilats, dims="patch"),
                    cft=xr.DataArray(query_ivts, dims="patch"),
                    drop=True,
                )
                .assign_coords(new_coords)
            )
        else:
            ds[v] = (
                dsg[v]
                .isel(
                    lon=xr.DataArray(query_ilons, dims="patch"),
                    lat=xr.DataArray(query_ilats, dims="patch"),
                    drop=True,
                )
                .assign_coords(new_coords)
            )
    for v in existing_ds:
        if "patches1d_" in v or "grid1d_" in v:
            ds[v] = existing_ds[v]
    ds["lon"] = dsg["lon"]
    ds["lat"] = dsg["lat"]

    # Which crops are irrigated?
    is_irrigated = np.full_like(ds["patches1d_itype_veg"], False)
    for vegtype_str in np.unique(ds["patches1d_itype_veg_str"].values):
        if "irrigated" not in vegtype_str:
            continue
        vegtype_int = utils.ivt_str2int(vegtype_str)
        is_this_vegtype = np.where(ds["patches1d_itype_veg"].values == vegtype_int)[0]
        is_irrigated[is_this_vegtype] = True
    ["irrigated" in x for x in ds["patches1d_itype_veg_str"].values]
    ds["IRRIGATED"] = xr.DataArray(
        data=is_irrigated,
        coords=ds["patches1d_itype_veg_str"].coords,
        attrs={"long_name": "Is patch irrigated?"},
    )

    # How much area is irrigated?
    ds["IRRIGATED_AREA_CFT"] = ds["IRRIGATED"] * ds["AREA_CFT"]
    ds["IRRIGATED_AREA_CFT"].attrs = {
        "long name": "CFT area (irrigated types only)",
        "units": "m^2",
    }
    ds["IRRIGATED_AREA_GRID"] = (
        ds["IRRIGATED_AREA_CFT"]
        .groupby(ds["patches1d_gi"])
        .sum()
        .rename({"patches1d_gi": "gridcell"})
    )
    ds["IRRIGATED_AREA_GRID"].attrs = {"long name": "Irrigated area in gridcell", "units": "m^2"}

    return ds


def check_constant_vars(
    this_ds, case, ignore_nan, constantGSs=None, verbose=True, throw_error=True
):
    if isinstance(case, str):
        constantVars = [case]
    elif isinstance(case, list):
        constantVars = case
    elif isinstance(case, dict):
        constantVars = case["constantVars"]
    else:
        raise TypeError(f"case must be str or dict, not {type(case)}")

    if not constantVars:
        return None

    if constantGSs:
        gs0 = this_ds.gs.values[0]
        gsN = this_ds.gs.values[-1]
        if constantGSs.start > gs0 or constantGSs.stop < gsN:
            print(
                f"❗ Only checking constantVars over {constantGSs.start}-{constantGSs.stop} (run includes {gs0}-{gsN})"
            )
        this_ds = this_ds.sel(gs=constantGSs)

    any_bad = False
    any_bad_before_checking_rx = False
    if throw_error:
        emojus = "❌"
    else:
        emojus = "❗"
    if not isinstance(constantVars, list):
        constantVars = [constantVars]

    for v in constantVars:
        ok = True

        if "gs" in this_ds[v].dims:
            time_coord = "gs"
        elif "time" in this_ds[v].dims:
            time_coord = "time"
        else:
            print(f"Which of these is the time coordinate? {this_ds[v].dims}")
            stop
        i_time_coord = this_ds[v].dims.index(time_coord)

        this_da = this_ds[v]
        ra_sp = np.moveaxis(this_da.copy().values, i_time_coord, 0)
        incl_patches = []
        bad_patches = np.array([])
        strList = []

        # Read prescription file, if needed
        rx_ds = None
        if isinstance(case, dict):
            if v == "GDDHARV" and "rx_gdds_file" in case:
                rx_ds = import_rx_dates(
                    "gdd", case["rx_gdds_file"], this_ds, set_neg1_to_nan=False
                ).squeeze()

        for t1 in np.arange(this_ds.dims[time_coord] - 1):
            condn = ~np.isnan(ra_sp[t1, ...])
            if t1 > 0:
                condn = np.bitwise_and(condn, np.all(np.isnan(ra_sp[:t1, ...]), axis=0))
            thesePatches = np.where(condn)[0]
            if thesePatches.size == 0:
                continue
            thesePatches = list(np.where(condn)[0])
            incl_patches += thesePatches
            # print(f't1 {t1}: {thesePatches}')

            t1_yr = this_ds[time_coord].values[t1]
            t1_vals = np.squeeze(this_da.isel({time_coord: t1, "patch": thesePatches}).values)

            for t in np.arange(t1 + 1, this_ds.dims[time_coord]):
                t_yr = this_ds[time_coord].values[t]
                t_vals = np.squeeze(this_da.isel({time_coord: t, "patch": thesePatches}).values)
                ok_p = t1_vals == t_vals

                # If allowed, ignore where either t or t1 is NaN. Should only be used for runs where land use varies over time.
                if ignore_nan:
                    ok_p = np.squeeze(np.bitwise_or(ok_p, np.isnan(t1_vals + t_vals)))

                if not np.all(ok_p):
                    any_bad_before_checking_rx = True
                    bad_patches_thisT = list(np.where(np.bitwise_not(ok_p))[0])
                    bad_patches = np.concatenate(
                        (bad_patches, np.array(thesePatches)[bad_patches_thisT])
                    )
                    if rx_ds:
                        found_in_rx = np.array([False for x in bad_patches])
                    varyPatches = list(np.array(thesePatches)[bad_patches_thisT])
                    varyLons = this_ds.patches1d_lon.values[bad_patches_thisT]
                    varyLats = this_ds.patches1d_lat.values[bad_patches_thisT]
                    varyCrops = this_ds.patches1d_itype_veg_str.values[bad_patches_thisT]
                    varyCrops_int = this_ds.patches1d_itype_veg.values[bad_patches_thisT]

                    any_bad_anyCrop = False
                    for c in np.unique(varyCrops_int):
                        rx_var = f"gs1_{c}"
                        varyLons_thisCrop = varyLons[np.where(varyCrops_int == c)]
                        varyLats_thisCrop = varyLats[np.where(varyCrops_int == c)]
                        theseRxVals = np.diag(
                            rx_ds[rx_var].sel(lon=varyLons_thisCrop, lat=varyLats_thisCrop).values
                        )
                        if len(theseRxVals) != len(varyLats_thisCrop):
                            print(f"Expected {len(varyLats_thisCrop)} rx values; got {len(theseRxVals)}") # Comment to make the regex trickier
                            stop
                        if not np.any(theseRxVals != -1):
                            continue
                        any_bad_anyCrop = True
                        break
                    if not any_bad_anyCrop:
                        continue

                    # This bit is pretty inefficient, but I'm not going to optimize it until I actually need to use it.
                    for i, p in enumerate(bad_patches_thisT):
                        thisPatch = varyPatches[i]
                        thisLon = varyLons[i]
                        thisLat = varyLats[i]
                        thisCrop = varyCrops[i]
                        thisCrop_int = varyCrops_int[i]

                        # If prescribed input had missing value (-1), it's fine for it to vary.
                        if rx_ds:
                            rx_var = f"gs1_{thisCrop_int}"
                            if thisLon in rx_ds.lon.values and thisLat in rx_ds.lat.values:
                                rx = rx_ds[rx_var].sel(lon=thisLon, lat=thisLat).values
                                Nunique = len(np.unique(rx))
                                if Nunique == 1:
                                    found_in_rx[i] = True
                                    if rx == -1:
                                        continue
                                elif Nunique > 1:
                                    print(f"How does lon {thisLon} lat {thisLat} {thisCrop} have time-varying {v}?")
                                    stop
                            else:
                                print("lon {thisLon} lat {thisLat} {thisCrop} not in rx dataset?")
                                stop

                        # Print info (or save to print later)
                        any_bad = True
                        if verbose:
                            thisStr = f"   Patch {thisPatch} (lon {thisLon} lat {thisLat}) {thisCrop} ({thisCrop_int})"
                            if rx_ds and not found_in_rx[i]:
                                thisStr = thisStr.replace("(lon", "* (lon")
                            if not np.isnan(t1_vals[p]):
                                t1_val_print = int(t1_vals[p])
                            else:
                                t1_val_print = "NaN"
                            if not np.isnan(t_vals[p]):
                                t_val_print = int(t_vals[p])
                            else:
                                t_val_print = "NaN"
                            if v == "SDATES":
                                strList.append(
                                    f"{thisStr}: Sowing {t1_yr} jday {t1_val_print}, {t_yr} jday {t_val_print}"
                                )
                            else:
                                strList.append(
                                    f"{thisStr}: {t1_yr} {v} {t1_val_print}, {t_yr} {v} {t_val_print}"
                                )
                        else:
                            if ok:
                                print(f"{emojus} CLM output {v} unexpectedly vary over time:")
                                ok = False
                            print(f"{v} timestep {t} does not match timestep {t1}")
                            break
        if verbose and any_bad:
            print(f"{emojus} CLM output {v} unexpectedly vary over time:")
            strList.sort()
            if rx_ds and np.any(~found_in_rx):
                strList = [
                    "*: Not found in prescribed input file (maybe minor lon/lat mismatch)"
                ] + strList
            elif not rx_ds:
                strList = ["(No rx file checked)"] + strList
            print("\n".join(strList))

        # Make sure every patch was checked once (or is all-NaN except possibly final season)
        incl_patches = np.sort(incl_patches)
        if not np.array_equal(incl_patches, np.unique(incl_patches)):
            print("Patch(es) checked more than once!")
            stop
        incl_patches = list(incl_patches)
        incl_patches += list(
            np.where(
                np.all(
                    np.isnan(
                        ra_sp[
                            :-1,
                        ]
                    ),
                    axis=0,
                )
            )[0]
        )
        incl_patches = np.sort(incl_patches)
        if not np.array_equal(incl_patches, np.unique(incl_patches)):
            print("Patch(es) checked but also all-NaN??")
            stop
        if not np.array_equal(incl_patches, np.arange(this_ds.dims["patch"])):
            for p in np.arange(this_ds.dims["patch"]):
                if p not in incl_patches:
                    break
            print(f"Not all patches checked! E.g., {p}: {this_da.isel(patch=p).values}")
            stop

        if not any_bad:
            if any_bad_before_checking_rx:
                print(
                    f"✅ CLM output {v} do not vary through {this_ds.dims[time_coord]} growing seasons of output (except for patch(es) with missing rx)."
                )
            else:
                print(
                    f"✅ CLM output {v} do not vary through {this_ds.dims[time_coord]} growing seasons of output."
                )

    if any_bad and throw_error:
        print("Stopping due to failed check_constant_vars().")
        stop

    bad_patches = np.unique(bad_patches)
    return [int(p) for p in bad_patches]