set (pfunit_sources
  test_WaterState_CalculateTotalH2osno.pf)

add_pfunit_ctest(WaterState
  TEST_SOURCES "${pfunit_sources}"
  LINK_LIBRARIES clm csm_share esmf
  EXTRA_FINALIZE unittest_finalize_esmf
  EXTRA_USE unittestInitializeAndFinalize)
