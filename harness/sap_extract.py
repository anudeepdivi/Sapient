"""Requirements Slice 1: deterministic SAP -> requirement extraction.

Harvests only operationally-stated facts from a constrained SAP fixture:
section-scoped labeled lines (Dataset: / Population expression: / TEAE
definition:) and sponsor-function references. No LLM, stdlib only. Every
extracted field carries verbatim-quote evidence gated on SECTION CONTAINMENT
(whitespace-normalized), so nothing can be emitted that the document did not
state — the mechanical anti-confabulation property. Unmatched prose mentions
become recorded gaps; conflicting values for the same (dataset, field) become
escalated conflicts, never a silently-chosen winner.

Output requirements carry one reserved envelope key (`extraction`) that the
harness resolver ignores; everything else is exactly the resolver's input
vocabulary. The composed output is directly consumable by resolve_case().
"""
import re

from harness.resolver import normalize_expr


class ExtractionError(Exception):
    """Validation-gate rejection: the extraction claims something the
    document does not support, or is structurally incomplete."""


HEADING_RE = re.compile(r"^#{1,6}\s+(?P<num>[\d.]+)\s+(?P<title>.+?)\s*$")

# Positive rules harvest stated facts. "fullmatch" rules anchor to a whole
# stripped line; "search" rules find an in-line phrase.
RULES = [
    {"id": "dataset_decl_v1",
     "pattern": re.compile(r"Dataset\s*[:=]\s*([A-Z][A-Z0-9]*)"),
     "match": "fullmatch", "kind": "dataset"},
    {"id": "population_expr_v1",
     "pattern": re.compile(r"Population(?:\s+expression)?\s*[:=]\s*(\S.*?)\s*"),
     "match": "fullmatch", "kind": "field", "field": "population"},
    {"id": "teae_definition_v1",
     "pattern": re.compile(r"TEAE\s+definition\s*[:=]\s*(\S.*?)\s*"),
     "match": "fullmatch", "kind": "field", "field": "teae_definition",
     "capability": "derive_teae"},
    {"id": "sponsor_function_v1",
     "pattern": re.compile(
         r"\bsponsor\s+(?:library\s+)?function\s+([a-z][a-z0-9_]*)"),
     "match": "search", "kind": "capability"},
]

# Gap rules record prose mentions with no operational statement in the same
# section — absence made explicit instead of silently defaulted.
GAP_RULES = [
    {"id": "population_mention_v1",
     "pattern": re.compile(
         r"\b(?:analysis|safety|per-protocol|intent-to-treat)\s+populations?\b",
         re.IGNORECASE),
     "field": "population"},
]


def sectionize(text):
    """Split into sections keyed by numbered markdown headings."""
    sections = [{"id": "front", "title": "", "start": 1, "pairs": []}]
    current = sections[0]
    for lineno, line in enumerate(text.splitlines(), start=1):
        m = HEADING_RE.match(line)
        if m:
            sections.append({"id": m.group("num"), "title": m.group("title"),
                             "start": lineno, "pairs": []})
            current = sections[-1]
        else:
            current["pairs"].append((lineno, line))
    for sec in sections:
        sec["text"] = "\n".join(line for _, line in sec["pairs"])
    return sections


def _scan_section(sec):
    """One deterministic pass: positive rule candidates + prose-gap hits."""
    candidates, gap_hits = [], []
    for lineno, raw in sec["pairs"]:
        line = raw.strip()
        if not line:
            continue
        for rule in RULES:
            if rule["match"] == "fullmatch":
                m = rule["pattern"].fullmatch(line)
            else:
                m = rule["pattern"].search(line)
            if not m:
                continue
            candidate = {"rule_id": rule["id"], "kind": rule["kind"],
                         "section_id": sec["id"], "line": lineno,
                         "quote": line}
            if rule["kind"] == "dataset":
                candidate["dataset"] = m.group(1).upper()
            elif rule["kind"] == "field":
                candidate["field"] = rule["field"]
                candidate["value"] = m.group(1)
                if rule.get("capability"):
                    candidate["capability"] = rule["capability"]
            else:  # capability
                candidate["capability"] = m.group(1)
            candidates.append(candidate)
        for rule in GAP_RULES:
            if rule["pattern"].search(line):
                gap_hits.append({"rule_id": rule["id"], "field": rule["field"],
                                 "section_id": sec["id"], "line": lineno,
                                 "quote": line})
    return candidates, gap_hits


def extract_requirements(text, study_id="STUDY-UNKNOWN", section_ids=None,
                         env=None):
    """Extract validated requirements from SAP text.

    section_ids restricts extraction to named sections (partial-SAP runs).
    env, when given, soft-flags dataset/capability names outside the sponsor
    registries — informational only, never raised (novel capabilities are a
    legitimate outcome downstream).
    """
    all_sections = sectionize(text)
    if section_ids is not None:
        wanted = [str(s) for s in section_ids]
        known = {s["id"] for s in all_sections}
        missing = [s for s in wanted if s not in known]
        if missing:
            raise ExtractionError(f"sections not found in document: {missing}")
        sections = [s for s in all_sections if s["id"] in wanted]
    else:
        sections = all_sections

    candidates, gaps = [], []
    for sec in sections:
        sec_candidates, sec_gap_hits = _scan_section(sec)
        candidates += sec_candidates
        # a positive hit for the field in the same section wins over the gap
        positives = {c["field"] for c in sec_candidates if c["kind"] == "field"}
        gaps += [{**g, "note": f"{g['field']} discussed but not operationalized "
                               "in this section"}
                 for g in sec_gap_hits if g["field"] not in positives]

    requirements, conflicts = _assemble(candidates, gaps)
    for req in requirements:
        req["study_id"] = study_id

    _validate(requirements, sections)

    report = {
        "sections_scanned": [s["id"] for s in sections],
        "requirements": requirements,
        "conflicts": conflicts,
        "gaps": [g for r in requirements for g in r["extraction"]["gaps"]],
        "case": {"study_requirement": {"study_id": study_id,
                                       "requirements": requirements}},
    }
    if env is not None:
        _flag_vocab(report, env)
    return report


def _assemble(candidates, gaps):
    """Group candidates by dataset; detect conflicts; emit requirements."""
    # anchor every non-dataset candidate to the most recent Dataset line;
    # a field/capability with no anchor behind it is a gate failure.
    # declared_sections maps each dataset to every section that declared or
    # used it — the membership test for attaching prose gaps.
    anchored, datasets, anchor = [], [], None
    declared_sections = {}
    for cand in candidates:
        if cand["kind"] == "dataset":
            anchor = cand["dataset"]
            if cand["dataset"] not in datasets:
                datasets.append(cand["dataset"])
        else:
            if anchor is None:
                raise ExtractionError(
                    f"{cand['rule_id']} at line {cand['line']}: no Dataset "
                    "declaration precedes it")
            anchored.append({**cand, "dataset": anchor})
            cand = anchored[-1]
        declared_sections.setdefault(cand.get("dataset", anchor),
                                     set()).add(cand["section_id"])

    conflicts, requirements = [], []
    for seq, dataset in enumerate(datasets, start=1):
        own = [c for c in anchored if c["dataset"] == dataset]
        fields, evidence, rule_ids = {}, [], set()
        section_ids = set()
        for cand in own:
            rule_ids.add(cand["rule_id"])
            section_ids.add(cand["section_id"])
            if cand["kind"] == "field":
                fields.setdefault(cand["field"], []).append(cand)

        # conflicting values for one (dataset, field): escalate ALL of them,
        # resolve none — the requirement loses the field entirely
        conflicted = set()
        for field, occs in sorted(fields.items()):
            if len({normalize_expr(o["value"]) for o in occs}) > 1:
                conflicts.append({
                    "dataset": dataset, "field": field,
                    "values": [{"value": o["value"],
                                "section_id": o["section_id"],
                                "quote": o["quote"]} for o in occs],
                })
                conflicted.add(field)

        # capabilities ride in on their field candidates; a capability whose
        # only carrier is a conflicted field does not survive the conflict
        capabilities = {c["capability"] for c in own
                        if c.get("capability") and c["kind"] != "field"}
        capabilities |= {c["capability"] for c in own
                         if c.get("capability") and c["kind"] == "field"
                         and c["field"] not in conflicted}

        surviving = {}
        for field, occs in sorted(fields.items()):
            if field not in conflicted:
                cand = occs[0]
                surviving[field] = cand["value"]
                evidence.append({"field": field,
                                 "section_id": cand["section_id"],
                                 "quote": cand["quote"],
                                 "line": cand["line"]})
        own_gaps = [g for g in gaps
                    if g["section_id"] in declared_sections[dataset]]
        for g in own_gaps:
            section_ids.add(g["section_id"])

        # nothing usable survived (e.g. every field conflicted): emit no
        # requirement at all rather than an unconstrained silent REUSE
        if not surviving and not own_gaps and not capabilities:
            continue
        requirements.append({
            "requirement_id": f"REQ-{seq:03d}",
            "study_id": None,
            "type": "adam_dataset",
            "dataset": dataset,
            "capabilities": sorted(capabilities),
            "variables": [],
            **surviving,
            "source_sections": sorted(section_ids),
            "extraction": {
                "status": "explicit",
                "method": "deterministic_rule",
                "rule_ids": sorted(rule_ids),
                "confidence": None,
                "evidence": evidence,
                "gaps": own_gaps,
            },
        })
    return requirements, conflicts


def _flag_vocab(report, env):
    registry = {c["name"] for c in env.list_capabilities()}
    standards = {s["dataset"] for s in env.list_standards()}
    for req in report["requirements"]:
        req["extraction"]["unverified_capabilities"] = sorted(
            set(req["capabilities"]) - registry)
        req["extraction"]["unverified_datasets"] = (
            [] if req["dataset"] in standards else [req["dataset"]])


def validate_quote_containment(items, sections):
    """Mechanical anti-confabulation gate shared by every extraction layer:
    each {section_id, quote} item must be whitespace-contained in its claimed
    section's text or ExtractionError is raised."""
    norm_text = {s["id"]: normalize_expr(s["text"]) for s in sections}
    for item in items:
        quote = normalize_expr(item["quote"])
        if quote not in norm_text.get(item["section_id"], ""):
            raise ExtractionError(
                f"evidence quote not contained in section "
                f"{item['section_id']}: {item['quote']!r}")


def _validate(requirements, sections):
    validate_quote_containment(
        [item for r in requirements
         for item in r["extraction"]["evidence"]], sections)
