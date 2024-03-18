import argparse
import os
import shutil
import sys
import numpy as np
import netCDF4 as netcdf4

'''
 specify a synthetic hillslope profile
'''

def parse_arguments(argv):
    """
    Parse arguments to script
    """
    parser = argparse.ArgumentParser(description="Specify a synthetic hillslope profile")

    # Input and output file settings
    parser.add_argument(
        "-i", "--input-file",
        help="Input surface dataset",
        required=True,
    )
    parser.add_argument(
        "-o", "--output-file",
        help="Output surface dataset",
        default=None,
    )
    parser.add_argument(
        "--overwrite",
        help="Overwrite existing output file",
        dest="overwrite",
        action="store_true",
    )

    # Synthetic hillslope settings
    parser.add_argument(
        "--delx",
        help="increments to use in numerical integration of mean elevation (m)",
        type=float,
        default=1.0,
    )
    parser.add_argument(
        "--hcase",
        help="hcase",
        type=str,
        default="slope_aspect",
        choices=["slope_aspect"],
    )
    parser.add_argument(
        "--hillslope-distance",
        help="distance from channel to ridge (m)",
        type=float,
        default=500.0,
    )
    parser.add_argument(
        "--nmaxhillcol",
        help="max. number of hillslope columns",
        type=int,
        default=16,
    )
    parser.add_argument(
        "--num-hillslopes",
        help="number of hillslopes",
        type=int,
        default=4,
    )
    parser.add_argument(
        "--phill",
        help="shape parameter (power law exponent)",
        type=float,
        default=1.0,
    )
    parser.add_argument(
        "--thresh",
        help="threshold for freating specified fractional bins",
        type=float,
        default=2.0,
    )
    parser.add_argument(
        "--width-reach",
        help="uniform width of reach (m)",
        type=float,
        default=500.0,
    )

    args = parser.parse_args(argv)
    
    if args.output_file is None:
        stem, ext = os.path.splitext(args.input_file)
        args.output_file = stem + ".synth_hillslopes" + ext
    
    if os.path.exists(args.output_file) and not args.overwrite:
        raise FileExistsError(f"Output file already exists: {args.output_file}")
    
    return args

def main(argv):
    
    args = parse_arguments(argv)
    
    f =  netcdf4.Dataset(args.input_file, 'r')
    im = len(f.dimensions['lsmlon'])
    jm = len(f.dimensions['lsmlat'])
    std_elev = np.asarray(f.variables['STD_ELEV'][:,:])
    lmask = np.asarray(f.variables['PFTDATA_MASK'][:,:])
    pct_natveg = np.asarray(f.variables['PCT_NATVEG'][:,:])
    f.close()

    # are any points in land mask but have zero % natveg?
    print('zero natveg pts ',np.sum(np.where(np.logical_and(lmask==1,pct_natveg==0),1,0)))
    lmask = np.where(np.logical_and(lmask==1,pct_natveg>0),1,0).astype(int)

    if args.hcase == 'slope_aspect':
        max_columns_per_hillslope = args.nmaxhillcol//args.num_hillslopes
        
        if max_columns_per_hillslope == 4:
            bin_fractions = np.array((0.25, 0.75, 1.0))
        elif max_columns_per_hillslope == 5:
            bin_fractions = np.array((0.25, 0.50, 0.75, 1.0))
        elif max_columns_per_hillslope == 6:
            bin_fractions = np.array((0.20, 0.40, 0.60, 0.80, 1.0))
        else:
            raise RuntimeError(f"Unhandled max_columns_per_hillslope: {max_columns_per_hillslope}")

        max_columns_per_landunit = args.num_hillslopes * max_columns_per_hillslope

        #--  define geometry of hillslopes
        # percentage of landunit occupied by each hillslope (must sum to 100)
        pct_landunit = np.zeros((args.num_hillslopes,jm,im))
        # distance of column midpoint from stream channel
        distance  = np.zeros((max_columns_per_landunit,jm,im),dtype=float)
        # area of column
        area      = np.zeros((max_columns_per_landunit,jm,im),dtype=float)
        # width of interface with downstream column (or channel)
        width     = np.zeros((max_columns_per_landunit,jm,im),dtype=float)
        # elevation of column midpoint
        elevation = np.zeros((max_columns_per_landunit,jm,im),dtype=float)
        # mean slope of column
        slope     = np.zeros((max_columns_per_landunit,jm,im),dtype=float)
        # azimuth angle of column
        aspect    = np.zeros((max_columns_per_landunit,jm,im),dtype=float)
        # column identifier index
        col_ndx   = np.zeros((max_columns_per_landunit,jm,im),dtype=np.int32)
        # index of downhill column
        col_dndx  = np.zeros((max_columns_per_landunit,jm,im),dtype=np.int32)
        # index of hillslope type
        hill_ndx  = np.zeros((max_columns_per_landunit,jm,im),dtype=np.int32)


        '''  
        ---------------------------------------------------
        #cosine - power law hillslope
        create bins of equal height
        this form ensures a near-zero slope at the hill top
        ---------------------------------------------------
        '''  

        def cosp_height(x,hlen,hhgt,phill):
            fx=0.5*(1.0+np.cos(np.pi*(1.0+(x/hlen))))
            h=hhgt*np.power(fx,phill)
            return h

        def icosp_height(h,hlen,hhgt,phill):
            if hhgt <= 0.0:
                x = 0.0
            else:
                fh=np.arccos(2.0*np.power((h/hhgt),(1.0/phill))-1)
                # np.arccos returns [0,pi]
                # want [pi,2pi] based on cosp_height definition
                fh = 2.0*np.pi - fh
                x=hlen*((1./np.pi)*fh - 1.0)
            return x

        cndx = 0
        for i in range(im):
            for j in range(jm):
                if lmask[j,i] == 1:

                    # slope tangent (y/x)
                    beta = np.min((std_elev[j,i],200.0))/args.hillslope_distance

                    # specify hill height from slope and length
                    hhgt = beta * args.hillslope_distance
                    hhgt = np.max([hhgt,4.0])

                    # create specified fractional bins
                    hbins = np.zeros(max_columns_per_hillslope+1)
                    hbins[1] = args.thresh
                    # array needs to be length max_columns_per_hillslope-1
                    hbins[2:max_columns_per_hillslope+1] = hbins[1] \
                    + (hhgt - args.thresh) * bin_fractions

                    # create length bins from height bins
                    lbins=np.zeros(max_columns_per_hillslope+1)
                    for n in range(max_columns_per_hillslope+1):
                        if hhgt > 0.:
                            lbins[n] = icosp_height(hbins[n],args.hillslope_distance,hhgt,args.phill)

                    # loop over aspect bins
                    for naspect in range(args.num_hillslopes):
                        pct_landunit[naspect,j,i]  = 100/float(args.num_hillslopes)
                        # index from ridge to channel (i.e. downhill)
                        for n in range(max_columns_per_hillslope):
                            ncol = n + naspect*max_columns_per_hillslope

                            cndx += 1 # start at 1 not zero (oceans are 0)
                            col_ndx[ncol,j,i] = cndx
                            hill_ndx[ncol,j,i] = (naspect + 1)

                            uedge = lbins[n+1]
                            ledge = lbins[n]
                            #      lowland column
                            if n == 0:
                                col_dndx[ncol,j,i] = -999
                            else:# upland columns
                                col_dndx[ncol,j,i] = col_ndx[ncol,j,i]-1

                            distance[ncol,j,i]  = 0.5*(uedge + ledge)
                            area[ncol,j,i]      = args.width_reach*(uedge - ledge)
                            width[ncol,j,i]     = args.width_reach
                            # numerically integrate to calculate mean elevation
                            nx = int(uedge - ledge)
                            mean_elev = 0.
                            for k in range(nx):
                                x1 = uedge - (k+0.5)*args.delx
                                mean_elev += cosp_height(x1,args.hillslope_distance,hhgt,args.phill)
                            mean_elev = mean_elev/float(nx)

                            elevation[ncol,j,i] = mean_elev

                            slope[ncol,j,i]     = (hbins[n+1]-hbins[n])/(lbins[n+1]-lbins[n])
                            if naspect == 0: # north
                                aspect[ncol,j,i] = 0.
                            if naspect == 1: # east
                                aspect[ncol,j,i] = 0.5*np.pi
                            if naspect == 2: # south
                                aspect[ncol,j,i] = np.pi
                            if naspect == 3: # west
                                aspect[ncol,j,i] = 1.5*np.pi


    # write to file  --------------------------------------------
    shutil.copyfile(args.input_file, args.output_file)

    w =  netcdf4.Dataset(args.output_file, 'a')
    w.createDimension('nhillslope',args.num_hillslopes)
    w.createDimension('nmaxhillcol',max_columns_per_landunit)

    ohand = w.createVariable('hillslope_elevation',np.float64,('nmaxhillcol','lsmlat','lsmlon',))
    ohand.units = 'm'
    ohand.long_name = 'hillslope elevation'

    odtnd = w.createVariable('hillslope_distance',np.float64,('nmaxhillcol','lsmlat','lsmlon',))
    odtnd.units = 'm'
    odtnd.long_name = 'hillslope distance'

    owidth = w.createVariable('hillslope_width',np.float64,('nmaxhillcol','lsmlat','lsmlon',))
    owidth.units = 'm'
    owidth.long_name = 'hillslope width'

    oarea = w.createVariable('hillslope_area',np.float64,('nmaxhillcol','lsmlat','lsmlon',))
    oarea.units = 'm2'
    oarea.long_name = 'hillslope area'

    oslop = w.createVariable('hillslope_slope',np.float64,('nmaxhillcol','lsmlat','lsmlon',))
    oslop.units = 'm/m'
    oslop.long_name = 'hillslope slope'

    oasp  = w.createVariable('hillslope_aspect',np.float64,('nmaxhillcol','lsmlat','lsmlon',))
    oasp.units = 'radians'
    oasp.long_name = 'hillslope aspect (clockwise from North)'

    onhill = w.createVariable('nhillcolumns',np.int32,('lsmlat','lsmlon',))
    onhill.units = 'unitless'
    onhill.long_name = 'number of columns per landunit'

    opcthill  = w.createVariable('pct_hillslope',np.float64,('nhillslope','lsmlat','lsmlon',))
    opcthill.units = 'per cent'
    opcthill.long_name = 'percent hillslope of landunit'

    ohillndx  = w.createVariable('hillslope_index',np.int32,('nmaxhillcol','lsmlat','lsmlon',))
    ohillndx.units = 'unitless'
    ohillndx.long_name = 'hillslope_index'

    ocolndx  = w.createVariable('column_index',np.int32,('nmaxhillcol','lsmlat','lsmlon',))
    ocolndx.units = 'unitless'
    ocolndx.long_name = 'column index'

    odcolndx  = w.createVariable('downhill_column_index',np.int32,('nmaxhillcol','lsmlat','lsmlon',))
    odcolndx.units = 'unitless'
    odcolndx.long_name = 'downhill column index'

    obed = w.createVariable('hillslope_bedrock_depth',np.float64,('nmaxhillcol','lsmlat','lsmlon',))
    obed.units = 'meters'
    obed.long_name = 'hillslope bedrock depth'

    opft = w.createVariable('hillslope_pftndx',np.int32,('nmaxhillcol','lsmlat','lsmlon',))
    opft.units = 'unitless'
    opft.long_name = 'hillslope pft indices'


    w.variables['nhillcolumns'][:,:] = max_columns_per_landunit * lmask
    w.variables['pct_hillslope'][:,] = pct_landunit
    w.variables['hillslope_index'][:,] = hill_ndx
    w.variables['column_index'][:,] = col_ndx
    w.variables['downhill_column_index'][:,] = col_dndx
    w.variables['hillslope_distance'][:,] = distance
    w.variables['hillslope_width'][:,]  = width
    w.variables['hillslope_elevation'][:,] = elevation
    w.variables['hillslope_slope'][:,]  = slope
    w.variables['hillslope_aspect'][:,] = aspect
    w.variables['hillslope_area'][:,]   = area
    w.variables['hillslope_bedrock_depth'][:,] = 2
    w.variables['hillslope_pftndx'][:,]  = 13

    # add stream variables
    wdepth = w.createVariable('hillslope_stream_depth', np.float64, ('lsmlat','lsmlon'))
    wwidth = w.createVariable('hillslope_stream_width', np.float64, ('lsmlat','lsmlon'))
    wslope = w.createVariable('hillslope_stream_slope', np.float64, ('lsmlat','lsmlon'))

    wdepth.long_name = 'stream channel bankfull depth'
    wdepth.units    = 'm'

    wwidth.long_name = 'stream channel bankfull width'
    wwidth.units    = 'm'

    wslope.long_name = 'stream channel slope'
    wslope.units    = 'm/m'

    # Calculate stream geometry from hillslope parameters
    uharea = np.sum(area,axis=0)
    adepth, bdepth = 1e-3, 0.4
    wdepth[:,] = adepth*(uharea**bdepth)
    awidth, bwidth = 1e-3, 0.6
    wwidth[:,] = awidth*(uharea**bwidth)
    wslope[:,] = 1e-2

    # Save settings as global attributes
    w.synth_hillslopes_delx = args.delx
    w.synth_hillslopes_hcase = args.hcase
    w.synth_hillslopes_hillslope_distance = args.hillslope_distance
    w.synth_hillslopes_nmaxhillcol = args.nmaxhillcol
    w.synth_hillslopes_num_hillslopes = args.num_hillslopes
    w.synth_hillslopes_phill = args.phill
    w.synth_hillslopes_thresh = args.thresh
    w.synth_hillslopes_width_reach = args.width_reach
            
    print('created ',args.output_file)

    #--  Close output file
    w.close


if __name__ == "__main__":
    main(sys.argv[1:])