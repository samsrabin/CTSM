#!/usr/bin/env python

# =======================================================================================
# This script modifies any FATES parameter file to update it to a new API spec.
#    It can change variable names
#    It can add new variables
#    It can add attributes
#    It can update attributes
#    It can add new dimensions
# =======================================================================================

import os
import argparse
import code  # For development: code.interact(local=dict(globals(), **locals()))
from scipy.io import netcdf
import xml.etree.ElementTree as et

# =======================================================================================

def load_xml(xmlfile): 

    # This routine parses the XML tree

    xmlroot = et.parse(xmlfile).getroot()
    print("\nOpened: {}\n".format(xmlfile))

    base_cdl = xmlroot.find('base_file').text
    new_cdl = xmlroot.find('new_file').text

    pft_list = xmlroot.find('pft_list').text.replace(" ","")
    
    modroot = xmlroot.find('mods') 

    return(base_cdl,new_cdl,pft_list,modroot)

# =======================================================================================

def str2fvec(numstr):

    # Convert a list of strings into floating point numbers
    
    numvec = [float(i) for i in numstr.split(',')]
    return(numvec)

# =======================================================================================

def str2ivec(numstr):

    # Convert a list of strings into integer numbers
    
    intvec = [int(i) for i in numstr.split(',')]
    return(intvec)

# =======================================================================================

def createvar(ncfile,paramname,dimnames,units,longname,usecase,sel_values):

    # Create a new netcdf variable inside an existing netcdf dataset (append)
    
    ncvar = ncfile.createVariable(paramname,'d',dimnames)
    ncvar.units = units
    ncvar.long_name = longname
    ncvar.use_case = usecase
    ncvar[:] = sel_values
    ncfile.flush()
    
    return(ncfile,ncvar)

# =======================================================================================

def selectvalues(ncfile,dimnames,ipft_list,values):

    # Reduce a list of values so that onlythe chosen pft values are left. This
    # only works on float arrays currently.  We need to pass in a file
    # so that we can get the dimension sizes associated with the dimension names.

    if(len(ipft_list) != ncfile.dimensions['fates_pft']):
        print('you list of pfts in the xml file must be')
        print('the same size as the fates_pft dimension')
        print('in your destination file. exiting')
        print('len(ipft_list) = {}'.format(len(ipft_list)))
        print('fates_pft dim = {}'.format(ncfile.dimensions['fates_pft']))
        exit(2)
    
    pft_dim = -1
    dim2_size = 1
    for idim,name in enumerate(list(dimnames)):
        if(name=='fates_pft'):
            pft_dim = idim
            pft_dim_size = ncfile.dimensions['fates_pft']
        else:
            dim2_size = ncfile.dimensions[name]

    sel_values = []
    if(pft_dim==0):
        for j in range(dim2_size):
            i0 = j*pft_dim_size 
            for i in ipft_list:
                sel_values.append(values[i-1+i0])
    elif(pft_dim==1):
        for i in ipft_list:
            i0 = i*dim2_size
            for j in range(dim2_size):
                sel_values.append(values[j-1+i0])
    else:
        sel_values = values

    return(sel_values)

# =======================================================================================

def removevar(base_nc,varname):

    # Remove a variable from a dataset. This is actually the hardest thing to do!
    # The trick here, is to copy the whole file, minus the variable of interest
    # into a temp file. Then completely remove the old file, and 

    fp_base = netcdf.netcdf_file(base_nc, 'r',mmap=False)

    new_nc = os.popen('mktemp').read().rstrip('\n')
    fp_new  = netcdf.netcdf_file(new_nc, 'w',mmap=False)

    for key, value in sorted(fp_base.dimensions.items()):
        fp_new.createDimension(key,int(value))

    found = False
    for key, value in fp_base.variables.items():

        if(key == varname):
            found = True
        else:
            datatype = value.typecode()
            new_var = fp_new.createVariable(key,datatype,value.dimensions)
            if(value.data.size == 1):
                new_var.assignValue(float(value.data))
            else:
                new_var[:] = value[:].copy()
                
            new_var.units = value.units
            new_var.long_name = value.long_name
            try:
                new_var.use_case = value.use_case
            except:
                new_var.use_case = "undefined"
    
    fp_new.history = fp_base.history

    if(not found):
        print("was not able to find variable: ()".format(varname))
        exit(2)

    fp_new.flush()
    fp_base.close()
    fp_new.close()
    
    mvcmd = "(rm -f "+base_nc+";mv "+new_nc+" "+base_nc+")"
    os.system(mvcmd)
    
    
# =======================================================================================

def main():

    # Parse arguments
    parser = argparse.ArgumentParser(description='Parse command line arguments to this script.')
    parser.add_argument('--f', dest='xmlfile', type=str, help="XML control file  Required.", required=True)
    args = parser.parse_args()


    # Load the xml file, which contains the base cdl, the output cdl,
    #  and the parameters to be modified
    [base_cdl,new_cdl,pft_list,modroot] = load_xml(args.xmlfile)

    ipft_list = str2ivec(pft_list)

    
    # Convert the base cdl file into a temp nc binary
    base_nc = os.popen('mktemp').read().rstrip('\n')
    gencmd = "ncgen -o "+base_nc+" "+base_cdl
    os.system(gencmd)
    
    modlist = []
    for mod in modroot:
        if(not('type' in mod.attrib.keys())):
            print("mod tag must have attribute type")
            print("exiting")
            exit(2)

        if(mod.attrib['type'].strip() == 'dimension_add'):

            try:
                dimname = mod.find('di').text.strip()
            except:
                print("{}, no dimension (di), exiting".format(mod.attrib['type']));exit(2)

            try:
                values = str2fvec(mod.find('val').text.strip())
            except:
                print("no values (val), exiting");exit(2)
                
            if(len(values)>1):
                print("The dimension size should be a scalar")
                exit(2)

            ncfile = netcdf.netcdf_file(base_nc,"a",mmap=False)
            ncfile.createDimension(dimname, values[0])
            ncfile.flush()
            ncfile.close()

            print("dimension: {}, size: {}, added".format(dimname,values[0]))
            
            
        elif(mod.attrib['type'].strip() == 'variable_add'):

            try:
                paramname = mod.find('na').text.strip()
            except:
                print("no name (na), exiting");exit(2)

            try:
                dimnames = tuple([mod.find('di').text.strip()])
            except:
                print("no dimension (di), exiting");exit(2)
                
            try:
                units = mod.find('un').text.strip()
            except:
                print("no units (un), exiting");exit(2)
                
            try:
                longname = mod.find('ln').text.strip()
            except:
                print("no long-name (ln), exiting");exit(2)
                
            try:
                usecase = mod.find('uc').text.strip()
            except:
                print("no use case (uc), exiting");exit(2)
                
            try:
                values = str2fvec(mod.find('val').text.strip())
            except:
                print("no values (val), exiting");exit(2)

            sel_values = selectvalues(ncfile,list(dimnames),ipft_list,values)
                        
            ncfile = netcdf.netcdf_file(base_nc,"a",mmap=False)
            [ncfile,ncvar] = createvar(ncfile,paramname,dimnames,units,longname,usecase,sel_values)
            ncfile.flush()
            ncfile.close()

            print("parameter: {}, added".format(paramname))

            
        elif(mod.attrib['type'] == 'variable_del'):
            try:
                paramname = mod.attrib['name']
            except:
                print('must define the parameter name to delete, using <na>')
                exit(2)
            removevar(base_nc,paramname)
            print("parameter: {}, removed".format(paramname))

            
        elif(mod.attrib['type'] == 'variable_change'):  

            try:
                paramname_o = mod.attrib['name'].strip()
            except:
                print("to change a parameter, the field must have a name attribute")
                exit(2)
                
            ncfile = netcdf.netcdf_file(base_nc,"a",mmap=False)
            ncvar_o = ncfile.variables[paramname_o]
            dims_o  = ncvar_o.dimensions
            units_o = ncvar_o.units.decode("utf-8")
            longname_o = ncvar_o.long_name.decode("utf-8")
            try:
                usecase_o = ncvar_o.use_case.decode("utf-8")
            except:
                usecase_o = 'undefined'

            try:
                paramname = mod.find('na').text.strip()
            except:
                paramname = None

            # Change the parameter's name
            if(not isinstance(paramname,type(None))):
                [ncfile,ncvar] = createvar(ncfile,paramname,dims_o,units_o,longname_o,usecase_o,ncvar_o[:].copy())
            else:
                ncvar = ncvar_o
               
            # Change the metadata:
            try:
                units = mod.find('un').text.strip()
            except:
                units = None
            if(not isinstance(units,type(None))):
                ncvar.units = units 
                
            try:
                longname = mod.find('ln').text.strip()
            except:
                longname = None
            if(not isinstance(longname,type(None))):
                ncvar.long_name = longname
                
            try:
                usecase = mod.find('uc').text.strip()
            except:
                usecase = None
            if(not isinstance(usecase,type(None))):
                ncvar.use_case = use_case
                
            try:
                values = str2fvec(mod.find('val').text.strip())
            except:
                values = None
                
            if(not isinstance(values,type(None))):
                sel_values = selectvalues(ncfile,list(dims_o),ipft_list,values)
                    
                # Scalars have their own thing
                if(ncvar.data.size == 1):
                    ncvar.assignValue(float(sel_values[0]))
                else:
                    ncvar[:] = sel_values[:]

                
            ncfile.flush()
            ncfile.close()
            
            # Finally, if we did perform a re-name, and
            # created a new variable. We need to delete the
            # old one
            if(not isinstance(paramname,type(None))):
               removevar(base_nc,paramname_o)
            
            print("parameter: {}, modified".format(paramname))

               
    # Sort the new file
    new_nc = os.popen('mktemp').read().rstrip('\n')
    os.system("../tools/ncvarsort.py --silent --fin "+base_nc+" --fout "+new_nc+" --overwrite")

    # Dump the new file to the cdl
    os.system("ncdump "+new_nc+" > "+new_cdl)

    
    
    print("\nAPI update complete, see file: {}\n".format(new_cdl))
    
        
# This is the actual call to main

if __name__ == "__main__":
    main()
