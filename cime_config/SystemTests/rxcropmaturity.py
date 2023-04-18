"""
CTSM-specific test that first performs a GDD-generating run, then calls
Python code to generate the maturity requirement file. This is then used
in a sowing+maturity forced run, which finally is tested to ensure
correct behavior.
"""

import os
import re
import subprocess
from CIME.SystemTests.system_tests_common import SystemTestsCommon
from CIME.XML.standard_module_setup import *
from CIME.SystemTests.test_utils.user_nl_utils import append_to_user_nl_files
import shutil, glob

logger = logging.getLogger(__name__)

class RXCROPMATURITY(SystemTestsCommon):

    def __init__(self, case):
        """
        initialize an object interface to the SMS system test
        """
        SystemTestsCommon.__init__(self, case)
        
        
        """
        Get some info
        """
        self._ctsm_root = self._case.get_value('COMP_ROOT_DIR_LND')
        run_startdate = self._case.get_value('RUN_STARTDATE')
        self._run_startyear = int(run_startdate.split('-')[0])
        
        # Minimum 4, but that only gets you 1 season usable for GDD
        # generation, so you can't check for season-to-season consistency.
        self._run_Nyears = 5
        
        
        """
        Set run length
        """

        self._case.set_value("STOP_OPTION", "nyears")
        self._case.set_value("STOP_N", self._run_Nyears)
        
        
        """
        Get and set sowing and harvest dates
        """
        
        # Get sowing and harvest dates for this resolution.
        # Eventually, I want to remove these hard-coded resolutions so that this test can generate
        # its own sowing and harvest date files at whatever resolution is requested.
        lnd_grid = self._case.get_value("LND_GRID")
        blessed_crop_dates_dir="/glade/work/samrabin/crop_dates_blessed"
        if lnd_grid == "10x15":
            self._sdatefile = os.path.join(
                blessed_crop_dates_dir,
                "sdates_ggcmi_crop_calendar_phase3_v1.01_nninterp-f10_f10_mg37.2000-2000.20230330_165301.fill1.nc")
            self._hdatefile = os.path.join(
                blessed_crop_dates_dir,
                "hdates_ggcmi_crop_calendar_phase3_v1.01_nninterp-f10_f10_mg37.2000-2000.20230330_165301.fill1.nc")
        elif lnd_grid == "1.9x2.5":
            self._sdatefile = os.path.join(
                blessed_crop_dates_dir,
                "sdates_ggcmi_crop_calendar_phase3_v1.01_nninterp-f19_g17.2000-2000.20230102_175625.fill1.nc")
            self._hdatefile = os.path.join(
                blessed_crop_dates_dir,
                "hdates_ggcmi_crop_calendar_phase3_v1.01_nninterp-f19_g17.2000-2000.20230102_175625.fill1.nc")
        else:
            print("ERROR: RXCROPMATURITY currently only supports 10x15 and 1.9x2.5 resolutions")
            raise
        if not os.path.exists(self._sdatefile):
            print(f"ERROR: Sowing date file not found: {self._sdatefile}")
            raise
        if not os.path.exists(self._hdatefile):
            print(f"ERROR: Harvest date file not found: {self._sdatefile}")
            raise
        
        # Set sowing dates file (and other crop calendar settings) for all runs
        logger.info("  modify user_nl files: all tests")
        self._modify_user_nl_allruns()


    def run_phase(self):
        
        # Create Prescribed Calendars clone of GDD-Generating case
        logger.info("  cloning")
        caseroot = self._case.get_value("CASEROOT")
        self._path_rxboth = f"{caseroot}.rxboth"
        if os.path.exists(self._path_rxboth):
            shutil.rmtree(self._path_rxboth)
        case_rxboth = self._case.create_clone(self._path_rxboth, keepexe=True)
        logger.info("  done cloning")
        
        #-------------------------------------------------------------------
        # (1) Set up GDD-generating run
        #-------------------------------------------------------------------
        logger.info("  modify user_nl files: generate GDDs")
        self._modify_user_nl_gengdds()
        self._case.create_namelists(component='lnd')
        
        """
        If needed, generate a surface dataset file with no crops missing years
        """
        
        # Is flanduse_timeseries defined? If so, where is it? 
        self._lnd_in_path = os.path.join(self._get_caseroot(), 'CaseDocs', 'lnd_in')
        self._flanduse_timeseries_in = None
        with open (self._lnd_in_path,'r') as lnd_in:
            for line in lnd_in:
                flanduse_timeseries_in = re.match(r" *flanduse_timeseries *= *'(.*)'", line)
                if flanduse_timeseries_in:
                    self._flanduse_timeseries_in = flanduse_timeseries_in.group(1)
                    break
        
        # If flanduse_timeseries is defined, we need to make our own version for
        # this test (if we haven't already).
        if self._flanduse_timeseries_in is not None:
            
            # Download files from the server, if needed
            self._case.check_all_input_data()
            
            # Make custom version of flanduse_timeseries
            logger.info("  run make_lu_for_gdden")
            self._run_make_lu_for_gdden()
        
        #-------------------------------------------------------------------
        # (2) Perform GDD-generating run and generate prescribed GDDs file
        #-------------------------------------------------------------------
        self.run_indv()
        self._run_generate_gdds()
        
        #-------------------------------------------------------------------
        # (3) Set up and perform Prescribed Calendars run
        #-------------------------------------------------------------------
        logger.info("  modify user_nl files: Prescribed Calendars")
        os.chdir(case_rxboth.get_value("CASEROOT"))
        self._set_active_case(case_rxboth)
        self._modify_user_nl_rxboth()
        self._skip_pnl = False
        self.run_indv(suffix=None, st_archive=True)
        
        #-------------------------------------------------------------------
        # (4) Check Prescribed Calendars run
        #-------------------------------------------------------------------
        logger.info("  output check: Prescribed Calendars")
        self._run_check_rxboth_run()
    
         
    def _run_make_lu_for_gdden(self):
        
        # Where we will save the flanduse_timeseries version for this test
        self._flanduse_timeseries_out = os.path.join(self._get_caseroot(), 'flanduse_timeseries.nc')
        
        # Make flanduse_timeseries for this test, if not already done
        if not os.path.exists(self._flanduse_timeseries_out):
            
            first_fake_year = self._run_startyear
            last_fake_year = first_fake_year + self._run_Nyears
            
            tool_path = os.path.join(self._ctsm_root,
                                    'python', 'ctsm', 'crop_calendars',
                                    'make_lu_for_gddgen.py')

            self._case.load_env(reset=True)
            conda_env = ". "+self._get_caseroot()+"/.env_mach_specific.sh; "
            # Preprend the commands to get the conda environment for python first
            conda_env += self._get_conda_env()
            # Source the env
            try:
                command = " ".join([
                    f"{conda_env}python3 {tool_path}",
                    f"--flanduse-timeseries {self._flanduse_timeseries_in}",
                    f"-y1 {first_fake_year}",
                    f"-yN {last_fake_year}",
                    f"--outfile {self._flanduse_timeseries_out}",
                ])
                print(f"command: {command}")
                subprocess.run(command, shell=True, check=True)
            except subprocess.CalledProcessError as error:
                print("ERROR while getting the conda environment and/or ")
                print("running the make_lu_for_gddgen tool: ")
                print("(1) If your npl environment is out of date or you ")
                print("have not created the npl environment, yet, you may ")
                print("get past this error by running ./py_env_create ")
                print("in your ctsm directory and trying this test again. ")
                print("(2) If conda is not available, install and load conda, ")
                print("run ./py_env_create, and then try this test again. ")
                print("(3) If (1) and (2) are not the issue, then you may be ")
                print("getting an error within the make_lu_for_gddgen tool itself. ")
                print("Default error message: ")
                print(error.output)
                raise
            except:
                print("ERROR trying to run make_lu_for_gddgen tool.")
                raise
        
        # Modify namelist
        logger.info("  modify user_nl files: new flanduse_timeseries")
        self._modify_user_nl_newflanduse_timeseries()


    def _run_make_surface_for_gdden(self):
        
        # fsurdat should be defined. Where is it?
        self._fsurdat_in = None
        with open (self._lnd_in_path,'r') as lnd_in:
            for line in lnd_in:
                fsurdat_in = re.match(r" *fsurdat *= *'(.*)'", line)
                if fsurdat_in:
                    self._fsurdat_in = fsurdat_in.group(1)
                    break
        if self._fsurdat_in is None:
            print("fsurdat not defined")
            raise
        
        # Where we will save the fsurdat version for this test
        self._fsurdat_out = os.path.join(self._get_caseroot(), 'fsurdat.nc')
        
        # Make fsurdat for this test, if not already done
        if not os.path.exists(self._fsurdat_out):
            tool_path = os.path.join(self._ctsm_root,
                                    'python', 'ctsm', 'crop_calendars',
                                    'make_surface_for_gddgen.py')

            self._case.load_env(reset=True)
            conda_env = ". "+self._get_caseroot()+"/.env_mach_specific.sh; "
            # Preprend the commands to get the conda environment for python first
            conda_env += self._get_conda_env()
            # Source the env
            try:
                command = f"{conda_env}python3 {tool_path} "\
                    + f"--flanduse-timeseries {self._flanduse_timeseries_in} "\
                    + f"--fsurdat {self._fsurdat_in} "\
                    + f"--outfile {self._fsurdat_out}"
                print(f"command: {command}")
                subprocess.run(command, shell=True, check=True)
            except subprocess.CalledProcessError as error:
                print("ERROR while getting the conda environment and/or ")
                print("running the make_surface_for_gddgen tool: ")
                print("(1) If your npl environment is out of date or you ")
                print("have not created the npl environment, yet, you may ")
                print("get past this error by running ./py_env_create ")
                print("in your ctsm directory and trying this test again. ")
                print("(2) If conda is not available, install and load conda, ")
                print("run ./py_env_create, and then try this test again. ")
                print("(3) If (1) and (2) are not the issue, then you may be ")
                print("getting an error within the make_surface_for_gddgen tool itself. ")
                print("Default error message: ")
                print(error.output)
                raise
            except:
                print("ERROR trying to run make_surface_for_gddgen tool.")
                raise
        
        # Modify namelist
        logger.info("  modify user_nl files: new fsurdat")
        self._modify_user_nl_newfsurdat()
        
    
    def _run_check_rxboth_run(self):
        
        first_usable_year = self._run_startyear + 2
        last_usable_year = self._run_startyear + self._run_Nyears - 2
                
        tool_path = os.path.join(self._ctsm_root,
                                'python', 'ctsm', 'crop_calendars',
                                'check_rxboth_run.py')

        self._case.load_env(reset=True)
        conda_env = ". "+self._get_caseroot()+"/.env_mach_specific.sh; "
        # Preprend the commands to get the conda environment for python first
        conda_env += self._get_conda_env()
        # Source the env
        try:
            command = f"{conda_env}python3 {tool_path} "\
                + f"--directory {self._path_rxboth} "\
                + f"-y1 {first_usable_year} "\
                + f"-yN {last_usable_year} "\
                + f"--rx-sdates-file {self._sdatefile} "\
                + f"--rx-gdds-file {self._gdds_file} "\
                + " | tee -p check_rxboth_run.log"
            print(f"command: {command}")
            subprocess.run(command, shell=True, check=True)
        except subprocess.CalledProcessError as error:
            print("ERROR while getting the conda environment and/or ")
            print("running the check_rxboth_run tool: ")
            print("(1) If your npl environment is out of date or you ")
            print("have not created the npl environment, yet, you may ")
            print("get past this error by running ./py_env_create ")
            print("in your ctsm directory and trying this test again. ")
            print("(2) If conda is not available, install and load conda, ")
            print("run ./py_env_create, and then try this test again. ")
            print("(3) If (1) and (2) are not the issue, then you may be ")
            print("getting an error within the check_rxboth_run tool itself. ")
            print("Default error message: ")
            print(error.output)
            raise
        except:
            print("ERROR trying to run check_rxboth_run tool.")
            raise
                
    
    
    def _modify_user_nl_allruns(self):
        nl_additions = [
            "stream_meshfile_cropcal = '{}'".format(self._case.get_value("LND_DOMAIN_MESH")),
            "stream_fldFileName_sdate = '{}'".format(self._sdatefile),
            "stream_year_first_cropcal = 2000",
            "stream_year_last_cropcal = 2000",
            "model_year_align_cropcal = 2000",
            " ",
            "! (h1) Daily outputs for GDD generation and figure-making",
            "hist_fincl2 = 'HUI', 'GDDACCUM', 'GDDHARV'",
            "hist_nhtfrq(2) = -24",
            "hist_mfilt(2) = 365",
            "hist_type1d_pertape(2) = 'PFTS'",
            "hist_dov2xy(2) = .false.",
            " ",
            "! (h2) Annual outputs for GDD generation (checks)",
            "hist_fincl3 = 'GRAINC_TO_FOOD_PERHARV', 'GRAINC_TO_FOOD_ANN', 'SDATES', 'SDATES_PERHARV', 'SYEARS_PERHARV', 'HDATES', 'GDDHARV_PERHARV', 'GDDACCUM_PERHARV', 'HUI_PERHARV', 'SOWING_REASON_PERHARV', 'HARVEST_REASON_PERHARV'",
            "hist_nhtfrq(3) = 17520",
            "hist_mfilt(3) = 999",
            "hist_type1d_pertape(3) = 'PFTS'",
            "hist_dov2xy(3) = .false.",
        ]
        for addition in nl_additions:
            append_to_user_nl_files(caseroot = self._get_caseroot(),
                                    component = "clm",
                                    contents = addition)


    def _modify_user_nl_gengdds(self):
        nl_additions = [
            "generate_crop_gdds = .true.",
            "use_mxmat = .false.",
        ]
        for addition in nl_additions:
            append_to_user_nl_files(caseroot = self._get_caseroot(),
                                    component = "clm",
                                    contents = addition)

    def _modify_user_nl_rxboth(self):
        nl_additions = [
            "generate_crop_gdds = .false.",
            f"stream_fldFileName_cultivar_gdds = '{self._gdds_file}'",
        ]
        for addition in nl_additions:
            append_to_user_nl_files(caseroot = self._get_caseroot(),
                                    component = "clm",
                                    contents = addition)

    def _modify_user_nl_newfsurdat(self):
        nl_additions = [
            "fsurdat = '{}'".format(self._fsurdat_out),
            "do_transient_crops = .false.",
            "flanduse_timeseries = ''",
            "use_init_interp = .true.",
        ]
        for addition in nl_additions:
            append_to_user_nl_files(caseroot = self._get_caseroot(),
                                    component = "clm",
                                    contents = addition)
    
    def _modify_user_nl_newflanduse_timeseries(self):
        nl_additions = [
            "flanduse_timeseries = '{}'".format(self._flanduse_timeseries_out),
        ]
        for addition in nl_additions:
            append_to_user_nl_files(caseroot = self._get_caseroot(),
                                    component = "clm",
                                    contents = addition)

    def _run_generate_gdds(self):
        caseroot = self._case.get_value("CASEROOT")
        self._generate_gdds_dir = os.path.join(caseroot, "generate_gdds_out")
        os.makedirs(self._generate_gdds_dir)

        run_dir = os.path.join(caseroot, "run")
        first_season = self._run_startyear + 2
        last_season = self._run_startyear + self._run_Nyears - 2
        sdates_file = self._sdatefile
        hdates_file = self._hdatefile

        tool_path = os.path.join(self._ctsm_root,
                                 'python', 'ctsm', 'crop_calendars',
                                 'generate_gdds.py')

        self._case.load_env(reset=True)
        conda_env = ". "+self._get_caseroot()+"/.env_mach_specific.sh; "
        # Preprend the commands to get the conda environment for python first
        conda_env += self._get_conda_env()
        # Source the env
        try:
            # It'd be much nicer to call generate_gdds.main(), but I can't import generate_gdds.
            command = " ".join([
                    f"{conda_env}python3 {tool_path}",
                    f"--run-dir {run_dir}",
                    f"--first-season {first_season}",
                    f"--last-season {last_season}",
                    f"--sdates-file {sdates_file}",
                    f"--hdates-file {hdates_file}",
                    #f"--output-dir {caseroot}"])
                    f"--output-dir generate_gdds_out"])
            print(f"command: {command}")
            subprocess.run(command, shell=True, check=True)
        except subprocess.CalledProcessError as error:
            print("ERROR while getting the conda environment and/or ")
            print("running the generate_gdds tool: ")
            print("(1) If your npl environment is out of date or you ")
            print("have not created the npl environment, yet, you may ")
            print("get past this error by running ./py_env_create ")
            print("in your ctsm directory and trying this test again. ")
            print("(2) If conda is not available, install and load conda, ")
            print("run ./py_env_create, and then try this test again. ")
            print("(3) If (1) and (2) are not the issue, then you may be ")
            print("getting an error within the generate_gdds tool itself. ")
            print("Default error message: ")
            print(error.output)
            raise
        except:
            print("ERROR trying to run generate_gdds tool.")
            raise
        
        # Where were the prescribed maturity requirements saved?
        generated_gdd_files = glob.glob(os.path.join(self._generate_gdds_dir, "gdds_*.nc"))
        generated_gdd_files = [x for x in generated_gdd_files if "fill0" not in x]
        if len(generated_gdd_files) != 1:
            print(f"ERROR: Expected one matching prescribed maturity requirements file; found {len(generated_gdd_files)}: {generated_gdd_files}")
            raise
        self._gdds_file = generated_gdd_files[0]
        

    def _get_conda_env(self):
        #
        # Add specific commands needed on different machines to get conda available
        # Use semicolon here since it's OK to fail
        #
        # Execute the module unload/load when "which conda" fails
        # eg on cheyenne
        try:
            subprocess.run( "which conda", shell=True, check=True)
            conda_env = " "
        except subprocess.CalledProcessError:
            # Remove python and add conda to environment for cheyennne
            conda_env = "module unload python; module load conda;"

        ## Run in the correct python environment
        # SSR: This was originally ctsm_pylib, but the fact that it's missing
        #      cf_units caused problems in utils.import_ds().
        conda_env += " conda run -n npl "


        return( conda_env )
