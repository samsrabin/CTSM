#!/usr/bin/env python3

"""System tests for RXCROPMATURITY tests"""

import tempfile
import shutil
import glob
import os
import sys
from pathlib import Path
from unittest import mock

import pytest


# -- add CTSM root to path (needed to import from cime_config)
_CTSM_PYTHON = os.path.join(os.path.dirname(os.path.realpath(__file__)), os.pardir, os.pardir)
_CTSM_ROOT = os.path.join(_CTSM_PYTHON, os.pardir)
sys.path.insert(1, _CTSM_PYTHON)
sys.path.insert(1, _CTSM_ROOT)


# pylint: disable=wrong-import-position
from ctsm import unit_testing

from cime_config.SystemTests.rxcropmaturity import RXCROPMATURITY

from CIME.scripts import create_test
from CIME.case import Case

# Allow names that pylint doesn't like, because otherwise I find it hard
# to make readable unit test names
# pylint: disable=invalid-name

# pylint: disable=protected-access


@pytest.fixture(name="temp_dir")
def fixture_temp_dir():
    """Create a temporary directory and clean it up after the test"""
    tmpdir = tempfile.mkdtemp()
    yield tmpdir
    shutil.rmtree(tmpdir)


@pytest.fixture(name="use_tmp_scratch")
def fixture_use_tmp_scratch(temp_dir, monkeypatch):
    """Temporarily set our environment's SCRATCH variable to be our temporary dir"""
    with mock.patch.dict(os.environ, clear=False):
        envvars = {
            "SCRATCH": temp_dir,
        }
        for k, v in envvars.items():
            monkeypatch.setenv(k, v)
        yield  # Restore the original environment afterward


# TODO: Change this to allow it to run on any supported machine. See machine= line in _create_test.
@pytest.mark.skipif(os.getenv("NCAR_HOST") != "derecho", reason="Test only runs on Derecho.")
class TestGetDirsForScripts:
    """Test RXCROPMATURITYSHARED._get_dirs_for_scripts()"""

    def _create_test(self, tmpdir):
        # Create test name
        systest = "RXCROPMATURITY"
        length = "Lm61"
        res = "f10_f10_mg37"
        compset = "IHistClm60BgcCrop"
        machine = "derecho"  # TODO: Change this to allow it to run on any supported machine
        compiler = "intel"  # TODO: Make this more flexible
        testmods = "clm-cropMonthOutput"
        test_name = f"{systest}_{length}.{res}.{compset}.{machine}_{compiler}.{testmods}"

        # Set up test case; stop before build phase
        cmdline_args = [
            "create_test",
            "--no-build",
            "--no-batch",
            test_name,
        ]
        with mock.patch.object(sys, "argv", cmdline_args):
            create_test_args = create_test.parse_command_line(sys.argv, "")
        create_test.create_test(*create_test_args)

        pattern = os.path.join(tmpdir, test_name + "*")
        dirs = glob.glob(pattern)
        assert len(dirs) == 1
        caseroot = dirs[0]
        return caseroot

    @mock.patch.object(RXCROPMATURITY, "_setup_case_gddgen")
    @mock.patch.object(RXCROPMATURITY, "_run_case_gdden")
    @mock.patch.object(RXCROPMATURITY, "_run_generate_gdds")
    @mock.patch.object(RXCROPMATURITY, "_setup_case_rxboth")
    @mock.patch.object(RXCROPMATURITY, "run_indv")
    @mock.patch.object(RXCROPMATURITY, "_run_check_rxboth_run")
    def test_get_dirs_for_scripts_full(
        self,
        _mock_run_check_rxboth_run,
        _mock_run_indv,
        _mock_setup_case_rxboth,
        _mock_run_generate_gdds,
        _mock_run_case_gdden,
        _mock_setup_case_gddgen,
        temp_dir,
        use_tmp_scratch,
    ):  # pylint: disable=unused-argument
        """Test _get_dirs_for_scripts() for full RXCROPMATURITY test"""
        caseroot = self._create_test(temp_dir)
        with Case(caseroot, read_only=False, non_local=False) as rxboth_case:
            systest_obj = RXCROPMATURITY(rxboth_case)
            systest_obj.run_phase()

        # Make sure that _generate_gdds_indir is in a subdirectory of the GDD-Generating case (or
        # its archive)
        rxboth_case_name = os.path.basename(caseroot)
        assert rxboth_case_name + ".gddgen" in Path(systest_obj._generate_gdds_indir).parts

        # Make sure that _check_rxboth_run_indir is in a subdirectory of the Prescribed Calendars
        # case (or its archive)
        rxboth_case_name = os.path.basename(caseroot)
        assert rxboth_case_name in Path(systest_obj._check_rxboth_run_indir).parts
