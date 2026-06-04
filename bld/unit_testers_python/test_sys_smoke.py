"""Proof-of-life smoke tests: build-namelist runs at all (-help, -version).

The first ported cases. Exercises the full fixture chain (build_namelist,
tmp_workdir) end-to-end and establishes the assert-against-expect.exit_zero
idiom that subsequent ported categories follow.

Note the two smoke cases have opposite expected polarities: -version exits 0,
while -help prints its usage via die() and so exits non-zero. The manifest's
expect.exit_zero captures that, and the perl harness's own assertion is even
weaker (it only checks that the subprocess ran at all).
"""

import pytest

from helpers import load_cases  # pylint: disable=import-error

_SMOKE_CASES = load_cases(category="smoke", ported_only=True)


@pytest.mark.sys
@pytest.mark.parametrize("case", _SMOKE_CASES, ids=[case.id for case in _SMOKE_CASES])
def test_sys_smoke(case, build_namelist):
    """build-namelist runs and exits with the polarity expect.exit_zero records."""
    result = build_namelist(case.bldnml_argv)
    exited_zero = result.returncode == 0
    assert exited_zero == case.expect.exit_zero, (
        f"build-namelist {case.bldnml_argv}: expected "
        f"{'exit 0' if case.expect.exit_zero else 'nonzero exit'}, "
        f"got returncode {result.returncode}\n"
        f"--- stderr ---\n{result.stderr}\n"
        f"--- stdout ---\n{result.stdout}\n"
    )
