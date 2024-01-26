module HillslopeHydrologyUtilsMod

  !-----------------------------------------------------------------------
  ! !DESCRIPTION:
  ! Utilities used in HillslopeHydrologyMod
  !
  ! !USES:
#include "shr_assert.h"
  use decompMod      , only : bounds_type
  use shr_kind_mod   , only : r8 => shr_kind_r8
  use shr_log_mod    , only : errMsg => shr_log_errMsg
  use spmdMod        , only : masterproc, iam
  use abortutils     , only : endrun
  use clm_varctl     , only : iulog

  ! !PUBLIC TYPES:
  implicit none

  private
  save

  ! !PUBLIC MEMBER FUNCTIONS:
  public HillslopeSoilThicknessProfile_linear

contains

  !------------------------------------------------------------------------
  subroutine HillslopeSoilThicknessProfile_linear(nbedrock, bounds, hill_distance, soil_depth_lowland, soil_depth_upland)
    !
    ! !DESCRIPTION:
    ! Modify soil thickness across hillslope by changing
    ! nbedrock according to the "Linear" method
    !
    ! !USES:
    use LandunitType    , only : lun
    use ColumnType      , only : col
    use clm_varpar      , only : nlevsoi
    use clm_varcon      , only : zisoi
    !
    ! !ARGUMENTS:
    integer, pointer, intent(inout) :: nbedrock(:)
    real(r8), pointer, intent(in) :: hill_distance(:)
    type(bounds_type), intent(in) :: bounds
    real(r8), intent(in) :: soil_depth_lowland, soil_depth_upland
    !
    ! !LOCAL VARIABLES
    real(r8) :: min_hill_dist, max_hill_dist
    real(r8) :: soil_depth_col
    real(r8) :: m, b
    integer :: c, j, l
    real(r8), parameter :: toosmall_distance  = 1e-6

    write(iulog, *) 'soil_depth_lowland = ',soil_depth_lowland
    write(iulog, *) 'soil_depth_upland  = ',soil_depth_upland

    write(iulog, *) 'START HillslopeSoilThicknessProfile_linear'
    do l = bounds%begl,bounds%endl
      write(iulog, *) 'l = ',l
       min_hill_dist = minval(hill_distance(lun%coli(l):lun%colf(l)))
       max_hill_dist = maxval(hill_distance(lun%coli(l):lun%colf(l)))

       write(iulog, *) 'min_hill_dist = ',min_hill_dist
       write(iulog, *) 'max_hill_dist = ',max_hill_dist

       if (abs(max_hill_dist - min_hill_dist) > toosmall_distance) then
          m = (soil_depth_lowland - soil_depth_upland)/ &
               (max_hill_dist - min_hill_dist)
       else
          m = 0._r8
       end if
       b = soil_depth_upland

       write(iulog, *) 'm = ',m
       write(iulog, *) 'b = ',b

       do c =  lun%coli(l), lun%colf(l)
          write(iulog, *) 'c = ',c
          if (col%is_hillslope_column(c) .and. col%active(c)) then
             soil_depth_col = m*(max_hill_dist - hill_distance(c)) + b
             write(iulog, *) 'hill_distance(c) = ',hill_distance(c)
             do j = 1,nlevsoi
               write(iulog, *) '   j = ',j
               write(iulog, *), '      soil_depth_col = ',soil_depth_col
               write(iulog, *), '      zisoi(j-1) = ',zisoi(j-1)
               write(iulog, *), '      zisoi(j)   = ',zisoi(j)
               if ((zisoi(j-1) <  soil_depth_col) .and. (zisoi(j) >= soil_depth_col)) then
                  write(iulog, *) '      SETTING NBEDROCK = ',j
                  nbedrock(c) = j
               end if
             enddo
          end if
       enddo
    enddo
    write(iulog, *) 'END HillslopeSoilThicknessProfile_linear'
   end subroutine HillslopeSoilThicknessProfile_linear
end module HillslopeHydrologyUtilsMod