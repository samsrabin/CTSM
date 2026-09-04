---
name: pfunit-tests
description: Use when writing, building, running, or debugging a Fortran unit test in either pFUnit harness in this tree - the CTSM .pf files under src/*/test/ that run_tests.py builds into unit_tests.temp, or the FATES .pf files under src/fates/testing/tests/unit/ that run_unit_tests.py builds into src/fates/_build - or when a test build reports "Unrecognized token '@' skipped" or "Global name too long", or when a green run leaves you unsure whether your new or renamed test actually ran.
---

# pFUnit unit tests

This tree has **two** pFUnit harnesses. They share a framework, a compiler
configuration and a set of traps; they share nothing operational. This file is
what is true of both. Read it, then read the companion for the harness you are
working in — the run command, the build layout, the registration steps, the
fixtures and the evidence recipe are all in there, and they do not transfer.

| Your `.pf` lives in | Harness | Read next |
|---|---|---|
| `src/<area>/test/<Name>_test/` | `cime/scripts/fortran_unit_testing/run_tests.py` | **`ctsm-harness.md`** |
| `src/fates/testing/tests/unit/<name>_test/` | `src/fates/testing/run_unit_tests.py` | **`fates-harness.md`** |

FATES *functional* tests are a third thing — standalone Fortran drivers, not
pFUnit — and have their own skill, `fates-functional-tests`.

Both harnesses resolve `PFUNIT_PATH` from the same CIME machine macros, so on
Derecho both are pFUnit 4.8.0 out of
`/glade/campaign/cesm/cesmdata/tools/pFUnit/`, and both configure
`CMAKE_BUILD_TYPE=CESM_DEBUG` against the same `Macros.cmake` — FATES always,
CTSM unless you ask for an optimized build. Everything below follows from that
and holds in either harness.

## Symptom → cause → fix

| Symptom | Cause | Fix |
|---|---|---|
| `error #5078: Unrecognized token '@' skipped`, then `#5082` on the same line | An `@assert` is split across lines with `&`, or carries a trailing comment | Put the whole `@assert` on one line; move the comment above it |
| Build is green and reports every test passing, but your new test never ran | You added a `.pf` **file** to an existing test directory; the driver object is stale | Delete the stale driver object — see below, and your harness companion for its path |
| `undefined reference to <module>_suite_` at link time | You *removed* a `.pf` from an existing test directory; same stale driver object | Same |
| `warning #5462: Global name too long, shortened from:` | `<module>_mp_<PROCEDURE>` exceeds 90 characters | Shorten the module name or the test name |
| `forrtl: error (65): floating invalid`, with no assertion reported | `-fpe0` trapped arithmetic on a signalling NaN — often a fixture component nothing ever set | Treat the abort as the failure and find the unset value; it is not a crash to debug |
| `forrtl: error (73): floating divide by zero` | `-fpe0` trapped a division a fixture left with a zero divisor | Same — the abort *is* the result, so read it as one |
| A compiler warning you expected is nowhere in the build log | Both runners print compiler output only when the build fails | Run `make` yourself in the build directory |

## The incremental rebuild will lie to you

The dangerous case is a **green run that proves nothing**. Both runners reuse
their build directory, and a `.pf` file you have just added to an existing test
directory is compiled, linked, and then never called. The run exits 0 and
reports 100% of tests passing. Your tests did not run.

Only the generated driver goes stale. pFUnit's driver does `#include
_TEST_SUITES` (`<PFUNIT_PATH>/PFUNIT-*/include/driver.F90`), and nothing tracks
the generated `<Suite>.inc` as a dependency of `<Suite>_driver.F90` — so the
`.inc` is regenerated and does list your new suite, while the object that would
call it is not rebuilt. You can see both halves of that in the build tree: the
`.inc` names `test_<YourModule>_suite`, and the driver `.o` still carries its
old timestamp.

| Change to an existing, populated build directory | Result |
|---|---|
| New `@Test` subroutine in an existing `.pf` | Picked up |
| **Renaming** a `@Test` subroutine in an existing `.pf` | Picked up |
| New `.pf` file in an **existing** test directory, even added to `CMakeLists.txt` | **Silently dropped** |
| Removing a `.pf` from an existing test directory | **Link failure** |
| New test **directory** with its own `add_pfunit_ctest` | Picked up |

A new directory is safe because it has no stale driver yet. A rename is safe
because it changes neither the suite list nor the suite's name — only the
generated `.F90` the driver already calls. Editing `CMakeLists.txt` does not
rescue you, and in the FATES harness neither does the runner's `--clean` flag.

Every row is confirmed by experiment in the FATES harness, and the rename row in
both. The fix is a full rebuild, but deleting the one stale driver object is
enough and is what the companions give you the path for.

### Two things that are not evidence

**The reported test count counts executables, not tests.** The `out of N` in
ctest's summary is the number of ctest entries — one per `add_pfunit_ctest`,
i.e. one per test directory. It cannot move when you add a test, or a whole
file, to a directory that already exists, so watching it is not a check.

**A green build prints nothing.** Both runners capture cmake and make output and
show it only on failure, so silence tells you nothing about warnings or about
what compiled.

### What is evidence

Run the test directory's own executable and read its `(N tests)` line; add `-v`
to list the individual test names. Check that the count moved by the number of
tests you added. Your harness companion has the path to that executable. If
something fails, ctest dumps the executable's verbose output and a `Tests run:
N, Failures: N, Errors: N` line — but only then.

## What the test build actually does

Both harnesses build `CESM_DEBUG`. The Fortran flags on Derecho with Intel are
byte-identical between them, in this order:

```
-O0 -no-fma -g -check uninit -check bounds -check pointers -fpe0
-check noarg_temp_created -qno-opt-dynamic-align -convert big_endian
-assume byterecl -ftz -traceback -assume realloc_lhs -fp-model source
-qopt-report -march=core-avx2 -check nouninit
```

Four consequences worth knowing before you write a fixture:

- **Uninitialized-variable checking is off**, despite `-check uninit` appearing in the
  list. `-check nouninit` comes *later* and last wins. It is appended by
  `ccs_config/machines/<machine>/intel_<machine>.cmake`, whose comment explains why. It
  cannot simply be turned back on: `ifx` implements `-check uninit` as MemorySanitizer
  instrumentation, and with `nouninit` removed the binary aborts inside glibc startup
  before any of your code runs — a backtrace through glibc, not a finding about your test.
  Re-check the flag order in a built `flags.make` when the machine files change.
- **`NDEBUG` is not defined**, so `#ifndef NDEBUG` blocks are live and count as coverage.
- **`-fpe0` turns a bad value into an abort, not a NaN.** Arithmetic on a signalling NaN
  stops the binary with `forrtl: error (65): floating invalid`, and a zero divisor with
  `error (73): floating divide by zero`. What traps is the *arithmetic*, not the read: a
  plain copy of a signalling NaN is silent, so a bad value can travel some way from the
  fixture that made it before the abort names a line. Either way, a fixture that leaves a
  divisor at zero does not produce a NaN result you can assert on.
- **`-check bounds` turns a broken index into an abort** rather than a failed assertion.

There are no `-warn` options at all.

## pFUnit authoring limits

The preprocessor rewrites `@` lines it can parse whole, and silently passes through the
ones it cannot. It reports success either way — `... Done.  Results in <name>.F90` — and
the compiler is what fails, so the error arrives one step removed from its cause.

**An `@assert` cannot be continued with `&`.**

```fortran
! Rejected
@assertEqual(expected_value(c), &
     actual_value(c), tolerance=tol)

! Fine - pull the operand into a local so the assert fits on one line
expected = expected_value(c)
@assertEqual(expected, actual_value(c), tolerance=tol)
```

**An `@assert` cannot carry a trailing comment.** Put the comment on the line above:

```fortran
! Rejected
@assertEqual(0._r8, h2osoi_liq(c))  ! the layer should be dry

! Fine
! The layer should be dry
@assertEqual(0._r8, h2osoi_liq(c))
```

Either mistake produces `error #5078: Unrecognized token '@' skipped` with a caret under
the `@`, then `error #5082: Syntax error, found '='`. The `.pf` is named through a doubled
path — the test's build directory, then the absolute path of the file. Everything after
the first two errors per file is cascade. Fix the first `#5078` and ignore the rest.

Use `message="..."` inside the assert when you want the explanation to appear in the
failure output rather than only in the source.

### Not every assert exists at every rank

In 4.8, `assertIsNaN` and `assertIsFinite` are **scalar only** — check an array element by
element, or assert on a reduction of it. The comparison asserts (`assertEqual`,
`assertLessThan`, `assertGreaterThan` and friends) exist for equal ranks, `(Nd, Nd)` up to
5d, and for a scalar against any rank, `(0d, Nd)` — but there is no `(1d, 0d)` form of any
assert, so a scalar has to be the expected value, on the left:

```fortran
! No specific procedure - a rank-1 expected against a scalar actual
@assertLessThan(bounds_array, upper_limit)

! Fine
@assertGreaterThan(upper_limit, bounds_array)
```

### Keep names under the symbol limit

`ifx` shortens any global name over 90 characters and warns
`#5462: Global name too long`. The symbol is `<module>_mp_<PROCEDURE>`, so your budget is
`len(module name) + 4 + len(test subroutine name) <= 90`, and truncation is from the
front. No test in either harness currently exceeds the limit, but the longest are in the
high 80s, so the margin is a few characters, not tens. The warning never appears in a
green build log.

## Writing a fixture

These four hold in either harness. The concrete symbols, the ready-made
fixtures, and each codebase's own testing entry points are in the companions.

**Module state outlives a test.** A module variable set by one test is still set for the
next test in the same executable. Set what you depend on in `setUp` rather than inheriting
whatever the previous test left behind.

**Look for a testing entry point before writing to module state directly.** Both
codebases have routines that exist only to let a test set state the model
protects — the naming convention is a `ForTesting` suffix, but nothing else about
the names is consistent, so grep the module for `ForTesting` rather than guessing
at one. Your companion lists what each codebase has.

**Setting a module's controls is not the same as initialising it.** A testing entry point
may set control variables without allocating the module's arrays, which the module's real
init routine does. If you skip that init, the arrays stay unallocated and the module's
matching cleanup routine fails trying to deallocate them. Check what actually allocates
the state you depend on — and check whether calling it twice is safe, because an init
routine that allocates without an `allocated()` guard aborts the executable the second
time rather than failing one test.

**A hand-allocated array must be nullified, then prefilled with a signalling
NaN.** Allocate only the components the routine under test actually touches:

```fortran
! in setUp - the pointer's association status is undefined until you do this,
! which makes an associated() guard in tearDown meaningless
nullify(this%some_inst%some_array)

! where you allocate it
allocate(this%some_inst%some_array(<bounds>))
this%some_inst%some_array(:,:) = nan

! in tearDown
if (associated(this%some_inst%some_array)) then
   deallocate(this%some_inst%some_array)
end if
```

with `use shr_infnan_mod, only : nan => shr_infnan_nan, assignment(=)`. That is
the shape for a **pointer** component; an allocatable needs neither the
`nullify` nor the guard, because `allocated()` is defined from the start.

**The `nan` prefill is the part people drop, and it is the part that matters.**
Uninitialized checking is off and cannot be turned on, so the only thing protecting you
is that both codebases' own init paths fill arrays with a *signalling* NaN, which `-fpe0`
traps as soon as anything computes with it. A bare `allocate` opts out of that, and then
fails **open**: fresh heap pages read as exactly `0.0`, so `@assertEqual(0._r8, ...)`
against a component nobody ever wrote will pass and tell you nothing. A sentinel value is
not a substitute — only a signalling NaN traps.

## Running one test over several inputs

When the same behaviour has to hold across several values of a module-level configuration
variable, use pFUnit's parameterized test case rather than a loop inside one test body or
three copy-pasted subroutines. Neither harness has an example of it, so the complete
pattern, the two pitfalls, and what the output looks like are in
**`parameterized-tests.md`** next to this file.
