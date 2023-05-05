"""
CTSM-specific test that first performs a GDD-generating run, then calls
Python code to generate the maturity requirement file. This is then used
in a sowing+maturity forced run, which finally is tested to ensure
correct behavior.

Currently only supports 10x15 and f19_g17 resolutions. Eventually, I want
this test to be able to generate its own files at whatever resolution it's
called at. Well, really, the ultimate goal would be to give CLM the files
at the original resolution (for GGCMI phase 3, 0.5°) and have the stream
code do the interpolation. However, that wouldn't act on harvest dates
(which are needed for generate_gdds.py). I could have Python interpolate
those, but this would cause a potential inconsistency.
"""

import os
import re
import subprocess
from CIME.SystemTests.system_tests_common import SystemTestsCommon
from CIME.XML.standard_module_setup import *
from CIME.SystemTests.test_utils.user_nl_utils import append_to_user_nl_files
import shutil, glob

from rxcropmaturityparent import *

logger = logging.getLogger(__name__)

# SSR: This was originally ctsm_pylib, but the fact that it's missing
#      cf_units caused problems in utils.import_ds().
this_conda_env = "ctsm_pylib"

class RXCROPMATURITY58(rxcropmaturityparent):
    _start_year = 1958

