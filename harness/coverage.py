"""Coverage checking: independently-authored obligation reference vs plan.

The core oracle of the obligations slice. `evaluate()` compares a reference
set of material obligations (hand-authored from reading the SAP, NEVER from
extractor output) against the current plan — extracted obligations plus,
via a narrow declared bridge, executable requirement-layer facts.

Metric definitions (pinned by unit test, rounded to 4dp):

- obligation_recall      |reference keys detected among emitted obligations| / |reference|
                         Detection includes unresolved items: recovering an
                         ambiguity IS extraction work. Abstract conflict
                         placeholders are never auto-matched.
- obligation_precision   matched non-conflict-emitted obligations / non-conflict-emitted
                         Unresolved-by-indeterminate items match their
                         human-required reference entry; conflicted values are
                         escalated claims, not claims at all, so they sit out.
- grounded_rate          extractor-reported containment-gate rate (1.0 or the
                         gate raised).
- unsupported_inference_rate  inferred obligations absent from the reference /
                         all inferred (0.0 when nothing was inferred).
- unresolved_high_risk_rate   human-required reference entries / |reference|
- coverage_recall        represented reference entries / |reference|
                         Representation = explicit obligation, declared
                         requirement bridge, or inferred obligation (flagged
                         via false-confidence below). Unresolved satisfies
                         NOTHING, and human-required entries are never
                         auto-covered by any plan output — they live only in
                         the outstanding queue. Vacuous convention: 1.0 on an
                         empty reference.
- false_confidence_rate  reference entries covered ONLY by inference /
                         covered entries (0.0 when nothing covered).

Vacuous conventions elsewhere: precision 1.0 when nothing was emitted;
unsupported-inference 0.0 when nothing inferred; false-confidence 0.0 when
nothing covered. Empty plans against empty references are fully "clean" —
coverage is meaningful only relative to an authored reference.
"""
from harness.obligations import subject_key


# Requirement-layer facts that represent obligation kinds downstream. Narrow
# by design: a requirement carrying field F evidences the operational fact F,
# nothing coarser (a population expression does NOT prove every prose
# population obligation is handled).
BRIDGE_FIELDS = {
    "teae_definition": ("parameter", "teae_definition"),
}


def requirement_representations(requirements):
    """Map executable requirements into obligation space via the bridge.
    A field only represents its obligation kind when it actually carries a
    value (an empty carrier proves nothing)."""
    reps = set()
    for req in requirements or ():
        for field, target in BRIDGE_FIELDS.items():
            if req.get(field):
                reps.add(target)
    return reps


def _entry(entry):
    key = entry.get("subject_key") or subject_key(entry["subject"])
    return {"kind": str(entry["kind"]), "key": key,
            "abstract": bool(entry.get("abstract")),
            "human": entry.get("resolution") == "human_required"}


def evaluate(reference, obligations, requirements=None, grounded_rate=1.0):
    """Compare authored reference obligations against the extracted plan."""
    # dedupe: duplicate reference rows are an authoring slip and would
    # permanently depress every fraction via list-length denominators
    ref, seen = [], set()
    for e in reference:
        norm = _entry(e)
        ident = (norm["kind"], norm["key"], norm["abstract"], norm["human"])
        if ident not in seen:
            seen.add(ident)
            ref.append(norm)
    concrete = {(e["kind"], e["key"]) for e in ref if not e["abstract"]}
    human = {(e["kind"], e["key"]) for e in ref if e["human"]}

    emitted = [(o["kind"], o["subject_key"], o["status"], o.get("reason"))
               for o in obligations]

    detected = {k for k in concrete
                if any(k == (ek, ek_key) for ek, ek_key, _, _ in emitted)}

    explicit_reps = {(k, kk) for k, kk, s, _ in emitted if s == "explicit"}
    inferred_reps = {(k, kk) for k, kk, s, _ in emitted if s == "inferred"}
    bridge_reps = requirement_representations(requirements)
    reps_any = explicit_reps | inferred_reps | bridge_reps

    # human-required entries are NEVER auto-covered: they stay exclusively in
    # the outstanding queue regardless of what the plan emits
    resolvable = concrete - human
    covered = resolvable & reps_any
    missing = sorted(f"{kind}/{key}" for kind, key in resolvable - reps_any)
    outstanding = sorted(f"{kind}/{key}" for kind, key in human)
    covered_only_inferred = (covered & inferred_reps) \
        - (explicit_reps | bridge_reps)

    non_conflict = [e for e in emitted if e[3] != "conflict"]
    matched = [e for e in non_conflict
               if (e[0], e[1]) in concrete
               or (e[2] == "unresolved" and (e[0], e[1]) in human)]
    inferred_emitted = [e for e in emitted if e[2] == "inferred"]
    unsupported_inferred = [e for e in inferred_emitted
                            if (e[0], e[1]) not in concrete]

    def pct(num, den, vacuous):
        return round(num / den, 4) if den else vacuous

    metrics = {
        "obligation_recall": pct(len(detected), len(ref), 1.0),
        "obligation_precision": pct(len(matched), len(non_conflict), 1.0),
        "grounded_rate": round(grounded_rate, 4),
        "unsupported_inference_rate":
            pct(len(unsupported_inferred), len(inferred_emitted), 0.0),
        "unresolved_high_risk_rate": pct(len(human), len(ref), 0.0),
        "coverage_recall": pct(len(covered), len(ref), 1.0),
        "false_confidence_rate": pct(len(covered_only_inferred),
                                     len(covered), 0.0),
    }
    return {
        "metrics": metrics,
        "covered": sorted(f"{kind}/{key}" for kind, key in covered),
        "missing": missing,
        "outstanding": outstanding,
        "unrepresented_detections": sorted(
            f"{kind}/{key}" for kind, key in detected - reps_any),
    }
