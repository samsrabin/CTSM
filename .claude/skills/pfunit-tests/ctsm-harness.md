# The CTSM unit test harness

Companion to `SKILL.md`, which holds everything shared with the FATES harness —
the rebuild trap, the compiler flags and their consequences, and the pFUnit
authoring limits. Read that first; this file is only what is specific to CTSM.

CTSM's unit tests are pFUnit tests in `.pf` files under
`src/<area>/test/<Name>_test/`, built and run by `run_tests.py`.

## Start here

For the basics, read these rather than re-deriving them — everything else here
is what they do not say.

- `src/README.unit_testing` — the command that runs the whole suite.
- `cime/scripts/fortran_unit_testing/README` — how the framework fits together.
- `doc/design/pfunit_testing.rst` — error handling and ESMF initialization in tests.

## Build layout

`run_tests.py` reuses `unit_tests.temp`. `--build-optimized` selects `CESM`
instead of the default `CESM_DEBUG`.

The executable for one test directory, whose `(N tests)` line is the only real
evidence a test ran:

```
unit_tests.temp/__command_line_test__/__command_line_test__/<lib>_test/<Dir>_test/<Name>
```

The stale driver object to delete when a new `.pf` in an existing directory is
being silently dropped, if you would rather not `rm -rf unit_tests.temp`:

```
unit_tests.temp/__command_line_test__/__command_line_test__/<lib>_test/<Dir>_test/CMakeFiles/<Name>.dir/<Name>_driver.F90.o
```

## Fixtures CTSM already provides

In `src/unit_test_shr/`:

| Module | What it gives you |
|---|---|
| `unittestSubgridMod` | `unittest_subgrid_setup_start` / `_setup_end` / `_teardown`, and `unittest_add_gridcell` / `_landunit` / `_column` / `_patch` for building a subgrid by hand |
| `unittestSimpleSubgridSetupsMod` | Ready-made subgrids: `setup_single_veg_patch`, `setup_n_veg_patches`, `setup_ncells_single_veg_patch`, `setup_landunit_ncols` |
| `unittestFilterBuilderMod` | `filter_from_range`, and `filter_empty` for the no-points case |
| `unittestWaterTypeFactory` | A complete `water_type`, without hand-rolling one. Its calls have a required order and one hidden side effect — see **`water-type-factory.md`** next to this file |
| `unittestArrayMod` | `grc_array` / `col_array` / `patch_array`, which build a subgrid-level 1-D array for you: called with no argument each returns an `r8` array prefilled with NaN, called with a value an array of that value's type filled with it. Also `logical_array_to_int` |
| `unittestTimeManagerMod` | `unittest_timemgr_setup`, `_set_curr_date`, `_set_nstep`, `_teardown` |

Worked examples, by file: `test_filter_col.pf` for filters and a simple subgrid,
`test_partition_precip.pf` for `setup_ncells_single_veg_patch`.

### Types with no factory

`SKILL.md`'s **Writing a fixture** has the nullify / allocate / NaN-prefill /
guarded-deallocate pattern; a CTSM instance of it is

```fortran
nullify(this%temperature_inst%t_soisno_col)
allocate(this%temperature_inst%t_soisno_col(bounds%begc:bounds%endc, -nlevsno+1:nlevgrnd))
this%temperature_inst%t_soisno_col(:,:) = nan
```

For a plain 1-D subgrid-level array, `col_array()` and its siblings above
already do all of it for you.

For the allocate/deallocate pair alone, `test_init_columns.pf` is the plainest example.
`test_dyn_cons_biogeophys.pf` guards every deallocation with `associated()` — which is
exactly the case the `nullify` exists to make meaningful.

## Testing entry points

CTSM has many, and the naming is not consistent beyond the `ForTesting` suffix —
`InitForTesting`, `SetNMLForTesting`, `setParamsForTesting` and
`SnowHydrologySetControlForTesting` all exist. Grep the module rather than
guessing at a name, and see `SKILL.md` for why setting a module's controls is
not the same as initialising it.
