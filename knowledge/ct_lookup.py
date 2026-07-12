"""Lookup into the compact CDISC controlled-terminology index built from the free
NCI-EVS machine-readable CT (see knowledge/ct/build_ct.py). Codelists are keyed by
CDISC submission value; use this to ground spec generation and conformance checks in
real, versioned CT instead of hand-typed value lists.

Coverage is currently partial (the subset in WANTED that resolved against the CT
release); expand WANTED in build_ct.py and re-run to add codelists.
"""
import json
from pathlib import Path

_CT_DIR = Path(__file__).resolve().parent / "ct"
_CT_PATH = _CT_DIR / "cdisc_ct.json"
_ct = None

# ADaM variable -> CDISC codelist submission value. Maps the analysis variables whose
# terminology is a clean, enumerable CDISC codelist. Dictionary-coded variables
# (AEDECOD/AEBODSYS via MedDRA, meds via WHODrug) are deliberately absent — those are
# validated against an external dictionary named in the SAP, not an enumerated list.
VARIABLE_CODELIST = {
    "SEX": "SEX",
    "AGEU": "AGEU",
    "DTYPE": "DTYPE",
    "DCDECOD": "NCOMPLT",
    "DCSREAS": "NCOMPLT",
    "EOSSTT": "SBJTSTAT", "EOTSTT": "SBJTSTAT",
    "SAFFL": "NY", "ITTFL": "NY", "EFFFL": "NY", "COMPLFL": "NY",
    "DISCONFL": "NY", "DTHFL": "NY", "TRTEMFL": "NY", "ABLFL": "NY",
    "AOCCFL": "NY", "AOCCPFL": "NY", "AOCCSFL": "NY",
    "AESER": "NY", "AESCAN": "NY", "AESCONG": "NY", "AESDISAB": "NY",
    "AESDTH": "NY", "AESHOSP": "NY", "AESLIFE": "NY",
}


def _load() -> dict:
    global _ct
    if _ct is None:
        _ct = json.loads(_CT_PATH.read_text()) if _CT_PATH.exists() else {}
    return _ct


def ct_values(submission_value: str) -> list[str]:
    """Allowed terms for a CDISC codelist by submission value (e.g. 'SEX'), or []."""
    entry = _load().get(submission_value)
    return entry["values"] if entry else []


def ct_values_for_variable(variable: str) -> list[str]:
    """Allowed CDISC terms for an ADaM variable via VARIABLE_CODELIST, or []."""
    return ct_values(VARIABLE_CODELIST.get(variable.upper(), ""))


def variable_ct() -> dict:
    """{variable: [allowed values]} for every mapped variable that resolved to CT."""
    out = {}
    for var, codelist in VARIABLE_CODELIST.items():
        vals = ct_values(codelist)
        if vals:
            out[var] = vals
    return out


def export_variable_ct() -> Path:
    """Write variable->allowed-values to knowledge/ct/variable_ct.json (read by the
    R conformance check to validate CT independent of the metacore spec's codelists)."""
    out = _CT_DIR / "variable_ct.json"
    out.write_text(json.dumps(variable_ct(), indent=1))
    return out


def available() -> list[str]:
    return sorted(_load())


if __name__ == "__main__":
    print(export_variable_ct())
