# Pytest-based build-namelist test suite

This directory is the pytest replacement for
`bld/unit_testers/build-namelist_test.pl`. As of PR1 it contains the
infrastructure plus two proof-of-life cases (`-help`, `-version`); subsequent
PRs port test categories from the Perl harness against this scaffold until
parity is reached and the Perl is deleted (final PR).

See `.claude/namelist-testing-modernization/design.md` for the full design and
`.claude/namelist-testing-modernization/plan-PR1.md` for the PR1 plan.

## Quick start

The suite runs in the `ctsm_pylib` conda environment (same one CTSM's other
Python uses):

```bash
cd bld/unit_testers_python
conda run -n ctsm_pylib python -m pytest          # run everything ported so far
conda run -n ctsm_pylib python -m pytest -v       # verbose
conda run -n ctsm_pylib python -m pytest test_sys_smoke.py
conda run -n ctsm_pylib python -m pytest -k smoke # select by id substring
```

Each test runs in its own `tmp_path` working directory, so there is no shared
state between tests — unlike the Perl tester, the suite is safely
parallelizable. Once `pytest-xdist` is wired in (a later PR) you can use
`pytest -n auto`.

## Per-commit gates

Confirm all three gates pass before marking a PR ready (this is the design
§9.2 contract; the reviewer runs them too):

```bash
# from the repo root:
.claude/namelist-testing-modernization/scripts/check_python.sh
cd bld/unit_testers_python
conda run -n ctsm_pylib python check_coverage.py
conda run -n ctsm_pylib python check_coverage.py --parity
```

- **`check_python.sh`** runs `black --check` and `pylint` with the
  CTSM-standard configs (`python/pyproject.toml`, `python/ctsm/.pylintrc`)
  inside `ctsm_pylib`. Gate on every commit that touches Python here.
- **`check_coverage.py`** reports how many manifest cases are ported vs stale
  vs unaccounted, and errors if pytest collects an id that isn't ported in the
  manifest (or a ported id pytest doesn't collect).
- **`check_coverage.py --parity`** runs the Perl suite and the pytest suite
  and reports any ported case where they disagree on pass/fail. A mismatch is,
  by definition, a port regression introduced by the current PR. Investigate
  before submitting.

The parity run re-executes the full Perl suite, which takes a few minutes. To
iterate faster, cache the Perl outcomes once and reuse them:

```bash
perl $(git rev-parse --show-toplevel)/bld/unit_testers/extract_cases.pl \
     --run-mode /tmp/perl_outcomes.json
conda run -n ctsm_pylib python check_coverage.py --parity \
     --perl-outcomes /tmp/perl_outcomes.json
```

## CLI options added by this suite

- `--csmdata <dir>` — CESM inputdata root (default: `$CSMDATA`, then
  `/glade/campaign/cesm/cesmdata/cseg/inputdata`).
- `--baseline <dir>` — diff produced `lnd_in` / `drv_flds_in` against
  `<dir>/<case.id>/` snapshots. (Comparison logic lands in a later PR.)
- `--baseline-regen <dir>` — write snapshots instead of diffing.

## Re-extracting the manifest

`cases.yaml` is generated from the Perl harness by
`bld/unit_testers/extract_cases.pl`. Regenerate it if
`build-namelist_test.pl` changes during the transition (someone adds a new
Perl assertion):

```bash
perl $(git rev-parse --show-toplevel)/bld/unit_testers/extract_cases.pl
```

Invoke the extractor by its **absolute path** (as above). Running it via a
relative path (e.g. `perl bld/unit_testers/extract_cases.pl`) breaks the Perl
test's `use lib` resolution of `XML::Lite`, which makes the body abort, emit
zero cases, and truncate `cases.yaml`.

The extractor:

- emits the manifest sorted by `(category, id)` and is deterministic — two
  back-to-back runs are byte-identical;
- preserves the `ported` / `stale` / `stale_reason` annotations for any case
  whose structural fields (`bldnml_argv`, `env_run`, `phys`, `infile.sources`)
  are unchanged; if those differ, `ported` is reset to `false` so the coverage
  gate forces a re-examination.

It exits with code 2 because two assertions (`inventoryfileDNE` and
`useFATESLUH2fileDNE`) fail under the forced `-no-test` mode — build-namelist
returns 0 where those `isnt($?, 0, ...)` assertions expected nonzero — and
Test::More's end-of-run handler sets the process exit code to the number of
failed assertions. This is pre-existing Perl behavior, not an extractor
failure; the manifest is still written with all 3407 cases.

## Files

- `conftest.py` — session and per-test fixtures (inputdata/bldnml paths,
  `current_machine`, `tmp_workdir`, `env_run`, `config_cache`,
  `build_namelist`) and the `--csmdata` / `--baseline` / `--baseline-regen`
  CLI options.
- `helpers.py` — the `Case` / `CaseExpect` / `CaseInfile` / `CaseSource` /
  `XFailSpec` / `RunResult` dataclasses, `load_cases()`, and `infile_writer()`.
- `pytest.ini` — pytest configuration (discovery pattern, `sys`/`unit`
  markers).
- `cases.yaml` — the generated manifest; the source of truth for what the
  Perl suite covers. Schema: design.md §6.
- `check_coverage.py` — the coverage and parity gates.
- `test_sys_*.py` — the test modules, one per Perl category (just
  `test_sys_smoke.py` so far).
