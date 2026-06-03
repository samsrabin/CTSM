"""Helpers for the pytest-based build-namelist test suite.

Defines the dataclasses that mirror the cases.yaml schema (see
.claude/namelist-testing-modernization/design.md section 6), a loader that
reads cases.yaml into those dataclasses, and the infile concatenation helper
that mirrors the perl harness's cat_and_create_namelistinfile.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

import yaml


@dataclass
class XFailSpec:
    # pylint: disable=too-few-public-methods
    """Machine-conditional expected-failure spec for a case."""

    condition: Optional[str] = None
    reason: Optional[str] = None
    strict: bool = True


@dataclass
class CaseExpect:
    # pylint: disable=too-few-public-methods
    """What a case expects: exit polarity, required files, grep assertions."""

    exit_zero: bool = True
    files: list = field(default_factory=list)
    greps: list = field(default_factory=list)


@dataclass
class CaseInfile:
    # pylint: disable=too-few-public-methods
    """user_nl_clm sources concatenated into the -infile namelist."""

    sources: list = field(default_factory=list)


@dataclass
class CaseSource:
    # pylint: disable=too-few-public-methods
    """Where in the perl harness this case's assertion originated."""

    perl_file: Optional[str] = None
    line: Optional[int] = None


@dataclass
class Case:
    # pylint: disable=too-few-public-methods,too-many-instance-attributes,invalid-name
    """One extracted build-namelist assertion, loaded from cases.yaml."""

    id: str
    category: str
    description: str
    bldnml_argv: list
    env_run: dict
    phys: Optional[str]
    infile: CaseInfile
    setup_files: list = field(default_factory=list)
    expect: CaseExpect = field(default_factory=CaseExpect)
    xfail: Optional[XFailSpec] = None
    source: CaseSource = field(default_factory=CaseSource)
    ported: bool = False
    stale: bool = False
    stale_reason: Optional[str] = None


@dataclass
class RunResult:
    # pylint: disable=too-few-public-methods
    """The outcome of running build-namelist once."""

    returncode: int
    stdout: str
    stderr: str
    produced_files: list


_CASES_YAML = Path(__file__).parent / "cases.yaml"


def load_cases(
    *,
    category: Optional[str] = None,
    ids: Optional[Iterable[str]] = None,
    ported_only: bool = True,
) -> "list[Case]":
    """Load cases.yaml, optionally filtered.

    Args:
        category: if given, only return cases with this category.
        ids: if given, only return cases whose id is in this iterable.
        ported_only: if True (default), skip cases with ported=False. Set
            False for tooling (e.g. check_coverage.py).
    """
    with open(_CASES_YAML, encoding="utf-8") as stream:
        raw = yaml.safe_load(stream)
    cases = [_case_from_dict(entry) for entry in raw]
    if category is not None:
        cases = [case for case in cases if case.category == category]
    if ids is not None:
        idset = set(ids)
        cases = [case for case in cases if case.id in idset]
    if ported_only:
        cases = [case for case in cases if case.ported]
    return cases


def _case_from_dict(entry: dict) -> Case:
    expect = entry.get("expect") or {}
    return Case(
        id=entry["id"],
        category=entry["category"],
        description=entry["description"],
        bldnml_argv=list(entry.get("bldnml_argv") or []),
        env_run=dict(entry.get("env_run") or {}),
        phys=entry.get("phys"),
        infile=CaseInfile(sources=list((entry.get("infile") or {}).get("sources") or [])),
        setup_files=list(entry.get("setup_files") or []),
        expect=CaseExpect(
            exit_zero=expect.get("exit_zero", True),
            files=list(expect.get("files") or []),
            greps=list(expect.get("greps") or []),
        ),
        xfail=_xfail_from_dict(entry.get("xfail")),
        source=CaseSource(
            perl_file=(entry.get("source") or {}).get("perl_file"),
            line=(entry.get("source") or {}).get("line"),
        ),
        ported=bool(entry.get("ported")),
        stale=bool(entry.get("stale")),
        stale_reason=entry.get("stale_reason"),
    )


def _xfail_from_dict(entry: Optional[dict]) -> Optional[XFailSpec]:
    if not entry or not entry.get("condition"):
        return None
    return XFailSpec(
        condition=entry["condition"],
        reason=entry.get("reason"),
        strict=bool(entry.get("strict", True)),
    )


def infile_writer(sources: Iterable[Path], dest: Path) -> Path:
    """Concatenate user_nl_clm sources into a &clm_settings ... / file.

    Mirrors the perl harness's cat_and_create_namelistinfile.
    """
    lines = ["&clm_settings\n", "\n"]
    for src in sources:
        with open(src, encoding="utf-8") as stream:
            for line in stream:
                lines.append(" " + line)
    lines.append("\n/\n")
    dest.write_text("".join(lines), encoding="utf-8")
    return dest
