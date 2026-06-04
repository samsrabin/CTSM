#!/usr/bin/env python3
"""Coverage and parity gates for the build-namelist test rewrite.

Usage:
    python check_coverage.py             # coverage report
    python check_coverage.py --parity    # parity check against the perl suite

Coverage (default): compares the manifest's case ids to the ids pytest
collects, and reports the ported / stale / unaccounted breakdown. Exits
non-zero if a case is marked ported but not collected (or pytest collects an
id that the manifest does not mark ported or stale).

Parity (--parity): runs the perl suite (via extract_cases.pl --run-mode) and
the pytest suite, joins on case id, and reports any ported case where the two
disagree on pass/fail. Exits non-zero on any disagreement.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

_HERE = Path(__file__).resolve().parent
_CASES_YAML = _HERE / "cases.yaml"
_REPO_ROOT = _HERE.parent.parent
_PERL_EXTRACTOR = _REPO_ROOT / "bld" / "unit_testers" / "extract_cases.pl"

# pytest node ids look like: test_sys_smoke.py::test_sys_smoke[smoke/help]
_PARAM_RE = re.compile(r"\[([^\]]+)\]")
_OUTCOME_RE = re.compile(r"\[([^\]]+)\]\s+(PASSED|FAILED|XFAIL|XPASS)")


def main() -> int:
    """Parse args and dispatch to the coverage or parity gate."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--parity",
        action="store_true",
        help="Run the parity gate (perl/pytest outcome comparison).",
    )
    parser.add_argument(
        "--perl-outcomes",
        type=Path,
        default=None,
        help="Cached perl outcomes JSON (from extract_cases.pl --run-mode). "
        "If omitted with --parity, the perl suite is re-run.",
    )
    args = parser.parse_args()
    if args.parity:
        return _parity(args.perl_outcomes)
    return _coverage()


def _coverage() -> int:
    manifest = _load_manifest()
    collected = _pytest_collect()
    manifest_ids = {case["id"] for case in manifest}
    ported_ids = {case["id"] for case in manifest if case.get("ported")}
    stale_ids = {case["id"] for case in manifest if case.get("stale")}
    unaccounted = manifest_ids - ported_ids - stale_ids

    missing_in_collection = ported_ids - collected
    extra_in_collection = collected - ported_ids - stale_ids

    print(f"Manifest: {len(manifest_ids)} cases")
    print(f"  ported: {len(ported_ids)}")
    print(f"  stale:  {len(stale_ids)}")
    print(f"  neither (unaccounted): {len(unaccounted)}")
    print(f"Pytest collected: {len(collected)} cases")

    bad = 0
    if missing_in_collection:
        print(
            f"\nERROR: {len(missing_in_collection)} cases marked ported but "
            "not collected by pytest:"
        )
        for cid in sorted(missing_in_collection):
            print(f"  - {cid}")
        bad += 1
    if extra_in_collection:
        print(
            f"\nERROR: {len(extra_in_collection)} pytest cases not in manifest "
            "as ported (possible drift):"
        )
        for cid in sorted(extra_in_collection):
            print(f"  - {cid}")
        bad += 1
    return 1 if bad else 0


def _parity(cached_outcomes: Path | None) -> int:
    manifest = _load_manifest()
    ported = [case for case in manifest if case.get("ported")]
    perl_outcomes = _perl_outcomes(cached_outcomes)
    pytest_outcomes = _pytest_outcomes()

    mismatches = []
    for case in ported:
        cid = case["id"]
        perl_out = perl_outcomes.get(cid)
        pytest_out = pytest_outcomes.get(cid)
        if perl_out is None:
            mismatches.append(f"{cid}: perl=<MISSING> pytest={pytest_out}")
        elif pytest_out is None:
            mismatches.append(f"{cid}: perl={perl_out} pytest=<MISSING>")
        elif perl_out != pytest_out:
            mismatches.append(f"{cid}: perl={perl_out} pytest={pytest_out}")

    if mismatches:
        print(f"PARITY FAILURE: {len(mismatches)} mismatches:")
        for line in mismatches:
            print(f"  {line}")
        return 1
    print(f"PARITY OK: {len(ported)} cases agree.")
    return 0


def _fail(message: str, proc: subprocess.CompletedProcess) -> None:
    """Print a subprocess failure (with its stderr) and exit the gate."""
    print(f"ERROR: {message} (exit {proc.returncode})", file=sys.stderr)
    if proc.stderr:
        print(proc.stderr, file=sys.stderr)
    sys.exit(2)


def _load_manifest() -> list[dict]:
    return yaml.safe_load(_CASES_YAML.read_text(encoding="utf-8"))


def _pytest_collect() -> set[str]:
    """Return the set of case ids pytest collects, parsed from node ids."""
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "--no-header"],
        cwd=str(_HERE),
        capture_output=True,
        text=True,
        check=False,
    )
    # 0 = collected ok, 5 = no tests collected (a legitimate empty set). Any
    # other code means pytest itself errored (e.g. a conftest/import failure);
    # surface its stderr rather than silently reporting every ported case as
    # "not collected".
    if proc.returncode not in (0, 5):
        _fail("pytest collection failed", proc)
    ids = set()
    for line in proc.stdout.splitlines():
        if "::" not in line:  # only parse node-id lines, not summaries/warnings
            continue
        match = _PARAM_RE.search(line)
        if match:
            ids.add(match.group(1))
    return ids


def _pytest_outcomes() -> dict[str, str]:
    """Run the pytest suite and return {case_id -> 'pass'|'fail'}.

    XFAIL (an expected failure) counts as 'pass' and XPASS as 'fail', so the
    result compares against the perl assertion's pass/fail. NOTE: no ported
    case is xfail-marked yet; when the first one is, revisit this mapping --
    an XPASS (test unexpectedly passed) maps to 'fail' here even though the
    perl side may record the underlying assertion as passing.
    """
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-v", "--tb=no", "--no-header", "-p", "no:warnings"],
        cwd=str(_HERE),
        capture_output=True,
        text=True,
        check=False,
    )
    # 0 = all passed, 1 = some tests failed, 5 = no tests -- all parseable.
    # 2/3/4 mean pytest itself errored (collection/internal/usage); surface it.
    if proc.returncode in (2, 3, 4):
        _fail("pytest run errored", proc)
    outcomes = {}
    for line in (proc.stdout + proc.stderr).splitlines():
        match = _OUTCOME_RE.search(line)
        if not match:
            continue
        cid, status = match.group(1), match.group(2)
        outcomes[cid] = "pass" if status in {"PASSED", "XFAIL"} else "fail"
    return outcomes


def _perl_outcomes(cached: Path | None) -> dict[str, str]:
    if cached:
        return json.loads(cached.read_text(encoding="utf-8"))
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as handle:
        outfile = Path(handle.name)
    # Invoke the extractor by ABSOLUTE path: a relative path breaks the perl
    # test's `use lib` resolution of XML::Lite and yields zero cases.
    try:
        subprocess.run(
            ["perl", str(_PERL_EXTRACTOR), "--run-mode", str(outfile)],
            cwd=str(_REPO_ROOT),
            check=True,
        )
        return json.loads(outfile.read_text(encoding="utf-8"))
    finally:
        outfile.unlink(missing_ok=True)


if __name__ == "__main__":
    sys.exit(main())
