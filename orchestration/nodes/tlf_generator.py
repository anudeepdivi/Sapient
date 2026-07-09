import json
import hashlib
from openai import OpenAI
from orchestration.state import SapientState
from cache.prompt_cache import get_cached, set_cached
from templates.tlf_templates import TLF_SKELETON
from config import NVIDIA_API_KEY, NVIDIA_BASE_URL, CODEGEN_MODEL, TEMPERATURE, MAX_TOKENS

client = OpenAI(base_url=NVIDIA_BASE_URL, api_key=NVIDIA_API_KEY, timeout=60.0)

TLF_PROMPT = """
You are an expert clinical programmer generating R code for TLF: {table_number}

STRICT RULES:
- Use rtables or tidytlg for table generation — not base R tables
- Load ADaM data based on data_source field in the LOT ENTRY provided below
- Filter population using flag variables from ADSL (e.g. SAFFL, FASFL, PPROTFL)
- Match column headers EXACTLY as specified in mockshell
- Match row structure EXACTLY as specified in mockshell
- Export MUST use exactly: formatters::export_as_txt(tbl, file = "output/{table_number}.txt")
- DO NOT use rtables::export_as_txt or any other export function
- NO hardcoded values anywhere — all values from metacore or SDTM input
- NO placeholder comments — generate real derivation code
- Column headers must use variable-driven labels, never hardcoded n=XX placeholders
- Output must contain only ASCII characters. No unicode, no non-English characters anywhere in the code.
- Treatment group column labels must be derived from unique values of TRTP or TRTPN in the data, never hardcoded strings

TABLE NUMBER: {table_number}
LOT ENTRY: {lot_entry}
MOCKSHELL: {mockshell}
SKELETON: {skeleton}

Return R code only. No explanation. No markdown fences.
"""

def run(state: SapientState) -> SapientState:
    tlf_programs = {}
    mockshell_map = {m["table_number"]: m for m in state["mockshells"]}
    for entry in state["lot_entries"]:
        table_number = entry["table_number"]
        mockshell = mockshell_map.get(table_number, {})
        prompt = TLF_PROMPT.format(
            table_number=table_number,
            lot_entry=json.dumps(entry, indent=2),
            mockshell=json.dumps(mockshell, indent=2),
            skeleton=TLF_SKELETON
        )
        cache_key = hashlib.sha256(prompt.encode()).hexdigest()
        cached = get_cached(cache_key)
        if cached:
            tlf_programs[table_number] = cached
        else:
            response = client.chat.completions.create(
                model=CODEGEN_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=TEMPERATURE,
                max_tokens=MAX_TOKENS
            )
            code = response.choices[0].message.content.strip().replace("```r", "").replace("```", "")
            tlf_programs[table_number] = code
            set_cached(cache_key, code)
    return {**state, "tlf_programs": tlf_programs, "current_node": "tlf_generator"}