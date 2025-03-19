# %%
"""
A simple script to revert CLM5 changes to parameters related to crop developmental phases
"""

import shutil
import os
from netCDF4 import Dataset


# %% Copy existing parameters to new file, open, and get info

file_old = "/glade/campaign/cesm/cesmdata/inputdata/lnd/clm2/paramdata/ctsm60_params_nfix.c241119.nc"
file_new = os.path.join(
    os.path.dirname(__file__),
    os.path.basename(__file__).replace(".py", ".nc"),
)
shutil.copyfile(file_old, file_new)

ds = Dataset(file_new, "r+")

# Get pft name list
pftname = [str(b"".join(x.data).strip(), "utf-8") for x in ds.variables["pftname"]]

# Function to set new values
def set_new_values(ds, pftname, this_var, new_values):
    for crop, new_value in new_values.items():
        for p, pft in enumerate(pftname):
            if crop not in pft:
                continue
            ds.variables[this_var][p] = new_value
    return ds

# Revert grnfill changes
this_var = "grnfill"
new_values = {
    "tropical_corn": 0.65,
    "cotton": 0.7,
    "rice": 0.6,
    "soybean": 0.7,
}
ds = set_new_values(ds, pftname, this_var, new_values)

# Revert lfemerg changes
this_var = "lfemerg"
new_values = {
    "rice": 0.05,
}
ds = set_new_values(ds, pftname, this_var, new_values)

# Save
ds.close()
