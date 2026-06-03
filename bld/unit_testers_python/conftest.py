"""Fixtures and CLI options for the build-namelist pytest suite.

Mirrors the per-iteration scaffolding of the perl harness
(make_env_run / make_config_cache / the build-namelist invocation), but gives
each test its own scratch cwd via pytest's tmp_path so the suite carries no
shared state and is safely parallelizable.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Callable, Optional

import pytest

# Make this directory importable (so `from helpers import ...` works here and
# in the test modules) and CTSM's python tree importable (for add_cime_to_path,
# which prepends CIME to sys.path as a side effect).
_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent.parent
sys.path.insert(0, str(_HERE))
sys.path.insert(1, str(_REPO_ROOT / "python"))

# These imports must follow the sys.path edits above. helpers, ctsm, and CIME
# are resolvable only at runtime, not by pylint's static analysis.
# pylint: disable=wrong-import-position,import-error,no-name-in-module
from ctsm import add_cime_to_path  # pylint: disable=unused-import
from helpers import RunResult

# pylint: enable=wrong-import-position,import-error,no-name-in-module

# Fixtures that request other fixtures necessarily shadow the fixture-function
# names; that is the standard pytest pattern, not a redefinition bug.
# pylint: disable=redefined-outer-name


_DEFAULT_INPUTDATA = "/glade/campaign/cesm/cesmdata/cseg/inputdata"


# --- pytest CLI options -----------------------------------------------------


def pytest_addoption(parser):
    """Register the suite's CLI options (inputdata root + baseline modes)."""
    parser.addoption(
        "--csmdata",
        default=None,
        help="CESM inputdata root. Falls back to $CSMDATA, then the default GLADE path.",
    )
    parser.addoption(
        "--baseline",
        default=None,
        help="Compare produced lnd_in/drv_flds_in against snapshots at <dir>/<case.id>/.",
    )
    parser.addoption(
        "--baseline-regen",
        default=None,
        help="Write snapshots to <dir>/<case.id>/ instead of comparing.",
    )


# --- session-scoped fixtures ------------------------------------------------


@pytest.fixture(scope="session")
def inputdata_root(request) -> str:
    """CESM inputdata root: --csmdata, then $CSMDATA, then the GLADE default."""
    return request.config.getoption("--csmdata") or os.environ.get("CSMDATA") or _DEFAULT_INPUTDATA


@pytest.fixture(scope="session")
def bldnml_path() -> Path:
    """Absolute path to bld/build-namelist."""
    return _REPO_ROOT / "bld" / "build-namelist"


@pytest.fixture(scope="session")
def baseline_dir(request) -> Optional[Path]:
    """Directory to compare produced namelists against, or None."""
    value = request.config.getoption("--baseline")
    return Path(value) if value else None


@pytest.fixture(scope="session")
def baseline_regen(request) -> Optional[Path]:
    """Directory to write baseline snapshots into, or None."""
    value = request.config.getoption("--baseline-regen")
    return Path(value) if value else None


@pytest.fixture(scope="session")
def current_machine() -> str:
    """CIME's name for the current machine, or 'unknown' if undetectable."""
    try:
        from CIME.XML.machines import (  # pylint: disable=import-outside-toplevel,import-error
            Machines,
        )

        return Machines().probe_machine_name() or "unknown"
    except Exception:  # pylint: disable=broad-except
        return "unknown"


# --- per-test fixtures ------------------------------------------------------


@pytest.fixture
def tmp_workdir(tmp_path, monkeypatch) -> Path:
    """Each test gets a fresh cwd. Cleanup is automatic via tmp_path."""
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture
def env_run(tmp_workdir) -> Callable[[Optional[dict]], Path]:
    """Return a callable that writes env_run.xml in cwd with overrides."""

    defaults = {
        "DIN_LOC_ROOT": "MYDINLOCROOT",
        "GLC_TWO_WAY_COUPLING": "FALSE",
        "LND_SETS_DUST_EMIS_DRV_FLDS": "TRUE",
        "NEONSITE": "",
        "PLUMBER2SITE": "",
        "CLM_CMIP_ERA": "cmip7",
        "CLM_NDEP_FROM_CPL": "FALSE",
    }

    def _write(overrides: Optional[dict] = None) -> Path:
        merged = dict(defaults)
        merged.update(overrides or {})
        path = tmp_workdir / "env_run.xml"
        with open(path, "w", encoding="utf-8") as stream:
            stream.write('<?xml version="1.0"?>\n\n<config_definition>\n\n')
            for key, value in merged.items():
                stream.write(f'<entry id="{key}" value="{value}"  />\n')
            stream.write("\n</config_definition>\n")
        return path

    return _write


@pytest.fixture
def config_cache(tmp_workdir) -> Callable[[str], Path]:
    """Return a callable that writes config_cache.xml with the given phys."""

    def _write(phys: str) -> Path:
        path = tmp_workdir / "config_cache.xml"
        with open(path, "w", encoding="utf-8") as stream:
            stream.write(
                '<?xml version="1.0"?>\n'
                "<config_definition>\n"
                "<commandline></commandline>\n"
                f'<entry id="phys" value="{phys}" list="" '
                'valid_values="clm4_5,clm5_0,clm6_0">Specifies clm physics</entry>\n'
                "</config_definition>\n"
            )
        return path

    return _write


@pytest.fixture
def build_namelist(tmp_workdir, bldnml_path, inputdata_root) -> Callable[..., RunResult]:
    """Return a callable that runs build-namelist and returns a RunResult."""

    base_argv = [
        str(bldnml_path),
        "-verbose",
        "-csmdata",
        inputdata_root,
        "-configuration",
        "clm",
        "-structure",
        "standard",
        "-glc_nec",
        "10",
        "-no-note",
    ]

    def _run(argv, *, infile=None, extra_env=None, setup_files=()) -> RunResult:
        for fname in setup_files:
            (tmp_workdir / fname).touch()
        cmd = list(base_argv)
        if infile is not None:
            cmd += ["-infile", str(infile)]
        cmd += list(argv)
        env = os.environ.copy()
        if extra_env:
            env.update(extra_env)
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            env=env,
            cwd=str(tmp_workdir),
            check=False,
        )
        produced = [p for p in ("lnd_in", "drv_flds_in") if (tmp_workdir / p).exists()]
        return RunResult(
            returncode=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            produced_files=produced,
        )

    return _run
