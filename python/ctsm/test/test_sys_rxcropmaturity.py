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
# pylint: disable=wrong-import-order
from ctsm import unit_testing

from cime_config.SystemTests.rxcropmaturity import RXCROPMATURITY, BASELINE_SUBDIR_WITH_INPUTS
from cime_config.SystemTests.rxcropmaturityscripts import RXCROPMATURITYSCRIPTS

from CIME.scripts import create_test
from CIME.case import Case

# Allow names that pylint doesn't like, because otherwise I find it hard
# to make readable unit test names
# pylint: disable=invalid-name

# pylint: disable=protected-access

BASELINE_VERSION_OF_SCRIPT_INPUT_FILES = "blver"
TEST_GRID = "f10_f10_mg37"
TEST_RES = "10x15"


@pytest.fixture(name="use_tmp_scratch")
def fixture_use_tmp_scratch(tmp_path, monkeypatch):
    """Temporarily set our environment's SCRATCH variable to be our temporary dir"""
    with mock.patch.dict(os.environ, clear=False):
        envvars = {
            "SCRATCH": str(tmp_path),
        }
        for k, v in envvars.items():
            monkeypatch.setenv(k, v)
        yield  # Restore the original environment afterward


@pytest.fixture(name="create_my_test")
def fixture_create_my_test(tmp_path):
    """Fixture factory that returns a function to create a test case"""

    def _create_test(systest: str):
        # Create test name
        length = "Lm61"
        grid = TEST_GRID
        compset = "IHistClm60BgcCrop"
        machine = "derecho"  # TODO: Change this to allow it to run on any supported machine
        compiler = "intel"  # TODO: Make this more flexible
        testmods = "clm-cropMonthOutput"
        test_name = f"{systest}_{length}.{grid}.{compset}.{machine}_{compiler}.{testmods}"

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

        # We're going to be working in the Prescribed Calendars case only
        pattern = os.path.join(str(tmp_path), test_name + "*")
        dirs = glob.glob(pattern)
        dirs = [d for d in dirs if not d.endswith(".gddgen")]
        assert len(dirs) == 1
        caseroot = dirs[0]

        return caseroot

    return _create_test


# TODO: Change this to allow it to run on any supported machine. See machine= line in create_test.
@pytest.mark.skipif(os.getenv("NCAR_HOST") != "derecho", reason="Test only runs on Derecho.")
class TestGetDirsForScripts:
    """Test RXCROPMATURITYSHARED._get_dirs_for_scripts()"""

    @mock.patch.object(RXCROPMATURITY, "_setup_case_gddgen")
    @mock.patch.object(RXCROPMATURITY, "_run_case_gddgen")
    @mock.patch.object(RXCROPMATURITY, "_run_generate_gdds")
    @mock.patch.object(RXCROPMATURITY, "_setup_case_rxboth")
    @mock.patch.object(RXCROPMATURITY, "run_indv")
    @mock.patch.object(RXCROPMATURITY, "_run_check_rxboth_run")
    @mock.patch.object(RXCROPMATURITY, "_get_years_for_scripts")
    def test_get_dirs_for_scripts_full(
        self,
        _mock_get_years_for_scripts,
        _mock_run_check_rxboth_run,
        _mock_run_indv,
        _mock_setup_case_rxboth,
        _mock_run_generate_gdds,
        _mock_run_case_gddgen,
        _mock_setup_case_gddgen,
        tmp_path,
        use_tmp_scratch,
        create_my_test,
    ):  # pylint: disable=unused-argument
        """Test _get_dirs_for_scripts() for full RXCROPMATURITY test"""
        caseroot = create_my_test("RXCROPMATURITY")
        with Case(caseroot, read_only=False, non_local=False) as rxboth_case:
            systest_obj = RXCROPMATURITY(rxboth_case)
            systest_obj.run_phase()

        rxboth_case_name = os.path.basename(caseroot)

        # Make sure that _generate_gdds_indir is in a subdirectory of the GDD-Generating case (or
        # its archive)
        assert rxboth_case_name + ".gddgen" in Path(systest_obj._generate_gdds_indir).parts

        # Make sure that _check_rxboth_run_indir is in a subdirectory of the Prescribed Calendars
        # case (or its archive)
        assert rxboth_case_name in Path(systest_obj._check_rxboth_run_indir).parts

    @mock.patch.object(RXCROPMATURITYSCRIPTS, "_setup_case_gddgen")
    @mock.patch.object(RXCROPMATURITYSCRIPTS, "_run_case_gddgen")
    @mock.patch.object(RXCROPMATURITYSCRIPTS, "_run_generate_gdds")
    @mock.patch.object(RXCROPMATURITYSCRIPTS, "_setup_case_rxboth")
    @mock.patch.object(RXCROPMATURITYSCRIPTS, "run_indv")
    @mock.patch.object(RXCROPMATURITYSCRIPTS, "_run_check_rxboth_run")
    @mock.patch.object(RXCROPMATURITYSCRIPTS, "_get_baseline_dir")
    @mock.patch.object(RXCROPMATURITYSCRIPTS, "_get_years_for_scripts")
    @mock.patch(
        "cime_config.SystemTests.rxcropmaturity.BASELINE_VERSION_OF_SCRIPT_INPUT_FILES",
        BASELINE_VERSION_OF_SCRIPT_INPUT_FILES,
    )
    def test_get_dirs_for_scripts_only(
        self,
        _mock_get_years_for_scripts,
        mock_get_baseline_dir,
        _mock_run_check_rxboth_run,
        _mock_run_indv,
        _mock_setup_case_rxboth,
        _mock_run_generate_gdds,
        _mock_run_case_gddgen,
        _mock_setup_case_gddgen,
        tmp_path,
        use_tmp_scratch,
        create_my_test,
    ):  # pylint: disable=unused-argument
        """Test _get_dirs_for_scripts() for RXCROPMATURITYSCRIPTS test"""

        # Define fake baseline dir
        baseline_root = baseline_dir = str(tmp_path / "baseline_dir")
        mock_get_baseline_dir.return_value = baseline_root
        prev_test_baseline = os.path.join(
            baseline_root,
            BASELINE_VERSION_OF_SCRIPT_INPUT_FILES,
            "prev_test",
        )

        # Create and fill fake baseline dir
        lnd_in = os.path.join(prev_test_baseline, "CaseDocs", "lnd_in")
        os.makedirs(os.path.dirname(lnd_in))
        with open(lnd_in, "w", encoding="utf8") as f:
            f.write(f"-res {TEST_RES}")
        for d in ["generate_gdds", "check_rxboth_run"]:
            os.makedirs(
                os.path.join(
                    prev_test_baseline,
                    BASELINE_SUBDIR_WITH_INPUTS,
                    d,
                )
            )

        # Create the test, doing everything through RUN except BUILD
        assert tmp_path.exists()
        caseroot = create_my_test("RXCROPMATURITYSCRIPTS")
        with Case(caseroot, read_only=False, non_local=False) as rxboth_case:
            systest_obj = RXCROPMATURITYSCRIPTS(rxboth_case)
            assert systest_obj._scriptsonly_test
            systest_obj.run_phase()

        # Check that scripts will be using data from our fake baseline
        assert systest_obj._generate_gdds_indir.startswith(baseline_dir)
        assert systest_obj._check_rxboth_run_indir.startswith(baseline_dir)
