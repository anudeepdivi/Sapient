"""Mock-shell eval: parse the pilot SAP's 24 display templates (SAP §13.2) into a
reference, and score generated shells against it.

The templates are the eval target, never generator input. Only the SAP body (through
§13.1.1, which lists table titles) may be given to the generator.

Usage:
    python scripts/eval_shells.py reference                 # -> data/reference/pilot_shells.json
    python scripts/eval_shells.py score <generated.json>    # list of shells keyed by "template"
"""
import json
import re
import subprocess
import sys
from pathlib import Path

import fitz

BASE_DIR = Path(__file__).resolve().parent.parent
SAP_FILE = BASE_DIR / "data/sap/cdiscpilot01_sap.pdf"
REF_FILE = BASE_DIR / "data/reference/pilot_shells.json"

TEMPLATE_RE = re.compile(r"^\s*Template\s+(\d+)\s*$")
POP_RE = re.compile(r"Population:\s*(.+?)\s*$")
PLACEHOLDER_RE = re.compile(r"\b(?:x+(?:\.x+)?|0\.x+)\b|\bxx")
NOTE_RE = re.compile(r"^\s*(NOTE|Note|\[\d+\]|Also summarize)")
# Statistic vocabulary; a shell "asks for" a statistic if it appears in its body.
STATS = {
    "n": r"\bn\b", "percent": r"%", "mean": r"\bmean\b", "sd": r"\bsd\b", "se": r"\bse\b",
    "median": r"\bmedian\b", "min": r"\bmin", "max": r"\bmax", "p-value": r"p-value",
    "events": r"\bevents\b", "ls mean": r"ls mean", "ci": r"\bci\b|confidence",
    "range": r"\brange\b", "change from baseline": r"change from baseline",
}


def norm(s: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9%<>=.\- ]", " ", s.lower()).split())


# Population named by category, not wording ("Efficacy Population (Male Subjects)" is
# the Efficacy population). Checked in order: a completer set is also efficacy-based.
POPULATIONS = [("completers", r"complet"), ("efficacy", r"efficacy|evaluable"),
               ("safety", r"safety"), ("itt", r"intent|\bitt\b|randomi"),
               ("all subjects", r"all subjects|all patients|entered|enrolled|screened")]


def population_of(text: str) -> str | None:
    t = text.lower()
    return next((name for name, pat in POPULATIONS if re.search(pat, t)), None)


def stats_in(text: str) -> list[str]:
    t = text.lower()
    return sorted(k for k, pat in STATS.items() if re.search(pat, t))


def parse_page(text: str) -> dict | None:
    lines = [l.rstrip() for l in text.split("\n") if l.strip()]
    idx = next((i for i, l in enumerate(lines) if TEMPLATE_RE.match(l)), None)
    if idx is None:
        return None
    population = next((POP_RE.search(l).group(1) for l in lines[:idx] if POP_RE.search(l)), "")
    title = lines[idx + 1].strip()
    rows, notes, body = [], [], []
    for l in lines[idx + 2:]:
        if NOTE_RE.match(l):
            notes.append(l.strip())
        elif "FINAL SAP" in l:
            break
        else:
            body.append(l)
            if PLACEHOLDER_RE.search(l):
                stub = PLACEHOLDER_RE.split(l, 1)[0]
                parts = [p for p in re.split(r"\s{2,}", stub.strip()) if p]
                if parts and "(N=" not in parts[-1]:  # column-header N cells, not rows
                    rows.append(parts[-1])
    return {"template": int(TEMPLATE_RE.match(lines[idx]).group(1)), "title": title,
            "population": population, "row_labels": rows,
            "stats": stats_in("\n".join(body)), "footnotes": notes}


def build_reference() -> list[dict]:
    shells, last = [], 0
    for n in range(1, fitz.open(SAP_FILE).page_count + 1):
        # -layout keeps the stub column and cells apart; fitz's reading order does not
        text = subprocess.run(["pdftotext", "-f", str(n), "-l", str(n), "-layout", str(SAP_FILE), "-"],
                              capture_output=True, text=True).stdout
        shell = parse_page(text)
        if shell and shell["template"] == last + 1:  # §13.2 runs 1..24; later appendices restart
            shells.append(shell)
            last = shell["template"]
    return shells


def token_f1(a: str, b: str) -> float:
    x, y = set(norm(a).split()), set(norm(b).split())
    if not x or not y:
        return 0.0
    tp = len(x & y)
    return 0.0 if not tp else 2 * tp / (len(x) + len(y))


def set_f1(gen: set, ref: set) -> float:
    if not gen and not ref:
        return 1.0
    tp = len(gen & ref)
    return 0.0 if not tp else 2 * tp / (len(gen) + len(ref))


def row_recall(gen_rows: list[str], ref_rows: list[str]) -> float:
    """Share of reference row labels matched (token F1 >= 0.5) by some generated row."""
    ref = [r for r in ref_rows if norm(r) not in ("etc", "etc..", "")]
    if not ref:
        return 1.0
    return sum(any(token_f1(r, g) >= 0.5 for g in gen_rows) for r in ref) / len(ref)


def score(generated: list[dict], reference: list[dict]) -> dict:
    gen = {int(s["template"]): s for s in generated if "template" in s}
    per = []
    for ref in reference:
        g = gen.get(ref["template"])
        if g is None:
            per.append({"template": ref["template"], "missing": True})
            continue
        g_text = " ".join([*g.get("row_structure", []), *g.get("column_headers", []),
                           g.get("display_format", "")])
        per.append({
            "template": ref["template"],
            "title": round(token_f1(g.get("title", ""), ref["title"]), 2),
            "population": population_of(g.get("population", "")) == population_of(ref["population"]),
            "stats_f1": round(set_f1(set(stats_in(g_text)), set(ref["stats"])), 2),
            "row_recall": round(row_recall(g.get("row_structure", []), ref["row_labels"]), 2),
        })
    scored = [p for p in per if not p.get("missing")]
    mean = lambda k: round(sum(float(p[k]) for p in scored) / len(scored), 3) if scored else 0.0
    return {"n_reference": len(reference), "n_scored": len(scored),
            "title_f1": mean("title"), "population_acc": mean("population"),
            "stats_f1": mean("stats_f1"), "row_recall": mean("row_recall"), "per_template": per}


if __name__ == "__main__":
    if sys.argv[1] == "reference":
        ref = build_reference()
        REF_FILE.write_text(json.dumps(ref, indent=1))
        print(f"{len(ref)} templates -> {REF_FILE}")
    else:
        result = score(json.loads(Path(sys.argv[2]).read_text()), json.loads(REF_FILE.read_text()))
        print(json.dumps({k: v for k, v in result.items() if k != "per_template"}, indent=1))
        for p in result["per_template"]:
            print(" ", p)
