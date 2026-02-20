#!/usr/bin/env python3

"""System tests for RXCROPMATURITY tests"""

import tempfile
import shutil
import glob
import os
import sys
import re
from pathlib import Path
from unittest import mock
from typing import Tuple

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
from cime_config.SystemTests.rxcropmaturity import CASEDOC_WITH_STOP_INFO
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
KNOWN_GOOD_LENGTH_STR = "Lm61"

# TODO: Change this to allow it to run on any supported machine. See machine= line in create_test.
pytestmark = pytest.mark.skipif(
    os.getenv("NCAR_HOST") != "derecho", reason="Test only runs on Derecho."
)


def parse_length_str(length_str: str) -> Tuple[int, str]:
    """
    Given a test run length str like Lm61 or Ly3, parse it into stop_n and stop_option
    """

    # Get stop_n
    m = re.search(r"(\d+)", length_str)
    assert m is not None, f"Couldn't get number from length_str: {length_str}"
    n = len(m.groups())
    assert n == 1, f"Expected 1 match group; found {n}"
    stop_n = int(m.group(1))

    # Get stop_option
    assert(length_str[0] == "L")
    stop_opt_code = length_str[1]
    match stop_opt_code:
        case "d":
            stop_option = "ndays"
        case "m":
            stop_option = "nmonths"
        case "y":
            stop_option = "nyears"
        case _:
            raise ValueError(f"Unknown stop_option code: {stop_opt_code}")
    return stop_n, stop_option


@pytest.fixture(autouse=True)
def _mock_get_baseline_dir(tmp_path):
    """Mock RXCROPMATURITYSCRIPTS._get_baseline_dir() for all tests in this module"""
    baseline_root = str(tmp_path / "baseline_dir")
    with mock.patch.object(RXCROPMATURITYSCRIPTS, "_get_baseline_dir", return_value=baseline_root):
        yield baseline_root


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

    def _create_test(systest: str, length: str = KNOWN_GOOD_LENGTH_STR):
        # Create test name
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


@pytest.fixture(name="fake_baseline")
def fixture_fake_baseline(tmp_path):
    """Create and populate a fake baseline directory structure for testing"""
    # Mock BASELINE_VERSION_OF_SCRIPT_INPUT_FILES for all tests using this fixture
    with mock.patch(
        "cime_config.SystemTests.rxcropmaturity.BASELINE_VERSION_OF_SCRIPT_INPUT_FILES",
        BASELINE_VERSION_OF_SCRIPT_INPUT_FILES,
    ):
        # Define fake baseline dir
        baseline_root = baseline_dir = str(tmp_path / "baseline_dir")
        prev_test_baseline = os.path.join(
            baseline_root,
            BASELINE_VERSION_OF_SCRIPT_INPUT_FILES,
            "prev_test",
        )

        # Create and fill fake baseline dir
        # First, write CaseDocs/lnd_in
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
        # Next, write whichever CaseDoc file has the run stop info
        stop_n, stop_option = parse_length_str(KNOWN_GOOD_LENGTH_STR)
        file_with_stop_info = os.path.join(os.path.dirname(lnd_in), CASEDOC_WITH_STOP_INFO)
        with open(file_with_stop_info, "a", encoding="utf8") as f:
            f.write(f"     stop_n = {stop_n}\n     stop_option = {stop_option}\n")

        yield baseline_dir


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
    @mock.patch.object(RXCROPMATURITYSCRIPTS, "_get_years_for_scripts")
    def test_get_dirs_for_scripts_only(
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
        fake_baseline,
    ):  # pylint: disable=unused-argument
        """Test _get_dirs_for_scripts() for RXCROPMATURITYSCRIPTS test"""

        # Create the test, doing everything through RUN except BUILD
        assert tmp_path.exists()
        caseroot = create_my_test("RXCROPMATURITYSCRIPTS")
        with Case(caseroot, read_only=False, non_local=False) as rxboth_case:
            systest_obj = RXCROPMATURITYSCRIPTS(rxboth_case)
            assert systest_obj._scriptsonly_test
            systest_obj.run_phase()

        # Check that scripts will be using data from our fake baseline
        assert systest_obj._generate_gdds_indir.startswith(fake_baseline)
        assert systest_obj._check_rxboth_run_indir.startswith(fake_baseline)


class TestRunLength:
    """Test handling of RXCROPMATURITYSHARED run length"""

    @pytest.mark.parametrize("length", [KNOWN_GOOD_LENGTH_STR, "Lm60", "Ly5"])
    def test_rxcropmaturity_ok(
        self, length, use_tmp_scratch, create_my_test
    ):  # pylint: disable=unused-argument
        """Test valid run lengths for RXCROPMATURITY test, ensuring no fail"""
        systest = RXCROPMATURITY
        caseroot = create_my_test(systest.__name__, length)
        with Case(caseroot, read_only=False, non_local=False) as rxboth_case:
            systest(rxboth_case)

    @pytest.mark.parametrize("length", [KNOWN_GOOD_LENGTH_STR, "Ld1"])
    def test_rxcropmaturityscripts_ok(
        self, length, use_tmp_scratch, create_my_test, fake_baseline
    ):  # pylint: disable=unused-argument
        """Test valid run lengths for RXCROPMATURITYSCRIPTS test, ensuring no fail"""
        systest = RXCROPMATURITYSCRIPTS
        caseroot = create_my_test(systest.__name__, length)
        with Case(caseroot, read_only=False, non_local=False) as rxboth_case:
            systest(rxboth_case)

    @pytest.mark.parametrize("length", ["Ld1", "Lm59", "Ld1824"])
    def test_rxcropmaturity_too_short_error(
        self, length, use_tmp_scratch, create_my_test
    ):  # pylint: disable=unused-argument
        """Test that error is thrown if RXCROPMATURITY test is too short"""
        systest = RXCROPMATURITY
        caseroot = create_my_test(systest.__name__, length)
        with Case(caseroot, read_only=False, non_local=False) as rxboth_case:
            with pytest.raises(RuntimeError, match="RXCROPMATURITY must be run for at least"):
                systest(rxboth_case)
