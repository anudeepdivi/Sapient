import json

from config import HARNESS_STATE_DIR
from harness.deltas import (
    DELTAABLE_FIELDS,
    FIELD_TO_DELTA_TYPE,
    build_delta,
    build_module_delta,
)
from harness.decisions import request_decision

RESERVED_FIELDS = {"file", "version", "status", "validated", "anchors",
                   "purpose", "notes", "module_behaviors", "extraction"}
NON_COMPARABLE = RESERVED_FIELDS | {
    "requirement_id", "study_id", "type", "dataset", "capabilities", "source_sections",
}


def normalize_expr(expr):
    return "".join(str(expr).split())


def _declared_fields(requirement):
    return {k: v for k, v in requirement.items()
            if k not in NON_COMPARABLE and v not in (None, [], "")}


def _field_equal(field, req_value, cand_value):
    if field == "population":
        return normalize_expr(req_value) == normalize_expr(cand_value)
    return req_value == cand_value


def _contradicts(version, declared):
    for field, value in declared.items():
        # a mismatch on a delta-able field is a delta, not a contradiction
        if field in version and field not in DELTAABLE_FIELDS \
                and not _field_equal(field, value, version[field]):
            return True
    return False


def _differing_fields(survivors):
    fields = set().union(*(set(v) - RESERVED_FIELDS for v in survivors))
    return sorted(f for f in fields
                  if len({json.dumps(v.get(f), sort_keys=True) for v in survivors}) > 1)


def _ambiguity_decision(dataset, requirement, survivors, differing, state_dir):
    candidates = []
    for v in survivors:
        candidates.append({
            "file": f"standards/{dataset.lower()}/{v['file']}",
            "version": str(v["version"]),
            "attributes": {f: v[f] for f in differing if f in v},
        })
    context = {
        "question": f"Which approved {dataset} standard applies to study {requirement.get('study_id')}?",
        "evidence": {
            "study_id": requirement.get("study_id"),
            "dataset": dataset,
            "candidates": candidates,
            "differing_fields": {
                f: sorted({str(v[f]) for v in survivors if f in v}) for f in differing
            },
        },
        "possible_interpretations": [
            f"{c['file']}: " + ", ".join(f"{k}={v}" for k, v in c["attributes"].items())
            for c in candidates
        ],
        "recommendation": None,
        "confidence": 0.0,
        "downstream_impact": (
            f"The selected {dataset} version determines its derivation behavior; "
            "all downstream artifacts depend on the choice."
        ),
    }
    return request_decision("STANDARD_SELECTION_AMBIGUITY", context, state_dir)


def resolve(requirement, env, state_dir=None):
    state_dir = state_dir or HARNESS_STATE_DIR
    base = {"requirement_id": requirement.get("requirement_id"), "dataset": requirement.get("dataset")}

    registry = {c["name"] for c in env.list_capabilities()}
    missing = [name for name in requirement.get("capabilities", []) if name not in registry]
    if missing:
        return {**base, "status": "NOVEL_CAPABILITY", "action": "CREATE_PROPOSAL",
                "missing_capabilities": missing}

    std = env.get_standard(requirement["dataset"])
    candidates = [v for v in (std or {}).get("versions", [])
                  if v.get("status") == "approved" and v.get("validated")]
    if not candidates:
        return {**base, "status": "NOVEL_CAPABILITY", "action": "CREATE_PROPOSAL",
                "reason": "NO_APPROVED_STANDARD"}

    declared = _declared_fields(requirement)
    survivors = [v for v in candidates if not _contradicts(v, declared)]
    if not survivors:
        return {**base, "status": "WAITING_FOR_HUMAN", "reason": "STANDARD_NOT_APPLICABLE"}

    if len(survivors) > 1:
        differing = _differing_fields(survivors)
        discriminating = [f for f in differing if f in declared]
        if discriminating:
            matched = [v for v in survivors
                       if all(_field_equal(f, declared[f], v[f]) for f in discriminating)]
            if matched:
                # no candidate matches exactly: all remain equally delta-able bases
                survivors = matched
        if len(survivors) > 1:
            decision = _ambiguity_decision(requirement["dataset"], requirement,
                                           survivors, differing, state_dir)
            return {**base, "status": "WAITING_FOR_HUMAN",
                    "reason": "STANDARD_SELECTION_AMBIGUITY", "action": "ASK_HUMAN",
                    "candidates": [v["file"] for v in survivors],
                    "differing_fields": differing, "decision": decision}

    version = survivors[0]
    behaviors = {}
    for behavior in (version.get("module_behaviors") or []):
        required = ("field", "value", "target_file", "pattern", "replacement")
        if any(behavior.get(k) in (None, "") for k in required):
            return {**base, "status": "WAITING_FOR_HUMAN",
                    "reason": "BEHAVIOR_DECLARATION_INCOMPLETE",
                    "standard_match": version["file"]}
        if behavior["field"] in behaviors:
            return {**base, "status": "WAITING_FOR_HUMAN",
                    "reason": "DUPLICATE_BEHAVIOR_DECLARATION",
                    "standard_match": version["file"], "field": behavior["field"]}
        behaviors[behavior["field"]] = behavior
    unknown = [f for f in declared if f not in version and f not in behaviors]
    if unknown:
        return {**base, "status": "WAITING_FOR_HUMAN",
                "reason": "UNKNOWN_REQUIREMENT_FIELD",
                "fields": unknown, "standard_match": version["file"]}
    diffs = [f for f in declared
             if f in version and not _field_equal(f, declared[f], version[f])]
    module_diffs = [f for f in declared if f in behaviors
                    and normalize_expr(declared[f])
                    != normalize_expr(behaviors[f]["value"])]
    if diffs and module_diffs:
        # no consumer applies program-grain and module-grain deltas together
        return {**base, "status": "WAITING_FOR_HUMAN",
                "reason": "MIXED_GRAIN_DELTA_UNSUPPORTED",
                "standard_match": version["file"],
                "fields": sorted(diffs + module_diffs)}
    if not diffs and not module_diffs:
        return {**base, "status": "RESOLVED", "action": "REUSE",
                "standard_match": version["file"], "version": str(version["version"]),
                "delta_count": 0, "generate_new_program": False}
    deltas = []
    for field in diffs:
        if FIELD_TO_DELTA_TYPE.get(field) not in (version.get("anchors") or {}):
            return {**base, "status": "WAITING_FOR_HUMAN", "reason": "DELTA_ANCHOR_MISSING",
                    "standard_match": version["file"], "field": field}
        deltas.append(build_delta(requirement, version, field))
    for field in module_diffs:
        deltas.append(build_module_delta(requirement, behaviors[field]))
    return {**base, "status": "RESOLVED", "action": "APPLY_DELTA",
            "standard_match": version["file"], "version": str(version["version"]),
            "deltas": deltas, "delta_count": len(deltas),
            "delta_types": [d["type"] for d in deltas]}


def resolve_case(case, env, state_dir=None):
    return [resolve(req, env, state_dir)
            for req in case["study_requirement"]["requirements"]]
