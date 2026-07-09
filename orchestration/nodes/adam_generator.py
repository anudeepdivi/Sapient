import json
import hashlib
from openai import OpenAI
from orchestration.state import SapientState
from cache.prompt_cache import get_cached, set_cached
from templates.adam_templates import (
    ADAM_SKELETON, ADAM_INPUTS, ADMIRAL_TEMPLATE_FILES,
    render_header, render_footer, get_admiral_template
)
from specs.metacore_loader import get_spec_variables
from config import NVIDIA_API_KEY, NVIDIA_BASE_URL, CODEGEN_MODEL, TEMPERATURE, MAX_TOKENS
from knowledge.vector_store import query_ig

client = OpenAI(base_url=NVIDIA_BASE_URL, api_key=NVIDIA_API_KEY, timeout=180.0)

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
- ONLY generate ADSL's own population flags (SAFFL, FASFL, PPROTFL) when {dataset} IS ADSL, by deriving them directly from SDTM (e.g. treatment start date present). Do NOT read SAFFL.xpt/FASFL.xpt/PPROTFL.xpt as SDTM input files — those are variables, not datasets.

These admiral functions have DIFFERENT argument shapes. Do not copy one function's arguments onto another:

EXAMPLE 1 — merge shape (derive_vars_merged, derive_var_merged_exist_flag):
adsl <- adsl |>
  derive_vars_merged(
    dataset_add = ex,
    filter_add = !is.na(EXSTDTC),
    new_vars = exprs(TRTSDT = convert_dtc_to_dt(EXSTDTC)),
    order = exprs(EXSTDTC),
    mode = "first",
    by_vars = exprs(STUDYID, USUBJID)
  )

EXAMPLE 2 — single-date-column shape (derive_vars_dt, derive_vars_dtm): dtc takes ONE column symbol, never c(...); the prefix is a string, not a new_vars list:
adsl <- adsl |>
  derive_vars_dt(
    new_vars_prefix = "TRTS",
    dtc = RFSTDTC
  )

EXAMPLE 3 — named single-variable shape (derive_var_age_years, derive_vars_duration): one input column and one output column, no by_vars/mode:
adsl <- adsl |>
  derive_var_age_years(
    age_var = AGE,
    new_var = AAGE
  )

DATASET: {dataset}
LOT ENTRY: {lot_entry}
SKELETON: {skeleton}
ADAMIG CONTEXT: {ig_context}

Return R code only. No explanation. No markdown fences.
"""

DERIVATION_PROMPT = """
You are an expert clinical programmer writing ONLY the derivation logic for ADaM dataset: {dataset}

This code already exists and runs before yours — do NOT repeat it, do NOT write library() calls, do NOT write read_xpt() calls, do NOT load the metacore spec yourself:
{header}

STRICT RULES:
- Use ONLY these admiral functions for derivations:
  derive_vars_merged(), derive_var_merged_exist_flag(),
  derive_vars_dt(), derive_vars_dtm(),
  derive_var_age_years(), derive_vars_duration(),
  derive_param_computed(), derive_extreme_records(),derive_vars_extreme_flag(), restrict_derivation(),
  derive_param_exist()
- Assign your final derived data frame to a variable named exactly `result` — nothing else reads or exports it
- NO hardcoded values anywhere — all values from metacore or SDTM input
- NO placeholder comments — generate real derivation code
- Output must contain only ASCII characters. No unicode, no non-English characters anywhere in the code.
- For non-standard domains, derive population flag by merging ADSL and using SAFFL, FASFL, or PPROTFL as appropriate per the LoT entry population field
- ONLY derive ADSL's own population flags (SAFFL, FASFL, PPROTFL) when {dataset} IS ADSL, directly from the loaded SDTM inputs (e.g. treatment start date present) — never read them as separate input files, they are variables, not datasets.

These admiral functions have DIFFERENT argument shapes. Do not copy one function's arguments onto another:

EXAMPLE 1 — merge shape (derive_vars_merged, derive_var_merged_exist_flag):
result <- dm |>
  derive_vars_merged(
    dataset_add = ex,
    filter_add = !is.na(EXSTDTC),
    new_vars = exprs(TRTSDT = convert_dtc_to_dt(EXSTDTC)),
    order = exprs(EXSTDTC),
    mode = "first",
    by_vars = exprs(STUDYID, USUBJID)
  )

EXAMPLE 2 — single-date-column shape (derive_vars_dt, derive_vars_dtm): dtc takes ONE column symbol, never c(...); the prefix is a string, not a new_vars list:
result <- result |>
  derive_vars_dt(
    new_vars_prefix = "TRTS",
    dtc = RFSTDTC
  )

EXAMPLE 3 — named single-variable shape (derive_var_age_years, derive_vars_duration): one input column and one output column, no by_vars/mode:
result <- result |>
  derive_var_age_years(
    age_var = AGE,
    new_var = AAGE
  )

REFERENCE ADMIRAL TEMPLATE for {dataset} (official admiral package template — copy its pipe operator style EXACTLY, always `|>` never bare `|`; adapt its derivation logic to the STRICT RULES function list above, do not add functions outside that list):
{admiral_template}

TARGET VARIABLES (from the study metacore spec — {dataset} must end up with these columns, no others invented):
{spec_variables}

DATASET: {dataset}
LOT ENTRY: {lot_entry}
ADAMIG CONTEXT: {ig_context}

Return ONLY the R derivation code (the pipe chain assigning to `result`). No library() calls, no read_xpt() calls, no spec loading, no explanation, no markdown fences.
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

        if dataset in ADAM_INPUTS:
            header = render_header(dataset)
            admiral_template = get_admiral_template(dataset) if dataset in ADMIRAL_TEMPLATE_FILES else "(no reference template available for this dataset)"
            spec_variables = ", ".join(get_spec_variables(dataset))
            prompt = DERIVATION_PROMPT.format(
                dataset=dataset,
                header=header,
                admiral_template=admiral_template,
                spec_variables=spec_variables,
                lot_entry=json.dumps(relevant_entries[0], indent=2),
                ig_context=ig_text
            )
        else:
            prompt = ADAM_PROMPT.format(
                dataset=dataset,
                lot_entry=json.dumps(relevant_entries[0], indent=2),
                skeleton=ADAM_SKELETON,
                ig_context=ig_text
            )

        cache_key = hashlib.sha256(prompt.encode()).hexdigest()
        cached = get_cached(cache_key)
        if cached:
            body = cached
        else:
            response = client.chat.completions.create(
                model=CODEGEN_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=TEMPERATURE,
                max_tokens=MAX_TOKENS
            )
            print(f"adam_generator: response received for {dataset}")
            body = response.choices[0].message.content.strip().replace("```r", "").replace("```", "")
            set_cached(cache_key, body)

        if dataset in ADAM_INPUTS:
            code = f"{header}\n\n{body}\n\n{render_footer(dataset)}"
        else:
            code = body
        adam_programs[dataset] = code
    return {**state, "adam_programs": adam_programs, "current_node": "adam_generator"}