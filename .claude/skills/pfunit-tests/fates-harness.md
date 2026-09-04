# The FATES unit test harness

Companion to `SKILL.md`, which holds everything shared with the CTSM harness —
the rebuild trap, the compiler flags and their consequences, and the pFUnit
authoring limits. Read that first; this file is only what is specific to FATES.

FATES's unit tests are pFUnit tests in `.pf` files under
`src/fates/testing/tests/unit/<name>_test/`, built and run by
`src/fates/testing/run_unit_tests.py`.

These are not the FATES *functional* tests, which are standalone Fortran drivers
and have their own skill, `fates-functional-tests`. Paths here are relative to
the CTSM repo root, except inside a code block whose commands run from
somewhere else.

## Running

```bash
conda activate fates_testing
cd src/fates/testing
./run_unit_tests.py              # everything in config/unit.cfg
./run_unit_tests.py -t great_circle
```

`--help` lists the flags; take that over any list written down elsewhere. Three
things it does not tell you, and one thing it gets wrong:

- The build directory it calls a default is at the FATES root, not under
  `testing/`: `src/fates/_build`. It is **shared with the functional tests**, so
  a unit test run builds the functional drivers too.
- **`-t` selects what runs, not what builds.** `build_tests()` is called once on
  the whole CMake tree before the run loop, so every registered test — unit and
  functional — is always built. A compile error in a test you are not running
  still fails your run.
- The `fates_testing` conda env is required (`run_unit_tests.py` imports
  `framework.utils.env_check` at module scope). **Activate it; never create or
  modify it.** If it is missing or an import fails, report that and stop.
- `-c/--clean` does not do what its help says, and does not fix the trap you
  will most want it for — next section.

## `--clean` does not clear a stale driver

The flag's help says it "Removes CMake cache and runs 'make clean'". There is no
`make clean` anywhere in `framework/builder.py`. `_clean_cmake_files` removes
`CMakeCache.txt`, `Macros.cmake`, `env_mach_specific.xml`, the **top-level**
`CMakeFiles/` and the `Depends*` files; the per-test object directories under
`_build/testing/` are untouched.

Confirmed by experiment: with a silently-dropped second `.pf` in place, a `-c`
run left the driver object's timestamp unchanged and the executable still
reported the old test count. Use `--clean` for what it does do — after a
`CMakeLists.txt` change or a compiler switch. For the stale driver, delete the
object.

## Build layout, and what counts as evidence

One test directory builds to `_build/testing/fates_<name>_utest/`:

```
<Suite>                                        the executable
<Suite>.inc                                    generated suite list
<Suite>_driver.F90                             pFUnit's driver
CMakeFiles/<Suite>.dir/<Suite>_driver.F90.o    the object that goes stale
```

`<Suite>` is the first argument to `add_pfunit_ctest`. It is CamelCase and is
not the directory name — `tests/unit/great_circle_test` builds
`_build/testing/fates_great_circle_utest/GreatCircle`.

So the evidence that a test ran, and the object to delete when it did not:

```bash
src/fates/_build/testing/fates_great_circle_utest/GreatCircle          # then read its (N tests) line
rm src/fates/_build/testing/fates_great_circle_utest/CMakeFiles/GreatCircle.dir/GreatCircle_driver.F90.o
```

**The runner's summary always says `out of 1`.** It invokes `ctest
--output-on-failure` inside one test directory at a time, so the count is the
number of `add_pfunit_ctest` entries in that directory, which is one:

```
1/1 Test #1: GreatCircle ......................   Passed    0.08 sec
100% tests passed, 0 tests failed out of 1
```

That line reads identically whether the directory holds seven tests or eight, so
it is never a check on your new test.

## Registration — all four, or the test silently won't run

1. the directory `tests/unit/<name>_test/`
2. its own `CMakeLists.txt`: `set(pfunit_sources ...)` and
   `add_pfunit_ctest(<Suite> TEST_SOURCES "${pfunit_sources}" LINK_LIBRARIES fates csm_share)`
3. `testing/CMakeLists.txt`: `add_subdirectory(tests/unit/<name>_test fates_<name>_utest)`,
   under the `## Unit tests` header, path relative to that file
4. `testing/config/unit.cfg`: a `[<name>]` section with `test_dir = fates_<name>_utest`

**`test_dir` is the binary-directory alias — the second argument of
`add_subdirectory` — not the source directory.** `fates_great_circle_utest`, not
`tests/unit/great_circle_test`.

Miss step 4 and the test compiles on every run and never executes: `-t all`
iterates the config file, so a CMake-registered test that is not in it is simply
absent from the list, and nothing warns. `-t <name>` for a name absent from the
config does fail, loudly, and before the build — so if you are unsure whether a
test is registered, ask for it by name rather than running everything.

## Writing a new one

Use the generator; it does all four registration steps.

```bash
cd src/fates/testing
./generate_empty_test.py unit --test-name great_circle
```

It derives every name from the one you give it, so give it the snake_case stem
without a `_test` suffix (a trailing `_test` is stripped if you add one):

| From `--test-name great_circle` | |
|---|---|
| source directory | `tests/unit/great_circle_test/` |
| `.pf` file and module | `test_GreatCircle.pf`, `module test_GreatCircle` |
| suite / executable | `GreatCircle` |
| binary dir and `test_dir` | `fates_great_circle_utest` |
| config section | `[great_circle]` |

`--test-sub-dir` nests the source directory further, the way the functional fire
tests are nested; the binary dir and `test_dir` stay flat either way. The
generator refuses to run if the directory already exists, so it is not a way to
regenerate one.

Then replace the template's `TemplateTest`. The template gives you a `@TestCase`
type with empty `setUp`/`tearDown` and `tol = 1.e-13_r8`; delete the fixture
procedures rather than leaving them empty if the test needs no fixture, as
`great_circle_test` does.

CMake does not pick up new `.F90` files. Adding a module to the FATES library
means adding it to the `fates_sources` list in the `CMakeLists.txt` of its own
source subdirectory — there is one in each.

## Fixtures

Unit tests link `fates csm_share`, and `tests/fortran_shr/` is compiled into the
`fates` library itself (`src/fates/CMakeLists.txt` adds it as `test_share`), so
everything the functional drivers share is reachable from a `.pf` too. That
inventory is in the `fates-functional-tests` skill; use it rather than writing
new setup code.

Two things the unit tests actually use today:

- `FatesFactoryMod::CreateTestPatchList(patch, heights [, dbhs])` — a patch with
  a hard-coded cohort linked list, built without allometry or a globals init.
  This is what the four cohort-list test directories are built on.
- `FatesUnitTestUtils::endrun_msg(msg)` — see **Testing an `endrun` path** below.

`FatesFactoryMod` declares `public :: GetSyntheticPatch` and
`public :: InitializeGlobals` and nothing else, but it has no default `private`
statement, so **every routine in it is public**. Do not read that list as a
restriction; `CreateTestPatchList` is not in it and four test directories call
it.

**No parameter file reaches a unit test.** `UnitTest.run` accepts `param_file`
to match the base class and ignores it, and nothing on the ctest command line
supplies one — unlike a functional driver, which takes it as `argv(1)`. A unit
test that needs FATES parameters has to get them some other way: a `ForTesting`
entry point on the module that owns them (below), or reading a file itself in
`setUp` via `FatesUnitTestParamReaderMod`, with a path it chooses. No current
test does the latter.

## Testing entry points

FATES has one today: `SFParamsMod::SpitFireParamsInitForTesting`, used by
`fire_fuel_test`. Read its header comment before adding another — it is the
worked argument for why a test takes protected parameters as arguments rather
than through `ReadParameters`, and it says what may and may not be widened.

`SKILL.md` warns that setting a module's controls is not the same as
initialising it, and that an init routine which allocates without a guard aborts
on a second call. **`FatesFactoryMod::InitializeGlobals` is exactly that
routine.** It allocates `element_list`, `prt_global_ac` (via
`InitPRTGlobalAllometricCarbon`), `ema_24hr`, `fixed_24hr`, `ema_lpa` and
`ema_longterm` with no guard on any of them, so calling it a second time dies
with

```
forrtl: severe (151): allocatable array is already allocated
```

on `element_list`, taking the whole binary down rather than failing one test.

Only what it needs: anything going through the cohort or patch factory, PARTEH,
or the leaf-layer VAI bins. `CreateTestPatchList` and direct allometry calls do
not need it.

**It can still go in `setUp`, if you undo it first.** Every one of those six is
public — `element_list` in `PRTGenericMod` and `prt_global_ac` in
`PRTAllometricCarbonMod` are allocatables, the four running means are pointers
in `FatesRunningMeanMod` — and `rmean_def_type` and the `state_descriptor`
component are plain enough that a bare `deallocate` is complete. A `setUp` that
deallocates all six and then calls `InitializeGlobals` runs correctly across a
multi-test suite.

The one wrinkle: those module pointers are declared without `=> null()`, so
their association status is undefined until something allocates them, and an
`if (associated(ema_24hr))` guard on the first pass through `setUp` is reading
undefined state. Gate the teardown on a `logical, save` in your test module —
which you need anyway to know whether there is something to undo — rather than
on `associated()`.

If you find yourself writing that teardown, consider instead adding the guards
to `InitializeGlobals`. It lives in `tests/fortran_shr/`, so it is test-support
code and making it idempotent is a fix rather than a workaround.

## `fates_unset_r8` is a sentinel, not a NaN

FATES's own init paths use both conventions, and only one of them is protective.
`shr_infnan_mod`'s signalling NaN — used in `FatesInterfaceTypesMod`,
`EDParamsMod`, `FatesRunningMeanMod` and a dozen others — is what `-fpe0` traps.
`fates_unset_r8` is `-1.e36_r8`, a plain number: arithmetic on it produces
plausible-looking garbage or an overflow, not an abort, and comparisons against
it succeed. Prefill a hand-allocated test array with `nan`, not with
`fates_unset_r8`, however much the surrounding FATES code uses the latter.

## Testing an `endrun` path

The `csm_share` library these tests link is built with
`share/unit_test_stubs/util/shr_abort_mod.abortthrows.F90` in place of the real
`shr_abort_mod`, so `shr_abort_abort` calls pFUnit's `throw` instead of exiting.
Two consequences: an `endrun` is assertable, and an *unexpected* `endrun` fails
the test it happened in rather than killing the executable.

`endrun_msg` builds the string that gets thrown:

```fortran
character(len=:), allocatable :: expected_msg

expected_msg = endrun_msg("one of shortest or tallest is null")

call patch%ValidateCohorts()      ! should abort
@assertExceptionRaised(expected_msg)
```

`endrun_msg` only prefixes `ABORTED: `, so its argument has to match the
`endrun` call's message exactly; rewording the message in the source breaks the
test. Worked examples: `validate_cohorts_test`.

## Local convention: assert argument order is reversed

pFUnit's signature is `assertEqual(expected, actual)`, and it labels its failure
output accordingly:

```
AssertEqual failure:
      Expected: <.000000000000000>
        Actual: <1.500000000000000>
    Difference: <1.500000000000000> (greater than tolerance of .9999999747378752E-05)
  Location: [test_GreatCircle.pf:30]
```

Most existing FATES unit tests write the arguments the other way round — roughly
three to one — as in

```fortran
@assertEqual(this%fireWeatherNesterov%fire_weather_index, 0.0_r8, tolerance=tol)
```

so the `Expected:` and `Actual:` lines come out swapped. Write new asserts in
pFUnit's order, and when reading a failure in an existing FATES test, check
which way round that file does it before believing the labels. The `Location:`
line does point at the `.pf`, not at the generated `.F90`.
