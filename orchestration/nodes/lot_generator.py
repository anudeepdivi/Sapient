import json
import hashlib
from openai import OpenAI
from cache.prompt_cache import get_cached, set_cached
from orchestration.llm_retry import create_with_retry
from orchestration.state import SapientState
from config import NVIDIA_API_KEY, NVIDIA_BASE_URL, REASONING_MODEL, TEMPERATURE, MAX_TOKENS

client = OpenAI(base_url=NVIDIA_BASE_URL, api_key=NVIDIA_API_KEY, timeout=60.0)

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
Completeness rules — a submission LoT is exhaustive, not representative:
- One table per endpoint PER analysis type: primary analysis, each sensitivity analysis, each subgroup analysis, and each timepoint/visit analysis the SAP mentions gets its OWN numbered table
- Efficacy endpoints typically produce a 14.3.x series with many entries (10+ in a real study) — enumerate them all: primary, secondary, per-parameter, per-visit, responder/categorical versions
- Standard safety set: AE summary, AEs by SOC/PT, severity, relatedness, serious AEs, deaths, discontinuations due to AE, labs (with shift tables), vital signs
- Standard baseline set: disposition, demographics, baseline characteristics, medical history, concomitant medications, protocol deviations
- If the SAP names N endpoints and M populations, expect roughly one table per endpoint-population-analysis combination — err on the side of MORE tables
Return a JSON array of these objects only. No explanation. No markdown.
STUDY METADATA:
{metadata}
SAP SECTIONS:
{sap_text}
"""

def build_prompt(state: SapientState) -> str:
    metadata = json.dumps(state["study_metadata"], indent=2)
    priority_sections = ["endpoint", "objective", "analysis", "statistical method", "population"]
    chunks = state["sap_chunks"]
    sorted_chunks = sorted(chunks, key=lambda c: any(p in c["section"].lower() for p in priority_sections), reverse=True)
    sap_text = "\n\n---\n\n".join([f"[{c['section']}]\n{c['text']}" for c in sorted_chunks[:30]])
    return LOT_PROMPT.format(metadata=metadata, sap_text=sap_text)

def validate_lot(lot_entries: list[dict]) -> list[dict]:
    required_fields = {"table_number", "title", "population", "data_source", "statistical_method", "tlf_type", "primary_endpoint"}
    validated = []
    for entry in lot_entries:
        missing = required_fields - set(entry.keys())
        if missing:
            entry["_warnings"] = f"Missing fields: {missing}"
        validated.append(entry)
    return validated

def run(state: SapientState) -> SapientState:
    print("lot_generator: starting")
    prompt = build_prompt(state)
    print(f"lot_generator: prompt built, length: {len(prompt)} chars")
    cache_key = hashlib.sha256(prompt.encode()).hexdigest()
    content = get_cached(cache_key)
    if content is None:
        response = create_with_retry(client,
            model=REASONING_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=TEMPERATURE,
            max_tokens=MAX_TOKENS
        )
        print("lot_generator: response received")
        content = response.choices[0].message.content
        if content:
            set_cached(cache_key, content)
    if not content:
        return {**state, "errors": state.get("errors", []) + ["lot_generator: empty response from LLM"], "current_node": "lot_generator"}
    raw = content.strip().replace("```json", "").replace("```", "")
    try:
        lot_entries = json.loads(raw)
    except json.JSONDecodeError:
        return {**state, "errors": state.get("errors", []) + ["lot_generator: failed to parse LLM response"], "current_node": "lot_generator"}
    lot_entries = validate_lot(lot_entries)
    return {**state, "lot_entries": lot_entries, "current_node": "lot_generator"}