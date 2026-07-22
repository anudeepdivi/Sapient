"""Deterministic spec linter — the defect class that silently poisons codegen.

Both spec origins carry the same defects: the human-authored, FDA-submitted pilot
Define.xml says ADLBC BASE = "LB.LBSTNRHI" (the upper normal range, not the baseline
AVAL), leaves AVISITN/PARCAT1 with no derivation, and defines ANRIND as returning 'Y'
against its own L/N/H codelist; generated specs invent CT bands and route variables
through domains the study never loaded. Codegen then faithfully implements whatever it
is told, so these surface as "codegen failures" that no amount of prompt work fixes.

Runs with no model call and no reference dataset — the only correctness check in the
stack that works on a real study on day one.

Usage: python scripts/lint_spec.py ADLBC [--sdtm data/sdtm]
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from config import R_EXECUTABLE, SDTM_SOURCE
from knowledge.adam_registry import resolve_class
from specs.metacore_loader import get_spec_rules

# DOMAIN.COLUMN reference inside a derivation ("LB.LBSTRESN", "ADSL.TRT01A")
REF_RE = re.compile(r"\b([A-Z][A-Z0-9]{1,7})\.([A-Z][A-Z0-9_]*)\b")
# single-quoted or double-quoted literal in derivation text
LITERAL_RE = re.compile(r"['\"]([^'\"]{1,40})['\"]")
# language that shows the author knew a type conversion was needed
CONVERSION_RE = re.compile(
    r"convert|as\.date|numeric|sas date|date9|impute|datepart|input\(|\bdtm?\b", re.I)

# Class-standard relationships (ADaMIG). A derivation that never mentions the variable
# it is defined in terms of is suspect regardless of what it does mention.
# Only relationships that are unambiguous in ADaMIG. Softer conventions (e.g. ADY from
# ADT vs a carried-through --DY) are left alone: a linter that cries wolf gets ignored.
EXPECTED_REFS = {
    "BDS": {"BASE": {"AVAL"}, "CHG": {"AVAL", "BASE"}, "PCHG": {"AVAL", "BASE"},
            "BASEC": {"AVALC"}},
    "TTE": {"AVAL": {"STARTDT", "ADT"}},
}


def source_columns(*dirs: str) -> dict:
    """Real columns per domain/dataset, read from the actual .xpt files, each mapped to
    its storage type ("C" character / "N" numeric). Covers SDTM domains and any
    already-built parent ADaM, so ADSL.TRT01A is verifiable too."""
    existing = [d for d in dirs if (BASE_DIR / d).is_dir()]
    r = ('for (d in c(%s)) for (f in list.files(d, pattern="[.]xpt$", full.names=TRUE)) {'
         ' x <- haven::read_xpt(f);'
         ' cat(toupper(sub("[.]xpt$","",basename(f))), ":",'
         ' paste0(names(x), "=", sapply(x, function(v) if (is.character(v)) "C" else "N"),'
         ' collapse=","), "\\n", sep="") }'
         ) % ",".join(f'"{d}"' for d in existing)
    out = subprocess.run([R_EXECUTABLE, "-e", r], capture_output=True, text=True,
                         timeout=300, cwd=BASE_DIR).stdout
    cols = {}
    for line in out.splitlines():
        if ":" in line:
            dom, names = line.split(":", 1)
            cols[dom.strip()] = {c.split("=")[0].strip().upper(): c.split("=")[-1].strip()
                                 for c in names.split(",") if "=" in c}
    return cols


def lint(dataset: str, sdtm_dir: str) -> list[dict]:
    rules = get_spec_rules(dataset)
    if not rules:
        return [{"variable": "-", "check": "spec-empty", "severity": "error",
                 "detail": f"no spec rules found for {dataset}"}]

    spec_vars = {r["variable"].upper() for r in rules}
    derivations = {r["variable"].upper(): str(r.get("derivation") or "") for r in rules}
    domains = source_columns(sdtm_dir, "data/adam")
    klass = resolve_class(dataset, spec_vars)
    findings, seen = [], set()

    def add(var, check, severity, detail):
        if (var, check, detail) in seen:
            return
        seen.add((var, check, detail))
        findings.append({"variable": var, "check": check, "severity": severity,
                         "detail": detail})

    for r in rules:
        var = r["variable"].upper()
        deriv = str(r.get("derivation") or "").strip()
        origin = str(r.get("origin") or "").strip().lower()
        raw_ct = r.get("ct") or []
        # a single-value codelist can arrive as a bare string; iterating it would
        # compare against its characters
        ct = [raw_ct] if isinstance(raw_ct, str) else [str(c) for c in raw_ct]

        # 1. a derived/assigned variable with no derivation text produces nothing
        if not deriv or deriv in ("{}", "None"):
            if origin in ("derived", "assigned"):
                add(var, "empty-derivation", "error",
                    f"origin '{origin}' but no derivation text")
            continue

        # 2. every DOMAIN.COLUMN reference must resolve to a real column
        for dom, col in REF_RE.findall(deriv):
            if dom == dataset.upper() or dom in spec_vars:
                continue
            if dom in domains:
                if col not in domains[dom]:
                    near = [c for c in domains[dom] if col in c or c in col]
                    add(var, "unknown-source-column", "error",
                        f"{dom}.{col} does not exist in {dom}"
                        + (f" (did you mean {'/'.join(sorted(near)[:3])}?)" if near else ""))
            elif dom.startswith("AD"):
                add(var, "unbuilt-parent", "warning",
                    f"references parent {dom}, which is not built yet — cannot verify {dom}.{col}")
            else:
                add(var, "unknown-source-domain", "error",
                    f"domain {dom} is not present in {sdtm_dir}")

        # 3. quoted literals should be values the variable is allowed to take
        if ct:
            ct_upper = {c.upper() for c in ct}
            for lit in LITERAL_RE.findall(deriv):
                if not lit.strip() or any(ch in lit for ch in "().*/+"):
                    continue
                if lit.upper() not in ct_upper and not lit.replace(".", "").isdigit():
                    add(var, "literal-not-in-ct", "warning",
                        f"derivation assigns '{lit}' but CT is {{{'|'.join(ct)}}}")

        # 4. class-standard relationship: BASE must be about AVAL, CHG about both, ...
        expected = EXPECTED_REFS.get(klass, {}).get(var)
        if expected:
            mentioned = set(re.findall(r"\b[A-Z][A-Z0-9_]*\b", deriv.upper()))
            # a baseline may legitimately be sourced straight from SDTM rather than
            # naming AVAL ("QS.QSSTRESN when QS.QSBLFL=Y") — accept it when it reads
            # the SAME source column AVAL does, and flag only a genuinely different one
            same_source = False
            for anchor in expected:
                anchor_deriv = derivations.get(anchor, "")
                shared = {c for _, c in REF_RE.findall(anchor_deriv)} & \
                         {c for _, c in REF_RE.findall(deriv)}
                if anchor_deriv and shared:
                    same_source = True
            if not (expected & mentioned) and not same_source:
                add(var, "missing-expected-reference", "error",
                    f"{klass} {var} should be derived from {'/'.join(sorted(expected))}"
                    f" but derivation is \"{deriv[:60]}\"")

        # 5. declared numeric/date but sourced from a character column: the derivation
        # has to convert, and if it never says so the merge silently yields character
        # (Phase 2's dropped "converted to SAS date" cue on TRTSDT)
        if str(r.get("type", "")).lower() in ("integer", "float") and not CONVERSION_RE.search(deriv):
            refs = [(d, c, domains.get(d, {}).get(c)) for d, c in REF_RE.findall(deriv)]
            # a numeric reference anywhere means the value plausibly comes from it and
            # the character one is a filter ("VS.VSSTRESN where VS.VSTESTCD='HEIGHT'")
            if refs and not any(t == "N" for _, _, t in refs):
                for dom, col, t in refs:
                    if t == "C":
                        add(var, "conversion-not-stated", "warning",
                            f"declared {r['type']} but source {dom}.{col} is character;"
                            " derivation does not state a conversion")

    return findings


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dataset")
    ap.add_argument("--sdtm", default=SDTM_SOURCE)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    findings = lint(args.dataset, args.sdtm)
    if args.json:
        print(json.dumps(findings, indent=1))
        return 1 if any(f["severity"] == "error" for f in findings) else 0

    errors = [f for f in findings if f["severity"] == "error"]
    warns = [f for f in findings if f["severity"] == "warning"]
    print(f"=== SPEC LINT {args.dataset} "
          f"(class {resolve_class(args.dataset, {r['variable'].upper() for r in get_spec_rules(args.dataset)})}) ===")
    for f in errors + warns:
        mark = "ERROR  " if f["severity"] == "error" else "warning"
        print(f"  {mark} {f['variable']:<10} [{f['check']}] {f['detail']}")
    print(f"summary: {len(errors)} errors, {len(warns)} warnings "
          f"over {len(get_spec_rules(args.dataset))} spec variables")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
