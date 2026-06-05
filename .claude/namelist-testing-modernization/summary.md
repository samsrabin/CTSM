# `build-namelist_test.pl`: how it works today

> Scope: an as-is reading of `bld/unit_testers/build-namelist_test.pl` and the
> code it directly touches, written to support a later pytest-based rewrite.
> Dependencies are name-dropped rather than fully decomposed.

## 1. What's being tested

The script under test is **`bld/build-namelist`** — a 23-line thin Perl
wrapper that just dispatches to `CLMBuildNamelist::main()` in
`bld/CLMBuildNamelist.pm` (~6,150 lines). `build-namelist` takes a long list
of command-line options plus an input "namelist" (Fortran-style `&group ... /`)
and emits a real CTSM run namelist (`lnd_in`) — sometimes also `drv_flds_in`
— consuming the XML defaults/definition files under `bld/namelist_files/`
and `bld/config_files/`.

`build-namelist_test.pl` runs that tool as a black-box subprocess hundreds of
times with different option combinations, asserting various properties of the
exit code, the produced files, and (optionally) the produced file contents
against a baseline.

## 2. Entry point, invocation, and CLI

- File: `bld/unit_testers/build-namelist_test.pl` (~2,150 lines, single file).
- Documented usage (see `doc/source/users_guide/testing/testing.rst`):
  ```
  cd bld/unit_testers
  ./build-namelist_test.pl 1>namelist_test.log 2>&1
  ```
  Success is "saw `Successfully ran all testing for build-namelist` and did
  not see `# Looks like you failed N tests of M`."
- The script's own options:
  - `-h` / `-help`
  - `-csmdata <dir>` — root of CESM inputdata. Defaults to `$CSMDATA` env var,
    else hard-coded Yellowstone path
    `/glade/campaign/cesm/cesmdata/cseg/inputdata` (still works on Derecho via
    GLADE).
  - `-no-test` — drop the `-test` flag normally passed to build-namelist (the
    dataset-existence check). Useful when you do not have inputdata staged.
  - `-generate` — after each test, copy the produced `lnd_in` / `drv_flds_in`
    out as a baseline snapshot tagged by (mode, options-string).
  - `-compare <dir>` — diff produced namelists against snapshots in `<dir>`.
    If both `-generate` and `-compare` are passed, `-compare` wins.

## 3. Testing framework in use

- Assertions: **`Test::More`** (`is`, `isnt`, `ok`, `like`, `fail`).
- The expected test count is **hard-coded**: `plan(tests => 3407)`, plus
  `+2061` when `-compare` is given. Test::More dies at the end if the actual
  count drifts from `plan`. This is the single largest maintenance burden the
  current script imposes.
- Test::More output is redirected into an in-memory string buffer:
  `Test::More->builder->output(\$captOut);`. The buffer is post-processed at
  the very end by the xFail module (see §5.2) so each result is re-emitted as
  `NNN/NNN <PASS|FAIL|xFAIL> <Test Id: N> <Desc: ...>`.

## 4. Per-iteration scaffolding

Each test iteration follows a common dance, implemented as Perl helper subs at
the top of the script:

- **`make_env_run(%settings)`** writes a fake CIME `env_run.xml` in the cwd
  containing the seven xml vars `build-namelist` actually reads: `DIN_LOC_ROOT`,
  `GLC_TWO_WAY_COUPLING`, `LND_SETS_DUST_EMIS_DRV_FLDS`, `NEONSITE`,
  `PLUMBER2SITE`, `CLM_CMIP_ERA`, `CLM_NDEP_FROM_CPL`. Test cases override
  individual values via keyword args.
- **`make_config_cache($phys)`** writes a minimal `config_cache.xml` declaring
  the CTSM physics tag (`clm4_5` / `clm5_0` / `clm6_0`). Many test loops change
  physics partway through and re-call this.
- **`cat_and_create_namelistinfile($file1, $file2, $outfile)`** concatenates
  two `user_nl_clm`-style files (typically a NEON/PLUMBER2 default + a
  site-specific override) into a single `&clm_settings ... /` group for
  `-infile`.
- **`cleanup($type)`** removes `temp_file.txt` and `*_in` files between
  iterations; with `$type eq "config"` also removes `config_cache.xml`.

Every test then runs:
```perl
eval { system( "$bldnml $options > $tempfile 2>&1" ); };
is( $@, '', "options: $options" );          # or isnt(...) for failure tests
$cfiles->checkfilesexist( ..., $mode );
# optional shownmldiff / comparefiles / copyfiles, depending on -generate/-compare
&cleanup();
```
where `$bldnml` is the prebuilt command line
```
../build-namelist -verbose -csmdata <root> -configuration clm
                  -structure standard -glc_nec 10 -no-note [-test]
```

## 5. Helper Perl modules (in `bld/unit_testers/`)

### 5.1 `NMLTest::CompFiles` (`NMLTest/CompFiles.pm`)

An object that bundles a directory + a list of files-to-check (typically
`lnd_in`, `drv_flds_in`, `temp_file.txt`) and exposes:
- `checkfilesexist(type, mode)` — asserts each file exists; if it does, also
  marks it for diffing.
- `copyfiles(type, mode)` — copies each file to a tagged name like
  `lnd_in.<mode>.<type>` (slashes/spaces/quotes in the tag get squashed to `+`),
  used both as in-run snapshots and as `-generate` baselines.
- `comparefiles(type, mode, [compdir])` — `diff`s each file against the
  matching tagged file (in cwd or in `compdir` for `-compare`), then emits an
  `ok(...)` whose polarity comes from a per-(mode, type, file) "should they
  match?" flag.
- `dodiffonfile` / `doNOTdodiffonfile` — set that flag.
- `shownmldiff(type, mode)` — prints a diff to stdout for humans.

This is essentially a tiny golden-file harness welded onto Test::More.

### 5.2 `xFail::expectedFail` (`xFail/expectedFail.pm`)

Post-processes the captured Test::More output to recognize "expected
failures". The intent (per the module's POD) is the standard
mark-known-failures workflow: run the suite, classify failing tests as
xFAIL via an external file, flag any xFAIL test that now passes so the
ChangeLog can record the recovery.

**The capability is intentional and worth preserving, but the current
implementation is broken end-to-end on every machine CTSM is tested on
today.** Four stacked latent bugs:

1. **Machine map is stale.** `_getMachInfo` does
   `substr(\`uname -n\`, 0, 2)` and only recognizes `ys` → yellowstone
   (retired ~2017) and `fr` → frankfurt (also retired). On Derecho
   (`derecho6` → `de`) it returns `"unknown"`; Casper (`ca`) and Izumi
   (`iz`) likewise fall through.
2. **Compiler map is also stale.** `%compNames` hard-codes `INTEL` for the
   two recognized machines, so there's no story for Derecho-with-GNU or
   Izumi-with-NAG/PGI even after the machine map is fixed.
3. **No XML entries exist for current machines.** Even if `_getMachInfo`
   returned `("derecho", "INTEL")`, there's no `<derecho>` block in
   `xFail/expectedClmTestFails.xml` — the lookup would still find nothing.
4. **The XML entries that DO exist are empty.** `<yellowstone>` and
   `<goldbach>` have empty `<compare>` and `<generate>` lists, so even on
   the recognized machines nothing would be classified as xFAIL.

Net behavior today: `_readXml` sets `$self->{_foundList} = "FALSE"`,
`_searchExpectedFail` early-returns `"FALSE"` for every lookup, every real
failure prints as `FAIL`, and the parseOutput post-processing layer is
just a TAP-to-pretty-print pass-through. Whether known-failing-on-Derecho
tests exist *and are being silently re-failed every run* is impossible to
tell without fixing detection first.

Recent commits have actively pruned this code (`0c26697a6`, `8ef1ff4a3`,
`69dbee814`), so the intent is clearly to keep the capability, not
retire it.

Implication for the rewrite: don't drop the capability, replace it with
pytest-native machinery. `@pytest.mark.xfail(condition=…, reason=…,
strict=True)` provides both halves — skip known failures and flag any
xfail that starts passing — without the captOut/TAP-parsing layer. The
machine/compiler condition should come from `$CIME_MACHINE` / a CIME
machine-detection helper rather than hostname prefix-matching, which is
the root cause of the rot.

## 6. The actual test surface (in execution order)

Categories the script walks through, each with its own `print "===…==="`
header. Counts are approximate where the script generates them via nested
loops.

1. **Smoke** — `-help`, `-version`, plain run.
2. **List options** — `-clm_demand list`, `-ssp_rcp list`, `-res list`,
   `-sim_year list`, `-use_case list`; assert listing text matches a regex and
   no `lnd_in` was produced.
3. **Combined-options sanity** — `-co2_ppmv 250 -res 10x15 -ssp_rcp SSP2-4.5`
   with `CLM_CMIP_ERA=cmip6`.
4. **Drydep / MEGAN / fire_emis combinations** with `-bgc sp/bgc`. Also
   checks `drv_flds_in` is produced.
5. **Big ad-hoc options matrix** under the `nuopc` driver — configuration,
   structure, irrigate, verbose, ssp_rcp, sim_year, use_case, LAI/soil-moisture
   streams, excess-ice streams, matrixcn, MIMICS, accelerated_spinup, branch/
   startup IC, `-infile myuser_nl_clm`, `1x1pt_US-UMB`, `1x1_brazil`, etc.
   For the `-infile myuser_nl_clm` case, additionally `grep` `fsurdat` out of
   `lnd_in` and assert a regex.
6. **NEON sites** — 47 sites × {bgc, fates} (STER/KONA skip fates). Each
   site's `cime_config/usermods_dirs/clm/NEON/<SITE>/user_nl_clm` is
   concatenated onto `NEON/defaults/user_nl_clm` and fed via `-infile`.
   Driven by `--res CLM_USRDAT --clm_usr_name NEON --use_case 2018_control
   --no-megan`. Sets `NEONSITE` in env_run and `$ENV{NEONSITE}` for variable
   expansion.
7. **PLUMBER2 sites** — ~170 sites × {sp}. Same shape as NEON but
   `cime_config/usermods_dirs/clm/PLUMBER2/...`, `--clm_usr_name PLUMBER2`.
8. **CAM special grids** — clm4_5/clm5_0/clm6_0 × a list including refined
   `ne0np4.*`, `1.9x2.5`, `0.9x1.25`, `1x1_brazil`, `C96`. Most use
   `lnd_tuning_mode <phys>_cam7.0`.
9. **`CAM_SETS_DRV_FLDS` tests** — set `LND_SETS_DUST_EMIS_DRV_FLDS=FALSE`,
   use `--infile empty_user_nl_clm`, verify `drv_flds_in` handoff.
10. **clm5_0 use_case / specific configuration tests** — including
    `cmip6`-era SSPs, FATES SP, dust `Zender_2003 / Leung_2023`, fire
    `nofire`, noanthro use_case + drydep/fire_emis/megan/light_res, FATES
    spitfire modes.
11. **`%failtest` — hard failures** (~150 entries, each
    `name => {options, namelst, phys, [GLC_TWO_WAY_COUPLING, LND_SETS_DUST_EMIS_DRV_FLDS, CLM_CMIP_ERA, CLM_NDEP_FROM_CPL]}`).
    Expectation: `isnt($?, 0, $key)`. Touches a `thing.nc` IC file beforehand
    so a few finidat tests have something on disk. Catches inconsistencies
    like `-vichydro` + `use_vichydro=.false.`, FATES + CN, exice on without
    streams, branch without nrevsn, bedrock with bad lower boundary, MIMICS
    + soil matrix, etc.
12. **`%warntest` — warnings** (~12 entries). Each is run twice: once
    without `-ignore_warnings` (expected non-zero), once with it (expected
    zero). Tests CN-spinup + supl-N, FUN without flexibleCN, missing ndep
    files, bad megan specifier, `use_excess_ice` cold-start mis-config, etc.
13. **`%coldwfinidat` — cold start + finidat** (2 entries, bgc and fates).
    Each has an `expected_fail` flag. The fates one asserts `finidat` is
    correctly retained in `lnd_in`.
14. **All-physics outer loop** (`foreach my $phys ( clm4_5, clm5_0, clm6_0 )`)
    containing:
    - **SP coverage** at every resolution that has surface datasets × {1850,
      2000}, with a separate list `@only2000_resolutions` for the
      single-point grids.
    - **BGC 20thC_transient** for an "important resolutions" subset.
    - **Use-case × physics sweep at f09** — uses
      `$bldnml -use_case list` to discover use-cases, expects exactly 16
      (`$#usecases != 15 ⇒ die`). 6 use-cases are hard-coded as
      `@expect_fails` because they require `CLM_CMIP_ERA=cmip6`.
15. **`%finidat_files`** — 8 explicit cases (clm4_5/clm5_0 × {GSWP3v1, CRUv7,
    cam6.0} × {sp/bgc, crop}). Asserts that when `lnd_in`'s `finidat` path
    contains `initdata_map`, `use_init_interp=.true.` is set.
16. **Crop resolutions** — `1x1_smallvilleIA`, `1x1_cidadinhoBR`, plus a
    bigger crop-grid sweep.
17. **`glc_mec` resolutions** — `0.9x1.25`, `1.9x2.5` × {1850, 2000, 2010,
    20thC, SSP2-4.5}. (Comment in the source notes these may be obsolete now
    that glc_mec is always on.)
18. **Transient 20thC + `do_grossunrep=T`** across grids.
19. **SSP2-4.5 transient over many grids** with `CLM_CMIP_ERA=cmip6`.
20. **Per-physics resolution × `clmoptions` sweep** — bgc/sp/vichydro/dynveg/
    c-isotope/etc. variants × roughly 11 grids; plus an `ne16np4.pg3`-only
    pass; plus a FATES sweep at `4x5` / `1.9x2.5` × {2000_control,
    1850_control, blank, methane+nitrif, accelerated_spinup}.
21. **`lnd_tuning_mode` matrix** — every physics × {CRUJRA2024, CRUv7,
    GSWP3v1, cam7.0, cam6.0, cam5.0, cam4.0} × {sp, bgc}, skipping the three
    known-bad combinations (`clm6_0_CRUv7`, `clm4_5_CRUJRA2024`,
    `clm5_0_CRUJRA2024`).

Tail: `&cleanup` configs, `rm thing.nc` and `$tempfile`, then `xFail->parseOutput($captOut)` and the final success banner.

## 7. External files and directories the script consumes

In addition to `../build-namelist` and `../CLMBuildNamelist.pm` and all of
`bld/namelist_files/` and `bld/config_files/`:

- `cime_config/usermods_dirs/clm/NEON/defaults/user_nl_clm`
- `cime_config/usermods_dirs/clm/NEON/<SITE>/user_nl_clm` (47 sites; some have no site-specific overrides)
- `cime_config/usermods_dirs/clm/PLUMBER2/defaults/user_nl_clm`
- `cime_config/usermods_dirs/clm/PLUMBER2/<SITE>/user_nl_clm` (~170 sites)
- `bld/unit_testers/empty_user_nl_clm` — empty namelist fixture
- `bld/unit_testers/myuser_nl_clm` — fixture that sets `fsurdat` to an inputdata path; tested in §6.5
- CESM inputdata at the `-csmdata` root — only actually read by build-namelist itself when `-test` is on (existence check)
- Domain file used by one failure test:
  `$inputdata_rootdir/atm/datm7/domain.lnd.fv0.9x1.25_gx1v6.090309.nc`
- `xFail/expectedClmTestFails.xml` — empty as configured today

## 8. Files generated during a run (cwd = `bld/unit_testers`)

Cleaned between iterations: `temp_file.txt`, `lnd_in`, `drv_flds_in`,
`env_run.xml`, `config_cache.xml`, `temp.namelistinfile_<SITE>`. Created and
left around at top of run: `thing.nc` (deleted near the end), `testfile.nc`
(used as a placeholder finidat).

When `-generate` is on, snapshot files named
`lnd_in.<mode>.<sanitized-options>` and `drv_flds_in.<mode>.<sanitized-options>`
are left in cwd.

## 9. Sibling utility scripts (NOT part of the test run)

- `bld/unit_testers/compare_namelists` (bash) — driver around
  `cime/CIME/Tools/compare_namelists` that walks `lnd_in.*` snapshots in cwd
  and diffs each against a baseline directory, with `-pa`/`-pb` knobs to
  cross-compare physics versions.
- `bld/unit_testers/cmp_baseline_lnd_in_files` (bash) — compares `CaseDocs/
  lnd_in` files between two named CTSM baselines under
  `/glade/campaign/cgd/tss/ctsm_baselines/` (i.e., compares aux_clm test
  outputs, not unit_tester outputs).

These are independent ways to compare namelists and only loosely related to
`build-namelist_test.pl`; the rewrite probably does not need to touch them.

## 10. Environment / runtime dependencies

- Perl 5 with stdlib: `Test::More`, `Getopt::Long`, `IO::File`, `English`,
  `Cwd`, `Scalar::Util`, `File::Basename`, `File::Glob`.
- Non-core: **`XML::Lite`** (used by `xFail::expectedFail` via the cime
  `perl5lib`). The main test loop does not use it directly.
- Build-namelist itself reads a lot of XML; that is out of scope for the
  rewrite of the test script but the new tests still need
  `bld/build-namelist` (and its dependency tree) to run as-is.
- Inputdata access on GLADE / Derecho when `-test` is in effect.
- Working directory **must** be `bld/unit_testers/` — the harness uses
  relative paths everywhere (`../build-namelist`, `../../cime_config/...`,
  `xFail/expectedClmTestFails.xml`).
- Uses the deprecated Perl smart-match operator (`~~`); modern Perls emit a
  warning.

## 11. Pain points worth flagging for the rewrite

These are observations, not plan items — they are the "why bother" answers
the rewrite gets to address.

1. **Hard-coded `$ntests = 3407`** (and `+2061`) — every new assertion forces
   a manual recount or the suite fails at the end. pytest doesn't need this.
2. **`$#usecases != 15` die** — same problem one rank deeper: adding a
   use-case to the XML defaults silently breaks the test runner.
3. **xFail mechanism is silently broken** — machine detection only matches
   retired clusters (yellowstone/frankfurt), so on Derecho/Casper/Izumi
   nothing can be marked xFAIL today. The capability is intentional (see
   §5.2) and should be preserved via `@pytest.mark.xfail(condition=…,
   strict=True)`, with machine identity coming from `$CIME_MACHINE`
   rather than hostname prefixes.
4. **Massive nested `foreach` loops with embedded `if (compare)` /
   `if (generate)` blocks** — every category re-implements the same five
   lines. A pytest parametrize fixture removes most of this duplication.
5. **Per-test cleanup is shared global state** (`env_run.xml`,
   `config_cache.xml`, `lnd_in` in cwd). Parallelizing the suite would
   require sandbox dirs per test; tmp_path fixtures get this for free.
6. **Captured-output post-processing** is a Perl-specific workaround for
   merging xFail bookkeeping into Test::More's TAP stream. pytest's native
   reporting plus `xfail` removes the whole captOut / parseOutput layer.
7. **Test identity is positional** — xFail entries (when they existed) were
   keyed by numerical test ID, so re-ordering or inserting tests
   silently invalidated the expected-fail list. pytest's node-IDs are stable
   per-name.
8. **Sub-keys in `%failtest` / `%warntest` / `%coldwfinidat` are checked at
   runtime by name** with a manual `die`; this is just struct validation, a
   natural fit for a Python dataclass / TypedDict / pydantic model.
9. **Baseline comparison logic is tangled with assertion logic** — the
   `dodiffonfile` / `doNOTdodiffonfile` state machine is opaque. A
   golden-file fixture (e.g., `pytest-regressions` or a hand-rolled snapshot
   fixture) would express the same intent more directly.
