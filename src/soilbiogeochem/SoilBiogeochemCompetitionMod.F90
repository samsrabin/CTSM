module SoilBiogeochemCompetitionMod
  
  !-----------------------------------------------------------------------
  ! !DESCRIPTION:
  ! Resolve plant/heterotroph competition for mineral N
  !
  ! !USES:
  use shr_kind_mod                    , only : r8 => shr_kind_r8
  use shr_log_mod                     , only : errMsg => shr_log_errMsg
  use clm_varcon                      , only : dzsoi_decomp
  use clm_varctl                      , only : use_nitrif_denitrif
  use abortutils                      , only : endrun
  use decompMod                       , only : bounds_type
  use SoilBiogeochemStateType         , only : soilbiogeochem_state_type
  use SoilBiogeochemCarbonStateType   , only : soilbiogeochem_carbonstate_type
  use SoilBiogeochemCarbonFluxType    , only : soilbiogeochem_carbonflux_type
  use SoilBiogeochemNitrogenStateType , only : soilbiogeochem_nitrogenstate_type
  use SoilBiogeochemNitrogenStateType , only : soilbiogeochem_nitrogenstate_type
  use SoilBiogeochemNitrogenFluxType  , only : soilbiogeochem_nitrogenflux_type
  use SoilBiogeochemNitrogenUptakeMod , only : SoilBiogeochemNitrogenUptake
  use ColumnType                      , only : col                
  use CNVegstateType                  , only : cnveg_state_type
  use CNVegCarbonStateType            , only : cnveg_carbonstate_type
  use CNVegCarbonFluxType             , only : cnveg_carbonflux_type
  use CNVegnitrogenstateType          , only : cnveg_nitrogenstate_type
  use CNVegnitrogenfluxType           , only : cnveg_nitrogenflux_type
  !use SoilBiogeochemCarbonFluxType    , only : soilbiogeochem_carbonflux_type
  use WaterStateBulkType                  , only : waterstatebulk_type
  use WaterFluxBulkType                   , only : waterfluxbulk_type
  use TemperatureType                 , only : temperature_type
  use SoilStateType                   , only : soilstate_type
  use CanopyStateType                 , only : CanopyState_type
  use CLMFatesInterfaceMod, only : hlm_fates_interface_type
  !
  implicit none
  private
  !
  ! !PUBLIC MEMBER FUNCTIONS:
  public :: readParams
  public :: SoilBiogeochemCompetitionInit         ! Initialization
  public :: SoilBiogeochemCompetition             ! run method

  type :: params_type
     real(r8) :: bdnr              ! bulk denitrification rate (1/s)
     real(r8) :: compet_plant_no3  ! (unitless) relative compettiveness of plants for NO3
     real(r8) :: compet_plant_nh4  ! (unitless) relative compettiveness of plants for NH4
     real(r8) :: compet_decomp_no3 ! (unitless) relative competitiveness of immobilizers for NO3
     real(r8) :: compet_decomp_nh4 ! (unitless) relative competitiveness of immobilizers for NH4
     real(r8) :: compet_denit      ! (unitless) relative competitiveness of denitrifiers for NO3
     real(r8) :: compet_nit        ! (unitless) relative competitiveness of nitrifiers for NH4
  end type params_type
  !
  type(params_type), private :: params_inst  ! params_inst is populated in readParamsMod  
  !
  ! !PUBLIC DATA MEMBERS:
  character(len=* ), public, parameter :: suplnAll='ALL'       ! Supplemental Nitrogen for all PFT's
  character(len=* ), public, parameter :: suplnNon='NONE'      ! No supplemental Nitrogen
  character(len=15), public            :: suplnitro = suplnNon ! Supplemental Nitrogen mode
  !
  ! !PRIVATE DATA MEMBERS:
  real(r8) :: dt   ! decomp timestep (seconds)
  real(r8) :: bdnr ! bulk denitrification rate (1/s)

  character(len=*), parameter, private :: sourcefile = &
       __FILE__
  !-----------------------------------------------------------------------

contains

  !-----------------------------------------------------------------------
  subroutine readParams ( ncid )
    !
    ! !USES:
    use ncdio_pio , only : file_desc_t,ncd_io

    ! !ARGUMENTS:
    type(file_desc_t),intent(inout) :: ncid   ! pio netCDF file id
    !
    ! !LOCAL VARIABLES:
    character(len=32)  :: subname = 'readParams'
    character(len=100) :: errCode = '-Error reading in parameters file:'
    logical            :: readv ! has variable been read in or not
    real(r8)           :: tempr ! temporary to read in parameter
    character(len=100) :: tString ! temp. var for reading
    !-----------------------------------------------------------------------

    ! read in parameters

    tString='bdnr'
    call ncd_io(varname=trim(tString),data=tempr, flag='read', ncid=ncid, readvar=readv)
    if ( .not. readv ) call endrun(msg=trim(errCode)//trim(tString)//errMsg(sourcefile, __LINE__))
    params_inst%bdnr=tempr

    tString='compet_plant_no3'
    call ncd_io(varname=trim(tString),data=tempr, flag='read', ncid=ncid, readvar=readv)
    if ( .not. readv ) call endrun(msg=trim(errCode)//trim(tString)//errMsg(sourcefile, __LINE__))
    params_inst%compet_plant_no3=tempr

    tString='compet_plant_nh4'
    call ncd_io(varname=trim(tString),data=tempr, flag='read', ncid=ncid, readvar=readv)
    if ( .not. readv ) call endrun(msg=trim(errCode)//trim(tString)//errMsg(sourcefile, __LINE__))
    params_inst%compet_plant_nh4=tempr
   
    tString='compet_decomp_no3'
    call ncd_io(varname=trim(tString),data=tempr, flag='read', ncid=ncid, readvar=readv)
    if ( .not. readv ) call endrun(msg=trim(errCode)//trim(tString)//errMsg(sourcefile, __LINE__))
    params_inst%compet_decomp_no3=tempr

    tString='compet_decomp_nh4'
    call ncd_io(varname=trim(tString),data=tempr, flag='read', ncid=ncid, readvar=readv)
    if ( .not. readv ) call endrun(msg=trim(errCode)//trim(tString)//errMsg(sourcefile, __LINE__))
    params_inst%compet_decomp_nh4=tempr
   
    tString='compet_denit'
    call ncd_io(varname=trim(tString),data=tempr, flag='read', ncid=ncid, readvar=readv)
    if ( .not. readv ) call endrun(msg=trim(errCode)//trim(tString)//errMsg(sourcefile, __LINE__))
    params_inst%compet_denit=tempr

    tString='compet_nit'
    call ncd_io(varname=trim(tString),data=tempr, flag='read', ncid=ncid, readvar=readv)
    if ( .not. readv ) call endrun(msg=trim(errCode)//trim(tString)//errMsg(sourcefile, __LINE__))
    params_inst%compet_nit=tempr   

  end subroutine readParams

  !-----------------------------------------------------------------------
  subroutine SoilBiogeochemCompetitionInit ( bounds)
    !
    ! !DESCRIPTION:
    !
    ! !USES:
    use clm_varcon      , only: secspday
    use clm_time_manager, only: get_step_size_real
    use clm_varctl      , only: iulog, allocate_carbon_only_set
    use shr_infnan_mod  , only: nan => shr_infnan_nan, assignment(=)
    !
    ! !ARGUMENTS:
    type(bounds_type), intent(in) :: bounds  
    !
    ! !LOCAL VARIABLES:
    character(len=32) :: subname = 'SoilBiogeochemCompetitionInit'
    logical :: carbon_only
    !-----------------------------------------------------------------------

    ! set time steps
    dt = get_step_size_real()

    ! set space-and-time parameters from parameter file
    bdnr = params_inst%bdnr * (dt/secspday)

    ! Change namelist settings into private logical variables
    select case(suplnitro)
    case(suplnNon)
       carbon_only = .false.
    case(suplnAll)
       carbon_only = .true.
    case default
       write(iulog,*) 'Supplemental Nitrogen flag (suplnitro) can only be: ', &
            suplnNon, ' or ', suplnAll
       call endrun(msg='ERROR: supplemental Nitrogen flag is not correct'//&
            errMsg(sourcefile, __LINE__))
    end select

    call allocate_carbon_only_set(carbon_only)

  end subroutine SoilBiogeochemCompetitionInit

  !-----------------------------------------------------------------------
   subroutine SoilBiogeochemCompetition (bounds, num_bgc_soilc, filter_bgc_soilc,num_bgc_vegp, filter_bgc_vegp, &
                                         p_decomp_cn_gain, pmnf_decomp_cascade, waterstatebulk_inst, &
                                         waterfluxbulk_inst, temperature_inst,soilstate_inst,                          &
                                         cnveg_state_inst,cnveg_carbonstate_inst,                                  &
                                         cnveg_carbonflux_inst,cnveg_nitrogenstate_inst,cnveg_nitrogenflux_inst,   &
                                         soilbiogeochem_carbonflux_inst,                                           &              
                                         soilbiogeochem_state_inst, soilbiogeochem_nitrogenstate_inst,             &
                                         soilbiogeochem_nitrogenflux_inst,canopystate_inst, clm_fates)
    !
    ! !USES:
    use clm_varctl       , only: fates_parteh_mode, allocate_carbon_only, iulog
    use clm_varpar       , only: clmfates_carbon_only,clmfates_carbon_nitrogen
    use clm_varpar       , only: nlevdecomp, ndecomp_cascade_transitions
    use clm_varpar       , only: i_cop_mic, i_oli_mic
    use clm_varcon       , only: nitrif_n2o_loss_frac
    use CNSharedParamsMod, only: use_fun
    use CNFUNMod         , only: CNFUN
    use subgridAveMod    , only: p2c
    use perf_mod         , only : t_startf, t_stopf
    use SoilBiogeochemDecompCascadeConType , only : decomp_cascade_con,  mimics_decomp, decomp_method
    !
    ! !ARGUMENTS:
    type(bounds_type)                       , intent(in)    :: bounds
    integer                                 , intent(in)    :: num_bgc_soilc        ! number of soil columns in filter
    integer                                 , intent(in)    :: filter_bgc_soilc(:)  ! filter for soil columns
    integer                                 , intent(in)    :: num_bgc_vegp        ! number of veg patches in filter
    integer                                 , intent(in)    :: filter_bgc_vegp(:)  ! filter for veg patches
    real(r8)                                , intent(in)    :: pmnf_decomp_cascade(bounds%begc:,1:,1:)  ! potential mineral N flux from one pool to another (gN/m3/s)
    real(r8)                                , intent(in)    :: p_decomp_cn_gain(bounds%begc:,1:,1:)  ! C:N ratio of the flux gained by the receiver pool
    type(waterstatebulk_type)                   , intent(in)    :: waterstatebulk_inst
    type(waterfluxbulk_type)                    , intent(in)    :: waterfluxbulk_inst
    type(temperature_type)                  , intent(in)    :: temperature_inst
    type(soilstate_type)                    , intent(in)    :: soilstate_inst
    type(cnveg_state_type)                  , intent(inout) :: cnveg_state_inst
    type(cnveg_carbonstate_type)            , intent(inout) :: cnveg_carbonstate_inst
    type(cnveg_carbonflux_type)             , intent(inout) :: cnveg_carbonflux_inst
    type(cnveg_nitrogenstate_type)          , intent(inout) :: cnveg_nitrogenstate_inst
    type(cnveg_nitrogenflux_type)           , intent(inout) :: cnveg_nitrogenflux_inst
    type(soilbiogeochem_carbonflux_type)    , intent(inout) :: soilbiogeochem_carbonflux_inst
    type(soilbiogeochem_state_type)         , intent(inout) :: soilbiogeochem_state_inst
    type(soilbiogeochem_nitrogenstate_type) , intent(inout) :: soilbiogeochem_nitrogenstate_inst
    type(soilbiogeochem_nitrogenflux_type)  , intent(inout) :: soilbiogeochem_nitrogenflux_inst
    type(canopystate_type)                  , intent(inout) :: canopystate_inst   
    type(hlm_fates_interface_type), intent(inout) :: clm_fates
!
    !
    ! !LOCAL VARIABLES:
    integer  :: c,p,l,pi,j,k                                          ! indices
    integer  :: fc                                                    ! filter column index
    integer :: ft  ! FATES functional type index
    integer :: f  ! loop index for FATES plant competitors
    integer :: n_pcomp  ! number of FATES plant competitors
    integer :: ci, s  ! used for FATES BC (clump index, site index)
    logical :: local_use_fun                                          ! local version of use_fun
    real(r8) :: amnf_immob_vr                                         ! actual mineral N flux from immobilization (gN/m3/s)
    real(r8) :: n_deficit_vr                                          ! microbial N deficit, vertically resolved (gN/m3/s)
    real(r8) :: compet_plant_no3                                      ! (unitless) relative compettiveness of plants for NO3
    real(r8) :: compet_plant_nh4                                      ! (unitless) relative compettiveness of plants for NH4
    real(r8) :: compet_decomp_no3                                     ! (unitless) relative competitiveness of immobilizers for NO3
    real(r8) :: compet_decomp_nh4                                     ! (unitless) relative competitiveness of immobilizers for NH4
    real(r8) :: compet_denit                                          ! (unitless) relative competitiveness of denitrifiers for NO3
    real(r8) :: compet_nit                                            ! (unitless) relative competitiveness of nitrifiers for NH4
    real(r8) :: ndemand  ! (gN/m2/s) nitrogen demand per FATES plant competitor f (see local variable f above)
    real(r8) :: fpi_no3_vr(bounds%begc:bounds%endc,1:nlevdecomp)      ! fraction of potential immobilization supplied by no3(no units)
    real(r8) :: fpi_nh4_vr(bounds%begc:bounds%endc,1:nlevdecomp)      ! fraction of potential immobilization supplied by nh4 (no units)
    real(r8) :: sum_nh4_demand(bounds%begc:bounds%endc,1:nlevdecomp)
    real(r8) :: sum_nh4_demand_scaled(bounds%begc:bounds%endc,1:nlevdecomp)
    real(r8) :: sum_no3_demand(bounds%begc:bounds%endc,1:nlevdecomp)
    real(r8) :: sum_no3_demand_scaled(bounds%begc:bounds%endc,1:nlevdecomp)
    real(r8) :: sum_ndemand_vr(bounds%begc:bounds%endc, 1:nlevdecomp) !total column N demand (gN/m3/s) at a given level
    real(r8) :: plant_ndemand_vr(bounds%begc:bounds%endc, 1:nlevdecomp)  !plant column N demand (gN/m3/s) at a given level
    real(r8) :: nuptake_prof(bounds%begc:bounds%endc, 1:nlevdecomp)
    real(r8) :: sminn_tot(bounds%begc:bounds%endc)
    integer  :: nlimit(bounds%begc:bounds%endc,0:nlevdecomp)          !flag for N limitation
    integer  :: nlimit_no3(bounds%begc:bounds%endc,0:nlevdecomp)      !flag for NO3 limitation
    integer  :: nlimit_nh4(bounds%begc:bounds%endc,0:nlevdecomp)      !flag for NH4 limitation
    real(r8) :: residual_sminn_vr(bounds%begc:bounds%endc, 1:nlevdecomp)
    real(r8) :: residual_sminn(bounds%begc:bounds%endc)
    real(r8) :: residual_smin_nh4_vr(bounds%begc:bounds%endc, 1:nlevdecomp)
    real(r8) :: residual_smin_no3_vr(bounds%begc:bounds%endc, 1:nlevdecomp)
    real(r8) :: residual_smin_nh4(bounds%begc:bounds%endc)
    real(r8) :: residual_smin_no3(bounds%begc:bounds%endc)
    real(r8) :: residual_plant_ndemand(bounds%begc:bounds%endc)
    real(r8) :: sminn_to_plant_new(bounds%begc:bounds%endc)
    !-----------------------------------------------------------------------

    associate(                                                                                           &
         fpg                          => soilbiogeochem_state_inst%fpg_col                             , & ! Output: [real(r8) (:)   ]  fraction of potential gpp (no units)    
         fpi                          => soilbiogeochem_state_inst%fpi_col                             , & ! Output: [real(r8) (:)   ]  fraction of potential immobilization (no units)
         fpi_vr                       => soilbiogeochem_state_inst%fpi_vr_col                          , & ! Output: [real(r8) (:,:) ]  fraction of potential immobilization (no units)
         nfixation_prof               => soilbiogeochem_state_inst%nfixation_prof_col                  , & ! Output: [real(r8) (:,:) ]                                        
         plant_ndemand                => soilbiogeochem_state_inst%plant_ndemand_col                   , & ! Input:  [real(r8) (:)   ]  column-level plant N demand

         sminn_vr                     => soilbiogeochem_nitrogenstate_inst%sminn_vr_col                , & ! Input:  [real(r8) (:,:) ]  (gN/m3) soil mineral N                
         smin_nh4_vr                  => soilbiogeochem_nitrogenstate_inst%smin_nh4_vr_col             , & ! Input:  [real(r8) (:,:) ]  (gN/m3) soil mineral NH4              
         smin_no3_vr                  => soilbiogeochem_nitrogenstate_inst%smin_no3_vr_col             , & ! Input:  [real(r8) (:,:) ]  (gN/m3) soil mineral NO3              

         c_overflow_vr                => soilbiogeochem_carbonflux_inst%c_overflow_vr                  , & ! Output: [real(r8) (:,:,:)] (gC/m3/s) vertically-resolved C rejected by microbes that cannot process it
         cascade_receiver_pool        => decomp_cascade_con%cascade_receiver_pool                      , & ! Input:  [integer (:)     ]  which pool is C added to for a given decomposition step

         pot_f_nit_vr                 => soilbiogeochem_nitrogenflux_inst%pot_f_nit_vr_col             , & ! Input:  [real(r8) (:,:) ]  (gN/m3/s) potential soil nitrification flux
         pot_f_denit_vr               => soilbiogeochem_nitrogenflux_inst%pot_f_denit_vr_col           , & ! Input:  [real(r8) (:,:) ]  (gN/m3/s) potential soil denitrification flux
         f_nit_vr                     => soilbiogeochem_nitrogenflux_inst%f_nit_vr_col                 , & ! Output: [real(r8) (:,:) ]  (gN/m3/s) soil nitrification flux     
         f_denit_vr                   => soilbiogeochem_nitrogenflux_inst%f_denit_vr_col               , & ! Output: [real(r8) (:,:) ]  (gN/m3/s) soil denitrification flux   
         potential_immob              => soilbiogeochem_nitrogenflux_inst%potential_immob_col          , & ! Output: [real(r8) (:)   ]                                          
         actual_immob                 => soilbiogeochem_nitrogenflux_inst%actual_immob_col             , & ! Output: [real(r8) (:)   ]                                          
         sminn_to_plant               => soilbiogeochem_nitrogenflux_inst%sminn_to_plant_col           , & ! Output: [real(r8) (:)   ]                                          
         sminn_to_denit_excess_vr     => soilbiogeochem_nitrogenflux_inst%sminn_to_denit_excess_vr_col , & ! Output: [real(r8) (:,:) ]                                        
         actual_immob_no3_vr          => soilbiogeochem_nitrogenflux_inst%actual_immob_no3_vr_col      , & ! Output: [real(r8) (:,:) ]                                        
         actual_immob_nh4_vr          => soilbiogeochem_nitrogenflux_inst%actual_immob_nh4_vr_col      , & ! Output: [real(r8) (:,:) ]                                        
         smin_no3_to_plant_vr         => soilbiogeochem_nitrogenflux_inst%smin_no3_to_plant_vr_col     , & ! Output: [real(r8) (:,:) ]                                        
         smin_nh4_to_plant_vr         => soilbiogeochem_nitrogenflux_inst%smin_nh4_to_plant_vr_col     , & ! Output: [real(r8) (:,:) ]                                        
         n2_n2o_ratio_denit_vr        => soilbiogeochem_nitrogenflux_inst%n2_n2o_ratio_denit_vr_col    , & ! Output: [real(r8) (:,:) ]  ratio of N2 to N2O production by denitrification [gN/gN]
         f_n2o_denit_vr               => soilbiogeochem_nitrogenflux_inst%f_n2o_denit_vr_col           , & ! Output: [real(r8) (:,:) ]  flux of N2O from denitrification [gN/m3/s]
         f_n2o_nit_vr                 => soilbiogeochem_nitrogenflux_inst%f_n2o_nit_vr_col             , & ! Output: [real(r8) (:,:) ]  flux of N2O from nitrification [gN/m3/s]
         supplement_to_sminn_vr       => soilbiogeochem_nitrogenflux_inst%supplement_to_sminn_vr_col   , & ! Output: [real(r8) (:,:) ]                                        
         sminn_to_plant_vr            => soilbiogeochem_nitrogenflux_inst%sminn_to_plant_vr_col        , & ! Output: [real(r8) (:,:) ]                                        
         potential_immob_vr           => soilbiogeochem_nitrogenflux_inst%potential_immob_vr_col       , & ! Input:  [real(r8) (:,:) ]                                        
         actual_immob_vr              => soilbiogeochem_nitrogenflux_inst%actual_immob_vr_col          , & ! Output: [real(r8) (:,:) ]                                        
         sminn_to_plant_fun_vr        => soilbiogeochem_nitrogenflux_inst%sminn_to_plant_fun_vr_col    , & ! Iutput: [real(r8) (:)   ]  Total layer soil N uptake of FUN (gN/m2/s) 
         sminn_to_plant_fun_no3_vr    => soilbiogeochem_nitrogenflux_inst%sminn_to_plant_fun_no3_vr_col, & ! Iutput: [real(r8) (:)   ]  Total layer no3 uptake of FUN (gN/m2/s)
         sminn_to_plant_fun_nh4_vr    => soilbiogeochem_nitrogenflux_inst%sminn_to_plant_fun_nh4_vr_col  & ! Iutput: [real(r8) (:)   ]  Total layer nh4 uptake of FUN (gN/m2/s)
         )

      ! calcualte nitrogen uptake profile
      ! nuptake_prof(:,:) = nan
      ! call SoilBiogelchemNitrogenUptakeProfile(bounds, &
      !     nlevdecomp, num_bgc_soilc, filter_bgc_soilc, &
      !     sminn_vr, dzsoi_decomp, nfixation_prof, nuptake_prof)

      ! column loops to resolve plant/heterotroph competition for mineral N

      sminn_to_plant_new(bounds%begc:bounds%endc)  =  0._r8

      local_use_fun = use_fun

      if_nitrif: if (.not. use_nitrif_denitrif) then

         ! init sminn_tot
         do fc=1,num_bgc_soilc
            c = filter_bgc_soilc(fc)
            sminn_tot(c) = 0.
         end do

         do j = 1, nlevdecomp
            do fc=1,num_bgc_soilc
               c = filter_bgc_soilc(fc)
               call accum_sminn_tot(sminn_tot(c), smin_no3_vr(c,j), smin_nh4_vr(c,j), dzsoi_decomp(j))
            end do
         end do

         do j = 1, nlevdecomp
            do fc=1,num_bgc_soilc
               c = filter_bgc_soilc(fc)      
               call compute_nuptake_prof(nuptake_prof(c,j), sminn_tot(c), sminn_vr(c,j), nfixation_prof(c,j))
            end do
         end do

         ! Get plant N demand
         call get_plant_ndemand(bounds, filter_bgc_soilc, num_bgc_soilc, clm_fates, plant_ndemand, plant_ndemand_vr, nuptake_prof)
         bgc_soilc_loop1: do fc = 1, num_bgc_soilc
            c = filter_bgc_soilc(fc)
            do j = 1, nlevdecomp
               sum_ndemand_vr(c,j) = plant_ndemand_vr(c,j) + potential_immob_vr(c,j)
            end do
         end do bgc_soilc_loop1

         do j = 1, nlevdecomp
            do fc=1,num_bgc_soilc
               c = filter_bgc_soilc(fc)      
               l = col%landunit(c)
               if (sum_ndemand_vr(c,j)*dt < sminn_vr(c,j)) then

                  ! N availability is not limiting immobilization or plant
                  ! uptake, and both can proceed at their potential rates
                  nlimit(c,j) = 0
                  fpi_vr(c,j) = 1.0_r8
                  actual_immob_vr(c,j) = potential_immob_vr(c,j)
                  sminn_to_plant_vr(c,j) = plant_ndemand_vr(c,j)
               else if ( allocate_carbon_only()) then !.or. &
                  ! this code block controls the addition of N to sminn pool
                  ! to eliminate any N limitation, when Carbon_Only is set.  This lets the
                  ! model behave essentially as a carbon-only model, but with the
                  ! benefit of keeping track of the N additions needed to
                  ! eliminate N limitations, so there is still a diagnostic quantity
                  ! that describes the degree of N limitation at steady-state.

                  nlimit(c,j) = 1
                  fpi_vr(c,j) = 1.0_r8
                  actual_immob_vr(c,j) = potential_immob_vr(c,j)
                  sminn_to_plant_vr(c,j) = plant_ndemand_vr(c,j)
                  supplement_to_sminn_vr(c,j) = sum_ndemand_vr(c,j) - (sminn_vr(c,j)/dt)
               else
                  ! N availability can not satisfy the sum of immobilization and
                  ! plant growth demands, so these two demands compete for available
                  ! soil mineral N resource.

                  nlimit(c,j) = 1
                  if (sum_ndemand_vr(c,j) > 0.0_r8) then
                     actual_immob_vr(c,j) = (sminn_vr(c,j)/dt)*(potential_immob_vr(c,j) / sum_ndemand_vr(c,j))
                  else
                     actual_immob_vr(c,j) = 0.0_r8
                  end if

                  if (potential_immob_vr(c,j) > 0.0_r8) then
                     fpi_vr(c,j) = actual_immob_vr(c,j) / potential_immob_vr(c,j)
                  else
                     fpi_vr(c,j) = 0.0_r8
                  end if

                  sminn_to_plant_vr(c,j) = (sminn_vr(c,j)/dt) - actual_immob_vr(c,j)
               end if
            end do
         end do

         if ( local_use_fun ) then
            call t_startf( 'CNFUN' )
            call CNFUN(bounds,num_bgc_soilc,filter_bgc_soilc,num_bgc_vegp,filter_bgc_vegp,waterstatebulk_inst, &
                      waterfluxbulk_inst,temperature_inst,soilstate_inst,cnveg_state_inst,cnveg_carbonstate_inst,&
                      cnveg_carbonflux_inst,cnveg_nitrogenstate_inst,cnveg_nitrogenflux_inst                ,&
                      soilbiogeochem_nitrogenflux_inst,soilbiogeochem_carbonflux_inst,canopystate_inst,      &
                      soilbiogeochem_nitrogenstate_inst)
            call p2c(bounds, nlevdecomp, &
                      cnveg_nitrogenflux_inst%sminn_to_plant_fun_vr_patch(bounds%begp:bounds%endp,1:nlevdecomp),&
                      soilbiogeochem_nitrogenflux_inst%sminn_to_plant_fun_vr_col(bounds%begc:bounds%endc,1:nlevdecomp), &
                      'unity')
            call t_stopf( 'CNFUN' )
         end if

         ! sum up N fluxes to plant
         do j = 1, nlevdecomp
            do fc=1,num_bgc_soilc
               c = filter_bgc_soilc(fc)    
               sminn_to_plant(c) = sminn_to_plant(c) + sminn_to_plant_vr(c,j) * dzsoi_decomp(j)
               if ( local_use_fun ) then
                  if (sminn_to_plant_fun_vr(c,j).gt.sminn_to_plant_vr(c,j)) then
                      sminn_to_plant_fun_vr(c,j)  = sminn_to_plant_vr(c,j)
                  end if
               end if
            end do
         end do

         ! give plants a second pass to see if there is any mineral N left over with which to satisfy residual N demand.
         do fc=1,num_bgc_soilc
            c = filter_bgc_soilc(fc)    
            residual_sminn(c) = 0._r8
         end do

         ! sum up total N left over after initial plant and immobilization fluxes
         do fc=1,num_bgc_soilc
            c = filter_bgc_soilc(fc)    
            residual_plant_ndemand(c) = plant_ndemand(c) - sminn_to_plant(c)
         end do
         do j = 1, nlevdecomp
            do fc=1,num_bgc_soilc
               c = filter_bgc_soilc(fc)    
               if (residual_plant_ndemand(c)  >  0._r8 ) then
                  if (nlimit(c,j) .eq. 0) then
                     residual_sminn_vr(c,j) = max(sminn_vr(c,j) - (actual_immob_vr(c,j) + sminn_to_plant_vr(c,j) ) * dt, 0._r8)
                     residual_sminn(c) = residual_sminn(c) + residual_sminn_vr(c,j) * dzsoi_decomp(j)
                  else
                     residual_sminn_vr(c,j)  = 0._r8
                  endif
               endif
            end do
         end do

         ! distribute residual N to plants
         do j = 1, nlevdecomp
            do fc=1,num_bgc_soilc
               c = filter_bgc_soilc(fc)    
               if ( residual_plant_ndemand(c)  >  0._r8 .and. residual_sminn(c)  >  0._r8 .and. nlimit(c,j) .eq. 0) then
                  sminn_to_plant_vr(c,j) = sminn_to_plant_vr(c,j) + residual_sminn_vr(c,j) * &
                       min(( residual_plant_ndemand(c) *  dt ) / residual_sminn(c), 1._r8) / dt
               endif
            end do
         end do

         ! re-sum up N fluxes to plant
         do fc=1,num_bgc_soilc
            c = filter_bgc_soilc(fc)    
            sminn_to_plant(c) = 0._r8
         end do
         do j = 1, nlevdecomp
            do fc=1,num_bgc_soilc
               c = filter_bgc_soilc(fc)    
               sminn_to_plant(c) = sminn_to_plant(c) + sminn_to_plant_vr(c,j) * dzsoi_decomp(j)
               if ( .not. local_use_fun ) then
                  sum_ndemand_vr(c,j) = potential_immob_vr(c,j) + sminn_to_plant_vr(c,j)
               else
                  sminn_to_plant_new(c)  = sminn_to_plant_new(c)   + sminn_to_plant_fun_vr(c,j) * dzsoi_decomp(j)
                  sum_ndemand_vr(c,j)    = potential_immob_vr(c,j) + sminn_to_plant_fun_vr(c,j)
               end if
            end do
         end do

         ! under conditions of excess N, some proportion is assumed to
         ! be lost to denitrification, in addition to the constant
         ! proportion lost in the decomposition pathways
         do j = 1, nlevdecomp
            do fc=1,num_bgc_soilc
               c = filter_bgc_soilc(fc)    
               if ( .not. local_use_fun ) then
                  if ((sminn_to_plant_vr(c,j) + actual_immob_vr(c,j))*dt < sminn_vr(c,j)) then
                     sminn_to_denit_excess_vr(c,j) = max(bdnr*((sminn_vr(c,j)/dt) - sum_ndemand_vr(c,j)),0._r8)
                  else
                     sminn_to_denit_excess_vr(c,j) = 0._r8
                  endif
               else
                  if ((sminn_to_plant_fun_vr(c,j)  + actual_immob_vr(c,j))*dt < sminn_vr(c,j))  then
                     sminn_to_denit_excess_vr(c,j) = max(bdnr*((sminn_vr(c,j)/dt) - sum_ndemand_vr(c,j)),0._r8)
                  else
                     sminn_to_denit_excess_vr(c,j) = 0._r8
                  endif
               end if
            end do
         end do

         ! sum up N fluxes to immobilization
         do j = 1, nlevdecomp
            do fc=1,num_bgc_soilc
               c = filter_bgc_soilc(fc)    
               actual_immob(c) = actual_immob(c) + actual_immob_vr(c,j) * dzsoi_decomp(j)
               potential_immob(c) = potential_immob(c) + potential_immob_vr(c,j) * dzsoi_decomp(j)
            end do
         end do

         do fc=1,num_bgc_soilc
            c = filter_bgc_soilc(fc)    
            ! calculate the fraction of potential growth that can be
            ! acheived with the N available to plants      
            if (plant_ndemand(c) > 0.0_r8) then
               if ( .not. local_use_fun ) then
                  fpg(c) = sminn_to_plant(c) / plant_ndemand(c)
               else
                  fpg(c) = sminn_to_plant_new(c) / plant_ndemand(c)
               end if
            else
               fpg(c) = 1.0_r8
            end if

            ! calculate the fraction of immobilization realized (for diagnostic purposes)
            if (potential_immob(c) > 0.0_r8) then
               fpi(c) = actual_immob(c) / potential_immob(c)
            else
               fpi(c) = 1.0_r8
            end if
         end do

      else  !----------NITRIF_DENITRIF-------------!

         ! column loops to resolve plant/heterotroph/nitrifier/denitrifier competition for mineral N
         !read constants from external netcdf file
         compet_plant_no3  = params_inst%compet_plant_no3
         compet_plant_nh4  = params_inst%compet_plant_nh4
         compet_decomp_no3 = params_inst%compet_decomp_no3
         compet_decomp_nh4 = params_inst%compet_decomp_nh4
         compet_denit      = params_inst%compet_denit
         compet_nit        = params_inst%compet_nit

         ! init total mineral N pools
         do fc=1,num_bgc_soilc
            c = filter_bgc_soilc(fc)
            sminn_tot(c) = 0.
         end do

         ! sum up total mineral N pools
         do j = 1, nlevdecomp
            do fc=1,num_bgc_soilc
               c = filter_bgc_soilc(fc)
               call accum_sminn_tot(sminn_tot(c), smin_no3_vr(c,j), smin_nh4_vr(c,j), dzsoi_decomp(j))
            end do
         end do

         ! define N uptake profile for initial vertical distribution of plant N uptake, assuming plant seeks N from where it is most abundant
         do j = 1, nlevdecomp
            do fc=1,num_bgc_soilc
               c = filter_bgc_soilc(fc)
               call compute_nuptake_prof(nuptake_prof(c,j), sminn_tot(c), sminn_vr(c,j), nfixation_prof(c,j))
            end do
         end do

         ! Get plant N demand
         call get_plant_ndemand(bounds, filter_bgc_soilc, num_bgc_soilc, clm_fates, plant_ndemand, plant_ndemand_vr, nuptake_prof)

         ! main column/vertical loop
         do j = 1, nlevdecomp  
            do fc=1,num_bgc_soilc
               c = filter_bgc_soilc(fc)
               l = col%landunit(c)

               !  first compete for nh4
               call compete_nh4( &
                    sum_nh4_demand(c,j), sum_nh4_demand_scaled(c,j), nlimit_nh4(c,j), &
                    fpi_nh4_vr(c,j), actual_immob_nh4_vr(c,j), &
                    f_nit_vr(c,j), smin_nh4_to_plant_vr(c,j), &
                    plant_ndemand(c), nuptake_prof(c,j), &
                    potential_immob_vr(c,j), pot_f_nit_vr(c,j), smin_nh4_vr(c,j), &
                    compet_plant_nh4, compet_decomp_nh4, compet_nit, &
                    decomp_method, mimics_decomp, plant_ndemand_vr(c,j))
              
               !  then compete for no3
               call compete_no3( &
                    sum_no3_demand(c,j), sum_no3_demand_scaled(c,j), nlimit_no3(c,j), &
                    fpi_no3_vr(c,j), actual_immob_no3_vr(c,j), &
                    f_denit_vr(c,j), smin_no3_to_plant_vr(c,j), &
                    plant_ndemand(c), nuptake_prof(c,j), &
                    smin_nh4_to_plant_vr(c,j), actual_immob_nh4_vr(c,j), fpi_nh4_vr(c,j), &
                    potential_immob_vr(c,j), pot_f_denit_vr(c,j), smin_no3_vr(c,j), &
                    compet_plant_no3, compet_decomp_no3, compet_denit, &
                    decomp_method, mimics_decomp, plant_ndemand_vr(c,j))

               ! Compute N2O emissions
               call compute_n2o_emissions( &
                    f_n2o_nit_vr(c,j), f_n2o_denit_vr(c,j), &
                    f_nit_vr(c,j), f_denit_vr(c,j), n2_n2o_ratio_denit_vr(c,j), &
                    nitrif_n2o_loss_frac)

               ! this code block controls the addition of N to sminn pool
               ! to eliminate any N limitation, when Carbon_Only is set.  This lets the
               ! model behave essentially as a carbon-only model, but with the
               ! benefit of keeping track of the N additions needed to
               ! eliminate N limitations, so there is still a diagnostic quantity
               ! that describes the degree of N limitation at steady-state.

               if ( allocate_carbon_only()) then !.or. &
                  if ( fpi_no3_vr(c,j) + fpi_nh4_vr(c,j) < 1._r8 ) then
                     fpi_nh4_vr(c,j) = 1.0_r8 - fpi_no3_vr(c,j)
                     supplement_to_sminn_vr(c,j) = (potential_immob_vr(c,j) &
                                                  - actual_immob_no3_vr(c,j)) - actual_immob_nh4_vr(c,j)
                     ! update to new values that satisfy demand
                     actual_immob_nh4_vr(c,j) = potential_immob_vr(c,j) -  actual_immob_no3_vr(c,j)   
                  end if
                  if ( smin_no3_to_plant_vr(c,j) + smin_nh4_to_plant_vr(c,j) < plant_ndemand_vr(c,j) ) then
                     supplement_to_sminn_vr(c,j) = supplement_to_sminn_vr(c,j) + &
                          (plant_ndemand_vr(c,j) - smin_no3_to_plant_vr(c,j)) - smin_nh4_to_plant_vr(c,j)  ! use old values
                     smin_nh4_to_plant_vr(c,j) = plant_ndemand_vr(c,j) - smin_no3_to_plant_vr(c,j)
                  end if
                  sminn_to_plant_vr(c,j) = smin_no3_to_plant_vr(c,j) + smin_nh4_to_plant_vr(c,j)
               end if

               ! sum up no3 and nh4 fluxes
               fpi_vr(c,j) = fpi_no3_vr(c,j) + fpi_nh4_vr(c,j)
               sminn_to_plant_vr(c,j) = smin_no3_to_plant_vr(c,j) + smin_nh4_to_plant_vr(c,j)
               actual_immob_vr(c,j) = actual_immob_no3_vr(c,j) + actual_immob_nh4_vr(c,j)
            end do
         end do

         if ( local_use_fun ) then
            call t_startf( 'CNFUN' )
            call CNFUN(bounds,num_bgc_soilc,filter_bgc_soilc,num_bgc_vegp,filter_bgc_vegp,waterstatebulk_inst,&
                      waterfluxbulk_inst,temperature_inst,soilstate_inst,cnveg_state_inst,cnveg_carbonstate_inst,&
                      cnveg_carbonflux_inst,cnveg_nitrogenstate_inst,cnveg_nitrogenflux_inst                ,&
                      soilbiogeochem_nitrogenflux_inst,soilbiogeochem_carbonflux_inst,canopystate_inst,      &
                      soilbiogeochem_nitrogenstate_inst)
                      
            ! sminn_to_plant_fun is output of actual N uptake from FUN
            call p2c(bounds,nlevdecomp, &
                       cnveg_nitrogenflux_inst%sminn_to_plant_fun_no3_vr_patch(bounds%begp:bounds%endp,1:nlevdecomp),&
                       soilbiogeochem_nitrogenflux_inst%sminn_to_plant_fun_no3_vr_col(bounds%begc:bounds%endc,1:nlevdecomp),&
                       'unity')

            call p2c(bounds,nlevdecomp, &
                       cnveg_nitrogenflux_inst%sminn_to_plant_fun_nh4_vr_patch(bounds%begp:bounds%endp,1:nlevdecomp),&
                       soilbiogeochem_nitrogenflux_inst%sminn_to_plant_fun_nh4_vr_col(bounds%begc:bounds%endc,1:nlevdecomp),&
                       'unity')
            call t_stopf( 'CNFUN' )
         end if



         if(.not.local_use_fun)then
            do fc=1,num_bgc_soilc
               c = filter_bgc_soilc(fc)
               ! sum up N fluxes to plant after initial competition
               sminn_to_plant(c) = 0._r8
            end do
            do j = 1, nlevdecomp  
               do fc=1,num_bgc_soilc
                  c = filter_bgc_soilc(fc)
                  sminn_to_plant(c) = sminn_to_plant(c) + sminn_to_plant_vr(c,j) * dzsoi_decomp(j)
               end do
            end do
         else
            do fc=1,num_bgc_soilc
               c = filter_bgc_soilc(fc)
               ! sum up N fluxes to plant after initial competition
               sminn_to_plant(c) = 0._r8 !this isn't use in fun. 
               do j = 1, nlevdecomp
                  if ((sminn_to_plant_fun_no3_vr(c,j)-smin_no3_to_plant_vr(c,j)).gt.0.0000000000001_r8) then
                      write(iulog,*) 'problem with limitations on no3 uptake', &
                                 sminn_to_plant_fun_no3_vr(c,j),smin_no3_to_plant_vr(c,j)
                      call endrun("too much NO3 uptake predicted by FUN")
                  end if
!KO                  if ((sminn_to_plant_fun_nh4_vr(c,j)-smin_nh4_to_plant_vr(c,j)).gt.0.0000000000001_r8) then
!KO
                  if ((sminn_to_plant_fun_nh4_vr(c,j)-smin_nh4_to_plant_vr(c,j)).gt.0.0000001_r8) then
!KO
                      write(iulog,*) 'problem with limitations on nh4 uptake', &
                                  sminn_to_plant_fun_nh4_vr(c,j),smin_nh4_to_plant_vr(c,j)
                      call endrun("too much NH4 uptake predicted by FUN")
                  end if
               end do
            end do

         end if

         if (decomp_method == mimics_decomp) then
            do j = 1, nlevdecomp
               do fc=1,num_bgc_soilc
                  c = filter_bgc_soilc(fc)

                  do k = 1, ndecomp_cascade_transitions
                     if (cascade_receiver_pool(k) == i_cop_mic .or. &
                         cascade_receiver_pool(k) == i_oli_mic) then
                        sum_ndemand_vr(c,j) = sum_no3_demand_scaled(c,j) + &
                                              sum_nh4_demand_scaled(c,j)
                        if (pmnf_decomp_cascade(c,j,k) > 0.0_r8 .and. &
                            sum_ndemand_vr(c,j) > 0.0_r8) then
                           amnf_immob_vr = (sminn_vr(c,j) / dt) * &
                                           (pmnf_decomp_cascade(c,j,k) / &
                                            sum_ndemand_vr(c,j))
                           n_deficit_vr = pmnf_decomp_cascade(c,j,k) - &
                                          amnf_immob_vr
                           c_overflow_vr(c,j,k) = &
                              n_deficit_vr * p_decomp_cn_gain(c,j,cascade_receiver_pool(k))
                        else  ! not pmnf and sum_ndemand > 0
                           c_overflow_vr(c,j,k) = 0.0_r8
                        end if
                     else  ! not microbes receiving
                        c_overflow_vr(c,j,k) = 0.0_r8
                     end if
                  end do
               end do
            end do
         else  ! not mimics_decomp
            c_overflow_vr(:,:,:) = 0.0_r8
         end if

         if(.not.local_use_fun)then
            ! give plants a second pass to see if there is any mineral N left over with which to satisfy residual N demand.
            ! first take frm nh4 pool; then take from no3 pool
            do fc=1,num_bgc_soilc
               c = filter_bgc_soilc(fc)
               residual_plant_ndemand(c) = plant_ndemand(c) - sminn_to_plant(c)
               residual_smin_nh4(c) = 0._r8
            end do
            do j = 1, nlevdecomp  
               do fc=1,num_bgc_soilc
                  c = filter_bgc_soilc(fc)
                  if (residual_plant_ndemand(c)  >  0._r8 ) then
                     if (nlimit_nh4(c,j) .eq. 0) then
                        residual_smin_nh4_vr(c,j) = max(smin_nh4_vr(c,j) - (actual_immob_nh4_vr(c,j) + &
                                                    smin_nh4_to_plant_vr(c,j) + f_nit_vr(c,j) ) * dt, 0._r8)

                        residual_smin_nh4(c) = residual_smin_nh4(c) + residual_smin_nh4_vr(c,j) * dzsoi_decomp(j)
                     else
                        residual_smin_nh4_vr(c,j)  = 0._r8
                     endif
   
                     if ( residual_smin_nh4(c) > 0._r8 .and. nlimit_nh4(c,j) .eq. 0 ) then
                        smin_nh4_to_plant_vr(c,j) = smin_nh4_to_plant_vr(c,j) + residual_smin_nh4_vr(c,j) * &
                             min(( residual_plant_ndemand(c) *  dt ) / residual_smin_nh4(c), 1._r8) / dt
                     endif
                  end if
               end do
            end do

            ! re-sum up N fluxes to plant after second pass for nh4
            do fc=1,num_bgc_soilc
               c = filter_bgc_soilc(fc)
               sminn_to_plant(c) = 0._r8
            end do
            do j = 1, nlevdecomp
               do fc=1,num_bgc_soilc
                  c = filter_bgc_soilc(fc)
                  sminn_to_plant_vr(c,j) = smin_nh4_to_plant_vr(c,j) + smin_no3_to_plant_vr(c,j)
                  sminn_to_plant(c) = sminn_to_plant(c) + (sminn_to_plant_vr(c,j)) * dzsoi_decomp(j)
               end do
            end do

            !
            ! and now do second pass for no3
            do fc=1,num_bgc_soilc
               c = filter_bgc_soilc(fc)
               residual_plant_ndemand(c) = plant_ndemand(c) - sminn_to_plant(c)
               residual_smin_no3(c) = 0._r8
            end do

            do j = 1, nlevdecomp
               do fc=1,num_bgc_soilc
                  c = filter_bgc_soilc(fc)
                  if (residual_plant_ndemand(c) > 0._r8 ) then
                     if (nlimit_no3(c,j) .eq. 0) then
                       residual_smin_no3_vr(c,j) = max(smin_no3_vr(c,j) - (actual_immob_no3_vr(c,j) + &
                                                   smin_no3_to_plant_vr(c,j) + f_denit_vr(c,j) ) * dt, 0._r8)
                        residual_smin_no3(c) = residual_smin_no3(c) + residual_smin_no3_vr(c,j) * dzsoi_decomp(j)
                     else
                        residual_smin_no3_vr(c,j)  = 0._r8
                     endif
   
                     if ( residual_smin_no3(c) > 0._r8 .and. nlimit_no3(c,j) .eq. 0) then
                        smin_no3_to_plant_vr(c,j) = smin_no3_to_plant_vr(c,j) + residual_smin_no3_vr(c,j) * &
                             min(( residual_plant_ndemand(c) *  dt ) / residual_smin_no3(c), 1._r8) / dt
                     endif
                  endif
               end do
            end do

            ! re-sum up N fluxes to plant after second passes of both no3 and nh4
            do fc=1,num_bgc_soilc
               c = filter_bgc_soilc(fc)
               sminn_to_plant(c) = 0._r8
            end do
            do j = 1, nlevdecomp
               do fc=1,num_bgc_soilc
                  c = filter_bgc_soilc(fc)
                  sminn_to_plant_vr(c,j) = smin_nh4_to_plant_vr(c,j) + smin_no3_to_plant_vr(c,j)
                  sminn_to_plant(c) = sminn_to_plant(c) + (sminn_to_plant_vr(c,j)) * dzsoi_decomp(j)
               end do
            end do
   
         else !use_fun
         !calculate maximum N available to plants. 
            do fc=1,num_bgc_soilc
               c = filter_bgc_soilc(fc)
               sminn_to_plant(c) = 0._r8
            end do
            do j = 1, nlevdecomp
               do fc=1,num_bgc_soilc
                  c = filter_bgc_soilc(fc)
                  sminn_to_plant_vr(c,j) = smin_nh4_to_plant_vr(c,j) + smin_no3_to_plant_vr(c,j)
                  sminn_to_plant(c) = sminn_to_plant(c) + (sminn_to_plant_vr(c,j)) * dzsoi_decomp(j)
               end do
            end do
   

             ! add up fun fluxes from SMINN to plant. 
             do j = 1, nlevdecomp
                do fc=1,num_bgc_soilc
                   c = filter_bgc_soilc(fc)
                   sminn_to_plant_new(c)  = sminn_to_plant_new(c) + &
                             (sminn_to_plant_fun_no3_vr(c,j) + sminn_to_plant_fun_nh4_vr(c,j)) * dzsoi_decomp(j)
                      
                end do
             end do
                             
                              
         end if !use_f
         ! sum up N fluxes to immobilization
         do fc=1,num_bgc_soilc
            c = filter_bgc_soilc(fc)
            actual_immob(c) = 0._r8
            potential_immob(c) = 0._r8
         end do
         do j = 1, nlevdecomp  
            do fc=1,num_bgc_soilc
               c = filter_bgc_soilc(fc)
               actual_immob(c) = actual_immob(c) + actual_immob_vr(c,j) * dzsoi_decomp(j)
               potential_immob(c) = potential_immob(c) + potential_immob_vr(c,j) * dzsoi_decomp(j)
            end do
         end do
        
        
     
       
         do fc=1,num_bgc_soilc
            c = filter_bgc_soilc(fc)   
            ! calculate the fraction of potential growth that can be
            ! acheived with the N available to plants
            ! calculate the fraction of immobilization realized (for diagnostic purposes)
            if(.not.local_use_fun)then !FUN has no concept of FPG.
            
               if (plant_ndemand(c) > 0.0_r8) then
                  fpg(c) = sminn_to_plant(c) / plant_ndemand(c)
               else
                  fpg(c) = 1._r8
               end if
            end if

            if (potential_immob(c) > 0.0_r8) then
               fpi(c) = actual_immob(c) / potential_immob(c)
            else
               fpi(c) = 1._r8
            end if
         end do ! end of column loops

         ! Set the FATES N uptake fluxes

         if (col%is_fates(c)) then
            do fc=1, num_bgc_soilc
               c = filter_bgc_soilc(fc)
               ci = bounds%clump_index
               s = clm_fates%f2hmap(ci)%hsites(c)
               n_pcomp = clm_fates%fates(ci)%bc_out(s)%num_plant_comps

               ! if fates_parteh_mode /= clmfates_carbon_nitrogen then
               ! plant_ndemand = 0 and this if-statement gets skipped
               if ( plant_ndemand(c) > tiny(plant_ndemand(c)) ) then
                  do f = 1, n_pcomp
                     ft = clm_fates%fates(ci)%bc_out(s)%ft_index(f)

                     ! [gN/m2/s]
                     ndemand = 0._r8

                     do j = 1, nlevdecomp
                        ndemand = ndemand + clm_fates%fates(ci)%bc_out(s)%veg_rootc(f,j) * &
                            (clm_fates%fates(ci)%bc_pconst%vmax_nh4(ft) + &
                             clm_fates%fates(ci)%bc_pconst%vmax_no3(ft)) * dzsoi_decomp(j)
                     end do

                     do j = 1, nlevdecomp
                        clm_fates%fates(ci)%bc_in(s)%plant_nh4_uptake_flux(f,1) = &
                            clm_fates%fates(ci)%bc_in(s)%plant_nh4_uptake_flux(f,1) + &
                            smin_nh4_to_plant_vr(c,j) * dt * dzsoi_decomp(j) * &
                            (ndemand / plant_ndemand(c))

                        clm_fates%fates(ci)%bc_in(s)%plant_no3_uptake_flux(f,1) = &
                            clm_fates%fates(ci)%bc_in(s)%plant_no3_uptake_flux(f,1) + &
                            smin_no3_to_plant_vr(c,j) * dt * dzsoi_decomp(j) * &
                            (ndemand / plant_ndemand(c))
                     end do
                  end do
               end if
            end do
         end if

      end if if_nitrif  !end of if_not_use_nitrif_denitrif

    end associate

  end subroutine SoilBiogeochemCompetition

  !-----------------------------------------------------------------------
  pure subroutine accum_sminn_tot(sminn_tot, smin_no3_vr, smin_nh4_vr, dzsoi_decomp_j)
    ! Add soil mineral N from a single column-layer into sminn_tot
    real(r8), intent(inout) :: sminn_tot     ! total soil mineral N accumulated so far
    real(r8), intent(in)    :: smin_no3_vr   ! (gN/m3) soil mineral NO3 in this column-layer
    real(r8), intent(in)    :: smin_nh4_vr   ! (gN/m3) soil mineral NH4 in this column-layer
    real(r8), intent(in)    :: dzsoi_decomp_j  ! thickness of this layer

    sminn_tot = sminn_tot + (smin_no3_vr + smin_nh4_vr) * dzsoi_decomp_j
  end subroutine accum_sminn_tot

  !-----------------------------------------------------------------------
  pure subroutine compute_nuptake_prof(nuptake_prof, sminn_tot, sminn_vr, nfixation_prof)
    ! define N uptake profile for initial vertical distribution of plant N uptake, assuming plant
    ! seeks N from where it is most abundant
    real(r8), intent(out) :: nuptake_prof    ! (unitless) Initial fraction of plant N uptake to come from this layer
    real(r8), intent(in)  :: sminn_tot       ! (gN/m3) soil mineral N in this column
    real(r8), intent(in)  :: sminn_vr        ! (gN/m3) soil mineral N in this layer of the column
    ! TODO: Improve nfixation_prof comment
    real(r8), intent(in)  :: nfixation_prof  ! N fixation profile (?) in this layer of the column
    if (sminn_tot > 0.) then
       nuptake_prof = sminn_vr / sminn_tot
    else
       nuptake_prof = nfixation_prof
    endif
  end subroutine compute_nuptake_prof

  !-----------------------------------------------------------------------
  subroutine get_plant_ndemand(bounds, filter_bgc_soilc, num_bgc_soilc, clm_fates, plant_ndemand, plant_ndemand_vr, nuptake_prof)
    !
    ! !USES:
    use clm_varctl       , only: fates_parteh_mode
    use clm_varpar       , only: clmfates_carbon_nitrogen
    use clm_varpar       , only: nlevdecomp
    !
    ! !ARGUMENTS:
    type(bounds_type)                       , intent(in)    :: bounds
    integer                                 , intent(in)    :: filter_bgc_soilc(:)  ! filter for soil columns
    integer, intent(in) :: num_bgc_soilc  ! number of soil columns in filter
    type(hlm_fates_interface_type), intent(inout) :: clm_fates
    real(r8), intent(inout) :: plant_ndemand(:)       ! column-level plant N demand (gN/m3/s)
    real(r8), intent(inout) :: plant_ndemand_vr(:,:)  ! column-level plant N demand (gN/m3/s) at a given level
    real(r8), intent(inout) :: nuptake_prof(:,:)
    !
    ! !LOCAL VARIABLES:
    integer :: c, j     ! indices
    integer :: fc       ! filter column index
    integer :: ft       ! FATES functional type index
    integer :: f        ! loop index for FATES plant competitors
    integer :: n_pcomp  ! number of FATES plant competitors
    integer :: ci, s    ! used for FATES BC (clump index, site index)

    bgc_soilc_loop: do fc = 1, num_bgc_soilc
       c = filter_bgc_soilc(fc)

       fates: if (col%is_fates(c)) then
          ci = bounds%clump_index
          s = clm_fates%f2hmap(ci)%hsites(c)
          n_pcomp = clm_fates%fates(ci)%bc_out(s)%num_plant_comps

          ! Overwrite the column level demands, since fates plants are all sharing
          ! the same space, in units per the same square meter, we just add demand
          ! to scale up to column
          plant_ndemand(c) = 0._r8

          ! We fill the vertically resolved array to simplify some jointly used code
          do j = 1, nlevdecomp
             plant_ndemand_vr(c,j) = 0._r8

             if (trim(fates_parteh_mode) == trim(clmfates_carbon_nitrogen))then
                do f = 1, n_pcomp
                   ft = clm_fates%fates(ci)%bc_out(s)%ft_index(f)

                   ! [gN/m3/s] = [gC/m3] * [gN/gC/s]
                   plant_ndemand_vr(c,j) = plant_ndemand_vr(c,j) + &
                       clm_fates%fates(ci)%bc_out(s)%veg_rootc(f,j) * &
                       (clm_fates%fates(ci)%bc_pconst%vmax_nh4(ft) + &
                        clm_fates%fates(ci)%bc_pconst%vmax_no3(ft))
                end do
             end if

             ! [gN/m2/s]
             plant_ndemand(c) = plant_ndemand(c) + plant_ndemand_vr(c,j) * dzsoi_decomp(j)

          end do

       else  ! not is_fates

          do j = 1, nlevdecomp
             plant_ndemand_vr(c,j) = plant_ndemand(c) * nuptake_prof(c,j)
          end do

       end if fates

    end do bgc_soilc_loop
  end subroutine get_plant_ndemand

  !-----------------------------------------------------------------------
  pure subroutine compete_nh4( &
       sum_nh4_demand, sum_nh4_demand_scaled, nlimit_nh4, &
       fpi_nh4_vr, actual_immob_nh4_vr, &
       f_nit_vr, smin_nh4_to_plant_vr, &
       plant_ndemand, nuptake_prof, &
       potential_immob_vr, pot_f_nit_vr, smin_nh4_vr, &
       compet_plant_nh4, compet_decomp_nh4, compet_nit, &
       decomp_method, mimics_decomp, plant_ndemand_vr)
    ! Competition in a given column-layer for NH4
    !
    ! !USES:
    use CNSharedParamsMod, only: use_fun
    !
    ! !ARGUMENTS:
    real(r8), intent(out) :: sum_nh4_demand
    real(r8), intent(out) :: sum_nh4_demand_scaled
    integer , intent(out) :: nlimit_nh4  ! flag for NH4 limitation
    real(r8), intent(out) :: fpi_nh4_vr  ! fraction of potential immobilization supplied by nh4 (no units)
    real(r8), intent(out) :: actual_immob_nh4_vr  ! col vertically-resolved actual immobilization of NH4 (gN/m3/s)
    real(r8), intent(out) :: f_nit_vr  ! soil nitrification flux (gN/m3/s)
    real(r8), intent(out) :: smin_nh4_to_plant_vr  ! col vertically-resolved plant uptake of soil NH4 (gN/m3/s)
    real(r8), intent(in)  :: plant_ndemand  ! column-level plant N demand (units?)
    real(r8), intent(in)  :: nuptake_prof
    real(r8), intent(in)  :: potential_immob_vr  ! col vertically-resolved potential N immobilization (gN/m3/s) at each level
    real(r8), intent(in)  :: pot_f_nit_vr  ! potential soil nitrification flux (gN/m3/s)
    real(r8), intent(in)  :: smin_nh4_vr  ! soil mineral NH4 (gN/m3)
    real(r8), intent(in)  :: compet_plant_nh4   ! relative competitiveness of plants for NH4 (unitless)
    real(r8), intent(in)  :: compet_decomp_nh4  ! relative competitiveness of immobilizers for NH4 (unitless)
    real(r8), intent(in)  :: compet_nit         ! relative competitiveness of nitrifiers for NH4 (unitless)
    integer , intent(in)  :: decomp_method  ! Type of decomposition to use
    integer , intent(in)  :: mimics_decomp  ! MIMICS decomposition method type
    real(r8), intent(in) :: plant_ndemand_vr  ! plant column N demand (gN/m3/s) at a given level

    sum_nh4_demand = plant_ndemand_vr + potential_immob_vr + pot_f_nit_vr
    sum_nh4_demand_scaled = plant_ndemand_vr * compet_plant_nh4 + &
         potential_immob_vr*compet_decomp_nh4 + pot_f_nit_vr*compet_nit

    if (sum_nh4_demand*dt < smin_nh4_vr) then

       ! NH4 availability is not limiting immobilization or plant
       ! uptake, and all can proceed at their potential rates
       nlimit_nh4 = 0
       fpi_nh4_vr = 1.0_r8
       actual_immob_nh4_vr = potential_immob_vr
       !RF added new term.

       f_nit_vr = pot_f_nit_vr

       if ( .not. use_fun ) then
          smin_nh4_to_plant_vr = plant_ndemand_vr
       else
          smin_nh4_to_plant_vr = smin_nh4_vr/dt - actual_immob_nh4_vr - f_nit_vr
       end if

    else

       ! NH4 availability can not satisfy the sum of immobilization, nitrification, and
       ! plant growth demands, so these three demands compete for available
       ! soil mineral NH4 resource.
       nlimit_nh4 = 1
       if (sum_nh4_demand > 0.0_r8) then
       ! RF microbes compete based on the hypothesised plant demand.
          actual_immob_nh4_vr = min((smin_nh4_vr/dt)*(potential_immob_vr* &
               compet_decomp_nh4 / sum_nh4_demand_scaled), potential_immob_vr)

          f_nit_vr =  min((smin_nh4_vr/dt)*(pot_f_nit_vr*compet_nit / &
               sum_nh4_demand_scaled), pot_f_nit_vr)

          if ( .not. use_fun ) then
              smin_nh4_to_plant_vr = min((smin_nh4_vr/dt) * (plant_ndemand_vr * &
               compet_plant_nh4 / sum_nh4_demand_scaled), plant_ndemand_vr)

          else
             ! RF added new term. send rest of N to plant - which decides whether it should pay or not?
             smin_nh4_to_plant_vr = smin_nh4_vr/dt - actual_immob_nh4_vr - f_nit_vr
          end if

       else
          actual_immob_nh4_vr = 0.0_r8
          smin_nh4_to_plant_vr = 0.0_r8
          f_nit_vr = 0.0_r8
       end if

       if (potential_immob_vr > 0.0_r8) then
          fpi_nh4_vr = actual_immob_nh4_vr / potential_immob_vr
       else
          fpi_nh4_vr = 0.0_r8
       end if

    end if

    if (decomp_method == mimics_decomp) then
       ! turn off fpi for MIMICS and only lets plants
       ! take up available mineral nitrogen.
       ! TODO slevis: -ve or tiny sminn_vr could cause problems
       fpi_nh4_vr = 1.0_r8
       actual_immob_nh4_vr = potential_immob_vr
    end if
  end subroutine compete_nh4

  !-----------------------------------------------------------------------
  pure subroutine compete_no3( &
       sum_no3_demand, sum_no3_demand_scaled, nlimit_no3, &
       fpi_no3_vr, actual_immob_no3_vr, &
       f_denit_vr, smin_no3_to_plant_vr, &
       plant_ndemand, nuptake_prof, &
       smin_nh4_to_plant_vr, actual_immob_nh4_vr, fpi_nh4_vr, &
       potential_immob_vr, pot_f_denit_vr, smin_no3_vr, &
       compet_plant_no3, compet_decomp_no3, compet_denit, &
       decomp_method, mimics_decomp, plant_ndemand_vr)
    ! Competition in a given column-layer for NO3
    !
    ! !USES:
    use CNSharedParamsMod, only: use_fun
    !
    ! !ARGUMENTS:
    real(r8), intent(out) :: sum_no3_demand
    real(r8), intent(out) :: sum_no3_demand_scaled
    integer , intent(out) :: nlimit_no3  ! flag for NO3 limitation
    real(r8), intent(out) :: fpi_no3_vr  ! fraction of potential immobilization supplied by no3 (no units)
    real(r8), intent(out) :: actual_immob_no3_vr  ! col vertically-resolved actual immobilization of NO3 (gN/m3/s)
    real(r8), intent(out) :: f_denit_vr  ! soil denitrification flux (gN/m3/s)
    real(r8), intent(out) :: smin_no3_to_plant_vr  ! col vertically-resolved plant uptake of soil NO3 (gN/m3/s)
    real(r8), intent(in)  :: plant_ndemand  ! column-level plant N demand (units?)
    real(r8), intent(in)  :: nuptake_prof
    real(r8), intent(in)  :: smin_nh4_to_plant_vr  ! col vertically-resolved plant uptake of soil NH4 (gN/m3/s)
    real(r8), intent(in)  :: actual_immob_nh4_vr  ! col vertically-resolved actual immobilization of NH4 (gN/m3/s)
    real(r8), intent(in)  :: fpi_nh4_vr    ! fraction of potential immobilization supplied by nh4 (no units)
    real(r8), intent(in)  :: potential_immob_vr  ! col vertically-resolved potential N immobilization (gN/m3/s) at each level
    real(r8), intent(in)  :: pot_f_denit_vr  ! potential soil denitrification flux (gN/m3/s)
    real(r8), intent(in)  :: smin_no3_vr  ! soil mineral NO3 (gN/m3)
    real(r8), intent(in)  :: compet_plant_no3   ! relative competitiveness of plants for NO3 (unitless)
    real(r8), intent(in)  :: compet_decomp_no3  ! relative competitiveness of immobilizers for NO3 (unitless)
    real(r8), intent(in)  :: compet_denit       ! relative competitiveness of denitrifiers for NO3 (unitless)
    integer , intent(in)  :: decomp_method  ! Type of decomposition to use
    integer , intent(in)  :: mimics_decomp  ! MIMICS decomposition method type
    real(r8), intent(in) :: plant_ndemand_vr  ! plant column N demand (gN/m3/s) at a given level

    if (.not. use_fun) then
        sum_no3_demand = (plant_ndemand_vr - smin_nh4_to_plant_vr) + &
       (potential_immob_vr-actual_immob_nh4_vr) + pot_f_denit_vr
        sum_no3_demand_scaled = (plant_ndemand_vr &
                                      -smin_nh4_to_plant_vr)*compet_plant_no3 + &
       (potential_immob_vr-actual_immob_nh4_vr)*compet_decomp_no3 + pot_f_denit_vr*compet_denit
    else
       sum_no3_demand = plant_ndemand_vr + &
       (potential_immob_vr-actual_immob_nh4_vr) + pot_f_denit_vr
        sum_no3_demand_scaled = (plant_ndemand_vr) * compet_plant_no3 + &
       (potential_immob_vr-actual_immob_nh4_vr)*compet_decomp_no3 + pot_f_denit_vr*compet_denit
    endif

    if (sum_no3_demand*dt < smin_no3_vr) then

       ! NO3 availability is not limiting immobilization or plant
       ! uptake, and all can proceed at their potential rates
       nlimit_no3 = 0
       fpi_no3_vr = 1.0_r8 -  fpi_nh4_vr
       actual_immob_no3_vr = (potential_immob_vr-actual_immob_nh4_vr)

       f_denit_vr = pot_f_denit_vr

       if(.not. use_fun) then
          smin_no3_to_plant_vr = (plant_ndemand_vr - smin_nh4_to_plant_vr)
       else
          ! This restricts the N uptake of a single layer to the value determined from the total demands and the
          ! hypothetical uptake profile above. Which is a strange thing to do, since that is independent of FUN
          ! do we need this at all?
          smin_no3_to_plant_vr = plant_ndemand_vr
          ! RF added new term. send rest of N to plant - which decides whether it should pay or not?
          if (use_fun) then
             smin_no3_to_plant_vr = smin_no3_vr/dt - actual_immob_no3_vr - f_denit_vr
          end if
       endif

    else

       ! NO3 availability can not satisfy the sum of immobilization, denitrification, and
       ! plant growth demands, so these three demands compete for available
       ! soil mineral NO3 resource.
       nlimit_no3 = 1

       if (sum_no3_demand > 0.0_r8) then
          if (.not. use_fun) then
             actual_immob_no3_vr = min((smin_no3_vr/dt)*((potential_immob_vr- &
             actual_immob_nh4_vr)*compet_decomp_no3 / sum_no3_demand_scaled), &
                       potential_immob_vr-actual_immob_nh4_vr)

             smin_no3_to_plant_vr = min((smin_no3_vr/dt) * ((plant_ndemand_vr - &
                       smin_nh4_to_plant_vr) * compet_plant_no3 / sum_no3_demand_scaled), &
                       plant_ndemand_vr - smin_nh4_to_plant_vr)

             f_denit_vr = min((smin_no3_vr/dt)*(pot_f_denit_vr*compet_denit / &
                       sum_no3_demand_scaled), pot_f_denit_vr)
          else
             actual_immob_no3_vr = min((smin_no3_vr/dt)*((potential_immob_vr- &
             actual_immob_nh4_vr)*compet_decomp_no3 / sum_no3_demand_scaled), &
                       potential_immob_vr-actual_immob_nh4_vr)

             f_denit_vr = min((smin_no3_vr/dt)*(pot_f_denit_vr*compet_denit / &
             sum_no3_demand_scaled), pot_f_denit_vr)

             smin_no3_to_plant_vr = (smin_no3_vr/dt) * ((plant_ndemand_vr - &
                       smin_nh4_to_plant_vr) * compet_plant_no3 / sum_no3_demand_scaled)

             ! RF added new term. send rest of N to plant - which decides whether it should pay or not?
             smin_no3_to_plant_vr = (smin_no3_vr / dt) - actual_immob_no3_vr - f_denit_vr

          end if ! use_fun

       else ! no no3 demand. no uptake fluxes.
          actual_immob_no3_vr = 0.0_r8
          smin_no3_to_plant_vr = 0.0_r8
          f_denit_vr = 0.0_r8

       end if !any no3 demand?

       if (potential_immob_vr > 0.0_r8) then
          fpi_no3_vr = actual_immob_no3_vr / potential_immob_vr
       else
          fpi_no3_vr = 0.0_r8
       end if

    end if

    if (decomp_method == mimics_decomp) then
       ! turn off fpi for MIMICS and only lets plants
       ! take up available mineral nitrogen.
       ! TODO slevis: -ve or tiny sminn_vr could cause problems
       fpi_no3_vr = 1.0_r8 - fpi_nh4_vr  ! => 0
       actual_immob_no3_vr = potential_immob_vr - &
                                  actual_immob_nh4_vr  ! => 0
    end if

  end subroutine compete_no3

  !-----------------------------------------------------------------------
  pure subroutine compute_n2o_emissions( &
       f_n2o_nit_vr, f_n2o_denit_vr, &
       f_nit_vr, f_denit_vr, n2_n2o_ratio_denit_vr, &
       nitrif_n2o_loss_frac)
    ! Compute N2O emissions
    !
    ! !ARGUMENTS:
    real(r8), intent(out) :: f_n2o_nit_vr    ! flux of N2O from nitrification [gN/m3/s]
    real(r8), intent(out) :: f_n2o_denit_vr  ! flux of N2O from denitrification [gN/m3/s]
    real(r8), intent(in)  :: f_nit_vr    ! soil nitrification flux [gN/m3/s]
    real(r8), intent(in)  :: f_denit_vr  ! soil denitrification flux [gN/m3/s]
    real(r8), intent(in)  :: n2_n2o_ratio_denit_vr  ! ratio of N2 to N2O production by denitrification [gN/gN]
    real(r8), intent(in)  :: nitrif_n2o_loss_frac   ! fraction of N lost as N2O in nitrification (from clm_varcon)

    ! N2O from nitrification is a constant fraction
    f_n2o_nit_vr = f_nit_vr * nitrif_n2o_loss_frac

    ! N2O from denitrification is calculated in subroutine SoilBiogeochemNitrifDenitrif()
    f_n2o_denit_vr = f_denit_vr / (1._r8 + n2_n2o_ratio_denit_vr)
  end subroutine compute_n2o_emissions

end module SoilBiogeochemCompetitionMod
