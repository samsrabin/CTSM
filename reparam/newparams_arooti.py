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

# Revert arooti changes
this_var = "arooti"
new_values = {
    "corn": 0.4,
    "cotton": 0.5,
    "rice": 0.3,
    "soybean": 0.5,
    "sugarcane": 0.4,
    "spring_wheat": 0.3,
}
ds = set_new_values(ds, pftname, this_var, new_values)


# Save
ds.close()
