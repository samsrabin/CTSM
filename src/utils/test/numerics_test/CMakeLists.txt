set (pfunit_sources
  test_truncate_small_values.pf)

add_pfunit_ctest(numerics
  TEST_SOURCES "${pfunit_sources}"
  LINK_LIBRARIES clm csm_share esmf)
