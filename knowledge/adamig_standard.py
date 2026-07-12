"""ADaMIG standard variable groups by ADaM class.

Public CDISC ADaMIG structure — the standard skeleton every conformant ADaM dataset
of a given class carries. Used to GROUND spec generation so the model completes a
known standard rather than inventing variables from scratch (the recall gap). This is
the public standard, NOT the pilot's Define.xml (which stays the held-out eval target):
grounding here is legitimate domain knowledge, not leakage.

Class comes from knowledge.adam_registry.classify(). Study-specific variables
(custom parameters, MMSETOT, subgroup flags) are NOT here — those come from the SAP
and SDTM availability, which is exactly the part spec-gen must reason about.
"""

# Identifiers shared across every ADaM dataset (treatment vars differ by class:
# ADSL carries subject-level TRT01P/TRT01A; BDS/OCCDS carry period/occurrence-level
# TRTP/TRTPN/TRTA/TRTAN, which is why they were missed before this split).
_COMMON = ["STUDYID", "USUBJID", "SUBJID", "SITEID"]

# Analysis treatment + timing carried from ADSL onto every non-subject dataset.
_ANALYSIS_TRT = ["TRTP", "TRTPN", "TRTA", "TRTAN", "TRTSDT", "TRTEDT"]

_DEMOG = ["AGE", "AGEGR1", "AGEGR1N", "SEX", "RACE", "RACEN", "ETHNIC",
          "SAFFL", "ITTFL", "EFFFL"]

ADAMIG_STANDARD = {
    "SUBJECT": {  # ADSL
        "structure": "one row per subject",
        "variables": _COMMON + [
            "TRT01P", "TRT01PN", "TRT01A", "TRT01AN",
            "ARM", "ACTARM", "TRTSDT", "TRTEDT", "TRTDURD",
            "AGE", "AGEGR1", "AGEGR1N", "AGEGR2", "AGEGR2N", "AGEU",
            "SEX", "RACE", "RACEN", "ETHNIC",
            "SAFFL", "ITTFL", "EFFFL", "COMPLFL",
            "DISCONFL", "DTHFL", "EOSSTT", "DCDECOD", "DCSREAS",
            "RFSTDTC", "RFENDTC", "BRTHDTC",
        ],
    },
    "OCCDS": {  # ADAE, ADCM, ADMH
        "structure": "one row per record (event/intervention) per subject",
        "variables": _COMMON + _ANALYSIS_TRT + _DEMOG + [
            "ASTDT", "ASTDTF", "ASTDY", "AENDT", "AENDY", "ADURN", "ADURU",
            "AESEQ", "TRTEMFL", "AOCCFL", "AOCCPFL", "AOCCSFL",
        ],
    },
    "BDS": {  # ADVS, ADLB, ADADAS, ADEG, ADQS, ...
        "structure": "one row per subject per parameter per analysis timepoint",
        "variables": _COMMON + _ANALYSIS_TRT + _DEMOG + [
            "PARAMCD", "PARAM", "PARAMN", "PARCAT1",
            "AVAL", "AVALC", "BASE", "BASETYPE", "CHG", "PCHG",
            "ABLFL", "AVISIT", "AVISITN", "VISIT", "VISITNUM", "ADT", "ADY",
            "ANRIND", "BNRIND", "ANL01FL", "DTYPE",
        ],
    },
    "TTE": {  # ADTTE
        "structure": "one row per subject per time-to-event parameter",
        "variables": _COMMON + _ANALYSIS_TRT + _DEMOG + [
            "PARAMCD", "PARAM", "PARAMN",
            "AVAL", "STARTDT", "ADT", "CNSR", "EVNTDESC", "SRCDOM", "SRCVAR", "SRCSEQ",
        ],
    },
}


def standard_block(adam_class: str) -> str:
    """Render the standard variable skeleton for a class as prompt grounding."""
    spec = ADAMIG_STANDARD.get(adam_class)
    if not spec:
        return "(no standard template for this class — derive variables from SAP + ADaMIG core)"
    # de-dupe while preserving order
    seen, ordered = set(), []
    for v in spec["variables"]:
        if v not in seen:
            seen.add(v)
            ordered.append(v)
    return f"Structure: {spec['structure']}\nStandard ADaMIG variables (include all that the study supports): " + ", ".join(ordered)
