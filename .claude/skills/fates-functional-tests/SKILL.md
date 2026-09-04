---
name: fates-functional-tests
description: Use when running the FATES standalone functional tests with src/fates/testing/run_functional_tests.py, when adding or modifying a functional test driver under src/fates/testing/tests/functional/, or when a newly added test builds but never runs.
---

# FATES functional tests

A FATES functional test is a standalone Fortran driver under
`src/fates/testing/tests/functional/<name>/`, built against the FATES library,
run outside any host land model, and plotted by a Python class in the same
directory. `src/fates/testing/run_functional_tests.py` does all three in one
step.

All paths here are relative to the CTSM repo root, except inside a code block
whose commands run from somewhere else.

These are not the pFUnit unit tests, which live in
`src/fates/testing/tests/unit/` and run the same way via `./run_unit_tests.py`
from the same directory.

## Running

```bash
conda activate fates_testing
cd src/fates/testing
./run_functional_tests.py -t <name>
```

That builds every test registered in `src/fates/testing/config/functional.cfg`
— or just the named ones, comma-separated — runs each with the default parameter
file, and shows the figures interactively. `./run_functional_tests.py --help`
lists the flags; take that over any list written down elsewhere.

Three things `--help` does not tell you:

- The paths it calls defaults are all at the FATES root, not under `testing/`:
  the build dir is `src/fates/_build`, the run dir `src/fates/_run`, figures go
  to `src/fates/_run/plots/<test>/`, and the default parameter file is
  `src/fates/parameter_files/fates_params_default.json`.
- `--save-figs` writes the PNGs but does **not** make the run non-interactive.
  `plt.show()` is called unconditionally at the end of `run_functional_tests.py`
  and no plotter closes its figures, so on a machine with a display the windows
  still open and the script still waits. Set `MPLBACKEND=Agg` if the run has to
  be unattended; headless, the backend already makes `plt.show()` a no-op.
- `-c/--clean` is needed after touching any `CMakeLists.txt` or switching
  compilers, not just when a build looks broken.

### The conda environment

The `src/fates/testing/*.py` scripts need the `fates_testing` env, which
`src/fates/testing/environment.yml` defines. **Activate it; never create or
modify it.** If it is missing or an import fails, report that and stop rather
than working around it. Building it is

```bash
conda env create --file=src/fates/testing/environment.yml
```

which is a command for a human to run, not for an agent to run.

## Reuse inventory — check here BEFORE writing driver code

Every standalone driver shares `src/fates/testing/tests/fortran_shr/`. Before
writing anything, find which of these already does the job. If a routine is close
but signature-bound to a derived type you don't have, **widen the signature and
update the existing callers** — do not reimplement. Whether a routine is really
coupled to a derived type is a question about its body, not its argument list:
list the fields it actually touches before concluding you cannot use it.

| Need | Use | Notes |
|---|---|---|
| Read parameter file | `FatesUnitTestParamReaderMod::ReadParameters` | |
| Command-line args | `FatesArgumentUtils::command_line_arg(n)` | positional; guard with `command_argument_count()` |
| netCDF output | `FatesUnitTestIOMod` | `OpenNCFile`/`RegisterNCDims`/`RegisterVar`/`RegisterFillValue`/`EndNCDef`/`WriteVar`/`CloseNCFile` |
| Build a cohort | `FatesFactoryMod::CohortFactory` | only if you actually need allometry |
| Build a patch | `FatesFactoryMod::PatchFactory`, `GetSyntheticPatch` | `GetSyntheticPatch(patch_data, num_levsoil, patch)` turns one synthetic patch description into a patch with its cohorts |
| Ready-made stands | `SyntheticPatchTypes::synthetic_patch_array_type` | `GetSyntheticPatchData` loads the hard-coded stands the module defines, each a cohort list of age/dbh/density/pft/canopy layer. `PatchDataPosition(patch_id=)` or `(patch_name=)` finds one; supplying both aborts |

The fire tests keep a second shared layer of their own in
`src/fates/testing/tests/functional/fire/shr/` — `FatesTestFireMod` and
`SyntheticFuelModels`. Check there too before writing anything fire-related.

## Driver setup

Only one step is universal. Every driver takes the parameter file off the command
line and reads it:

```fortran
param_file = command_line_arg(1)
call ReadParameters(param_file)
```

`ReadParameters` handles the derived-parameter work itself — a `TransferParams*`
call per parameter group, then `param_derived%Init` — so a driver does not repeat
any of it.

A driver that sizes arrays per PFT reads the count off the parameters it just
loaded:

```fortran
numpft = size(prt_params%wood_density, dim=1)
```

`FatesFactoryMod::InitializeGlobals(step_size)` is needed only by drivers that go
through the cohort or patch factory, PARTEH, or the leaf-layer VAI bins. It sets
`hlm_parteh_mode` and the element list, allocates the EMA accumulators, and fills
`dinc_vai`/`dlower_vai`. Of the tests in the tree only `patch` calls it;
`allometry` calls `h_allom` and `bagw_allom` with no globals init at all. Call it
if you touch any of that state, and don't if you are calling an allometry or leaf
function directly.

## Registration — all four, or the test silently won't run

1. `src/fates/testing/CMakeLists.txt` — `add_subdirectory(tests/functional/<name> fates_<name>_ftest)`, whose path is relative to that file
2. the test's own `CMakeLists.txt` (`add_executable`, `target_link_libraries`)
3. `src/fates/testing/config/functional.cfg` — an `out_file` entry has to be there, though it may be `None` for a test that writes no netCDF
4. a Python class in the test directory whose `name` attribute matches the
   config section name

CMake does not pick up new `.F90` files automatically. A build that fails right
after you add one is usually that file missing from the relevant `fates_sources`
list — in the shared `CMakeLists.txt` or in the test's own.

## Reading a driver's netCDF output

Output arrays come back with **dimensions reversed** relative to the Fortran
declaration: a Fortran `(nlevleaf, n_lai)` variable reads as `(lai, layer)`.
Index with named dims, never positionally:

```python
arr.isel(lai=i, layer=slice(0, nv))     # not arr.values[i, :nv]
```

Getting this wrong yields plausible-looking wrong numbers that mimic a physics
bug — a prescribed LAI of 3 "recovering" as 1.75, for instance. Suspect an axis
swap in the plotting code before you go looking for the problem in the Fortran.
