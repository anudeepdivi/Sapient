"""Spec generation (Phase 2c). LLM proposes a per-dataset variable spec from LoT entries
+ available SDTM columns; human reviews the JSON before build_metacore_from_spec.R uses it.

Usage:
    python scripts/gen_spec.py ADSL            # propose -> specs/proposed/ADSL.json
    python scripts/gen_spec.py ADSL --approve  # mark human-approved -> specs/approved/ADSL.json
    python scripts/eval_spec.py ADSL           # score approved/proposed spec vs Define.xml spec
"""
import hashlib
import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from openai import OpenAI
from orchestration.llm_retry import create_with_retry
from cache.prompt_cache import get_cached, set_cached
from config import NVIDIA_API_KEY, NVIDIA_BASE_URL, REASONING_MODEL, TEMPERATURE, MAX_TOKENS

PROPOSED_DIR = BASE_DIR / "specs/proposed"
APPROVED_DIR = BASE_DIR / "specs/approved"

SPEC_PROMPT = """You are a CDISC ADaM specification author.
Propose the variable-level specification for dataset {dataset}.

Return a JSON array only, one object per variable, fields exactly:
- variable: string (ADaM variable name per ADaMIG)
- label: string
- type: "text" or "integer" or "float" or "date"
- origin: "predecessor" | "derived" | "assigned"
- derivation: string (source SDTM column for predecessor, otherwise a one-line derivation rule)

Rules:
- Only variables justified by the LoT entries below or required by ADaMIG core for {dataset}
- Be COMPLETE: include every standard ADaMIG variable group for {dataset} — identifiers, treatment variables with their numeric companions (e.g. TRT01P/TRT01PN), all timing/date variables (treatment start/end, reference end, first visit), treatment duration, every population flag, demographic grouping variables with numeric companions (e.g. AGEGR1/AGEGR1N, RACEN), baseline value variables, and site grouping
- Variable names must be exact, complete ADaMIG names — never truncate (SAFFL not SAFF, ITTFL not ITF)
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


def propose(dataset: str) -> Path:
    lot = json.loads((BASE_DIR / "data/lot_entries.json").read_text())
    relevant = [e for e in lot if dataset in e.get("data_source", [])]
    prompt = SPEC_PROMPT.format(dataset=dataset,
                                lot_entries=json.dumps(relevant, indent=1),
                                sdtm_columns=sdtm_columns())
    cache_key = hashlib.sha256(prompt.encode()).hexdigest()
    content = get_cached(cache_key)
    if content is None:
        client = OpenAI(base_url=NVIDIA_BASE_URL, api_key=NVIDIA_API_KEY, timeout=60.0)
        response = create_with_retry(client, model=REASONING_MODEL,
                                     messages=[{"role": "user", "content": prompt}],
                                     temperature=TEMPERATURE, max_tokens=MAX_TOKENS)
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
