# No NaNs in inputs!

Including NaN values in netCDFs used as input to CESM can cause problems. This is especially bad if a variable's fill value is NaN: Code compiled with the `ifx` compiler will simply crash. These scripts are designed to easily identify and replace problematic input files.

## `get_replacement_fill_values`
This script:
1. Searches `bld/namelist_files/namelist_defaults_ctsm.xml` and all `user_nl_` files in `cime_config/` for netCDF files.
2. Checks those netCDF files for NaN fill values.
3. Asks the user what new fill values should be used. (If no elements of the variable are filled, the user can choose to delete the fill value.)
4. Saves the user's choices to a JSON file.

## `replace_fill_values`
This script reads the JSON file from `get_replacement_fill_values`. Then, for each affected netCDF file:
1. Creates a new version using the user's specified fill values (or requests for fill value deletion). New version has the `.nc` extension replaced with `no_nan_fill.nc`.
2. Replaces all occurrences of that netCDF file in `bld/namelist_files/namelist_defaults_ctsm.xml` and our `cime_config/**/user_nl_*` file with the path to the new file.
3. Pauses to allow the user time to review, commit changes, etc.
4. Continues when the user is ready, or exits otherwise.
