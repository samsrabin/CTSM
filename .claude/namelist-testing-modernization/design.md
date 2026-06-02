# Build-namelist Test Suite Modernization — Design

> Companion to `summary.md` (the as-is analysis of the existing Perl
> harness). This document is the to-be design: a manifest-driven,
> pytest-parametrized rewrite that lands incrementally across ~10 pull
> requests with mechanical coverage verification at every step.

## 1. Context

`bld/unit_testers/build-namelist_test.pl` is a 2,154-line Perl Test::More
script that exercises `bld/build-namelist` across ~3,400 assertions
spanning 21 test categories. The existing harness has accumulated rot
that the simple act of adding a test now exposes:

- the `plan(tests => 3407)` count drifts every PR;
- the `xFail::expectedFail` subsystem is inert on every machine CTSM
  is currently tested on;
- per-test cleanup is shared cwd state, so the suite cannot be
  parallelized;
- baseline-comparison logic is tangled with assertion logic via the
  `dodiffonfile`/`doNOTdodiffonfile` state machine in
  `NMLTest::CompFiles`;
- positional test IDs make any reordering of tests silently invalidate
  the (currently broken) xFail list.

We are converting the harness to pytest. The user requirements are:

1. **Verifiable coverage** — we must be able to demonstrate that no
   assertion from the Perl script was dropped silently.
2. **Free to restructure** — the perl script's nested for-loops are
   the single biggest readability problem; they get replaced with
   `@pytest.mark.parametrize`.
3. **Incrementally portable** — the conversion lands as a sequence of
   pull requests, not a big-bang rewrite on a long-lived branch.

This document is the design that reconciles those three requirements.

## 2. Goals and non-goals

**In scope.**
- Replace `build-namelist_test.pl` with a pytest suite at
  `bld/unit_testers_python/`.
- Preserve the Perl harness's `-compare` / `-generate` baseline-snapshot
  workflow as pytest CLI options, with stable case IDs as the lookup
  key.
- Preserve the *intent* of the existing xFail mechanism via
  `@pytest.mark.xfail` markers attached to per-case entries; fix the
  machine-detection bug naturally by using CIME's
  `probe_machine_name()` as the source of truth.
- Land the rewrite as ~10 reviewable, independently-mergeable PRs.

**Out of scope.**
- Changes to `bld/build-namelist` or `bld/CLMBuildNamelist.pm` (the
  code under test).
- Reorganization of the existing CTSM python test tree at
  `python/ctsm/test/`.
- CI integration (the perl test is not currently in CTSM CI; the new
  suite gets invoked the same way — bare shell from
  `bld/unit_testers_python/` — until someone wants to plumb it in).
- Parallelization (pytest-xdist) — easy to add later once the suite
  reaches parity, but explicitly not blocking on it.
- Replacing the sibling perl utilities (`compare_namelists`,
  `cmp_baseline_lnd_in_files`) — they are separate concerns; they
  get deleted alongside the perl tester in the final cleanup PR but
  no replacement is built.

## 3. Approach overview

The rewrite is **manifest-driven**:

1. **Extract once.** `bld/unit_testers/extract_cases.pl` is a one-time
   harness that imports `build-namelist_test.pl`, hooks
   `Test::Builder` to intercept every assertion, and watches
   `make_env_run` / `make_config_cache` / `system` / `print` so each
   assertion gets paired with the context that produced it. Output:
   a checked-in `bld/unit_testers_python/cases.yaml` enumerating
   every assertion the perl script makes.
2. **Port incrementally.** Each PR ports one (or a few) categories
   from `cases.yaml` into a `test_sys_<category>.py` module using
   `@pytest.mark.parametrize(case_id → case)`. The parametrize IDs
   *are* the manifest IDs — there is no separate mapping to drift.
3. **Verify mechanically.** `bld/unit_testers_python/check_coverage.py`
   runs `pytest --collect-only -q`, loads `cases.yaml`, and reports
   which cases are `ported`, which are `stale`, and which are
   neither. The "neither" set must be empty before the final cleanup
   PR can land.
4. **Coexist during transition.** The perl suite keeps running
   unchanged until the final PR. Both green is the bar for every
   intermediate PR.
5. **Clean up at the end.** The final PR deletes the perl tester, the
   extractor, `cases.yaml` itself (pytest collection becomes the
   manifest), and the perl-only sibling scripts.

The key reconciliation: `cases.yaml` lets us restructure the *pytest*
layer however we want while still proving every assertion was
accounted for. Restructure-vs-verify stop being in tension.

## 4. File layout

```
bld/unit_testers_python/
    __init__.py
    conftest.py                  # fixtures (see §7)
    pytest.ini                   # local pytest config: discovery, markers
    cases.yaml                   # extracted manifest, source of truth
    helpers.py                   # load_cases(), infile_writer(), RunResult
    check_coverage.py            # coverage-checker tool (manifest vs collected IDs)
    README.md                    # how to run, how to re-extract, intent
    test_sys_smoke.py            # PR2
    test_sys_list_options.py     # PR2
    test_sys_drydep_megan.py     # PR3
    test_sys_nuopc_matrix.py     # PR4
    test_sys_neon.py             # PR5
    test_sys_plumber2.py         # PR5
    test_sys_cam_grids.py        # PR6
    test_sys_use_cases.py        # PR6
    test_sys_failures.py         # PR7
    test_sys_warnings.py         # PR7
    test_sys_coldwfinidat.py     # PR7
    test_sys_resolutions_*.py    # PR8 (split — see §10)
    test_sys_lnd_tuning_*.py     # PR9 (split — see §10)
```

```
bld/unit_testers/
    extract_cases.pl             # NEW: writes ../unit_testers_python/cases.yaml
    build-namelist_test.pl       # unchanged until PR10
    NMLTest/, xFail/, ...        # unchanged until PR10
    compare_namelists,           # unchanged until PR10
    cmp_baseline_lnd_in_files,   #   "
    empty_user_nl_clm,           #   "
    myuser_nl_clm                #   "
```

Files are named `test_sys_*.py` to leave room for future
`test_unit_*.py`-style narrow unit tests in the same directory.

The new suite is invoked directly (`cd bld/unit_testers_python && pytest`),
mirroring how the perl tester is invoked today. It does not flow
through `python/run_ctsm_py_tests` — those tests are unittest-style and
auto-discovered relative to `python/`. Plumbing the new suite into the
central runner is deferred (easy glob-pattern change if ever wanted).

## 5. Extractor mechanism

`bld/unit_testers/extract_cases.pl` is the one-time-use tool that
produces `cases.yaml`. Three responsibilities:

1. **Hook `Test::Builder`.** `Test::More`'s `is` / `isnt` / `ok` / `like`
   all bottom out in `Test::Builder::ok`. The extractor overrides
   `Test::Builder::ok` so each invocation captures
   `{description, passed, file, line}` into an in-memory list. This is
   the same Test::More-builder hooking that the existing
   `xFail::expectedFail` already uses, but one layer deeper — we get
   structured records rather than TAP text.
2. **Wrap context-establishing calls.** The extractor overrides /
   wraps:
   - `xFail::expectedFail` package's `make_env_run` and
     `make_config_cache` analogues — actually these are subs defined
     in `build-namelist_test.pl` itself. The extractor uses
     `*main::make_env_run = sub {...}` to intercept them.
   - `system()` builtin (via `BEGIN { *CORE::GLOBAL::system = sub {...} }`)
     to capture each invocation's command line.
   - `print` to STDOUT, watching for `=== Test <res> ===` and the
     section banner lines (`==…== Run simple tests ==…==`), which
     tell us which category we're in.
3. **Run and serialize.** After hooking, `do "build-namelist_test.pl"`
   executes the perl test in the same process. The extractor passes
   `-no-test` so dataset existence checks are skipped (the extractor
   does not need inputdata to enumerate cases). When the script
   finishes, the extractor walks the captured stream in source order,
   pairs each assertion with the most-recent context at the time it
   ran, generates a stable `id`, and writes the YAML.

**Stable IDs.** `id` is `<category>/<slug>` where `<slug>` is derived
from the assertion description if it is meaningfully unique (e.g. the
keys of `%failtest` are already slug-shaped) or from a normalized form
of the bldnml argv if it is not (e.g. parametrized loops in
"resolutions" emit slugs like `resolutions/clm5_0--res-0.9x1.25--bgc-sp--use-case-1850_control`).
IDs are deterministic across extractor runs.

**Idempotence + preservation of human annotations.** When the
extractor regenerates `cases.yaml`, it loads the existing file first
and preserves `ported` and `stale`/`stale_reason` annotations for any
case whose `id` matches. If a case's structural fields (`bldnml_argv`,
`env_run`, `phys`, `infile`) materially differ from the previous
version, `ported` is reset to `false` so the coverage checker forces
re-examination.

**No edits to `build-namelist_test.pl`.** The extractor is a
self-contained sibling; the perl harness keeps running its existing
flow during transition.

## 6. Case schema

```yaml
- id: failures/cmip7_w_issp
  category: failures
  description: "cmip7_w_issp"                     # verbatim from the perl is/isnt call
  bldnml_argv:
    - -envxml_dir
    - "."
    - -use_case
    - 1850-2100_SSP2-4.5_transient
    - -namelist
    - "&clmexp  /"
  env_run:
    CLM_CMIP_ERA: cmip7
  phys: clm6_0
  infile:
    sources: []                                   # paths concatenated into a temp &clm_settings file
  setup_files: []                                 # files touched in cwd before the build-namelist run
  expect:
    exit_zero: false
    files: []                                     # required to exist on success (lnd_in, drv_flds_in)
    greps: []                                     # post-run grep assertions on lnd_in
  xfail:                                          # optional; null means no xfail
    condition: null                               # e.g. "machine == 'derecho'"
    reason: null
    strict: true
  source:
    perl_file: bld/unit_testers/build-namelist_test.pl
    line: 638
  ported: false
  stale: false
  stale_reason: null
```

The `description` field captures what the perl assertion's third
argument was, verbatim, so debugging back-and-forth between the
manifest and the perl source stays trivial.

## 7. Pytest infrastructure

### 7.1 conftest.py top matter

CIME is loaded via the existing CTSM utility:

```python
import os, sys
_CTSM_PYTHON = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "python")
)
sys.path.insert(1, _CTSM_PYTHON)
from ctsm import add_cime_to_path  # noqa: F401 — side-effect import
```

### 7.2 Session-scoped fixtures

- `inputdata_root` — resolves from `--csmdata <dir>` pytest CLI arg,
  then `$CSMDATA`, then the default GLADE path. Matches the perl's
  precedence.
- `bldnml_path` — absolute path to `bld/build-namelist`.
- `baseline_dir` — value of `--baseline=<dir>`, or `None`.
- `baseline_regen` — value of `--baseline-regen=<dir>`, or `None`.
- `current_machine` — calls `CIME.XML.machines.Machines().probe_machine_name()`.

### 7.3 Per-test fixtures

- `tmp_workdir` — wraps pytest's `tmp_path` + `monkeypatch.chdir(tmp_path)`.
  Each test runs in its own scratch directory. Cleanup is automatic.
- `env_run` — callable: `env_run(settings: dict)` writes `env_run.xml`
  in cwd with merged defaults + overrides.
- `config_cache` — callable: `config_cache(phys: str)` writes
  `config_cache.xml` in cwd.
- `infile_writer` — callable: `infile_writer(sources: list[Path]) -> Path`
  concatenates user_nl_clm sources into a temp `&clm_settings ... /`
  file and returns its path. Mirrors `cat_and_create_namelistinfile`.
- `build_namelist` — callable: runs build-namelist via
  `subprocess.run(..., capture_output=True)`. Returns a `RunResult`
  with `returncode`, `stdout`, `stderr`, `produced_files`. Does not
  assert outcome — that is the test's responsibility.

### 7.4 Baseline comparison

`-compare` and `-generate` map to pytest CLI options:

- `--baseline=<dir>` enables comparison mode. For each case with
  `expect.exit_zero == true`, the test diffs the produced `lnd_in`
  (and `drv_flds_in` if listed in `expect.files`) against
  `<dir>/<case.id>/lnd_in`. Mismatch fails the test.
- `--baseline-regen=<dir>` enables snapshot mode. Same flow but
  writes the snapshot file instead of diffing.
- Default (neither flag) skips comparison — just exit code + file
  existence are checked.

Baselines are organized by `case.id`, not by sanitized option-strings.
The IDs are stable; the perl's option-string snapshot names were lossy.

### 7.5 xFail handling

Per-case xfail entries in `cases.yaml` become pytest markers:

```python
def _maybe_xfail(case, current_machine):
    if not case.xfail or not case.xfail.condition:
        return ()
    condition = eval(case.xfail.condition, {"machine": current_machine})
    return (pytest.mark.xfail(condition=condition,
                              reason=case.xfail.reason,
                              strict=case.xfail.strict),)

@pytest.mark.parametrize(
    "case",
    [pytest.param(c, marks=_maybe_xfail(c), id=c.id) for c in load_cases("failures")],
)
def test_sys_failures(case, ...):
    ...
```

`strict=True` is the "this test now passes — go remove the xfail
entry" semantics the perl xFail subsystem was trying to provide.
With the broken `_getMachInfo` replaced by CIME's
`probe_machine_name`, machine-conditional xfails work correctly on
Derecho/Casper/Izumi without any custom Perl machinery.

### 7.6 Reproducing other perl quirks

- The perl `touch $finidat` / `touch $testfile` setup-file pattern is
  encoded as a per-case `setup_files: [thing.nc]` list; the
  `build_namelist` fixture touches each in `tmp_workdir` before
  invoking build-namelist.
- The perl shells out via `system(... > $tempfile 2>&1)` and then
  `cat`s `$tempfile` on failure. We use `subprocess.run(...,
  capture_output=True)` and put the captured output in the
  `RunResult`; pytest's `--showlocals -vv` surfaces it on failure
  automatically.
- The perl's `like($result, "/.../")` regex assertions on stdout (the
  "list options" tests) become `assert re.search(pattern, result.stdout)`.

## 8. PR sequence

Ten PRs, plus a possible split of PR8 and PR9 as noted in §10.

| PR  | Scope                                                            | ~Cases  |
| --- | ---------------------------------------------------------------- | ------- |
| 1   | Infrastructure: skeleton dir, conftest fixtures, helpers, extractor, cases.yaml, check_coverage.py, README, one trivial proof-of-life test (-help, -version) | 2     |
| 2   | Smoke (finish) + list options                                    | ~15     |
| 3   | drydep / MEGAN / fire_emis matrix                                | ~5      |
| 4   | nuopc options matrix (the 20-ish ad-hoc combos)                  | ~25     |
| 5   | NEON sites + PLUMBER2 sites (may split into 5a / 5b)             | ~265    |
| 6   | CAM grids + CAM_SETS_DRV_FLDS + clm5_0 use-cases                 | ~35     |
| 7   | Failure (%failtest) + warning (%warntest) + coldwfinidat tables  | ~165    |
| 8   | Resolution sweeps (§14 of summary.md). **MUST be split** — see §10 | ~2,000 |
| 9   | Per-physics resolution × clmoptions matrix + lnd_tuning matrix. **MUST be split** — see §10 | ~700  |
| 10  | Cleanup: delete perl tester, NMLTest/, xFail/, extractor, cases.yaml, sibling perl utilities; update testing.rst | n/a |

PR1's "proof-of-life" test runs green entirely on its own; subsequent
PRs only add tests, never remove perl infrastructure.

## 9. Verification and policies

### 9.1 Coverage check

`check_coverage.py` is the gate between PRs. It:

1. Loads `cases.yaml`, partitions by `ported` / `stale` / neither.
2. Runs `pytest --collect-only -q` and parses the collected node IDs
   into a set of case IDs.
3. Reports `<X ported> + <Y stale> = <Z covered> / <total>` and lists
   any ID mismatches (a manifest entry says `ported: true` but no
   pytest test claims it, or vice versa).
4. Exits non-zero if mismatches exist.

PR10 cannot land until `check_coverage.py` exits zero with
"covered == total" and the "neither" set is empty.

### 9.2 Parity gate (informal)

Reviewer of any intermediate PR can verify behavior parity by running
both the perl suite (`./build-namelist_test.pl`) and the pytest
suite (`pytest`) and confirming that every case marked `ported: true`
has the same pass/fail outcome in both. A `check_coverage.py
--parity` subcommand can wrap this as
`diff <(perl-output | grep -E '^.*FAIL') <(pytest-output | grep FAIL)`
if desired — easy to add later.

### 9.3 Stale-decision policy

`stale: true` is the explicit way to drop a case during the rewrite.
Required:
- `stale_reason` populated with a one-liner ("retired feature: X",
  "covered by aux_clm now", "uses retired-machine-only logic", etc.).
- The PR description lists every newly-staled case ID and its reason.
- Sam (project owner) sign-off in the PR review.

Reversible: if review disagrees, flip `stale` back to `false` and
write the pytest test.

### 9.4 Bug-fix-during-port policy

If porting reveals a bug in `bld/build-namelist` itself (not in the
perl tester), the right move is normally a small standalone PR that
fixes build-namelist first; the port-PR then lands with the
now-passing case.

If porting reveals a bug in `build-namelist_test.pl` (a perl
assertion that's wrong), document it in the PR description, fix the
perl too if convenient, otherwise mark the case `stale` with reason
"perl test was wrong: <what it asserted vs what it should have>".

Tangle "rewrite" and "fix the system under test" in the same diff
only when it would be more painful to separate them.

### 9.5 Coexistence

Both suites are green-and-runnable throughout PRs 1–9. The perl tester
keeps its existing invocation contract; the new pytest suite is
runnable from `bld/unit_testers_python/` from day one of PR1.
Neither is plumbed into CI by this rewrite — that is a separate,
later concern.

### 9.6 Pre-commit linting

Every PR that touches Python in `bld/unit_testers_python/` (or any
other `*.py` this project adds) must pass black and pylint checks
before commit. The configs are CTSM-standard:

- black:  `python/pyproject.toml`
- pylint: `python/ctsm/.pylintrc`  (with `-j 4`)

These are the same configs `python/Makefile`'s `make black` and
`make lint` targets use for the rest of CTSM's python, so the new
suite stays consistent with the project's existing style.

The runner is `.claude/namelist-testing-modernization/scripts/check_python.sh`.
It activates the `ctsm_pylib` conda environment, applies the configs
above to its arguments (defaulting to `bld/unit_testers_python/`), and
exits non-zero on the first violation. Reproduce its effect manually
with the three-liner in the script header.

This check is a gate on every commit, not a PR-level afterthought.
Equivalent of running `make black lint` from `python/` for the rest
of CTSM.

## 10. Deferred decisions

### 10.1 How to split PR8

PR8 covers Category 14 of `summary.md`, which is itself a per-physics
outer loop containing seven distinct sub-blocks:

- SP × all resolutions × {1850, 2000}
- BGC × important-resolutions × 20thC_transient
- All use-cases × clm4_5/clm5_0/clm6_0 × f09
- `%finidat_files` (8 explicit cases)
- crop resolutions
- glc_mec resolutions
- transient + gross-unrep, SSP2-4.5-transient

~2,000 cases total. Probably ≥3 PRs. Defer concrete split decision
until PR7 lands and we have a clearer sense of review pacing and
which sub-blocks share fixture / parametrize idioms.

### 10.2 How to split PR9

PR9 covers Categories 20 and 21 of `summary.md`:

- Per-physics resolution × clmoptions matrix (~500 cases) — bgc/sp/
  vichydro/dynveg/c-isotope variants × ~11 grids, plus an
  `ne16np4.pg3`-only pass, plus a FATES sweep.
- `lnd_tuning_mode` matrix (~200 cases) — every physics × atm
  forcing × {sp, bgc}.

These two categories have different parametrize shapes (clmoptions
sweep is options × resolution; lnd_tuning is forcing × bgc × physics)
and probably want to be separate PRs. Defer concrete split decision
until PR8 lands.

### 10.3 Other deferrals

- **pytest-xdist parallelism.** Worth turning on once parity is
  reached. Out of scope for this design.
- **Plumbing into `python/run_ctsm_py_tests`.** Possible later but
  not part of the rewrite.
- **Replacement for `compare_namelists` / `cmp_baseline_lnd_in_files`.**
  Out of scope; they get deleted in PR10 with no direct replacement,
  consistent with how they are currently used (rarely).

## 11. Open risks

- **The extractor's source-order pairing of context and assertions
  assumes the perl script is straight-line.** If a future perl edit
  introduces dynamic context juggling (e.g., reusing a `%settings`
  hash across multiple sections), the extractor needs a corresponding
  update. Mitigation: PR1's review includes spot-checking a sample of
  generated cases against the perl source.
- **`stale` decisions concentrate in PRs 7–9.** The fail/warn tables
  (PR7) and the resolution sweeps (PR8, PR9) are where retired-feature
  tests cluster. Allocate extra review time there.
- **Baseline regeneration is destructive when run with
  `--baseline-regen` against a populated dir.** Same risk the perl
  `-generate` has today; we just need the README to call it out.

## 12. Next step

This design covers the full 10-PR rewrite. The **immediately next**
implementation plan is for **PR1 only** (infrastructure + proof-of-life
test). Subsequent PRs each get their own short brainstorm/plan cycle
once the previous one lands — they all follow the same pattern
established in PR1, so each successor plan should be small. Per
§10.1/§10.2, PR8 and PR9 also need an explicit split-decision
sub-brainstorm before their plans get written.
