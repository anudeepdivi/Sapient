import json
import google.generativeai as genai
from orchestration.state import SapientState
from config import GEMINI_API_KEY, REASONING_MODEL

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel(REASONING_MODEL)


LOT_PROMPT = """
You are an expert clinical programmer with deep knowledge of CDISC standards.

Given the SAP sections below, extract every analysis requirement and generate a 
structured List of Tables (LoT).

For each TLF return a JSON object with exactly these fields:
- table_number: string (e.g. "14.1.1")
- title: string
- population: string (e.g. "Safety Population", "Full Analysis Set")
- data_source: list of strings (ADaM datasets needed e.g. ["ADAE", "ADSL"])
- statistical_method: string (e.g. "Descriptive statistics", "Kaplan-Meier")
- tlf_type: string — one of "table", "listing", "figure"
- primary_endpoint: boolean

Return a JSON array of these objects only. No explanation. No markdown.

STUDY METADATA:
{metadata}

SAP SECTIONS:
{sap_text}
"""


def build_prompt(state: SapientState) -> str:
    metadata = json.dumps(state["study_metadata"], indent=2)

    # prioritise endpoint and analysis sections
    priority_sections = [
        "endpoint", "objective", "analysis", 
        "statistical method", "population"
    ]
    
    chunks = state["sap_chunks"]
    
    sorted_chunks = sorted(
        chunks,
        key=lambda c: any(
            p in c["section"].lower() for p in priority_sections
        ),
        reverse=True
    )

    # take top 20 chunks to stay within context
    sap_text = "\n\n---\n\n".join(
        [f"[{c['section']}]\n{c['text']}" for c in sorted_chunks[:20]]
    )

    return LOT_PROMPT.format(metadata=metadata, sap_text=sap_text)


def validate_lot(lot_entries: list[dict]) -> list[dict]:
    required_fields = {
        "table_number", "title", "population",
        "data_source", "statistical_method", 
        "tlf_type", "primary_endpoint"
    }
    
    validated = []
    for entry in lot_entries:
        missing = required_fields - set(entry.keys())
        if missing:
            entry["_warnings"] = f"Missing fields: {missing}"
        validated.append(entry)
    
    return validated


def run(state: SapientState) -> SapientState:
    prompt = build_prompt(state)
    response = model.generate_content(prompt)
    
    raw = response.text.strip().replace("```json", "").replace("```", "")
    try:
        lot_entries = json.loads(raw)
    except json.JSONDecodeError:
        return {**state, "errors": state.get("errors", []) + ["lot_generator: failed to parse LLM response"], "current_node": "lot_generator"}
    lot_entries = validate_lot(lot_entries)

    return {
        **state,
        "lot_entries": lot_entries,
        "current_node": "lot_generator"
    }