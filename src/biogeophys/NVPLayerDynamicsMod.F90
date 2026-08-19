module NVPLayerDynamicsMod

  !-----------------------------------------------------------------------
  ! !DESCRIPTION:
  ! Geometry and cold-start/restart handling of the non-vascular plant layer
  ! (NVP: moss, lichen) that occupies vertical index 0 on istsoil and istcrop
  ! columns when use_nvp is on.
  !
  ! Thickness and coverage are namelist constants assigned once, at
  ! initialization, and constant for the run. Because nothing activates or
  ! deactivates the layer at runtime, no conservation flux has to accompany a
  ! geometry change; the FATES-prognostic UpdateNVPLayer of ctsm5.4.028_nvp
  ! merges alongside these routines.
  !
  ! Geometry: the soil surface remains the depth datum, so zi(c,0) = 0 is
  ! unchanged and the soil column is untouched. NVP occupies [-dz_nvp, 0], so
  ! zi(c,-1) = -dz_nvp is both the NVP top and the snow bottom, which is what
  ! the snow-geometry recursions reproduce when anchored at zi(c,jbot_sno).
  !
  ! !USES:
  use shr_kind_mod    , only : r8 => shr_kind_r8
  use shr_log_mod     , only : errMsg => shr_log_errMsg
  use abortutils      , only : endrun
  use decompMod       , only : bounds_type
  use ColumnType      , only : col
  use LandunitType    , only : lun
  use landunit_varcon , only : istsoil, istcrop
  use clm_varcon      , only : denh2o, denice, tfrz
  use clm_varctl      , only : use_nvp, iulog
  use TemperatureType , only : temperature_type
  use WaterStateType  , only : waterstate_type
  use WaterDiagnosticBulkType, only : waterdiagnosticbulk_type
  use NVPParamsMod    , only : dz_nvp, frac_nvp, watsat_nvp, nvp_coldstart_saturation
  !
  implicit none
  private
  !
  ! !PUBLIC MEMBER FUNCTIONS:
  public :: NVPLayerInit     ! claim index 0 and set the static NVP geometry
  public :: NVPLayerRestart  ! read/write the NVP column geometry
  public :: NVPColdStart     ! fill the NVP pore space at cold start

  character(len=*), parameter, private :: sourcefile = &
       __FILE__

!-----------------------------------------------------------------------
contains
!-----------------------------------------------------------------------

  !-----------------------------------------------------------------------
  subroutine NVPLayerInit(bounds)
    !
    ! !DESCRIPTION:
    ! Claim vertical index 0 for the NVP layer on every istsoil/istcrop column
    ! and give it the namelist geometry.
    !
    ! Must run before InitSnowLayers, which lays the snow slots out against
    ! col%jbot_sno, and before any presence query runs on an NVP column: on such
    ! a column col%nvp_is_present reads col%dz(c,0), which is NaN until this
    ! routine assigns it.
    !
    ! Columns of every other type are left with jbot_sno == 0 and untouched,
    ! which is what makes lake, glacier, wetland and urban columns reduce to
    ! stock code.
    !
    ! !ARGUMENTS:
    type(bounds_type), intent(in) :: bounds
    !
    ! !LOCAL VARIABLES:
    integer :: c, l   ! column, landunit indices
    !-----------------------------------------------------------------------

    if (.not. use_nvp) return

    do c = bounds%begc, bounds%endc
       l = col%landunit(c)

       if (lun%itype(l) /= istsoil .and. lun%itype(l) /= istcrop) then
          ! The NVP slot may exist only on vegetated and crop columns: every
          ! other column type reduces to stock code only while its jbot_sno
          ! stays 0.
          if (col%jbot_sno(c) /= 0) then
             call endrun(msg='NVPLayerInit ERROR: the NVP layer at index 0 is claimed on a '// &
                  'column that is neither istsoil nor istcrop'//errMsg(sourcefile, __LINE__))
          end if
          cycle
       end if

       col%jbot_sno(c)         = -1
       col%nvp_layer_active(c) = .true.
       col%dz_nvp(c)           = dz_nvp
       col%frac_nvp(c)         = frac_nvp

       ! dz_nvp = 0 is a supported state meaning the slot exists but holds no
       ! NVP; the geometry then collapses onto the soil surface and every flux
       ! must skip the layer.
       col%dz(c,0)  = dz_nvp
       col%z(c,0)   = -0.5_r8 * dz_nvp
       col%zi(c,-1) = -dz_nvp
    end do

  end subroutine NVPLayerInit

  !-----------------------------------------------------------------------
  subroutine NVPLayerRestart(bounds, ncid, flag)
    !
    ! !DESCRIPTION:
    ! Read/write the three column variables that define NVP presence and
    ! geometry. The layer's water, ice and temperature ride in slot 0 of the
    ! standard levtot variables (H2OSOI_LIQ, H2OSOI_ICE, T_SOISNO) and its
    ! dz/z/zi in DZSNO/ZSNO/ZISNO, so those need nothing here.
    !
    ! Callers must enter this on every 'read', use_nvp = .false. included, so
    ! that the reverse cross-flag probe below runs; 'define' and 'write' only
    ! under use_nvp, so that a use_nvp = .false. run does not stamp the NVP
    ! variables onto its own restart file and trip that same probe when the file
    ! is read back.
    !
    ! !USES:
    use ncdio_pio   , only : file_desc_t, ncd_double, ncd_int, check_var
    ! restUtilMod, not restFileMod: restFileMod uses clm_instMod, which uses
    ! this module, so naming restFileMod here is a build-dependency cycle.
    use restUtilMod , only : restartvar
    !
    ! !ARGUMENTS:
    type(bounds_type) , intent(in)    :: bounds
    type(file_desc_t) , intent(inout) :: ncid
    character(len=*)  , intent(in)    :: flag   ! 'define', 'write' or 'read'
    !
    ! !LOCAL VARIABLES:
    integer :: c            ! column index
    logical :: readvar      ! whether restartvar found the variable
    ! Set by check_var and read only inside the same flag == 'read' block; not
    ! initialized here, because a local with an initializer acquires SAVE
    logical :: nvp_on_file  ! whether the file carries the NVP variables

    ! Geometry is written and read as a double, so the only admissible
    ! difference is round-trip representation error, not a physical tolerance
    real(r8), parameter :: dz_nvp_restart_tol = 1.e-12_r8   ! [m]
    !-----------------------------------------------------------------------

    if (flag == 'read') then
       ! JBOT_SNO on the file is the proxy for "written with use_nvp on". The
       ! two flag settings lay the snow block out one slot apart, so a
       ! cross-flag read would silently mistake moss for snow or snow for moss.
       !
       ! check_var, not restartvar: restartvar aborts a branch or continue run
       ! on a missing field, which would kill every use_nvp = .false. restart
       ! off a stock file.
       call check_var(ncid, 'JBOT_SNO', nvp_on_file, print_err=.false.)

       if (.not. use_nvp) then
          if (nvp_on_file) then
             call endrun(msg='NVPLayerRestart ERROR: restart was written with use_nvp on; '// &
                  'enable use_nvp or use a different initial file'//errMsg(sourcefile, __LINE__))
          end if
          ! The probe is the whole job when use_nvp is off.
          return
       end if

       ! Do not suggest interpolating: init_interp support is deferred (spec
       ! section 8), and that path sets is_cold_start false, so NVPColdStart
       ! never runs and the moss slot would inherit the source file's snow
       ! water. A cold start is the only route that initializes NVP correctly.
       if (.not. nvp_on_file) then
          call endrun(msg='NVPLayerRestart ERROR: restart predates use_nvp; '// &
               'cold-start instead'//errMsg(sourcefile, __LINE__))
       end if
    end if

    readvar = .false.
    call restartvar(ncid=ncid, flag=flag, varname='DZ_NVP', xtype=ncd_double, &
         dim1name='column', &
         long_name='NVP (moss/lichen) layer thickness', units='m', &
         interpinic_flag='interp', readvar=readvar, data=col%dz_nvp)

    readvar = .false.
    call restartvar(ncid=ncid, flag=flag, varname='FRAC_NVP', xtype=ncd_double, &
         dim1name='column', &
         long_name='NVP (moss/lichen) fractional coverage', units='unitless', &
         interpinic_flag='interp', readvar=readvar, data=col%frac_nvp)

    ! 'skip', not 'interp': jbot_sno is an index flag whose only legal values
    ! are 0 and -1, and interpolating between columns produces neither.
    ! init_interp therefore keeps the value NVPLayerInit assigned.
    readvar = .false.
    call restartvar(ncid=ncid, flag=flag, varname='JBOT_SNO', xtype=ncd_int, &
         dim1name='column', &
         long_name='bottom index of the snow pack (0, or -1 where the NVP slot exists)', &
         units='unitless', &
         interpinic_flag='skip', readvar=readvar, data=col%jbot_sno)

    if (flag == 'read') then
       ! nvp_layer_active is redundant with jbot_sno == -1 and is not on the
       ! file; re-deriving it here is what keeps the two from disagreeing.
       col%nvp_layer_active(bounds%begc:bounds%endc) = &
            (col%jbot_sno(bounds%begc:bounds%endc) == -1)

       ! Geometry is static for the run, so a namelist dz_nvp that disagrees
       ! with the restarted layer would change the column's water and heat
       ! capacity mid-run with no flux to account for it.
       do c = bounds%begc, bounds%endc
          if (col%nvp_layer_exists(c)) then
             if (abs(col%dz(c,0) - dz_nvp) > dz_nvp_restart_tol) then
                write(iulog,*) 'NVPLayerRestart ERROR: column ', c, &
                     ' restart dz(c,0) = ', col%dz(c,0), ' namelist dz_nvp = ', dz_nvp
                call endrun(msg='NVPLayerRestart ERROR: namelist dz_nvp differs from the NVP '// &
                     'layer thickness on the restart file'//errMsg(sourcefile, __LINE__))
             end if
          end if
       end do
    end if

  end subroutine NVPLayerRestart

  !-----------------------------------------------------------------------
  subroutine NVPColdStart(bounds, temperature_inst, waterstate_inst, waterdiagnosticbulk_inst)
    !
    ! !DESCRIPTION:
    ! Fill the NVP pore space at cold start. The generic WaterStateType cold
    ! start fills slot 0 as though it were a snow slot, which on an NVP column
    ! is neither the right pore volume nor necessarily the right phase.
    !
    ! The liquid/ice split follows the column's own initial soil temperature
    ! rather than assuming a frozen start, so it tracks whatever the cold-start
    ! soil temperature is. Note what that means today: TemperatureType cold
    ! starts every soil column at 272 K, below tfrz, so the liquid branch is
    ! currently unreachable and every column fills as ice. That is correct
    ! behaviour for the temperature it is given -- the branch is here so the
    ! fill follows the soil temperature if that ever varies, not because it
    ! varies now.
    !
    ! Slot 0 also gets a temperature here. TemperatureType blankets the range
    ! with spval and then fills only snl(c)+1:0, so on a snow-free column slot 0
    ! keeps spval; giving it mass without a temperature would hand the first
    ! energy calculation ~4 kg m-2 of ice at 1.e36 K.
    !
    ! fwet_nvp_col is set here too, because it is a lagged state, not a
    ! derived diagnostic: surface fluxes read it to get the evaporation
    ! resistance, and the moss water balance writes it, but BareGroundFluxes
    ! and CanopyFluxes run before HydrologyNoDrainage in every timestep. So the
    ! resistance always uses the wetness hydrology wrote on the previous step,
    ! and the first step needs an initial value or it reads spval.
    !
    ! !ARGUMENTS:
    type(bounds_type)      , intent(in)    :: bounds
    type(temperature_type) , intent(inout) :: temperature_inst
    class(waterstate_type) , intent(inout) :: waterstate_inst
    type(waterdiagnosticbulk_type), intent(inout) :: waterdiagnosticbulk_inst
    !
    ! !LOCAL VARIABLES:
    integer  :: c            ! column index
    real(r8) :: pore_water   ! water filling the NVP pore space [m3 m-2]
    !-----------------------------------------------------------------------

    if (.not. use_nvp) return

    associate(                                       &
         t_soisno   => temperature_inst%t_soisno_col , & ! In/out: [real(r8) (:,:)] soil temperature (K)
         t_nvp      => temperature_inst%t_nvp_col    , & ! Output: [real(r8) (:)  ] NVP layer temperature (K)
         h2onvp     => waterstate_inst%h2onvp_col    , & ! Output: [real(r8) (:)  ] NVP layer water (kg m-2)
         fwet_nvp   => waterdiagnosticbulk_inst%fwet_nvp_col, & ! Output: [real(r8) (:)] NVP wetness fraction (-)
         h2osoi_liq => waterstate_inst%h2osoi_liq_col, & ! Output: [real(r8) (:,:)] liquid water (kg m-2)
         h2osoi_ice => waterstate_inst%h2osoi_ice_col  & ! Output: [real(r8) (:,:)] ice lens (kg m-2)
         )

    do c = bounds%begc, bounds%endc
       if (col%nvp_is_present(c)) then
          pore_water = nvp_coldstart_saturation * watsat_nvp * col%dz(c,0)
          if (t_soisno(c,1) >= tfrz) then
             h2osoi_liq(c,0) = pore_water * denh2o
             h2osoi_ice(c,0) = 0._r8
          else
             h2osoi_liq(c,0) = 0._r8
             h2osoi_ice(c,0) = pore_water * denice
          end if
       else if (col%nvp_is_empty(c)) then
          ! A slot that holds no NVP must hold no mass either, or the
          ! zero-thickness state stops reducing to stock.
          h2osoi_liq(c,0) = 0._r8
          h2osoi_ice(c,0) = 0._r8
       end if
       ! Every slot-bearing column, with moss or without: slot 0 must not be
       ! left at spval once anything downstream reads it as a layer, and the
       ! NVP mirrors must agree with the state built above. TemperatureType and
       ! WaterStateType give t_nvp_col and h2onvp_col blanket cold-start values
       ! before this runs; those cannot know the layer is all ice at 272 K, and
       ! the surface-flux blends read the mirrors before Phasechange re-syncs
       ! them, so a disagreement here is visible in the first timestep.
       if (col%nvp_layer_exists(c)) then
          t_soisno(c,0) = t_soisno(c,1)
          t_nvp(c)      = t_soisno(c,0)
          h2onvp(c)     = h2osoi_liq(c,0) + h2osoi_ice(c,0)
          ! The pore space was just filled to this saturation, so this is the
          ! wetness the first timestep's evaporation resistance should see. An
          ! empty slot is dry, which is what its zero thickness implies.
          if (col%nvp_is_present(c)) then
             fwet_nvp(c) = nvp_coldstart_saturation
          else
             fwet_nvp(c) = 0._r8
          end if
       end if
    end do

    end associate

  end subroutine NVPColdStart

end module NVPLayerDynamicsMod
