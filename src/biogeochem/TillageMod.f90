module TillageMod
  !-----------------------------------------------------------------------
  ! !DESCRIPTION:
  ! Module for soil tillage.
  !
  ! As described in ChangeLog:
  !     history field name change as follows...
  !     LITR1 becomes MET_LIT (metabolic)
  !     LITR2 becomes CEL_LIT (cellulosic)
  !     LITR3 becomes LIG_LIT (lignin)
  !     SOIL1 becomes ACT_SOM (active)
  !     SOIL2 becomes SLO_SOM (slow)
  !     SOIL3 becomes PAS_SOM (passive)
  !
  ! !USES:
  use shr_kind_mod   , only : r8 => shr_kind_r8
  use shr_log_mod    , only : errMsg => shr_log_errMsg
  use abortutils     , only : endrun
  use clm_varctl     , only : iulog
  use clm_varpar     , only : ndecomp_pools
  use ColumnType     , only : col
  use PatchType      , only : patch
  !
  implicit none
  private
  ! !PUBLIC MEMBER PROCEDURES
  public :: tillage_init
  public :: get_do_tillage
  public :: get_apply_tillage_multipliers
  !
  ! !PRIVATE DATA MEMBERS
  logical  :: do_tillage_low   ! Do low-intensity tillage?
  logical  :: do_tillage_high  ! Do high-intensity tillage?
  logical  :: use_original_tillage ! Use get_tillage_multipliers_orig?
  real(r8), pointer :: tillage_mults(:) ! (ndecomp_pools)
  real(r8), pointer :: tillage_mults_allphases(:,:) ! (ndecomp_pools, nphases)
  integer, parameter :: nphases = 3 ! How many different tillage phases are there? (Not including all-1 phases.)


!==============================================================================
contains
!==============================================================================

  subroutine tillage_init()
    !
    ! Read namelist parameters and allocate variables related to tillage
    !
    ! !USES:
    use spmdMod        , only : masterproc
    use controlMod     , only : NLFilename
    use clm_nlUtilsMod , only : find_nlgroup_name
    use shr_mpi_mod    , only : shr_mpi_bcast
    !
    ! !ARGUMENTS
    !
    ! !LOCAL VARIABLES
    integer                :: nu_nml       ! unit for namelist file
    integer                :: nml_error    ! namelist i/o error flag
    integer                :: mpicom       ! MPI communicator
    character(*), parameter :: subname = "('tillage_init')"

    namelist /tillage_inparm/    &
        do_tillage_low,       &
        do_tillage_high,      &
        use_original_tillage

    ! Default values
    do_tillage_low = .false.
    do_tillage_high = .false.
    use_original_tillage = .false.

    ! Read tillage namelist
    if (masterproc) then
        open(newunit=nu_nml, file=trim(NLFilename), status='old', iostat=nml_error )
        call find_nlgroup_name(nu_nml, 'tillage_inparm', status=nml_error)
        if (nml_error == 0) then
           read(nu_nml, nml=tillage_inparm, iostat=nml_error)
           if (nml_error /= 0) then
              call endrun(subname // ':: ERROR reading tillage namelist')
           end if
        else
           call endrun(subname // ':: ERROR finding tillage namelist')
        end if
        close(nu_nml)
     endif
     call shr_mpi_bcast(do_tillage_low, mpicom)
     call shr_mpi_bcast(do_tillage_high , mpicom)
     call shr_mpi_bcast(use_original_tillage , mpicom)

     if (masterproc) then
        write(iulog,*) ' '
        write(iulog,*) 'tillage settings:'
        write(iulog,*) '  do_tillage_low  = ',do_tillage_low
        write(iulog,*) '  do_tillage_high   = ',do_tillage_high
        write(iulog,*) '  use_original_tillage   = ',use_original_tillage
     endif

     if (do_tillage_low .and. do_tillage_high) then
        call endrun(subname // ':: ERROR do_tillage_low and do_tillage_high are mutually exclusive')
     endif

     if (do_tillage_high) then
        call endrun(subname // ':: ERROR high-intensity tillage not yet set up')
     endif

     ! Allocate tillage multipliers
     if (get_do_tillage()) then
        allocate(tillage_mults(ndecomp_pools)); tillage_mults(:) = 1.0_r8
        allocate(tillage_mults_allphases(ndecomp_pools, nphases)); tillage_mults_allphases(:,:) = 1.0_r8
     end if

  end subroutine tillage_init


  function get_do_tillage()
    logical :: get_do_tillage
    get_do_tillage = do_tillage_low .or. do_tillage_high
  end function get_do_tillage


  subroutine get_tillage_multipliers(idop, p, i_act_som, i_slo_som, i_pas_som, i_cel_lit, i_lig_lit)
    ! !DESCRIPTION:
    !
    !  Get the cultivation effective multiplier if prognostic crops are on and
    !  cultivation is turned on. Created by Sam Levis. Modified by Michael Graham
    !  to use days past planting. Modified by Sam Rabin to include "new" version
    !  that *actually* uses days past planting.
    !
    ! !USES:
    use clm_time_manager, only : get_curr_calday, get_curr_days_per_year
    use pftconMod       , only : ntmp_corn, nirrig_tmp_corn, ntmp_soybean, nirrig_tmp_soybean
    ! !ARGUMENTS:
    integer          , intent(in) :: idop(:) ! patch day of planting
    integer          , intent(in) :: p       ! index of patch this is being called for
    integer          , intent(in) :: i_act_som, i_slo_som, i_pas_som  ! indices for soil organic matter pools
    integer          , intent(in) :: i_cel_lit, i_lig_lit  ! indices for litter pools
    !
    ! !LOCAL VARIABLES:
    !
    integer :: day                  ! julian day
    integer :: idpp                 ! days past planting
    integer :: phase                ! which tillage phase are we in?
    real(r8) dayspyr                ! days per year
    !-----------------------------------------------------------------------
        
    !get info from externals
    day = get_curr_calday()
    dayspyr = get_curr_days_per_year()               !Add by MWG for IDPP-based routine

    ! days past planting may determine harvest/tillage
    if (day >= idop(p)) then
        idpp = day - idop(p)
    else
        idpp = int(dayspyr) + day - idop(p)
    end if

    ! -----------------------------------------------------
    ! 3) assigning cultivation practices and mapping to the
    !    effect on soil C decomposition
    ! -----------------------------------------------------
    ! info from DAYCENT (Melannie Hartman CSU)
    ! temp. cereals: P 30 d bef, C 15 d bef, D on day of planting
    ! corn, soy    : P           C           D           & HW-7 30 d aftr

    phase = 0

    if (use_original_tillage) then
        if (day >= idop(p) .and. day < idop(p)+15) then ! based on Point Chisel Tandem Disk multipliers
            phase = 1
        else if (day >= idop(p)+15 .and. day < idop(p)+45) then ! based on Field and Row Cultivator multipliers
            phase = 2
        else if (day >= idop(p)+45 .and. day <idop(p)+75) then ! based on Rod Weed Row Planter
            phase = 3
        end if
    else
        if (idpp < 15) then ! based on Point Chisel Tandem Disk multipliers
            phase = 1
        else if (idpp < 45) then ! based on Field and Row Cultivator multipliers
            phase = 2
        else if (idpp < 75) then ! based on Rod Weed Row Planter
            phase = 3
        end if
    end if

    tillage_mults(:) = 1._r8
    if (phase > 0) then
        if (phase > nphases) then
            call endrun(msg='Tillage phase > nphases')
        end if
        tillage_mults = tillage_mults_allphases(:, phase)
    end if
    
  end subroutine get_tillage_multipliers


  subroutine get_apply_tillage_multipliers(idop, c, decomp_k, i_act_som, i_slo_som, i_pas_som, i_cel_lit, i_lig_lit)
    ! !DESCRIPTION:
    !
    ! Multiply decomposition rate constants by tillage coefficients.
    ! Written by Sam Rabin, based on original code by Michael Graham.
    !
    ! !USES
    use pftconMod , only : npcropmin
    !
    ! !ARGUMENTS:
    integer       , intent(in) :: idop(:) ! patch day of planting
    integer       , intent(in) :: c       ! index of column this is being called for
    real(r8), dimension(:,:,:), intent(inout) :: decomp_k ! Output: [real(r8) (:,:,:) ]  rate constant for decomposition (1./sec)
    integer          , intent(in) :: i_act_som, i_slo_som, i_pas_som  ! indices for soil organic matter pools
    integer          , intent(in) :: i_cel_lit, i_lig_lit  ! indices for litter pools
    !
    ! !LOCAL VARIABLES
    integer :: p, this_patch, j, n_noncrop

    if (.not. col%active(c)) then
        return
    end if

    ! TODO: Figure out why adding ".and. col%lun_itype(c) == istcrop" to conditional
    !       controlling call of this subroutine didn't properly exclude non-crop columns.
    !       That working would allow simplification here.
    this_patch = 0
    n_noncrop = 0
    do p = col%patchi(c),col%patchf(c)
        if (patch%active(p)) then
            if (patch%itype(p) >= npcropmin) then
                if (this_patch > 0) then
                    call endrun('ERROR multiple active crop patches found in this column')
                end if
                this_patch = p
            else
                n_noncrop = n_noncrop + 1
            end if
        end if
    end do
    if (n_noncrop > 0) then
        if (this_patch > 0) then
            call endrun('ERROR Active crop and non-crop patches found in this active column')
        end if
        return
    elseif (this_patch == 0) then
        call endrun('ERROR No active patches found (crop OR non-crop)')
    end if

    ! Set up tillage multipliers
    ! (It would be better to do this in tillage_init, but that can't happen
    ! because these indices are private members of SoilBiogeochemDecompCascadeBGCMod.
    tillage_mults_allphases(:,:) = 1.0_r8
    tillage_mults_allphases(i_cel_lit,:) = (/ 1.5_r8, 1.5_r8, 1.1_r8 /)
    tillage_mults_allphases(i_lig_lit,:) = (/ 1.5_r8, 1.5_r8, 1.1_r8 /)
    tillage_mults_allphases(i_act_som,:) = (/ 1.0_r8, 1.0_r8, 1.0_r8 /)
    tillage_mults_allphases(i_slo_som,:) = (/ 3.0_r8, 1.6_r8, 1.3_r8 /)
    tillage_mults_allphases(i_pas_som,:) = (/ 3.0_r8, 1.6_r8, 1.3_r8 /)

    call get_tillage_multipliers(idop, this_patch, i_act_som, i_slo_som, i_pas_som, i_cel_lit, i_lig_lit)

    ! Top 5 layers (instead of all nlevdecomp) so that model only tills the top 26-40 cm
    ! of the soil surface, rather than whole soil - MWGraham
    do j = 1,5
        decomp_k(c,j,:) = decomp_k(c,j,:) * tillage_mults(:)
    end do

  end subroutine get_apply_tillage_multipliers

end module TillageMod
