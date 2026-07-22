"""Controlled vocabulary of ADaM datasets.

The LoT generator was free-inventing dataset names (ADPD, ADOS, ADIG, ...) in its
data_source field — the documented 21-50% clinical-LLM hallucination class. This
registry bounds data_source to real ADaM datasets, tags each with its structural
class (feeds BDS/OCCDS handling), and flags anything off-list for human review
rather than silently generating a dataset that can never be built or scored.

Class values: SUBJECT (ADSL only), OCCDS (occurrence/event), BDS (basic data
structure, value/visit), TTE (time-to-event, a BDS family needing its own template).

Class is resolved by name for known datasets and by variable-structure inference for
sponsor-defined ones (resolve_class) — the codegen conventions key on class, never name.
"""
import re

ADAM_REGISTRY = {
    "ADSL": {"class": "SUBJECT", "label": "Subject-Level Analysis Dataset"},
    "ADAE": {"class": "OCCDS", "label": "Adverse Events Analysis Dataset"},
    "ADCM": {"class": "OCCDS", "label": "Concomitant Medications Analysis Dataset"},
    "ADMH": {"class": "OCCDS", "label": "Medical History Analysis Dataset"},
    "ADEX": {"class": "OCCDS", "label": "Exposure Analysis Dataset"},
    "ADVS": {"class": "BDS", "label": "Vital Signs Analysis Dataset"},
    "ADLB": {"class": "BDS", "label": "Laboratory Analysis Dataset"},
    "ADLBC": {"class": "BDS", "label": "Laboratory Chemistry Analysis Dataset"},
    "ADLBH": {"class": "BDS", "label": "Laboratory Hematology Analysis Dataset"},
    "ADEG": {"class": "BDS", "label": "ECG Analysis Dataset"},
    "ADADAS": {"class": "BDS", "label": "ADAS-Cog Analysis Dataset"},
    "ADNPIX": {"class": "BDS", "label": "NPI-X Analysis Dataset"},
    "ADTTE": {"class": "TTE", "label": "Time-to-Event Analysis Dataset"},
    "ADQS": {"class": "BDS", "label": "Questionnaire Analysis Dataset"},
    "ADEFF": {"class": "BDS", "label": "Efficacy Analysis Dataset"},
    "ADPC": {"class": "BDS", "label": "Pharmacokinetic Concentrations Analysis Dataset"},
    "ADPP": {"class": "BDS", "label": "PK Parameters Analysis Dataset"},
}


def allowed_datasets_block() -> str:
    """Compact vocabulary for a generation prompt: NAME (class) - label."""
    return "\n".join(f"{name} ({meta['class']}) - {meta['label']}"
                     for name, meta in ADAM_REGISTRY.items())


def classify(dataset: str) -> str | None:
    meta = ADAM_REGISTRY.get(dataset.upper())
    return meta["class"] if meta else None


# Structural class signatures (ADaMIG). A sponsor-defined dataset carries no
# recognisable NAME, but its variable list still carries its class — which is what
# the codegen conventions actually dispatch on. Order matters: TTE and BDS both
# carry PARAMCD/AVAL, so CNSR is tested first.
_OCCDS_MARKER = re.compile(r"^[A-Z]{2}(SEQ|DECOD|TERM|BODSYS)$")


def infer_class(variables) -> str | None:
    """Infer the structural class from a dataset's variable names alone.

    Lets non-standard (sponsor-specific) datasets reach the class-keyed codegen
    conventions, which key on class and never on dataset name."""
    v = {str(x).upper() for x in variables}
    if "CNSR" in v:
        return "TTE"
    if "PARAMCD" in v and ("AVAL" in v or "AVALC" in v):
        return "BDS"
    # period-indexed treatment (TRT01P/TRT01A) is subject-level; BDS/OCCDS/TTE carry
    # the un-indexed TRTP/TRTA. Tested before the OCCDS markers because subject-level
    # datasets legitimately carry --DECOD variables (ADSL has DCDECOD).
    if {"TRT01P", "TRT01A"} & v:
        return "SUBJECT"
    if any(_OCCDS_MARKER.match(x) for x in v):
        return "OCCDS"
    return None


def resolve_class(dataset: str, variables=None) -> str | None:
    """Registry first (known datasets), structural inference second (everything else)."""
    return classify(dataset) or (infer_class(variables) if variables else None)


def constrain_data_source(entries: list[dict]) -> tuple[list[dict], set[str]]:
    """Filter each LoT entry's data_source to registry datasets. Off-list names are
    dropped from data_source and collected into the entry's _dataset_warnings and the
    returned set (for a human-review surface) — never silently kept."""
    flagged = set()
    for entry in entries:
        sources = entry.get("data_source", []) or []
        kept, unknown = [], []
        for ds in sources:
            (kept if ds.upper() in ADAM_REGISTRY else unknown).append(ds)
        if unknown:
            entry["_dataset_warnings"] = f"off-registry datasets flagged for review: {unknown}"
            flagged.update(unknown)
        entry["data_source"] = kept
    return entries, flagged
