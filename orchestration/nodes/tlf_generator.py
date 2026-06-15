import json
import hashlib
import google.generativeai as genai
from orchestration.state import SapientState
from cache.prompt_cache import get_cached, set_cached
from templates.tlf_templates import TLF_SKELETON
from config import GEMINI_API_KEY, CODEGEN_MODEL

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel(CODEGEN_MODEL)


TLF_PROMPT = """
You are an expert clinical programmer. Generate a complete R program for this TLF.

Rules:
- Use tidyverse and pharmaverse packages only
- Follow the mockshell structure exactly
- Match column headers, row structure and footnotes from mockshell
- Return R code only. No explanation. No markdown.

TABLE NUMBER: {table_number}
LOT ENTRY: {lot_entry}
MOCKSHELL: {mockshell}
SKELETON:
{skeleton}
"""


def run(state: SapientState) -> SapientState:
    tlf_programs = {}

    mockshell_map = {
        m["table_number"]: m for m in state["mockshells"]
    }

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
            response = model.generate_content(prompt)
            code = response.text.strip().replace("```r", "").replace("```", "")
            tlf_programs[table_number] = code
            set_cached(cache_key, code)

    return {
        **state,
        "tlf_programs": tlf_programs,
        "current_node": "tlf_generator"
    }