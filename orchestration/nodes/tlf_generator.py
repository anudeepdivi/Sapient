import json
import hashlib
from pathlib import Path
from openai import OpenAI
from orchestration.llm_retry import create_with_retry
from orchestration.state import SapientState
from cache.prompt_cache import get_cached, set_cached
from templates.tlf_templates import TLF_SKELETON
from r_layer.deterministic_checks import strip_markdown_fences
from knowledge.tern_functions import signatures_block
from config import NVIDIA_API_KEY, NVIDIA_BASE_URL, CODEGEN_MODEL, CODEGEN_FALLBACK_MODEL, TEMPERATURE, MAX_TOKENS, BASE_DIR

client = OpenAI(base_url=NVIDIA_BASE_URL, api_key=NVIDIA_API_KEY, timeout=180.0, max_retries=0)

TLF_PROMPT = """
You are an expert clinical programmer generating R code for TLF: {table_number}

ALLOWED FUNCTIONS (rtables/tern) — SIGNATURES. Table construction may use ONLY these,
plus dplyr verbs and haven::read_xpt. Any other table function does not exist:
{signatures}

AVAILABLE ADaM DATASETS AND THEIR REAL COLUMNS — read ONLY these files, reference ONLY these columns:
{adam_columns}

STRICT RULES:
- Build the table as: lyt <- basic_table(...) |> split_cols_by(<treatment variable>) |> ... ; tbl <- build_table(lyt, <dataset>)
- Population flags (SAFFL, ITTFL, EFFFL) are character "Y"/"N" — filter with e.g. SAFFL == "Y", never == 1
- ADSL treatment variables are TRT01P/TRT01A (there is no TRTP in ADSL); occurrence datasets (ADAE) carry TRTA
- Match row structure of the mockshell via split_rows_by/analyze on the listed columns
- Export MUST use exactly: formatters::export_as_txt(tbl, file = "output/{table_number}.txt")
- NO hardcoded counts, percentages, or treatment-arm string literals anywhere
- Output must contain only ASCII characters
- Return R code only. No explanation. No markdown fences.

TABLE NUMBER: {table_number}
LOT ENTRY: {lot_entry}
MOCKSHELL: {mockshell}
SKELETON: {skeleton}
"""

_adam_columns_cache = None


def adam_columns_block() -> str:
    """Real columns of every built ADaM dataset in data/adam/ — the TLF ground truth."""
    global _adam_columns_cache
    if _adam_columns_cache is None:
        import subprocess
        from config import R_EXECUTABLE
        r_code = ('for (f in list.files("data/adam", pattern="[.]xpt$", full.names=TRUE)) '
                  'cat(sub(".xpt","",basename(f)), ": ", paste(names(haven::read_xpt(f)), collapse=", "), "\\n", sep="")')
        result = subprocess.run([R_EXECUTABLE, "-e", r_code], capture_output=True, text=True, timeout=120, cwd=BASE_DIR)
        _adam_columns_cache = result.stdout.strip()
    return _adam_columns_cache


def available_adam() -> set:
    return {p.stem for p in (BASE_DIR / "data/adam").glob("*.xpt")}


def run(state: SapientState) -> SapientState:
    from orchestration.nodes.adam_generator import failure_feedback
    tlf_programs = dict(state.get("tlf_programs") or {})
    tlf_skipped = dict(state.get("tlf_skipped") or {})
    regen = set(state.get("needs_regeneration") or [])
    mockshell_map = {m["table_number"]: m for m in state["mockshells"]}
    built = available_adam()
    for entry in state["lot_entries"]:
        table_number = entry["table_number"]
        if tlf_programs and regen and table_number not in regen:
            continue
        missing = [d for d in entry.get("data_source", []) if d.upper() not in built]
        if missing:
            tlf_skipped[table_number] = f"pending upstream ADaM: {', '.join(missing)}"
            tlf_programs.pop(table_number, None)
            continue
        print(f"tlf_generator: generating {table_number}")
        mockshell = mockshell_map.get(table_number, {})
        prompt = TLF_PROMPT.format(
            table_number=table_number,
            signatures=signatures_block(),
            adam_columns=adam_columns_block(),
            lot_entry=json.dumps(entry, indent=2),
            mockshell=json.dumps(mockshell, indent=2),
            skeleton=TLF_SKELETON
        )
        prompt += failure_feedback(state, table_number)
        cache_key = hashlib.sha256(f"{CODEGEN_MODEL}\n{prompt}".encode()).hexdigest()
        cached = get_cached(cache_key)
        if cached:
            tlf_programs[table_number] = strip_markdown_fences(cached)
        else:
            response = create_with_retry(client, fallback_model=CODEGEN_FALLBACK_MODEL,
                model=CODEGEN_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=TEMPERATURE,
                max_tokens=MAX_TOKENS
            )
            code = strip_markdown_fences(response.choices[0].message.content.strip())
            tlf_programs[table_number] = code
            set_cached(cache_key, code)
    return {**state, "tlf_programs": tlf_programs, "tlf_skipped": tlf_skipped, "current_node": "tlf_generator"}
