#!/bin/bash
set -e

ssp=$1
if [[ ${ssp} == "" ]]; then
    echo "You must provide an SSP number (e.g., 245)" >&2
    exit 1
fi

casedir="$HOME/cases_ctsm/test_cdeps_ssp-temperature"
compset="SSP${ssp}_DATM%GSWP3v1_CLM51%BGC-CROP_SICE_SOCN_MOSART_CISM2%NOEVOLVE_SWAV"
res="f10_f10_mg37"

if [[ -d "${casedir}" ]]; then
    rm -r "${casedir}"
fi

cime/scripts/create_newcase --run-unsupported --case "${casedir}" --compset ${compset} --res ${res} \
    --handle-preexisting-dirs r

cd "${casedir}"
./case.setup
echo "anomaly_forcing = 'Anomaly.Forcing.Temperature'" >> user_nl_datm

echo "Generating namelists..."
./preview_namelists  1>/dev/null

./xmlquery COMPSET
grep "<file>" CaseDocs/datm.streams.xml | grep anomaly_forcing | grep '.tas.'

exit 0
