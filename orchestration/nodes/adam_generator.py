import json
import hashlib
import google.generativeai as genai
from orchestration.state import SapientState
from cache.prompt_cache import get_cached, set_cached
from templates.adam_templates import ADAM_SKELETON
from config import GEMINI_API_KEY, CODEGEN_MODEL

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel(CODEGEN_MODEL)


ADAM_PROMPT = """
You are an expert clinical programmer. Generate a complete R program for this ADaM dataset.

Rules:
- Use admiral functions only
- Use metacore object for spec compliance
- Follow the skeleton structure provided
- Temperature is 0 — be deterministic and precise
- Return R code only. No explanation. No markdown.

DATASET: {dataset}
LOT ENTRY: {lot_entry}
SKELETON:
{skeleton}
"""


def run(state: SapientState) -> SapientState:
    adam_programs = {}

    # collect unique datasets across all lot entries
    datasets = set()
    for entry in state["lot_entries"]:
        for ds in entry.get("data_source", []):
            datasets.add(ds)

    for dataset in datasets:
        relevant_entries = [
            e for e in state["lot_entries"]
            if dataset in e.get("data_source", [])
        ]

        prompt = ADAM_PROMPT.format(
            dataset=dataset,
            lot_entry=json.dumps(relevant_entries[0], indent=2),
            skeleton=ADAM_SKELETON
        )

        # check cache first
        cache_key = hashlib.sha256(prompt.encode()).hexdigest()
        cached = get_cached(cache_key)

        if cached:
            adam_programs[dataset] = cached
        else:
            response = model.generate_content(prompt)
            code = response.text.strip().replace("```r", "").replace("```", "")
            adam_programs[dataset] = code
            set_cached(cache_key, code)

    return {
        **state,
        "adam_programs": adam_programs,
        "current_node": "adam_generator"
    }