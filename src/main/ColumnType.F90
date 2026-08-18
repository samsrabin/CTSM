module ColumnType

  !-----------------------------------------------------------------------
  ! !DESCRIPTION:
  ! Column data type allocation and initialization
  ! -------------------------------------------------------- 
  ! column types can have values of
  ! -------------------------------------------------------- 
  !   1  => (istsoil)          soil (vegetated or bare soil)
  !   2  => (istcrop)          crop (only for crop configuration)
  !   3  => (UNUSED)           (formerly non-multiple elevation class land ice; currently unused)
  !   4  => (istice)           land ice
  !   5  => (istdlak)          deep lake
  !   6  => (istwet)           wetland
  !   71 => (icol_roof)        urban roof
  !   72 => (icol_sunwall)     urban sunwall
  !   73 => (icol_shadewall)   urban shadewall
  !   74 => (icol_road_imperv) urban impervious road
  !   75 => (icol_road_perv)   urban pervious road
  !
  use shr_kind_mod   , only : r8 => shr_kind_r8
  use shr_infnan_mod , only : nan => shr_infnan_nan, assignment(=)
  use clm_varpar     , only : nlevsno, nlevgrnd, nlevlak, nlevmaxurbgrnd
  use clm_varcon     , only : spval, ispval
  use shr_sys_mod    , only : shr_sys_abort
  use clm_varctl     , only : iulog
  use column_varcon  , only : is_hydrologically_active
  use LandunitType   , only : lun
  !
  ! !PUBLIC TYPES:
  implicit none
  save
  private
  !
  type, public :: column_type
     ! g/l/c/p hierarchy, local g/l/c/p cells only
     integer , pointer :: landunit             (:)   ! index into landunit level quantities
     real(r8), pointer :: wtlunit              (:)   ! weight (relative to landunit)
     integer , pointer :: gridcell             (:)   ! index into gridcell level quantities
     real(r8), pointer :: wtgcell              (:)   ! weight (relative to gridcell)
     integer , pointer :: patchi               (:)   ! beginning patch index for each column
     integer , pointer :: patchf               (:)   ! ending patch index for each column
     integer , pointer :: npatches             (:)   ! number of patches for each column

     ! topological mapping functionality
     integer , pointer :: itype                (:)   ! column type (after init, should only be modified via update_itype routine)
     integer , pointer :: lun_itype            (:)   ! landunit type (col%lun_itype(ci) is the
                                                     ! same as lun%itype(col%landunit(ci)), but is often a more convenient way to access this type
     logical , pointer :: active               (:)   ! true=>do computations on this column
     logical , pointer :: type_is_dynamic      (:)   ! true=>itype can change throughout the run
     
     logical , pointer :: is_fates             (:)   ! .true. -> this is a fates column
                                                     ! .false. -> this is NOT a fates column
     
     ! topography
     ! TODO(wjs, 2016-04-05) Probably move these things into topoMod
     real(r8), pointer :: micro_sigma          (:)   ! microtopography pdf sigma (m)
     real(r8), pointer :: topo_slope           (:)   ! gridcell topographic slope
     real(r8), pointer :: topo_std             (:)   ! gridcell elevation standard deviation

     ! vertical levels
     integer , pointer :: snl                  (:)   ! number of snow layers
     ! Non-vascular plant (NVP) layer at vertical index 0. jbot_sno is the bottom
     ! index of the snow pack: 0 where there is no NVP slot (stock CLM), -1 where
     ! the slot exists. Assigned once at initialization and constant thereafter;
     ! snl keeps its stock meaning, -(number of snow layers), on every column.
     integer , pointer :: jbot_sno             (:)   ! bottom index of the snow pack (0, or -1 where the NVP slot exists)
     ! Redundant with jbot_sno == -1 and write-only here; carried solely so that
     ! the ctsm5.4.028_nvp branch merges. Nothing may read this: test the slot
     ! with nvp_layer_exists(c).
     logical , pointer :: nvp_layer_active     (:)   ! .true. iff jbot_sno == -1
     ! NVP geometry: namelist constants applied at initialization, static for the
     ! run. dz_nvp = 0 is a supported value meaning the slot exists but holds no
     ! NVP; frac_nvp must be 0 whenever dz_nvp is 0.
     real(r8), pointer :: dz_nvp               (:)   ! NVP layer thickness (m)
     real(r8), pointer :: frac_nvp             (:)   ! NVP fractional coverage of the column (0-1)
     real(r8), pointer :: dz                   (:,:) ! layer thickness (m)  (-nlevsno+1:nlevgrnd) 
     real(r8), pointer :: z                    (:,:) ! layer depth (m) (-nlevsno+1:nlevgrnd) 
     real(r8), pointer :: zi                   (:,:) ! interface level below a "z" level (m) (-nlevsno+0:nlevgrnd) 
     real(r8), pointer :: zii                  (:)   ! convective boundary height [m]
     real(r8), pointer :: dz_lake              (:,:) ! lake layer thickness (m)  (1:nlevlak)
     real(r8), pointer :: z_lake               (:,:) ! layer depth for lake (m)
     real(r8), pointer :: lakedepth            (:)   ! variable lake depth (m)                             
     integer , pointer :: nbedrock             (:)   ! variable depth to bedrock index
     ! hillslope hydrology variables
     integer,  pointer :: col_ndx              (:)   ! column index of column (hillslope hydrology)
     integer,  pointer :: colu                 (:)   ! column index of uphill column (hillslope hydrology)
     integer,  pointer :: cold                 (:)   ! column index of downhill column (hillslope hydrology)
     integer,  pointer :: hillslope_ndx        (:)   ! hillslope identifier
     real(r8), pointer :: hill_elev            (:)   ! mean elevation of column relative to stream channel (m)
     real(r8), pointer :: hill_slope           (:)   ! mean along-hill slope (m/m)
     real(r8), pointer :: hill_area            (:)   ! mean surface area (m2)
     real(r8), pointer :: hill_width           (:)   ! across-hill width of bottom boundary of column (m)
     real(r8), pointer :: hill_distance        (:)   ! along-hill distance of column from bottom of hillslope (m)
     real(r8), pointer :: hill_aspect          (:)   ! azimuth angle of column wrt to north, positive to east (radians)

     ! other column characteristics
     logical , pointer :: is_hillslope_column(:)     ! true if this column is a hillslope element
     logical , pointer :: hydrologically_active(:)   ! true if this column is a hydrologically active type
     logical , pointer :: urbpoi               (:)   ! true=>urban point

     ! levgrnd_class gives the class in which each layer falls. This is relevant for
     ! columns where there are 2 or more fundamentally different layer types. For
     ! example, this distinguishes between soil and bedrock layers. The particular value
     ! assigned to each class is irrelevant; the important thing is that different
     ! classes (e.g., soil vs. bedrock) have different values of levgrnd_class.
     !
     ! levgrnd_class = ispval indicates that the given layer is completely unused for
     ! this column (i.e., this column doesn't use the full nlevgrnd layers).
     integer , pointer :: levgrnd_class        (:,:) ! class in which each layer falls (1:nlevgrnd)
   contains

     procedure, public :: Init
     procedure, public :: Clean

     ! Update the column type for one column. Any updates to col%itype after
     ! initialization should be made via this routine.
     procedure, public :: update_itype

     ! NVP index-0 queries. Type-bound rather than module procedures so that a
     ! routine holding col as a dummy argument queries that dummy: referencing
     ! the module col through host association while it is argument-associated
     ! is not conforming (F2018 15.5.2.13), and lets a compiler assume the read
     ! cannot alias writes made through the dummy.
     procedure, public :: get_jtop_snow      ! index of the top snow layer
     procedure, public :: get_jbot_snow      ! index of the bottom snow layer
     procedure, public :: nvp_layer_exists   ! the index-0 NVP slot exists here
     procedure, public :: nvp_is_present     ! the slot exists and holds NVP of nonzero thickness
     procedure, public :: nvp_is_empty       ! the slot exists but holds no NVP

  end type column_type

  type(column_type), public, target :: col !column data structure (soil/snow/canopy columns)
  !------------------------------------------------------------------------

contains
  
  !------------------------------------------------------------------------
  subroutine Init(this, begc, endc)
    !
    ! !ARGUMENTS:
    class(column_type)  :: this
    integer, intent(in) :: begc,endc
    !------------------------------------------------------------------------

    ! The following is set in initGridCellsMod
    allocate(this%gridcell    (begc:endc))                     ; this%gridcell    (:)   = ispval
    allocate(this%wtgcell     (begc:endc))                     ; this%wtgcell     (:)   = nan
    allocate(this%landunit    (begc:endc))                     ; this%landunit    (:)   = ispval
    allocate(this%wtlunit     (begc:endc))                     ; this%wtlunit     (:)   = nan
    allocate(this%patchi      (begc:endc))                     ; this%patchi      (:)   = ispval
    allocate(this%patchf      (begc:endc))                     ; this%patchf      (:)   = ispval
    allocate(this%npatches     (begc:endc))                    ; this%npatches     (:)   = ispval
    allocate(this%itype       (begc:endc))                     ; this%itype       (:)   = ispval
    allocate(this%lun_itype   (begc:endc))                     ; this%lun_itype   (:)   = ispval
    allocate(this%active      (begc:endc))                     ; this%active      (:)   = .false.
    allocate(this%type_is_dynamic(begc:endc))                  ; this%type_is_dynamic(:) = .false.

    allocate(this%is_fates(begc:endc))                         ; this%is_fates(:) = .false.
    
    ! The following is set in initVerticalMod
    allocate(this%snl         (begc:endc))                     ; this%snl         (:)   = ispval  !* cannot be averaged up
    allocate(this%jbot_sno    (begc:endc))                     ; this%jbot_sno    (:)   = 0       ! stock: snow runs to index 0
    allocate(this%nvp_layer_active(begc:endc))                 ; this%nvp_layer_active(:) = .false.
    allocate(this%dz_nvp      (begc:endc))                     ; this%dz_nvp      (:)   = 0._r8
    allocate(this%frac_nvp    (begc:endc))                     ; this%frac_nvp    (:)   = 0._r8
    allocate(this%dz          (begc:endc,-nlevsno+1:nlevmaxurbgrnd)) ; this%dz          (:,:) = nan
    allocate(this%z           (begc:endc,-nlevsno+1:nlevmaxurbgrnd)) ; this%z           (:,:) = nan
    allocate(this%zi          (begc:endc,-nlevsno+0:nlevmaxurbgrnd)) ; this%zi          (:,:) = nan
    allocate(this%zii         (begc:endc))                     ; this%zii         (:)   = nan
    allocate(this%lakedepth   (begc:endc))                     ; this%lakedepth   (:)   = spval  
    allocate(this%dz_lake     (begc:endc,nlevlak))             ; this%dz_lake     (:,:) = nan
    allocate(this%z_lake      (begc:endc,nlevlak))             ; this%z_lake      (:,:) = nan
    allocate(this%col_ndx    (begc:endc))                      ; this%col_ndx(:) = ispval
    allocate(this%colu       (begc:endc))                      ; this%colu   (:) = ispval
    allocate(this%cold       (begc:endc))                      ; this%cold   (:) = ispval
    allocate(this%hillslope_ndx(begc:endc))                    ; this%hillslope_ndx (:) = ispval
    allocate(this%hill_elev(begc:endc))                        ; this%hill_elev     (:) = spval
    allocate(this%hill_slope(begc:endc))                       ; this%hill_slope    (:) = spval
    allocate(this%hill_area(begc:endc))                        ; this%hill_area     (:) = spval
    allocate(this%hill_width(begc:endc))                       ; this%hill_width    (:) = spval
    allocate(this%hill_distance(begc:endc))                    ; this%hill_distance (:) = spval
    allocate(this%hill_aspect(begc:endc))                      ; this%hill_aspect (:) = spval
    allocate(this%nbedrock   (begc:endc))                      ; this%nbedrock   (:)   = ispval  
    allocate(this%levgrnd_class(begc:endc,nlevmaxurbgrnd))     ; this%levgrnd_class(:,:) = ispval
    allocate(this%micro_sigma (begc:endc))                     ; this%micro_sigma (:)   = nan
    allocate(this%topo_slope  (begc:endc))                     ; this%topo_slope  (:)   = nan
    allocate(this%topo_std    (begc:endc))                     ; this%topo_std    (:)   = nan
    allocate(this%is_hillslope_column(begc:endc))              ; this%is_hillslope_column(:) = .false.
    allocate(this%hydrologically_active(begc:endc))            ; this%hydrologically_active(:) = .false.
    allocate(this%urbpoi      (begc:endc))                     ; this%urbpoi      (:)   = .false.

  end subroutine Init

  !------------------------------------------------------------------------
  subroutine Clean(this)
    !
    ! !ARGUMENTS:
    class(column_type) :: this
    !------------------------------------------------------------------------

    deallocate(this%gridcell   )
    deallocate(this%wtgcell    )
    deallocate(this%landunit   )
    deallocate(this%wtlunit    )
    deallocate(this%patchi     )
    deallocate(this%patchf     )
    deallocate(this%npatches    )
    deallocate(this%itype      )
    deallocate(this%lun_itype  )
    deallocate(this%active     )
    deallocate(this%is_fates   )
    deallocate(this%type_is_dynamic)
    deallocate(this%snl        )
    deallocate(this%jbot_sno   )
    deallocate(this%nvp_layer_active)
    deallocate(this%dz_nvp     )
    deallocate(this%frac_nvp   )
    deallocate(this%dz         )
    deallocate(this%z          )
    deallocate(this%zi         )
    deallocate(this%zii        )
    deallocate(this%lakedepth  )
    deallocate(this%dz_lake    )
    deallocate(this%z_lake     )
    deallocate(this%micro_sigma)
    deallocate(this%topo_slope )
    deallocate(this%topo_std   )
    deallocate(this%nbedrock   )
    deallocate(this%levgrnd_class)
    deallocate(this%is_hillslope_column)
    deallocate(this%hydrologically_active)
    deallocate(this%col_ndx    )
    deallocate(this%colu       )
    deallocate(this%cold       )
    deallocate(this%hillslope_ndx)
    deallocate(this%hill_elev    )
    deallocate(this%hill_slope   )
    deallocate(this%hill_area    )
    deallocate(this%hill_width   )
    deallocate(this%hill_distance)
    deallocate(this%hill_aspect  )
    deallocate(this%urbpoi       )
  end subroutine Clean

  !-----------------------------------------------------------------------
  subroutine update_itype(this, c, itype)
    !
    ! !DESCRIPTION:
    ! Update the column type for one column. Any updates to col%itype after
    ! initialization should be made via this routine.
    !
    ! This can NOT be used to change the landunit type: it can only be used to change the
    ! column type within a fixed landunit.
    !
    ! !ARGUMENTS:
    class(column_type), intent(inout) :: this
    integer, intent(in) :: c
    integer, intent(in) :: itype
    !
    ! !LOCAL VARIABLES:

    character(len=*), parameter :: subname = 'update_itype'
    !-----------------------------------------------------------------------

    if (col%type_is_dynamic(c)) then
       col%itype(c) = itype
       col%hydrologically_active(c) = is_hydrologically_active( &
            col_itype = itype, &
            lun_itype = col%lun_itype(c))
       ! Properties that are tied to the landunit's properties (like urbpoi) are assumed
       ! not to change here.
    else
       write(iulog,*) subname//' ERROR: attempt to update itype when type_is_dynamic is false'
       write(iulog,*) 'c, col%itype(c), itype = ', c, col%itype(c), itype
       ! Need to use shr_sys_abort rather than endrun, because using endrun would cause
       ! circular dependencies
       call shr_sys_abort(subname//' ERROR: attempt to update itype when type_is_dynamic is false')
    end if
  end subroutine update_itype

  !-----------------------------------------------------------------------
  pure function get_jtop_snow(this, c) result(j)
    !
    ! !DESCRIPTION:
    ! Index of the top snow layer on column c. Reduces to the stock snl(c)+1
    ! wherever the NVP slot does not exist.
    !
    ! When snl==0 on an NVP column this returns 0 (the NVP index) -- callers
    ! wanting a surface layer with actual mass must fall back to soil layer 1
    ! when .not. nvp_is_present(c).
    !
    ! Requires snl(c) >= -(nlevsno-1) on NVP columns: the slot at index 0 costs
    ! one snow level, so a full pack there is one layer shallower than stock.
    ! Violating it returns an index below dz's lower bound of -nlevsno+1.
    !
    ! !ARGUMENTS:
    integer :: j                          ! function result
    class(column_type), intent(in) :: this
    integer, intent(in) :: c
    !-----------------------------------------------------------------------

    j = this%snl(c) + 1 + this%jbot_sno(c)

  end function get_jtop_snow

  !-----------------------------------------------------------------------
  pure function get_jbot_snow(this, c) result(j)
    !
    ! !DESCRIPTION:
    ! Index of the bottom snow layer on column c: 0 wherever the NVP slot does
    ! not exist, -1 where it does. Paired with get_jtop_snow so snow loops read
    ! do j = col%get_jtop_snow(c), col%get_jbot_snow(c).
    !
    ! !ARGUMENTS:
    integer :: j                          ! function result
    class(column_type), intent(in) :: this
    integer, intent(in) :: c
    !-----------------------------------------------------------------------

    j = this%jbot_sno(c)

  end function get_jbot_snow

  !-----------------------------------------------------------------------
  pure function nvp_layer_exists(this, c) result(slot_exists)
    !
    ! !DESCRIPTION:
    ! The index-0 slot is reserved for NVP on this column. Says nothing about
    ! whether NVP is physically there -- use nvp_is_present for that.
    !
    ! !ARGUMENTS:
    logical :: slot_exists                ! function result
    class(column_type), intent(in) :: this
    integer, intent(in) :: c
    !-----------------------------------------------------------------------

    slot_exists = this%jbot_sno(c) == -1

  end function nvp_layer_exists

  !-----------------------------------------------------------------------
  pure function nvp_is_present(this, c) result(is_present)
    !
    ! !DESCRIPTION:
    ! NVP physically present: the slot exists AND holds a layer of nonzero
    ! thickness.
    !
    ! dz(c,0) is read only where the slot exists, via a nested if rather than
    ! .and., which Fortran does not guarantee to short-circuit. Off NVP columns
    ! index 0 is snow storage that InitSnowLayers fills with spval (1.e36) --
    ! and spval > 0 is .true., so an unguarded read reports NVP that is not
    ! there. NaN, the other value it holds before ZeroEmptySnowLayers runs, is
    ! the benign case: NaN > 0 is .false.
    !
    ! !ARGUMENTS:
    logical :: is_present                 ! function result
    class(column_type), intent(in) :: this
    integer, intent(in) :: c
    !-----------------------------------------------------------------------

    is_present = .false.
    if (this%nvp_layer_exists(c)) then
       is_present = this%dz(c,0) > 0._r8
    end if

  end function nvp_is_present

  !-----------------------------------------------------------------------
  pure function nvp_is_empty(this, c) result(empty)
    !
    ! !DESCRIPTION:
    ! The slot exists but holds no NVP. Derived from the two functions above, so
    ! it inherits their protection against reading dz(c,0) off an NVP column,
    ! and so present/empty partition the NVP columns for any value of dz(c,0).
    !
    ! !ARGUMENTS:
    logical :: empty                      ! function result
    class(column_type), intent(in) :: this
    integer, intent(in) :: c
    !-----------------------------------------------------------------------

    empty = this%nvp_layer_exists(c) .and. .not. this%nvp_is_present(c)

  end function nvp_is_empty

end module ColumnType
