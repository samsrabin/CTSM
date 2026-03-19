#!/usr/bin/env bash
set -euo pipefail

module load nco
module load nccmp
cd /glade/work/samrabin/ctsm_replace-more-netcdfs-with-ifx-issues

file0=/glade/campaign/collections/gdex/data/d651077/cesmdata/inputdata/lnd/clm2/initdata_esmf/ctsm5.4/ctsm5.4.CMIP7_ciso_ctsm5.3.075_f09_124_HIST.clm2.r.2000-01-01-00000.nc
#file0=/glade/campaign/cesm/cesmdata/cseg/inputdata/lnd/clm2/initdata_esmf/ctsm5.4/ctsm5.4.CMIP7_ciso_ctsm5.3.075_SP_f09_127_HIST.clm2.r.2000-01-01-00000.nc
file1=${file0/.nc/.no_nan_fill.nc}

outdir=$SCRATCH/finidat_ncap2_1var
mkdir -p $outdir

# Function to get the output file
function get_output_file {
    fn_var=$1
    file2_base=$(basename $file1)
    file2_base=${file2_base/.nc/.$fn_var.nc}
    file2=$outdir/$file2_base
    echo $file2
}

# Get variables to process
echo "Getting variables to process..."
set +o pipefail
vars="$(nccmp -dfN -c 1 $file0 $file1 2>&1 | cut -d" " -f5)"
set -o pipefail
n_vars=$(echo $vars | wc -w)
echo -e "Found ${n_vars} variables.\n"

############################
### Setting up the tests ###
############################
git stash 1>/dev/null

# Delete </testlist> line
xml_file="cime_config/testdefs/testlist_clm.xml"
sed -i "\@</testlist>@d" $xml_file

for var in $vars; do
    file2="$(get_output_file $var)"

    # Make the testmod
    testmod_dir_base="finidat_ncap2_1var_${var}"
    testmod_dir="cime_config/testdefs/testmods_dirs/clm/$testmod_dir_base"
    mkdir -p $testmod_dir
    echo "finidat = '$file2'" > $testmod_dir/user_nl_clm

    # Put text in XML
    cat <<EOF >> $xml_file
  <test name="SMS_D" grid="f10_f10_mg37" compset="I2000Clm60Bgc" testmods="clm/$testmod_dir_base">
    <machines>
      <machine name="derecho" compiler="gnu" category="finidat_ncap2_1var"/>
    </machines>
    <options>
      <option name="wallclock">00:20:00</option>
    </options>
  </test>

EOF

    # Link original test to new location for comparison
    pushd /glade/campaign/cgd/tss/ctsm_baselines 1>/dev/null
    tag="ctsm5.4.022"
    newtag="${tag}_finidat_ncap2_1var"
    mkdir -p $newtag
    cd $newtag
    test="SMS_D.f10_f10_mg37.I2000Clm60Bgc.derecho_gnu"
    newtest="$test.clm-$testmod_dir_base"
    ln -sf ../$tag/$test $newtest
    popd 1>/dev/null


done

# Put back </testlist>
echo "</testlist>" >> $xml_file

# Print end of testlist
echo "########## End of testlist file ##########"
tail -n 30 $xml_file
echo "##########################################"
echo " "


####################################
### Making the new finidat files ###
####################################

n=0
for var in $vars; do
    n=$((n+1))
    file2="$(get_output_file $var)"
    if [[ -e $file2 ]]; then
        echo "$n/$n_vars: Skipping $var because output file exists"
        continue
    fi
    echo "$n/$n_vars: Processing $var..."
    ncap2 -O -s "where(${var}!=${var}) ${var}=1e36; " $file0 $file2

    # Make sure it worked
    echo "nccmp result:"
    set +e
    nccmp -dfsN -c 1 $file0 $file2
    set -e

    echo " "
done

echo "Done!"
exit 0

