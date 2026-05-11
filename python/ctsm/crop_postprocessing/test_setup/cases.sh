#!/usr/bin/env bash
set -eo pipefail

case_parent_dir="$1"
if [[ "${case_parent_dir}" == "" ]]; then
    echo "You must provide case_parent_dir (positional arg)" >&2
    exit 1
fi

# Error on unset variables (wait until after input arg processing)
set -u

# Define run settings
compset="IHistClm60BgcCropCrujra"
res="f10_f10_mg37"
stop_n=$((3*365+35)) # 3 years + a bit over a month to test handling of incomplete years

# Setup
mkdir -p "${case_parent_dir}"
cd "$(dirname "$(realpath $0)")/../../../.."

# Case with PFT-level outputs
case="${case_parent_dir}/clm_crop_pp_testdata_pft"
cime/scripts/create_newcase --compset ${compset} --res ${res} --run-unsupported --case ${case}
pushd ${case} 1>/dev/null
./case.setup
# Run for 3 years + a bit over a month to test handling of incomplete years
./xmlchange STOP_OPTION=ndays,STOP_N=${stop_n}

cat >user_nl_clm <<EOL
hist_empty_htapes = .true.

! h0: daily, PFT, gridded
hist_nhtfrq(1) = -24
hist_dov2xy(1) = .true.
hist_mfilt(1) = 365
hist_type1d_pertape(1) = 'PFTS'
hist_fincl1 = 'GRAINC_TO_FOOD', 'GPP'
hist_fincl1 += 'GRAINC_TO_FOOD_ANN'  ! Invalid when saved sub-annually; should warn and skip

! h1: monthly, PFT, gridded
hist_nhtfrq(2) = 0
hist_dov2xy(2) = .true.
hist_mfilt(2) = 12
hist_type1d_pertape(2) = 'PFTS'
hist_fincl2 = 'GRAINC_TO_FOOD', 'GPP'
hist_fincl2 += 'GRAINC_TO_FOOD_ANN'  ! Invalid when saved sub-annually; should warn and skip

! h2: annual, PFT, gridded
hist_nhtfrq(3) = -8760
hist_dov2xy(3) = .true.
hist_mfilt(3) = 2  ! to ensure we test properly with time dimension ≠ 1
hist_type1d_pertape(3) = 'PFTS'
hist_fincl3 = 'SDATES', 'SDATES_PERHARV', 'SYEARS_PERHARV', 'HDATES', 'GRAINC_TO_FOOD_PERHARV', 'GRAINC_TO_FOOD_ANN', 'GRAINN_TO_FOOD_PERHARV', 'GRAINN_TO_FOOD_ANN', 'GRAINC_TO_SEED_PERHARV', 'GRAINC_TO_SEED_ANN', 'GRAINN_TO_SEED_PERHARV', 'GRAINN_TO_SEED_ANN', 'HDATES', 'GDDHARV_PERHARV', 'GDDACCUM_PERHARV', 'HUI_PERHARV', 'SOWING_REASON_PERHARV', 'HARVEST_REASON_PERHARV', 'SWINDOW_STARTS', 'SWINDOW_ENDS', 'GDD20_BASELINE', 'GDD20_SEASON_START', 'GDD20_SEASON_END', 'MAX_TLAI_PERHARV'
! hist_fincl3 += 'FROOTC_AT_EMERGENCE_PERHARV', 'FROOTC_AT_ANTHESIS_PERHARV', 'FROOTC_AT_MATURITY_PERHARV', 'FROOTC_AT_HARVEST_PERHARV'
! hist_fincl3 += 'LIVECROOTC_AT_EMERGENCE_PERHARV', 'LIVECROOTC_AT_ANTHESIS_PERHARV', 'LIVECROOTC_AT_MATURITY_PERHARV', 'LIVECROOTC_AT_HARVEST_PERHARV'
! hist_fincl3 += 'LIVESTEMC_AT_EMERGENCE_PERHARV', 'LIVESTEMC_AT_ANTHESIS_PERHARV', 'LIVESTEMC_AT_MATURITY_PERHARV', 'LIVESTEMC_AT_HARVEST_PERHARV'
hist_fincl3 += 'LEAFC_AT_EMERGENCE_PERHARV', 'LEAFC_AT_ANTHESIS_PERHARV', 'LEAFC_AT_MATURITY_PERHARV', 'LEAFC_AT_HARVEST_PERHARV'
! hist_fincl3 += 'REPRC_AT_EMERGENCE_PERHARV', 'REPRC_AT_ANTHESIS_PERHARV', 'REPRC_AT_MATURITY_PERHARV', 'REPRC_AT_HARVEST_PERHARV'
hist_fincl3 += "GPP", "GRAINC_TO_FOOD"

! h3: daily, PFT, not gridded
hist_nhtfrq(4) = -24
hist_dov2xy(4) = .false.
hist_mfilt(4) = 365
hist_type1d_pertape(4) = 'PFTS'
hist_fincl4 = 'GRAINC_TO_FOOD', 'GPP'
hist_fincl4 += 'GRAINC_TO_FOOD_ANN'  ! Invalid when saved sub-annually; should warn and skip

! h4: monthly, PFT, not gridded
hist_nhtfrq(5) = 0
hist_dov2xy(5) = .false.
hist_mfilt(5) = 12
hist_type1d_pertape(5) = 'PFTS'
hist_fincl5 = 'GRAINC_TO_FOOD', 'GPP'
hist_fincl5 += 'GRAINC_TO_FOOD_ANN'  ! Invalid when saved sub-annually; should warn and skip

! h5: annual, PFT, not gridded
hist_nhtfrq(6) = -8760
hist_dov2xy(6) = .false.
hist_mfilt(6) = 2  ! to ensure we test properly with time dimension ≠ 1
hist_type1d_pertape(6) = 'PFTS'
hist_fincl6 = 'SDATES', 'GRAINC_TO_FOOD_PERHARV', 'GRAINC_TO_FOOD_ANN'
hist_fincl6 += "GPP", "GRAINC_TO_FOOD"
EOL
popd 1>/dev/null

# Case with coarser-than-PFT-level outputs
case="${case_parent_dir}/clm_crop_pp_testdata_nonpft"
cime/scripts/create_newcase --compset ${compset} --res ${res} --run-unsupported --case ${case}
pushd ${case} 1>/dev/null
./case.setup
# Run for 3 years + a bit over a month to test handling of incomplete years
./xmlchange STOP_OPTION=ndays,STOP_N=${stop_n}

cat >user_nl_clm <<EOL
hist_empty_htapes = .true.

! h0: annual, column, not gridded
hist_nhtfrq(1) = -8760
hist_dov2xy(1) = .false.
hist_mfilt(1) = 2  ! to ensure we test properly with time dimension ≠ 1
hist_type1d_pertape(1) = 'COLS'
hist_fincl1 = 'SDATES', 'GRAINC_TO_FOOD_PERHARV', 'GRAINC_TO_FOOD_ANN'
hist_fincl1 += "GPP", "GRAINC_TO_FOOD"

! h1: annual, landunit, not gridded
hist_nhtfrq(2) = -8760
hist_dov2xy(2) = .false.
hist_mfilt(2) = 2  ! to ensure we test properly with time dimension ≠ 1
hist_type1d_pertape(2) = 'LAND'
hist_fincl2 = "GPP", "GRAINC_TO_FOOD"
!hist_fincl2 += 'SDATES', 'GRAINC_TO_FOOD_PERHARV', 'GRAINC_TO_FOOD_ANN'
! DISABLED; see https://github.com/ESCOMP/CTSM/issues/4009

! h2: annual, gridcell, not gridded
hist_nhtfrq(3) = -8760
hist_dov2xy(3) = .false.
hist_mfilt(3) = 2  ! to ensure we test properly with time dimension ≠ 1
hist_type1d_pertape(3) = 'GRID'
hist_fincl3 = 'SDATES', 'GRAINC_TO_FOOD_PERHARV', 'GRAINC_TO_FOOD_ANN'
hist_fincl3 += "GPP", "GRAINC_TO_FOOD"

! h3: annual, column, gridded
hist_nhtfrq(4) = -8760
hist_dov2xy(4) = .true.
hist_mfilt(4) = 2  ! to ensure we test properly with time dimension ≠ 1
hist_type1d_pertape(4) = 'COLS'
hist_fincl4 = 'SDATES', 'GRAINC_TO_FOOD_PERHARV', 'GRAINC_TO_FOOD_ANN'
hist_fincl4 += "GPP", "GRAINC_TO_FOOD"

! h4: annual, landunit, gridded
hist_nhtfrq(5) = -8760
hist_dov2xy(5) = .true.
hist_mfilt(5) = 2  ! to ensure we test properly with time dimension ≠ 1
hist_type1d_pertape(5) = 'LAND'
hist_fincl5 = 'SDATES', 'GRAINC_TO_FOOD_PERHARV', 'GRAINC_TO_FOOD_ANN'
hist_fincl5 += "GPP", "GRAINC_TO_FOOD"

! h5: annual, gridcell, gridded
hist_nhtfrq(6) = -8760
hist_dov2xy(6) = .true.
hist_mfilt(6) = 2  ! to ensure we test properly with time dimension ≠ 1
hist_type1d_pertape(6) = 'GRID'
hist_fincl6 = 'SDATES', 'GRAINC_TO_FOOD_PERHARV', 'GRAINC_TO_FOOD_ANN'
hist_fincl6 += "GPP", "GRAINC_TO_FOOD"
EOL
popd 1>/dev/null

exit 0
