from pathlib import Path

FIELD_TO_DELTA_TYPE = {"population": "population_filter", "variables": "variable_addition"}


class DeltaAnchorError(Exception):
    pass


def build_delta(requirement, version_meta, field):
    anchor = version_meta["anchors"][FIELD_TO_DELTA_TYPE[field]]
    req_text = requirement[field]
    if isinstance(req_text, list):
        req_text = " & ".join(req_text)
    return {
        "type": FIELD_TO_DELTA_TYPE[field],
        "source_requirement": requirement.get("requirement_id"),
        "target": field,
        "evidence": {
            "standard_text": anchor["pattern"],
            "requirement_text": req_text,
            "source_sections": requirement.get("source_sections", []),
        },
        "replacement": anchor["replacement"].replace("{population}", req_text),
    }


def build_module_delta(requirement, behavior):
    req_text = str(requirement[behavior["field"]])
    return {
        "type": "module_behavior",
        "source_requirement": requirement.get("requirement_id"),
        "target": behavior["field"],
        "target_file": behavior["target_file"],
        "capability": behavior.get("capability"),
        "evidence": {
            "standard_text": behavior["pattern"],
            "requirement_text": req_text,
            "source_sections": requirement.get("source_sections", []),
        },
        "replacement": behavior["replacement"].replace(
            "{%s}" % behavior["field"], req_text),
    }


def apply_deltas(code, deltas):
    for delta in deltas:
        pattern = delta["evidence"]["standard_text"]
        count = code.count(pattern)
        if count != 1:
            raise DeltaAnchorError(
                f"anchor {pattern!r} occurs {count} times, expected exactly 1")
        code = code.replace(pattern, delta["replacement"])
    return code


def materialize(env, base_rel_path, code, study_id, state_dir):
    out_dir = Path(state_dir) / "artifacts" / study_id
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / Path(base_rel_path).name.replace(".R", "_delta.R")
    out_path.write_text(code)
    return out_path
