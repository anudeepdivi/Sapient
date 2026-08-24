"""Requirements Slice 2: deterministic SAP -> analysis-obligation extraction.

Above the operational requirement layer (sap_extract.py) sits a coarser
question: what does this SAP OBLIGATE the analysis effort to do? This module
harvests obligation-bearing statements from constrained SAP prose into nine
declared kinds (KINDS). Design contracts:

- Every obligation carries verbatim-quote evidence gated on section
  containment (the shared anti-confabulation gate); nothing can be emitted
  that the document did not state.
- Status is honest: `explicit` (stated), `inferred` (derived ONLY by a
  declared, id-carrying inference rule with its basis recorded), or
  `unresolved` (obligation-bearing but indeterminate, e.g. "as appropriate",
  or conflicting statements escalated rather than adjudicated).
- Unresolved obligations satisfy nothing downstream; they are surfaced for a
  human instead of silently defaulted.
- Table/listing numbering is deliberately NOT parsed or optimized: numbers in
  background text create no obligations (see TC-O-007).

Known boundary: conflict escalation groups only ANCHORED statements (rules
declaring `anchor`, e.g. statistical methods for the primary analysis). Two
contradictory statements whose rule shapes carry no shared anchor are not
detected as conflicting — they surface as separate explicit obligations.
Widening that requires subject-anchor inference and is a deliberate design
decision, not an oversight.

No LLM, stdlib only. The LLM seam is deliberately absent from this slice:
extraction on constrained prose is fully rule-covered, and an LLM path would
need its own evidence-gating contract before it may exist here.
"""
import re

from harness.sap_extract import (
    ExtractionError,
    sectionize,
    validate_quote_containment,
)

KINDS = frozenset({
    "endpoint", "population", "treatment_group", "parameter", "timepoint",
    "statistical_method", "subgroup", "sensitivity_analysis",
    "output_obligation",
})


def subject_key(text):
    """Canonical comparison form of a subject phrase."""
    return re.sub(r"[^a-z0-9]+", " ", str(text).lower()).strip()


SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
ENUM_SPLIT = re.compile(r"\s*(?:,\s*|\s+and\s+)")
STRIP_THE = re.compile(r"^the\s+", re.IGNORECASE)
STRIP_BY = re.compile(r"^by\s+", re.IGNORECASE)


def _enum_items(payload):
    return [STRIP_THE.sub("", i.strip())
            for i in ENUM_SPLIT.split(payload) if i.strip()]


# Positive prose rules over individual sentences. `mode: match` anchors to the
# sentence start; `search` finds an in-sentence phrase. `requires` gates the
# rule on a co-occurring context phrase (e.g. only primary analyses).
PROSE_RULES = [
    {"id": "endpoint_primary_v1", "kind": "endpoint",
     "pattern": re.compile(r"The primary endpoint is (.+?)\.?$"),
     "mode": "match"},
    {"id": "endpoint_secondary_v1", "kind": "endpoint",
     "pattern": re.compile(r"Secondary endpoints include (.+?)\.?$"),
     "mode": "match", "enumerate": True, "marker": "secondary_endpoints"},
    {"id": "treatment_groups_v1", "kind": "treatment_group",
     "pattern": re.compile(r"two treatment groups,?\s+(\w+)\s+and\s+(\w+)"),
     "mode": "search",
     "subject": lambda m: f"{m.group(1)} vs {m.group(2)}"},
    {"id": "method_ancova_v1", "kind": "statistical_method",
     "pattern": re.compile(r"\banalysed using (ANCOVA[^,.]*)"),
     "mode": "search", "anchor": "primary",
     "requires": re.compile(r"\bprimary\b")},
    {"id": "method_mmrm_v1", "kind": "statistical_method",
     "pattern": re.compile(
         r"\bbased on a (mixed model for repeated measurements)"),
     "mode": "search", "anchor": "primary",
     "requires": re.compile(r"\bprimary\b")},
    {"id": "population_full_v1", "kind": "population",
     "pattern": re.compile(
         r"analysis population for this comparison is the (.+?)\.?$"),
     "mode": "search"},
    {"id": "population_safety_v1", "kind": "population",
     "pattern": re.compile(r"for the (safety population)"),
     "mode": "search"},
    {"id": "subgroup_by_v1", "kind": "subgroup",
     "pattern": re.compile(r"Subgroup summaries are produced by (.+?)\.?$"),
     "mode": "match", "enumerate": True, "strip_by": True},
    {"id": "sensitivity_v1", "kind": "sensitivity_analysis",
     "pattern": re.compile(
         r"A sensitivity analysis of (?:the )?(.+?)\s+will be performed\.?$"),
     "mode": "match"},
    {"id": "output_ae_v1", "kind": "output_obligation",
     "pattern": re.compile(r"adverse events are summarised by (.+?)\s+for\b"),
     "mode": "search", "compose": "adverse events by {}"},
    {"id": "output_continuous_v1", "kind": "output_obligation",
     "pattern": re.compile(r"Continuous endpoints are summarised (.+?)\.?$"),
     "mode": "search",
     "compose": "continuous endpoints summarised {}"},
    {"id": "output_table_v1", "kind": "output_obligation",
     "pattern": re.compile(
         r"The primary efficacy result is presented in a table\.?$"),
     "mode": "match", "subject": lambda m: "primary efficacy result table"},
    {"id": "timepoint_at_v1", "kind": "timepoint",
     "pattern": re.compile(r"\bat (Week \d+|Day \d+)\b", re.IGNORECASE),
     "mode": "search", "multi": True},
]

# Labeled operational lines double as parameter-kind obligations. `key`
# pins the canonical comparison key so prose and requirement layers agree.
LABELED_RULES = [
    {"id": "parameter_teae_v1", "kind": "parameter",
     "pattern": re.compile(r"TEAE\s+definition\s*[:=]\s*(\S.*?)\s*$"),
     "subject": "TEAE definition", "key": "teae_definition"},
]

# Indeterminate-statement detection: obligation-shaped but undetermined.
UNRESOLVED_RULES = [
    {"id": "indeterminate_scope_v1",
     "pattern": re.compile(
         r"\banalyses\b.*\bas appropriate\b|\bmay be performed\b"),
     "reason": "indeterminate scope"},
]

INFERENCES = [
    {"id": "secondary_endpoint_output_v1",
     "basis": "convention: every enumerated secondary endpoint requires "
              "at least one summary presentation"},
]


def _paragraphs(sec):
    """Blank-line-delimited paragraphs keeping per-line structure (labeled
    rules) alongside joined text (prose sentences)."""
    paras, buf = [], []
    start = None
    for lineno, raw in sec["pairs"]:
        if raw.strip():
            if start is None:
                start = lineno
            buf.append((lineno, raw.strip()))
        elif buf:
            paras.append(_para(buf, start))
            buf, start = [], None
    if buf:
        paras.append(_para(buf, start))
    return paras


def _para(buf, start):
    return {"lines": buf,
            "text": " ".join(text for _, text in buf),
            "start_line": start}


def _candidates_from_sentence(sentence, sec_id, line):
    """Positive prose rules over one sentence -> (candidates, marker items)."""
    out, markers = [], []
    for rule in PROSE_RULES:
        if "requires" in rule and not rule["requires"].search(sentence):
            continue
        base = {"rule_id": rule["id"], "kind": rule["kind"],
                "status": "explicit", "section_id": sec_id, "line": line,
                "quote": sentence}
        if "anchor" in rule:
            base["anchor"] = rule["anchor"]
        if rule.get("multi"):
            seen = set()
            for m in rule["pattern"].finditer(sentence):
                subject = m.group(1)
                if subject_key(subject) in seen:
                    continue
                seen.add(subject_key(subject))
                out.append({**base, "subject": subject})
            continue
        m = (rule["pattern"].match(sentence) if rule["mode"] == "match"
             else rule["pattern"].search(sentence))
        if not m:
            continue
        if rule.get("enumerate"):
            for item in _enum_items(m.group(1)):
                if rule.get("strip_by"):
                    item = STRIP_BY.sub("", item)
                out.append({**base, "subject": item})
            if rule.get("marker"):
                markers.extend({"subject": i, "key": subject_key(i),
                                "section_id": sec_id, "line": line,
                                "quote": sentence}
                               for i in _enum_items(m.group(1)))
        else:
            subject = (rule["subject"](m) if callable(rule.get("subject"))
                       else m.group(1))
            if rule.get("compose"):
                subject = rule["compose"].format(subject)
            out.append({**base, "subject": subject})
    return out, markers


def _line_at(offsets, char_idx):
    """Map a character offset in a joined paragraph back to its source line."""
    for lineno, start, end in offsets:
        if start <= char_idx < end:
            return lineno
    return offsets[-1][0]


def extract_obligations(text, section_ids=None):
    """Extract evidence-gated analysis obligations from SAP text.

    section_ids restricts extraction to named sections (partial-plan runs).
    Raises ExtractionError if a named section is absent or any evidence quote
    fails containment in its claimed section.
    """
    all_sections = sectionize(text)
    if section_ids is not None:
        wanted = [str(s) for s in section_ids]
        known = {s["id"] for s in all_sections}
        missing_secs = [s for s in wanted if s not in known]
        if missing_secs:
            raise ExtractionError(
                f"sections not found in document: {missing_secs}")
        sections = [s for s in all_sections if s["id"] in wanted]
    else:
        sections = all_sections

    collected, markers = [], []
    for sec in sections:
        for para in _paragraphs(sec):
            # labeled operational lines (one rule per physical line)
            for lineno, line_text in para["lines"]:
                for rule in LABELED_RULES:
                    m = rule["pattern"].search(line_text)
                    if m:
                        collected.append({
                            "rule_id": rule["id"], "kind": rule["kind"],
                            "status": "explicit", "subject": rule["subject"],
                            "subject_key_override": rule.get("key"),
                            "value": m.group(1), "section_id": sec["id"],
                            "line": lineno, "quote": line_text})
                        break
            # prose sentences over the joined paragraph; evidence lines are
            # recovered from each sentence's character offset
            offsets, pos = [], 0
            for lineno, line_text in para["lines"]:
                offsets.append((lineno, pos, pos + len(line_text)))
                pos += len(line_text) + 1
            spans, pos = [], 0
            for sm in SENTENCE_SPLIT.finditer(para["text"]):
                spans.append((pos, sm.start()))
                pos = sm.end()
            spans.append((pos, len(para["text"])))
            for start, end in spans:
                sentence = para["text"][start:end].strip()
                if not sentence:
                    continue
                line_no = _line_at(offsets, start)
                cands, sent_markers = _candidates_from_sentence(
                    sentence, sec["id"], line_no)
                collected.extend(cands)
                markers.extend(sent_markers)
                # indeterminacy is a property of the sentence itself: it is
                # recorded even when a positive rule also harvested it
                for rule in UNRESOLVED_RULES:
                    if rule["pattern"].search(sentence):
                        collected.append({
                            "rule_id": rule["id"],
                            "kind": "indeterminate",
                            "status": "unresolved",
                            "reason": rule["reason"],
                            "subject": sentence.rstrip(".")[:80],
                            "section_id": sec["id"],
                            "line": line_no,
                            "quote": sentence})
                        break

    # declared inference rules: derived obligations, visibly marked
    existing_outputs = {subject_key(c["subject"]) for c in collected
                        if c["kind"] == "output_obligation"}
    for marker in markers:
        subject = f"{marker['subject']} summary"
        if any(subject_key(subject) in k for k in existing_outputs):
            continue
        collected.append({
            "rule_id": INFERENCES[0]["id"], "kind": "output_obligation",
            "status": "inferred", "subject": subject,
            "section_id": marker["section_id"], "line": marker["line"],
            "quote": marker["quote"],
            "inference": {"basis_id": INFERENCES[0]["id"],
                          "basis": INFERENCES[0]["basis"]}})

    obligations, conflicts = _dedupe_and_conflict(collected)

    validate_quote_containment(
        [{"section_id": e["section_id"], "quote": e["quote"]}
         for o in obligations for e in o["evidence"]], sections)

    report = {
        "sections_scanned": [s["id"] for s in sections],
        "obligations": obligations,
        "conflicts": conflicts,
        "unresolved_ids": [o["obligation_id"] for o in obligations
                           if o["status"] == "unresolved"],
        "inferred_ids": [o["obligation_id"] for o in obligations
                         if o["status"] == "inferred"],
        "counts": {
            "total": len(obligations),
            "explicit": sum(1 for o in obligations
                            if o["status"] == "explicit"),
            "inferred": sum(1 for o in obligations
                            if o["status"] == "inferred"),
            "unresolved": sum(1 for o in obligations
                              if o["status"] == "unresolved"),
        },
        "grounded_rate": 1.0,  # the containment gate raised otherwise
    }
    return report


def _dedupe_and_conflict(cands):
    """Collapse duplicate subjects (merging evidence), escalate anchored
    disagreements into conflicts, assign stable doc-order ids."""
    merged, order = {}, []
    for seq, cand in enumerate(cands):
        skey = cand.get("subject_key_override") or subject_key(cand["subject"])
        key = (cand["kind"], skey)
        if key in merged:
            ev = {"section_id": cand["section_id"], "line": cand["line"],
                  "quote": cand["quote"]}
            if ev not in merged[key]["evidence"]:
                merged[key]["evidence"].append(ev)
            merged[key]["rule_ids"].append(cand["rule_id"])
            continue
        entry = {
            "kind": cand["kind"], "status": cand["status"],
            "subject": cand["subject"], "subject_key": skey,
            "rule_ids": [cand["rule_id"]],
            "evidence": [{"section_id": cand["section_id"],
                          "line": cand["line"], "quote": cand["quote"]}],
            "_order": seq,
        }
        for opt in ("reason", "inference", "anchor", "value"):
            if opt in cand:
                entry[opt] = cand[opt]
        merged[key] = entry
        order.append(entry)

    conflicts = []
    groups = {}
    for entry in order:
        if "anchor" in entry:
            groups.setdefault((entry["kind"], entry["anchor"]), []).append(entry)
    for (kind, anchor), members in sorted(groups.items()):
        if len({e["subject"] for e in members}) > 1:
            conflicts.append({
                "kind": kind, "anchor": anchor,
                "values": [{"value": e["subject"],
                            "section_id": e["evidence"][0]["section_id"],
                            "quote": e["evidence"][0]["quote"]}
                           for e in members],
            })
            for e in members:
                e["status"] = "unresolved"
                e["reason"] = "conflict"

    order.sort(key=lambda e: e["_order"])
    for seq, entry in enumerate(order, start=1):
        entry["obligation_id"] = f"OB-{seq:03d}"
        del entry["_order"]
    return order, conflicts
