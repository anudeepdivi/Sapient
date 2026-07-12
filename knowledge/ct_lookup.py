"""Lookup into the compact CDISC controlled-terminology index built from the free
NCI-EVS machine-readable CT (see knowledge/ct/build_ct.py). Codelists are keyed by
CDISC submission value; use this to ground spec generation and conformance checks in
real, versioned CT instead of hand-typed value lists.

Coverage is currently partial (the subset in WANTED that resolved against the CT
release); expand WANTED in build_ct.py and re-run to add codelists.
"""
import json
from pathlib import Path

_CT_PATH = Path(__file__).resolve().parent / "ct" / "cdisc_ct.json"
_ct = None


def _load() -> dict:
    global _ct
    if _ct is None:
        _ct = json.loads(_CT_PATH.read_text()) if _CT_PATH.exists() else {}
    return _ct


def ct_values(submission_value: str) -> list[str]:
    """Allowed terms for a CDISC codelist by submission value (e.g. 'SEX'), or []."""
    entry = _load().get(submission_value)
    return entry["values"] if entry else []


def available() -> list[str]:
    return sorted(_load())
