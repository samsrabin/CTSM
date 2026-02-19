"""
CTSM-specific test that first performs a GDD-generating run, then calls
Python code to generate the maturity requirement file. This is then used
in a sowing+maturity forced run, which finally is tested to ensure
correct behavior.

Currently only supports 0.9x1.25, 1.9x2.5, and 10x15 resolutions. Eventually,
this test should be able to generate its own files at whatever resolution it's
called at. Well, really, the ultimate goal would be to give CLM the files
at the original resolution (for GGCMI phase 3, 0.5°) and have the stream
code do the interpolation. However, that wouldn't act on harvest dates
(which are needed for generate_gdds.py). I could have Python interpolate
those, but this would cause a potential inconsistency.
"""

import os
import re
import shutil
import glob
from typing import List, Tuple

try:
    from . import systemtest_utils as stu
    from cime.CIME.SystemTests.system_tests_common import SystemTestsCommon
    from cime.CIME.XML.standard_module_setup import logging
    from cime.CIME.SystemTests.test_utils.user_nl_utils import append_to_user_nl_files
    from cime.CIME.case import Case
    from cime.CIME.utils import safe_copy
    from python.ctsm.machine_defaults import MACHINE_DEFAULTS
    from python.ctsm.crop_calendars.systemtest_helpers.utils import (
        get_usable_years_for_check_rxboth_run,
    )
    from python.ctsm.crop_calendars.cropcal_constants import (
        FILE_PATTERN_FOR_CHECK_RXBOTH_RUN,
    )
    from python.ctsm.crop_calendars.cropcal_utils_1stparty import (
        check_first_last_seasons,
    )
    from python.ctsm.ctsm_logging import error, log
except ImportError:
    import systemtest_utils as stu
    from CIME.SystemTests.system_tests_common import SystemTestsCommon
    from CIME.XML.standard_module_setup import logging
    from CIME.SystemTests.test_utils.user_nl_utils import append_to_user_nl_files
    from CIME.case import Case
    from CIME.utils import safe_copy

    _CTSM_PYTHON = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), os.pardir, "python"
    )
    import sys

    sys.path.insert(1, _CTSM_PYTHON)
    from ctsm.crop_calendars.systemtest_helpers.utils import (
        get_usable_years_for_check_rxboth_run,
    )
    from ctsm.crop_calendars.cropcal_constants import FILE_PATTERN_FOR_CHECK_RXBOTH_RUN
    from ctsm.machine_defaults import MACHINE_DEFAULTS
    from ctsm.crop_calendars.cropcal_utils_1stparty import check_first_last_seasons
    from ctsm.ctsm_logging import error, log

logger = logging.getLogger(__name__)

# See _copy_extra_files_from_run_to_baseline()
BASELINE_SUBDIR_WITH_INPUTS = "inputs_for_cropcal_script_tests"

# See _get_baseline_dir_with_files_from_gddgen_run()
BASELINE_VERSION_OF_SCRIPT_INPUT_FILES = "improve-rxcropmaturity-tests.7d9d830de"


def _copy_extra_files_from_run_to_baseline(
    which_script: str, gddgen_out_dir: str, baseline_dir: str
) -> None:
    """
    When we generate a baseline of an RXCROPMATURITY test, we want to save all the h1 and h2 files
    for future use by RXCROPMATURITYSCRIPTS tests. This function copies them to the RXCROPMATURITY
    test's baseline directory, in a new subdirectory. If the file already exists at the top level
    of the baseline directory, this script will just softlink it into the subdirectory.
    """
    basename_pattern = None
    if which_script == "generate_gdds":
        basename_pattern = "*clm2.h[12]i*.nc"
    elif which_script == "check_rxboth_run":
        basename_pattern = FILE_PATTERN_FOR_CHECK_RXBOTH_RUN
    else:
        error(logger, f"Unrecognized {which_script=}", error_type=ValueError)

    if not os.path.exists(gddgen_out_dir):
        msg = f"File not found: {gddgen_out_dir}"
        error(logger, msg, error_type=FileNotFoundError)
    if not os.path.exists(baseline_dir):
        msg = f"File not found: {baseline_dir}"
        error(logger, msg, error_type=FileNotFoundError)

    # Get files to copy
    file_list = glob.glob(pattern := os.path.join(gddgen_out_dir, basename_pattern))
    if not file_list:
        error(
            logger,
            f"No files found matching pattern: '{pattern}'",
            error_type=FileNotFoundError,
        )

    # Create subdir in baseline
    baseline_subdir = os.path.join(
        baseline_dir, BASELINE_SUBDIR_WITH_INPUTS, which_script
    )
    os.makedirs(baseline_subdir, mode=0o755)  # rwxr-xr-x

    for file in file_list:
        target_file = os.path.join(baseline_subdir, os.path.basename(file))
        existing_file = os.path.join(baseline_dir, os.path.basename(file))
        if os.path.exists(existing_file):
            os.symlink(existing_file, target_file)
        else:
            # See safe_copy for why preserving metadata while copying baseline files is a bad idea
            safe_copy(file, target_file, preserve_meta=False)
            # Explicitly set permissions rw-r--r-- to ensure all-readable
            os.chmod(target_file, 0o644)


def _get_baseline_dir_with_files_from_run(
    which_script: str, baseline_dir: str, res: str
) -> str:
    """
    Get the directory containing baseline files from a run.

    This function searches for baseline files from a previous GDD-Generating or Prescribed Calendars
    run that match the specified resolution. It looks in a versioned baseline directory for tests
    with the required output files.

    Note that, if multiple such tests exist, it will only return the first it sees.

    Args:
        which_script (str): Which script will be using this data? See options in
                            _copy_extra_files_from_run_to_baseline().
        baseline_dir (str): The root directory containing baseline data.
        res (str): The resolution string to match (e.g., grid resolution).

    Returns:
        str: Path to the directory containing the matching GDD generation output files.

    Raises:
        FileNotFoundError: If no baseline directories are found matching the pattern,
            or if no tests are found with archived data matching the specified resolution.
        RuntimeError: If multiple matches for the resolution are found in a single lnd_in file
            (expected at most one match).
    """
    # Get the path to the baseline version we want to use
    this_baseline_dir = os.path.join(
        baseline_dir, BASELINE_VERSION_OF_SCRIPT_INPUT_FILES
    )

    # Find all cases in that baseline with outputs we can use
    gddgen_out_dir_list = glob.glob(
        pattern := os.path.join(
            this_baseline_dir, "*", BASELINE_SUBDIR_WITH_INPUTS, which_script
        )
    )
    gddgen_out_dir_list.sort()
    if not gddgen_out_dir_list:
        msg = f"No files found matching pattern: {pattern}"
        error(logger, msg, error_type=FileNotFoundError)

    # Find a case matching this case's grid
    baseline_dir_with_files_from_gddgen_run = None
    for d in gddgen_out_dir_list:
        lnd_in = os.path.join(d, os.pardir, os.pardir, "CaseDocs", "lnd_in")
        with open(lnd_in, "r", encoding="utf8") as f:
            matches = re.findall(rf"-res {re.escape(res)}\b", f.read())
            if not matches:
                continue
            if len(matches) > 1:
                error(
                    logger,
                    f"Expected at most 1 match for '-res {res}' in {lnd_in}; got {len(matches)}",
                    error_type=RuntimeError,
                )
            baseline_dir_with_files_from_gddgen_run = d
            break
    if not baseline_dir_with_files_from_gddgen_run:
        error(
            logger,
            f"No tests found in {this_baseline_dir} with archived data matching res {res}",
            error_type=FileNotFoundError,
        )

    return baseline_dir_with_files_from_gddgen_run


def _get_seasons_for_generate_gdds(run_startyear: int, run_nyears: int) -> Tuple[int]:
    """
    Get and check the seasons to be used by generate_gdds script
    """
    # It can take up to two years for all sowings to obey the prescribed dates.
    first_season_offset = 2
    first_season = run_startyear + first_season_offset

    # You don't want to use the last year because some gridcells might not finish out the season
    # (will happen after Jan. 1). Then I think I subtracted another year to be extra safe in case
    # the model didn't complete its final calendar year.
    last_season_offset = 2
    last_season = run_startyear + run_nyears - last_season_offset

    # Check that the seasons are valid inputs to generate_gdds
    try:
        check_first_last_seasons(first_season, last_season)
    except ValueError as exc:
        min_run_nyears = first_season_offset + last_season_offset
        if run_nyears < min_run_nyears:
            error(logger, f"run_nyears < minimum ({min_run_nyears})", error_type=ValueError)
        else:
            raise exc

    return first_season, last_season


class RXCROPMATURITYSHARED(SystemTestsCommon):
    """
    Parent class of RXCROPMATURITY and RXCROPMATURITYSCRIPTS SystemTests
    """

    # pylint: disable=too-many-instance-attributes
    def __init__(self, case: Case) -> None:
        # initialize an object interface to the SMS system test
        SystemTestsCommon.__init__(self, case)

        # To help with IDE tools
        self._case: Case

        # Directories:
        #   _check_rxboth_run_indir: Directory with files from Prescribed Calendars run, to be used
        #                            as input to check_rxboth_run.py.
        #   _gddgen_baseline_dir: If generating an RXCROPMATURITY baseline, the relevant files from
        #                         _gddgen_phase_outdir will be copied here: A subdirectory of the
        #                         case's baseline directory.
        #   _gddgen_phase_outdir: Where the results from the GDD-Generating run are saved after that
        #                         case completes.
        #   _generate_gdds_indir: Directory with files from GDD-Generating run, to be used as input
        #                         to generate_gdds.py.
        #   _generate_gdds_outdir: The directory where generate_gdds.py will save its outputs.
        #   _prescribed_calendars_phase_outdir: Where the results from the Prescribed Calendars run
        #                                       are saved after that case completes.
        self._check_rxboth_run_indir: str = None
        self._generate_gdds_indir: str = None
        self._gddgen_baseline_dir: str = None
        self._gddgen_phase_outdir: str = None
        self._generate_gdds_outdir: str = None
        self._prescribed_calendars_phase_outdir: str = None

        # Define other variables that will be set outside __init__()

        # Define other variables that will be set outside __init__()
        self._cfg_path: str = None
        self._flanduse_timeseries_in: str = None
        self._fsurdat_in: str = None
        self._fsurdat_out: str = None
        self._lnd_in_path: str = None
        self._path_gddgen: str = None
        self._run_startyear: int = None
        self._run_nyears: int = None
        self._this_conda_env: str = None

        # Where is our CTSM checkout?
        self._ctsm_root: str = self._case.get_value("COMP_ROOT_DIR_LND")

        # Is this a real RXCROPMATURITY test or not?
        casebaseid: str = self._case.get_value("CASEBASEID")
        full_test = "RXCROPMATURITY_" in casebaseid
        self._scriptsonly_test = "RXCROPMATURITYSCRIPTS_" in casebaseid
        # Assert that exactly one is true (XOR)
        assert full_test ^ self._scriptsonly_test

        # Get the run start year
        run_startdate: str = self._case.get_value("RUN_STARTDATE")
        self._run_startyear = int(run_startdate.split("-")[0])

        # Get the number of complete years that will be run
        self._run_nyears = self._get_run_nyears()

        # Only allow RXCROPMATURITY to be called with test cropMonthOutput
        if casebaseid.split("-")[-1] != "cropMonthOutput":
            error_message = (
                "Only call RXCROPMATURITY with test cropMonthOutput "
                + "to avoid potentially huge sets of daily outputs."
            )
            error(logger, error_message, error_type=RuntimeError)

        # Get files with prescribed sowing and harvest dates
        self._get_rx_dates()

        # Get cultivar maturity requirement file to fall back on if not generating it here
        self._gdds_file: str = None
        self._fallback_gdds_file = os.path.join(
            os.path.dirname(self._sdatefile), "gdds_20230829_161011.nc"
        )

        # Which conda environment should we use?
        self._get_conda_env()

    def _get_run_nyears(self) -> int:
        """
        Get the number of complete years that will be run, checking that it's enough for the scripts
        to work and be tested properly.
        """
        # Ensure run length is at least 5 years. Minimum to produce one complete growing season
        # (i.e., two complete calendar years) actually 4 years, but that only gets you 1 season
        # usable for GDD generation, so you can't check for season-to-season consistency.
        stop_n: int = self._case.get_value("STOP_N")
        stop_option: str = self._case.get_value("STOP_OPTION")
        stop_n_orig = stop_n
        stop_option_orig = stop_option
        if "nsecond" in stop_option:
            stop_n /= 60
            stop_option = "nminutes"
        if "nminute" in stop_option:
            stop_n /= 60
            stop_option = "nhours"
        if "nhour" in stop_option:
            stop_n /= 24
            stop_option = "ndays"
        if "nday" in stop_option:
            stop_n /= 365
            stop_option = "nyears"
        if "nmonth" in stop_option:
            stop_n /= 12
            stop_option = "nyears"
        error_message = None
        if "nyear" not in stop_option:
            error_message = (
                f"STOP_OPTION ({stop_option_orig}) must be nsecond(s), nminute(s), "
                + "nhour(s), nday(s), nmonth(s), or nyear(s)"
            )
        elif not self._scriptsonly_test and stop_n < 5:
            error_message = (
                "RXCROPMATURITY must be run for at least 5 years; you requested "
                + f"{stop_n_orig} {stop_option_orig[1:]}"
            )
        if error_message is not None:
            error(logger, error_message, error_type=RuntimeError)

        # Get the number of complete years that will be run
        return int(stop_n)

    def run_phase(self, h1_inst: bool = False) -> None:
        # Modeling this after the SSP test, we create a clone to be the case whose outputs we don't
        # want to be saved as baseline.

        # -------------------------------------------------------------------
        # (1) Set up GDD-generating run
        # -------------------------------------------------------------------
        # Create clone to be GDD-Generating case
        case_rxboth, caseroot, case_gddgen = self._create_case_gddgen()

        os.chdir(self._path_gddgen)
        self._set_active_case(case_gddgen)

        self._setup_case_gddgen(h1_inst, caseroot, case_gddgen)

        # Get the directories that scripts will use. Do this now, before running any cases, to fail
        # quickly if only doing an RXCROPMATURITYSCRIPTS test but there's no baseline available.
        self._get_dirs_for_scripts(case_gddgen, case_rxboth)

        # -------------------------------------------------------------------
        # (2) Perform GDD-generating run and generate prescribed GDDs file
        # -------------------------------------------------------------------
        self._run_case_gdden()

        # Process outputs into new crop maturity requirements file
        self._run_generate_gdds(self._generate_gdds_indir)

        # -------------------------------------------------------------------
        # (3) Set up and perform Prescribed Calendars run
        # -------------------------------------------------------------------
        os.chdir(caseroot)
        self._set_active_case(case_rxboth)

        # Set up stuff that applies to both tests
        self._setup_case_rxboth(h1_inst)

        # Run
        self.run_indv()

        # -------------------------------------------------------------------
        # (4) Check Prescribed Calendars run
        # -------------------------------------------------------------------
        log(logger, "RXCROPMATURITY log:  output check: Prescribed Calendars")
        self._run_check_rxboth_run()

    def _setup_case_rxboth(self, h1_inst):
        self._setup_all(h1_inst)

        # Add stuff specific to Prescribed Calendars run
        log(logger, "RXCROPMATURITY log:  modify user_nl files: Prescribed Calendars")
        self._append_to_user_nl_clm(
            [
                "generate_crop_gdds = .false.",
                f"stream_fldFileName_cultivar_gdds = '{self._gdds_file}'",
            ]
        )

    def _run_case_gdden(self):
        log(logger, "RXCROPMATURITY log:  Start GDD-Generating run")

        # As per SSP test:
        # "No history files expected, set suffix=None to avoid compare error"
        # We *do* expect history files here, but anyway. This works.
        self._skip_pnl = False

        # Run GDD-Generating case
        self.run_indv(suffix=None, st_archive=True)

    # TODO: Move this to be module-level, since self isn't used
    def _get_baseline_dir(self, case: Case):
        return MACHINE_DEFAULTS[case.get_value("MACH")].baseline_dir

    def _get_dirs_for_scripts(self, case_gddgen: Case, case_rxboth: Case):
        if self._scriptsonly_test:
            baseline_dir = self._get_baseline_dir(case_gddgen)
            lnd_grid = case_gddgen.get_value("LND_GRID")
            # Input for generate_gdds.py
            self._generate_gdds_indir = _get_baseline_dir_with_files_from_run(
                "generate_gdds", baseline_dir, lnd_grid
            )
            # Input for check_rxboth_run.py
            self._check_rxboth_run_indir = _get_baseline_dir_with_files_from_run(
                "check_rxboth_run", baseline_dir, lnd_grid
            )
        else:
            # Input for generate_gdds.py
            dout_sr = case_gddgen.get_value("DOUT_S_ROOT")
            self._gddgen_phase_outdir = os.path.join(dout_sr, "lnd", "hist")
            self._generate_gdds_indir = self._gddgen_phase_outdir
            # Input for check_rxboth_run.py
            self._prescribed_calendars_phase_outdir = case_rxboth.get_value("RUNDIR")
            self._check_rxboth_run_indir = self._prescribed_calendars_phase_outdir

    def _setup_case_gddgen(self, h1_inst: bool, caseroot: str, case_gddgen: Case):
        os.chdir(self._path_gddgen)
        self._set_active_case(case_gddgen)

        # Set up stuff that applies to both tests
        self._setup_all(h1_inst)

        # Add stuff specific to GDD-Generating run
        log(logger, "RXCROPMATURITY log:  modify user_nl files: generate GDDs")
        self._append_to_user_nl_clm(
            [
                "stream_fldFileName_cultivar_gdds = ''",
                "generate_crop_gdds = .true.",
                "use_mxmat = .false.",
                " ",
                "! (h2) Daily outputs for GDD generation and figure-making",
                "hist_fincl3 = 'GDDACCUM', 'GDDHARV'",
                "hist_nhtfrq(3) = -24",
                "hist_mfilt(3) = 365",
                "hist_type1d_pertape(3) = 'PFTS'",
                "hist_dov2xy(3) = .false.",
            ]
        )

        # If flanduse_timeseries is defined, we need to make a static version for this test. This
        # should have every crop in most of the world.
        self._get_flanduse_timeseries_in(case_gddgen)
        if self._flanduse_timeseries_in is not None:
            # Download files from the server, if needed
            case_gddgen.check_all_input_data()

            # Copy needed file from original to gddgen directory
            shutil.copyfile(
                os.path.join(caseroot, ".env_mach_specific.sh"),
                os.path.join(self._path_gddgen, ".env_mach_specific.sh"),
            )

            # Make custom version of surface file
            log(logger, "RXCROPMATURITY log:  run fsurdat_modifier")
            self._run_fsurdat_modifier()

    def _create_case_gddgen(self):
        log(logger, "RXCROPMATURITY log:  cloning setup")
        case_rxboth = self._case
        caseroot: str = self._case.get_value("CASEROOT")
        clone_path = f"{caseroot}.gddgen"
        self._path_gddgen = clone_path
        if os.path.exists(self._path_gddgen):
            shutil.rmtree(self._path_gddgen)
        log(logger, "RXCROPMATURITY log:  cloning")
        case_gddgen: Case = self._case.create_clone(clone_path, keepexe=True)
        log(logger, "RXCROPMATURITY log:  done cloning")
        return case_rxboth, caseroot, case_gddgen

    # Get sowing and harvest dates for this resolution.
    def _get_rx_dates(self) -> None:
        # Eventually, I want to remove these hard-coded resolutions so that this test can generate
        # its own sowing and harvest date files at whatever resolution is requested.
        lnd_grid: str = self._case.get_value("LND_GRID")
        input_data_root: str = self._case.get_value("DIN_LOC_ROOT")
        processed_crop_dates_dir = (
            f"{input_data_root}/lnd/clm2/cropdata/calendars/processed"
        )
        if lnd_grid == "10x15":
            ts = "20230330_165301"
            self._sdatefile = os.path.join(
                processed_crop_dates_dir,
                f"sdates_ggcmi_crop_calendar_phase3_v1.01_nninterp-f10_f10_mg37.2000-2000.{ts}.nc",
            )
            self._hdatefile = os.path.join(
                processed_crop_dates_dir,
                f"hdates_ggcmi_crop_calendar_phase3_v1.01_nninterp-f10_f10_mg37.2000-2000.{ts}.nc",
            )
        elif lnd_grid == "1.9x2.5":
            ts = "20230102_175625"
            self._sdatefile = os.path.join(
                processed_crop_dates_dir,
                f"sdates_ggcmi_crop_calendar_phase3_v1.01_nninterp-f19_g17.2000-2000.{ts}.nc",
            )
            self._hdatefile = os.path.join(
                processed_crop_dates_dir,
                f"hdates_ggcmi_crop_calendar_phase3_v1.01_nninterp-f19_g17.2000-2000.{ts}.nc",
            )
        elif lnd_grid == "0.9x1.25":
            ts = "20230520_13441"
            self._sdatefile = os.path.join(
                processed_crop_dates_dir,
                f"sdates_ggcmi_crop_calendar_phase3_v1.01_nninterp-f09_g17.2000-2000.{ts}7.nc",
            )
            self._hdatefile = os.path.join(
                processed_crop_dates_dir,
                f"hdates_ggcmi_crop_calendar_phase3_v1.01_nninterp-f09_g17.2000-2000.{ts}8.nc",
            )
        else:
            res_list = ["0.9x1.25", "1.9x2.5", "10x15"]
            error_message = f"ERROR: RXCROPMATURITY currently only supports resolutions: {', '.join(res_list)}"
            error(logger, error_message, error_type=RuntimeError)

        # Ensure files exist
        error_message = None
        if not os.path.exists(self._sdatefile):
            error_message = f"ERROR: Sowing date file not found: {self._sdatefile}"
        elif not os.path.exists(self._hdatefile):
            error_message = f"ERROR: Harvest date file not found: {self._sdatefile}"
        if error_message is not None:
            error(logger, error_message, error_type=RuntimeError)

    def _setup_all(self, h1_inst: bool) -> None:
        log(logger, "RXCROPMATURITY log:  _setup_all start")

        # Set sowing dates file (and other crop calendar settings) for all runs
        log(logger, "RXCROPMATURITY log:  modify user_nl files: all tests")
        self._modify_user_nl_allruns(h1_inst)
        log(logger, "RXCROPMATURITY log:  _setup_all done")

    # Make a surface dataset that has every crop in every gridcell
    def _run_fsurdat_modifier(self) -> None:

        # fsurdat should be defined. Where is it?
        self._fsurdat_in = None
        with open(self._lnd_in_path, "r", encoding="utf8") as lnd_in:
            for line in lnd_in:
                fsurdat_in = re.match(r" *fsurdat *= *'(.*)'", line)
                if fsurdat_in:
                    self._fsurdat_in = fsurdat_in.group(1)
                    break
        if self._fsurdat_in is None:
            error_message = "fsurdat not defined"
            error(logger, error_message, error_type=RuntimeError)

        # Where we will save the fsurdat version for this test
        path, ext = os.path.splitext(self._fsurdat_in)
        _, filename_in_noext = os.path.split(path)
        self._fsurdat_out = os.path.join(
            self._path_gddgen, f"{filename_in_noext}.all_crops_everywhere{ext}"
        )

        # Make fsurdat for this test, if not already done
        if not os.path.exists(self._fsurdat_out):
            tool_path = os.path.join(
                self._ctsm_root,
                "tools",
                "modify_input_files",
                "fsurdat_modifier",
            )

            # Create configuration file for fsurdat_modifier
            self._cfg_path = os.path.join(
                self._path_gddgen,
                "modify_fsurdat_allcropseverywhere.cfg",
            )
            self._create_config_file_evenlysplitcrop()

            command = f"python3 {tool_path} {self._cfg_path} "
            stu.run_python_script(
                self._get_caseroot(),
                self._this_conda_env,
                command,
                tool_path,
            )

        # Modify namelist
        log(logger, "RXCROPMATURITY log:  modify user_nl files: new fsurdat")
        self._append_to_user_nl_clm(
            [
                f"fsurdat = '{self._fsurdat_out}'",
                "do_transient_crops = .false.",
                "flanduse_timeseries = ''",
                "use_init_interp = .true.",
            ]
        )

    def _create_config_file_evenlysplitcrop(self) -> None:
        """
        Open the new and the template .cfg files
        Loop line by line through the template .cfg file
        When string matches, replace that line's content
        """
        cfg_template_path = os.path.join(
            self._ctsm_root, "tools/modify_input_files/modify_fsurdat_template.cfg"
        )

        with open(self._cfg_path, "w", encoding="utf-8") as cfg_out:
            # Copy template, replacing some lines
            with open(cfg_template_path, "r", encoding="utf-8") as cfg_in:
                for line in cfg_in:
                    if re.match(r" *evenly_split_cropland *=", line):
                        line = "evenly_split_cropland = True"
                    elif re.match(r" *fsurdat_in *=", line):
                        line = f"fsurdat_in = {self._fsurdat_in}"
                    elif re.match(r" *fsurdat_out *=", line):
                        line = f"fsurdat_out = {self._fsurdat_out}"
                    elif re.match(r" *process_subgrid_section *=", line):
                        line = "process_subgrid_section = True"
                    cfg_out.write(line)

            # Add new lines
            cfg_out.write("\n")
            cfg_out.write("[modify_fsurdat_subgrid_fractions]\n")
            cfg_out.write("PCT_CROP    = 100.0\n")
            cfg_out.write("PCT_NATVEG  = 0.0\n")
            cfg_out.write("PCT_GLACIER = 0.0\n")
            cfg_out.write("PCT_WETLAND = 0.0\n")
            cfg_out.write("PCT_LAKE    = 0.0\n")
            cfg_out.write("PCT_OCEAN   = 0.0\n")
            cfg_out.write("PCT_URBAN   = 0.0 0.0 0.0\n")

    def _run_check_rxboth_run(self) -> None:

        first_usable_year, last_usable_year = get_usable_years_for_check_rxboth_run(
            self._run_startyear, self._run_nyears, self._scriptsonly_test
        )

        tool_path = os.path.join(
            self._ctsm_root, "python", "ctsm", "crop_calendars", "check_rxboth_run.py"
        )
        command = (
            f"python3 {tool_path} "
            + f"--directory {self._check_rxboth_run_indir} "
            + f"-y1 {first_usable_year} "
            + f"-yN {last_usable_year} "
            + f"--rx-sdates-file {self._sdatefile} "
            + f"--rx-gdds-file {self._gdds_file} "
        )
        stu.run_python_script(
            self._get_caseroot(),
            self._this_conda_env,
            command,
            tool_path,
        )

    def _modify_user_nl_allruns(self, h1_inst: bool) -> None:
        nl_additions = [
            "cropcals_rx = .true.",
            "cropcals_rx_adapt = .false.",
            f"stream_meshfile_cropcal = '{self._case.get_value('LND_DOMAIN_MESH')}'",
            f"stream_fldFileName_swindow_start = '{self._sdatefile}'",
            f"stream_fldFileName_swindow_end   = '{self._sdatefile}'",
            "stream_year_first_cropcal_swindows = 2000",
            "stream_year_last_cropcal_swindows = 2000",
            "model_year_align_cropcal_swindows = 2000",
            " ",
            "! (h1) Annual outputs on sowing or harvest axis",
            (
                "hist_fincl2 = 'GRAINC_TO_FOOD_PERHARV', 'GRAINC_TO_FOOD_ANN', 'SDATES',"
                " 'SDATES_PERHARV', 'SYEARS_PERHARV', 'HDATES', 'GDDHARV_PERHARV',"
                " 'GDDACCUM_PERHARV', 'HUI_PERHARV', 'SOWING_REASON_PERHARV',"
                " 'HARVEST_REASON_PERHARV'"
            ),
            "hist_nhtfrq(2) = 17520",
            "hist_mfilt(2) = 999",
            "hist_type1d_pertape(2) = 'PFTS'",
            "hist_dov2xy(2) = .false.",
        ]
        if h1_inst:
            nl_additions.append("hist_avgflag_pertape(2) = 'I'")
        self._append_to_user_nl_clm(nl_additions)

    def _run_generate_gdds(self, input_dir: str):
        self._generate_gdds_outdir = os.path.join(
            self._path_gddgen, "generate_gdds_out"
        )
        os.makedirs(self._generate_gdds_outdir)

        # Get arguments to generate_gdds.py
        first_season, last_season = _get_seasons_for_generate_gdds(self._run_startyear, self._run_nyears)
        sdates_file = self._sdatefile
        hdates_file = self._hdatefile

        # It'd be much nicer to call generate_gdds.main(), but I can't import generate_gdds.
        # See https://github.com/ESCOMP/CTSM/issues/2603
        tool_path = os.path.join(
            self._ctsm_root, "python", "ctsm", "crop_calendars", "generate_gdds.py"
        )
        command = " ".join(
            [
                f"python3 {tool_path}",
                f"--input-dir {input_dir}",
                f"--first-season {first_season}",
                f"--last-season {last_season}",
                f"--sdates-file {sdates_file}",
                f"--hdates-file {hdates_file}",
                "--output-dir generate_gdds_out",
                "--skip-crops miscanthus,irrigated_miscanthus,switchgrass,irrigated_switchgrass",
                "--max-season-length-from-hdates-file",
            ]
        )
        stu.run_python_script(
            self._get_caseroot(),
            self._this_conda_env,
            command,
            tool_path,
        )

        # Where were the prescribed maturity requirements saved?
        generated_gdd_files = glob.glob(
            os.path.join(self._generate_gdds_outdir, "gdds_*.nc")
        )
        if n_files := len(generated_gdd_files) != 1:
            error_message = (
                "ERROR: Expected one matching prescribed maturity requirements file; found "
                f"{n_files}: {generated_gdd_files}"
            )
            error(logger, error_message, error_type=RuntimeError)
        self._gdds_file = generated_gdd_files[0]

    def _get_conda_env(self) -> None:
        stu.cmds_to_setup_conda(self._get_caseroot())
        self._this_conda_env = "ctsm_pylib"

    def _append_to_user_nl_clm(self, additions: List[str]) -> None:
        caseroot = self._get_caseroot()
        append_to_user_nl_files(caseroot=caseroot, component="clm", contents=additions)

    # Is flanduse_timeseries defined? If so, where is it?
    def _get_flanduse_timeseries_in(self, case: Case) -> None:
        case.create_namelists(component="lnd")
        self._lnd_in_path = os.path.join(self._path_gddgen, "CaseDocs", "lnd_in")
        self._flanduse_timeseries_in = None
        with open(self._lnd_in_path, "r", encoding="utf8") as lnd_in:
            for line in lnd_in:
                flanduse_timeseries_in = re.match(
                    r" *flanduse_timeseries *= *'(.*)'", line
                )
                if flanduse_timeseries_in:
                    self._flanduse_timeseries_in = flanduse_timeseries_in.group(1)
                    break


class RXCROPMATURITY(RXCROPMATURITYSHARED):
    """
    SystemTest to run a GDD-Generating run, then generate_gdd.py on the outputs, and then a
    Prescribed Calendars run with the resulting crop calendar input files.
    """

    def generate_baseline_phase(self, basegen_dir):
        # Copy files from GDD-Generating phase
        _copy_extra_files_from_run_to_baseline(
            "generate_gdds", self._gddgen_phase_outdir, basegen_dir
        )

        # Copy files from Prescribed Calendars phase
        _copy_extra_files_from_run_to_baseline(
            "check_rxboth_run", self._prescribed_calendars_phase_outdir, basegen_dir
        )
