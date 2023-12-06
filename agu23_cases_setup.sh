#!/bin/bash
set -e

# Experiment info
prefix="$1"      # E.g., agu2023d_1deg_Toff_Roff
res="$2"         # E.g., f09_g17
subcompset="$3"  # E.g., GSWP3v1_CLM51%BGC-CROP_SICE_SOCN_MOSART_CISM2%NOEVOLVE_SWAV
if [[ "${subcompset}" == "" ]]; then
    echo "agu23_cases_setup.sh requires 3 arguments: prefix, res, subcompset" >&2
    exit 1
fi
proj="$4" # OPTIONAL; e.g., P93300641
if [[ "${proj}" == "" ]]; then
    if [[ "$PROJECT" == "" ]]; then
        echo "\$PROJECT not set; you must provide 4th argument proj" >&2
        exit 1
    fi
    proj="$PROJECT"
fi

# Set up CESM repo
cd /glade/u/home/samrabin/ctsm_agu2023_derecho
#git checkout 86b4a74e6
#manage_externals/checkout_externals

# Function to set Ntasks for 1-degree run
function ntasks_1deg {
ntasks_atm=36
ntasks_other=1716
./xmlchange \
NTASKS_CPL=${ntasks_other},\
NTASKS_ATM=${ntasks_atm},\
NTASKS_LND=${ntasks_other},\
NTASKS_ICE=${ntasks_other},\
NTASKS_OCN=${ntasks_other},\
NTASKS_ROF=${ntasks_other},\
NTASKS_GLC=${ntasks_other},\
NTASKS_WAV=${ntasks_other},\
NTASKS_ESP=1
./case.setup --reset
}

# Function: Set reference case
function set_ref_case {
refcase="$1"
y1=$2
restdir="${SCRATCH}/archive/${refcase}/rest/${y1}-01-01-00000"
./xmlchange RUN_TYPE="hybrid"
./xmlchange RUN_REFCASE="${refcase}",RUN_REFDIR="${restdir}",GET_REFCASE=TRUE
./xmlchange RUN_REFDATE=${y1}-01-01,RUN_STARTDATE=${y1}-01-01
}

# Function: Append to user_nl_clm for starting an SSP case in 1850
function append_nlclm_sspcase1850 {
cat <<EOT >> user_nl_clm

! To start an SSP case in 1850
model_year_align_ndep = 1850
model_year_align_popdens = 1850
model_year_align_urbantv = 1850
stream_year_first_ndep = 1850
stream_year_first_popdens = 1850
stream_year_first_urbantv = 1850
! Do not adjust lightning years---it is a 1995-2013 climatology
EOT
}

# Function: Append to user_nl_clm: paramfile and outputs
function append_nlclm_outputsetc {
cat <<EOT >> user_nl_clm

paramfile = '/glade/u/home/samrabin/ctsm_tillage/ctsm51_params.c211112.tillage.nc'

! Keep default outputs, but save annually
hist_nhtfrq(1) = 17520
hist_mfilt(1) = 1
hist_dov2xy(1) = .false.

! Annual PFT-level outputs (of interest)
hist_fincl2 = 'GRAINC_TO_FOOD_ANN'
hist_nhtfrq(2) = 17520
hist_mfilt(2) = 1
hist_type1d_pertape(2) = 'PFTS'
hist_dov2xy(2) = .false.

! Annual column-level outputs (of interest)
hist_fincl3 = 'TOTSOMC', 'TOTSOMC_1m', 'TOTLITC', 'TOTLITC_1m', 'TOTSOMN', 'TOTSOMN_1m', 'TOTLITN', 'TOTLITN_1m'
hist_nhtfrq(3) = 17520
hist_mfilt(3) = 1
hist_type1d_pertape(3) = 'COLS'
hist_dov2xy(3) = .false.

! Annual gridcell-level outputs (of interest)
hist_fincl4 = 'CROPPROD1C', 'CROPPROD1C_LOSS', 'CROPPROD1N', 'CROPPROD1N_LOSS', 'DWT_CROPPROD1C_GAIN', 'DWT_CROPPROD1N_GAIN'
hist_nhtfrq(4) = 17520
hist_mfilt(4) = 1
hist_type1d_pertape(4) = 'GRID'
hist_dov2xy(4) = .false.
EOT
}

# Function: Append to user_nl_datm_streams: presaero and presndep
function append_nldatm_aerondep {
cat <<EOT >> user_nl_datm_streams

presaero.SSP3-7.0:datafiles=/glade/p/cesmdata/cseg/inputdata/atm/cam/chem/trop_mozart_aero/aero/aerodep_clm_SSP370_b.e21.BWSSP370cmip6.f09_g17.CMIP6-SSP3-7.0-WACCM.001_1849-2101_monthly_0.9x1.25_c201103.nc
presaero.SSP3-7.0:year_first=1850
presaero.SSP3-7.0:year_align=1850

presndep.SSP3-7.0:year_first=1850
presndep.SSP3-7.0:year_align=1850
EOT
}

# Function: Append to user_nl_datm: anomalies to use
function append_nldatm_anoms {
cat <<EOT >> user_nl_datm

anomaly_forcing = 'Anomaly.Forcing.Precip','Anomaly.Forcing.Temperature','Anomaly.Forcing.Pressure','Anomaly.Forcing.Humidity','Anomaly.Forcing.Uwind','Anomaly.Forcing.Vwind','Anomaly.Forcing.Shortwave','Anomaly.Forcing.Longwave'
EOT
}

# 1850-1900
years="1850-1900"
casename_1850="${prefix}_${years}"
casedir="$HOME/cases_agu23/${casename_1850}"
[[ -d "${casedir}" ]] && rm -rf "${casedir}"
cime/scripts/create_newcase --case ${casedir} --res ${res} --compset SSP370_DATM%${subcompset} --project ${proj} --run-unsupported --handle-preexisting-dirs r
# Initialize case
echo " "
echo " "
pushd "${casedir}"
./case.setup
ntasks_1deg
# Run 1850-1900 (51 yrs), repeating 1901-1920 climate
./xmlchange RUN_STARTDATE=1850-01-01
./xmlchange STOP_N=17,STOP_OPTION=nyears,RESUBMIT=2
./xmlchange DATM_YR_START=1901,DATM_YR_END=1920
# Set expected walltime
./xmlchange --subgroup case.run JOB_WALLCLOCK_TIME=08:00:00
# Set up namelists
append_nlclm_sspcase1850
append_nlclm_outputsetc
append_nldatm_aerondep
./preview_namelists
popd

# 1901-2014
echo " "
echo " "
years="1901-2014"
casename_1901="${prefix}_${years}"
casedir="$HOME/cases_agu23/${casename_1901}"
[[ -d "${casedir}" ]] && rm -rf "${casedir}"
cime/scripts/create_newcase --case ${casedir} --res ${res} --compset SSP370_DATM%${subcompset} --project ${proj} --run-unsupported --handle-preexisting-dirs r
# Initialize case
echo " "
echo " "
pushd "${casedir}"
./case.setup
ntasks_1deg
# Run 1901-2014 (114 yrs)
./xmlchange RUN_STARTDATE=1901-01-01
./xmlchange STOP_N=19,STOP_OPTION=nyears,RESUBMIT=5
./xmlchange DATM_YR_START=1901,DATM_YR_END=2014
# Set expected walltime
./xmlchange --subgroup case.run JOB_WALLCLOCK_TIME=08:00:00
# Set up namelists
append_nlclm_sspcase1850
append_nlclm_outputsetc
append_nldatm_aerondep
./preview_namelists
# Start from end of previous run
set_ref_case "${casename_1850}" 1901
popd

# 2015-2100
echo " "
echo " "
years="2015-2100"
casedir="$HOME/cases_agu23/${prefix}_${years}"
[[ -d "${casedir}" ]] && rm -rf "${casedir}"
cime/scripts/create_newcase --case ${casedir} --res ${res} --compset SSP370_DATM%${subcompset} --project ${proj} --run-unsupported --handle-preexisting-dirs r
# Initialize case
echo " "
echo " "
pushd "${casedir}"
./case.setup
ntasks_1deg
# Run 2015-2100 (84 yrs)
./xmlchange RUN_STARTDATE=2015-01-01
./xmlchange STOP_N=21,STOP_OPTION=nyears,RESUBMIT=4
./xmlchange DATM_YR_START=1901,DATM_YR_END=2014
# Set expected walltime
./xmlchange --subgroup case.run JOB_WALLCLOCK_TIME=09:00:00
# Set up namelists
append_nlclm_sspcase1850
append_nlclm_outputsetc
append_nldatm_aerondep
append_nldatm_anoms
./preview_namelists
# Start from end of previous run
set_ref_case "${casename_1901}" 2015

exit 0
