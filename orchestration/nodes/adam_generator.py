import json
import hashlib
from openai import OpenAI
from orchestration.state import SapientState
from cache.prompt_cache import get_cached, set_cached
from templates.adam_templates import ADAM_SKELETON
from config import NVIDIA_API_KEY, NVIDIA_BASE_URL, CODEGEN_MODEL, TEMPERATURE, MAX_TOKENS
from knowledge.vector_store import query_ig

client = OpenAI(base_url=NVIDIA_BASE_URL, api_key=NVIDIA_API_KEY, timeout=60.0)

ADAM_PROMPT = """
You are an expert clinical programmer generating R code for ADaM dataset: {dataset}

STRICT RULES:
- Use ONLY these admiral functions for derivations:
  derive_vars_merged(), derive_var_merged_exist_flag(),
  derive_vars_dt(), derive_vars_dtm(),
  derive_var_age_years(), derive_vars_duration(),
  derive_param_computed(), derive_extreme_records(),derive_vars_extreme_flag(), restrict_derivation(),
  derive_param_exist()
- Load spec via: metacore <- metacore::load_metacore("specs/metacore_spec.rds")
- Export via: xportr::xportr_write(dataset, path = "data/adam/{dataset}.xpt", domain = "{dataset}")
- NO hardcoded values anywhere — all values from metacore or SDTM input
- NO placeholder comments — generate real derivation code
- For non-standard domains, derive population flag by merging ADSL and using SAFFL, FASFL, or PPROTFL as appropriate per the LoT entry population field
- Output must contain only ASCII characters. No unicode, no non-English characters anywhere in the code.

DATASET: {dataset}
LOT ENTRY: {lot_entry}
SKELETON: {skeleton}
ADAMIG CONTEXT: {ig_context}

Return R code only. No explanation. No markdown fences.
"""

def run(state: SapientState) -> SapientState:
    print(f"adam_generator: starting")
    adam_programs = {}
    datasets = set()
    for entry in state["lot_entries"]:
        for ds in entry.get("data_source", []):
            datasets.add(ds)
    print(f"adam_generator: datasets to generate: {datasets}")
    for dataset in datasets:
        print(f"adam_generator: generating {dataset}")
        relevant_entries = [e for e in state["lot_entries"] if dataset in e.get("data_source", [])]
        ig_context = query_ig(query=f"{dataset} derivation rules population flags", doc_type="adamig", n_results=5)
        ig_text = "\n\n".join(ig_context)
        prompt = ADAM_PROMPT.format(
            dataset=dataset,
            lot_entry=json.dumps(relevant_entries[0], indent=2),
            skeleton=ADAM_SKELETON,
            ig_context=ig_text
        )
        cache_key = hashlib.sha256(prompt.encode()).hexdigest()
        cached = get_cached(cache_key)
        if cached:
            adam_programs[dataset] = cached
        else:
            response = client.chat.completions.create(
                model=CODEGEN_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=TEMPERATURE,
                max_tokens=MAX_TOKENS
            )
            print(f"adam_generator: response received for {dataset}")
            code = response.choices[0].message.content.strip().replace("```r", "").replace("```", "")
            adam_programs[dataset] = code
            set_cached(cache_key, code)
    return {**state, "adam_programs": adam_programs, "current_node": "adam_generator"}