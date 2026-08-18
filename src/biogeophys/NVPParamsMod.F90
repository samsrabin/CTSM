module NVPParamsMod

  ! Parameters for the non-vascular plant (NVP) layer, read via the nvp_inparm
  ! namelist group in controlMod. Stub configuration: thickness/coverage/optics
  ! are namelist constants (FATES-prognostic in the ctsm5.4.028_nvp merge).

  use shr_kind_mod, only : r8 => shr_kind_r8

  implicit none
  public

  ! Evaporation resistance: rnvp = rnvp_min + rnvp_amp*(1 - satfrac)**rnvp_exp
  real(r8) :: rnvp_min      = 10.0_r8     ! resistance when saturated       [s m-1]
  real(r8) :: rnvp_amp      = 1000.0_r8   ! amplitude of increase when dry  [s m-1]
  real(r8) :: rnvp_exp      = 3.0_r8      ! exponent of dryness function    [-]
  real(r8) :: rnvp_ice      = 1500.0_r8   ! resistance when frozen          [s m-1]

  ! Hydraulic properties (Mualem-van Genuchten); consumed by
  ! NVPWaterRetentionCurve / NVPHydraulicConductivity
  real(r8) :: ksat_nvp      = 1.0e-4_r8   ! saturated hydraulic conductivity [m s-1]
  real(r8) :: n_van_nvp     = 1.5_r8      ! van Genuchten shape parameter n  [-]
  real(r8) :: alpha_van_nvp = 0.01_r8     ! van Genuchten alpha              [cm-1]
  real(r8) :: watsat_nvp    = 0.85_r8     ! porosity                         [m3 m-3]
  real(r8) :: watres_nvp    = 0.05_r8     ! residual water content           [m3 m-3]

  ! Thermal properties of the dry NVP matrix (Farouki-style mixing)
  real(r8) :: thk_dry_nvp   = 0.05_r8     ! dry NVP thermal conductivity     [W m-1 K-1]
  real(r8) :: csol_nvp      = 0.58e6_r8   ! dry NVP volumetric heat capacity [J m-3 K-1]

  ! Stub-only: prescribed here, FATES-driven in the ctsm5.4.028_nvp merge
  real(r8) :: dz_nvp                    = 0._r8    ! prescribed thickness (m); 0 = moss absent
  real(r8) :: frac_nvp                  = 0._r8    ! prescribed areal coverage        [0-1]
  real(r8) :: nvp_transmissivity        = 1._r8    ! SW fraction transmitted to soil  [0-1]
  real(r8) :: alb_nvp_vis               = 0.10_r8  ! NVP albedo, visible              [-]
  real(r8) :: alb_nvp_nir               = 0.25_r8  ! NVP albedo, near-infrared        [-]
  real(r8) :: nvp_coldstart_saturation  = 0.5_r8   ! cold-start pore saturation       [0-1]

end module NVPParamsMod
