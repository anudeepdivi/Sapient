import json
from openai import OpenAI
from orchestration.state import SapientState
from config import NVIDIA_API_KEY, NVIDIA_BASE_URL, REASONING_MODEL, TEMPERATURE, MAX_TOKENS
from r_layer.runner import run_all_adam_programs
client = OpenAI(base_url=NVIDIA_BASE_URL, api_key=NVIDIA_API_KEY, timeout=60.0)

VALIDATOR_PROMPT = """
You are a clinical programming QC reviewer. Review this R program strictly.

Flag as "error" ONLY if:
- A non-admiral function is used for a derivation that admiral covers
- For ADaM programs: export method is not xportr::xportr_write
- For TLF programs: export method is not formatters::export_as_txt- Hardcoded numeric patient counts or statistics exist
- Population flag variable is missing or wrong

Flag as "warning" if:
- Code style is suboptimal but functionally correct
- Minor formatting issues

Flag as "pass" if code is functionally correct and compliant.

Return JSON only:
{{"status": "pass|fail", "severity": "none|warning|error", "issues": []}}

LOT ENTRY: {lot_entry}
R PROGRAM: {program}
"""

def run(state: SapientState) -> SapientState:
    if state.get("completed"):
        return state
    r_results = run_all_adam_programs(state.get("adam_programs", {}))
    print(f"validator: R execution results: {r_results}")
    validation_results = {}
    needs_regeneration = []
    all_programs = {**state.get("adam_programs", {}), **state.get("tlf_programs", {})}
    lot_map = {e["table_number"]: e for e in state["lot_entries"]}
    for name, code in all_programs.items():
        lot_entry = lot_map.get(name, {})
        prompt = VALIDATOR_PROMPT.format(lot_entry=json.dumps(lot_entry, indent=2), program=code)
        response = client.chat.completions.create(
            model=REASONING_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=TEMPERATURE,
            max_tokens=MAX_TOKENS
        )
        content = response.choices[0].message.content
        if not content:
            result = {"status": "fail", "issues": ["Validator: empty response from LLM"], "severity": "error"}
            validation_results[name] = result
            needs_regeneration.append(name)
            continue
        raw = content.strip().replace("```json", "").replace("```", "")
        try:
            result = json.loads(raw)
        except json.JSONDecodeError:
            result = {"status": "fail", "issues": ["Validator parse error"], "severity": "error"}
        validation_results[name] = result
        if result.get("severity") == "error":
            needs_regeneration.append(name)
    return {**state, "validation_results": validation_results, "needs_regeneration": needs_regeneration, "completed": len(needs_regeneration) == 0, "current_node": "validator"}