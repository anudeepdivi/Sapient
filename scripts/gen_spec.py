"""Spec generation (Phase 2c). LLM proposes a per-dataset variable spec from LoT entries
+ available SDTM columns; human reviews the JSON before build_metacore_from_spec.R uses it.

Usage:
    python scripts/gen_spec.py ADSL            # propose -> specs/proposed/ADSL.json
    python scripts/gen_spec.py ADSL --approve  # mark human-approved -> specs/approved/ADSL.json
    python scripts/eval_spec.py ADSL           # score approved/proposed spec vs Define.xml spec
"""
import hashlib
import json
import re
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

import fitz
from openai import OpenAI
from orchestration.llm_retry import create_with_retry
from cache.prompt_cache import get_cached, set_cached
from knowledge.adam_registry import classify
from knowledge.adamig_standard import standard_block
from knowledge.ct_lookup import variable_ct
from config import NVIDIA_API_KEY, NVIDIA_BASE_URL, REASONING_MODEL, CODEGEN_MODEL, CODEGEN_FALLBACK_MODEL, TEMPERATURE, MAX_TOKENS, NO_THINKING, SAP_DIR

PROPOSED_DIR = BASE_DIR / "specs/proposed"
APPROVED_DIR = BASE_DIR / "specs/approved"
# The SAP of the study the eval target describes (CDISC pilot CSR Appendix 9).
SAP_FILE = SAP_DIR / "cdiscpilot01_sap.pdf"

# Numbered heading on its own line ("9.2."), title on the next line.
SAP_HEADING_RE = re.compile(r"^(\d+(?:\.\d+)*)\.\s*$")
SAP_STOP_TITLES = ("references", "attachments")  # display templates/appendices follow
# Section-title topics that carry derivation rules for each class — only these
# sections enter the prompt, not the whole SAP.
SAP_TOPICS = {
    "SUBJECT": ["design", "population", "subgroup", "early termination", "disposition",
                "demographic", "baseline", "compliance", "exposure"],
    "OCCDS": ["population", "exposure", "adverse event", "serious"],
    "BDS": ["population", "window", "early termination", "laboratory", "clinical concern",
            "efficacy", "baseline"],
    "TTE": ["design", "population", "early termination", "adverse event"],
}
SPEC_PROMPT = """You are a CDISC ADaM specification author.
Propose the variable-level specification for dataset {dataset}.

Return a JSON array only, one object per variable, fields exactly:
- variable: string (ADaM variable name per ADaMIG)
- label: string
- type: "text" or "integer" or "float" or "date"
- origin: "predecessor" | "derived" | "assigned"
- derivation: string (source SDTM column for predecessor, otherwise a one-line derivation rule)

This dataset is ADaM class {adam_class}.
{standard_variables}

CONTROLLED TERMINOLOGY (CDISC CT — these variables may take ONLY these values; derive to them):
{controlled_terminology}
Variables coded by an external dictionary (AEDECOD/AEBODSYS via MedDRA, medications via WHODrug) are NOT enumerated here — mark their derivation as "coded per <dictionary> as specified in the SAP".

STUDY SAP EXCERPTS (authoritative for this study's populations, category cut-points, baseline, windows and treatment-emergence):
{sap_excerpts}

Rules:
- START from the standard ADaMIG variables above: include every one the study data supports, with exact complete names (SAFFL not SAFF, ITTFL not ITF).
- THEN add study-specific variables the SAP excerpts or LoT entries require (population flags, subgroup/category variables, completion flags, questionnaire totals) — these are the part not covered by the standard.
- Derivation text must carry the SAP's own rule where the SAP states one (population definition, cut-points, windows); never substitute generic values.
- predecessor origins must reference only the SDTM columns listed below
- No markdown, no explanation.

LOT ENTRIES USING {dataset}:
{lot_entries}

AVAILABLE SDTM COLUMNS:
{sdtm_columns}
"""


def sdtm_columns() -> str:
    import subprocess
    from config import R_EXECUTABLE
    r_code = 'for (f in list.files("data/sdtm", full.names=TRUE)) cat(sub(".xpt","",basename(f)), ": ", paste(names(haven::read_xpt(f)), collapse=", "), "\\n", sep="")'
    result = subprocess.run([R_EXECUTABLE, "-e", r_code], capture_output=True, text=True, timeout=120, cwd=BASE_DIR)
    return result.stdout.strip()


def sap_sections(path: Path = SAP_FILE) -> list[tuple[str, str, str]]:
    """(number, title, text) for each numbered SAP section, TOC pages skipped."""
    sections, last = [], ()
    for page in fitz.open(path):
        text = page.get_text()
        if text.count(".....") > 5:  # table-of-contents page
            continue
        lines = text.split("\n")
        for i, line in enumerate(lines):
            m = SAP_HEADING_RE.match(line)
            if m and i + 1 < len(lines) and lines[i + 1].strip()[:1].isalpha():
                num = tuple(int(x) for x in m.group(1).split("."))
                if num > last:  # out-of-order numbers are list items, not headings
                    title = lines[i + 1].strip()
                    if title.lower() in SAP_STOP_TITLES:
                        return [(n, t, " ".join(" ".join(b).split())) for n, t, b in sections]
                    last = num
                    sections.append((m.group(1), title, []))
                    continue
            if sections and not (sections[-1][2] == [] and line.strip() == sections[-1][1]):
                sections[-1][2].append(line)
    return [(n, t, " ".join(" ".join(b).split())) for n, t, b in sections]


def sap_excerpts(adam_class: str) -> str:
    topics = SAP_TOPICS.get(adam_class, ["population"])
    picked = [f"[{n} {t}] {body}" for n, t, body in sap_sections()
              if any(k in t.lower() for k in topics) and body]
    return "\n".join(picked) or "(no SAP sections matched)"


def propose(dataset: str) -> Path:
    lot = json.loads((BASE_DIR / "data/lot_entries.json").read_text())
    relevant = [e for e in lot if dataset in e.get("data_source", [])]
    adam_class = classify(dataset) or "UNKNOWN"
    ct_lines = "\n".join(f"- {var}: {', '.join(vals)}" for var, vals in variable_ct().items())
    prompt = SPEC_PROMPT.format(dataset=dataset,
                                adam_class=adam_class,
                                standard_variables=standard_block(adam_class),
                                controlled_terminology=ct_lines or "(none loaded)",
                                sap_excerpts=sap_excerpts(adam_class),
                                lot_entries=json.dumps(relevant, indent=1),
                                sdtm_columns=sdtm_columns())
    cache_key = hashlib.sha256(f"{CODEGEN_MODEL}\n{NO_THINKING}\n{prompt}".encode()).hexdigest()
    content = get_cached(cache_key)
    if content is None:
        client = OpenAI(base_url=NVIDIA_BASE_URL, api_key=NVIDIA_API_KEY, timeout=300.0, max_retries=0)
        response = create_with_retry(client, model=CODEGEN_MODEL, fallback_model=CODEGEN_FALLBACK_MODEL,  # DiffusionGemma truncates/hallucinates var names — never use it for spec-gen
                                     messages=[{"role": "user", "content": prompt}],
                                     temperature=TEMPERATURE, max_tokens=MAX_TOKENS,
                                     extra_body=NO_THINKING)
        if response.choices[0].finish_reason == "length":
            raise RuntimeError(f"{dataset} spec truncated at max_tokens={MAX_TOKENS}; not cached")
        content = response.choices[0].message.content
        set_cached(cache_key, content)
    raw = content.strip().replace("```json", "").replace("```", "")
    spec = json.loads(raw)
    PROPOSED_DIR.mkdir(exist_ok=True)
    out = PROPOSED_DIR / f"{dataset}.json"
    out.write_text(json.dumps(spec, indent=1))
    return out


def approve(dataset: str) -> Path:
    src = PROPOSED_DIR / f"{dataset}.json"
    APPROVED_DIR.mkdir(exist_ok=True)
    out = APPROVED_DIR / f"{dataset}.json"
    out.write_text(src.read_text())
    return out


if __name__ == "__main__":
    dataset = sys.argv[1]
    if "--approve" in sys.argv:
        print(approve(dataset))
    else:
        print(propose(dataset))
