import json
from openai import OpenAI
from orchestration.state import SapientState
from config import NVIDIA_API_KEY, NVIDIA_BASE_URL, REASONING_MODEL, TEMPERATURE, MAX_TOKENS
from r_layer.runner import run_all_adam_programs
from r_layer.validator import validate_metacore
from r_layer.deterministic_checks import run_gate
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
    validation_results = {}
    needs_regeneration = []
    adam_programs = state.get("adam_programs", {})
    all_programs = {**adam_programs, **state.get("tlf_programs", {})}
    lot_map = {e["table_number"]: e for e in state["lot_entries"]}
    for name, code in all_programs.items():
        gate = run_gate(code)
        if not gate["passed"]:
            validation_results[name] = {"status": "fail", "stage": "deterministic_gate", "issues": gate["issues"], "severity": "error"}
            needs_regeneration.append(name)
            continue

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
            result = {"status": "fail", "stage": "llm_validator", "issues": ["Validator: empty response from LLM"], "severity": "error"}
            validation_results[name] = result
            needs_regeneration.append(name)
            continue
        raw = content.strip().replace("```json", "").replace("```", "")
        try:
            result = json.loads(raw)
        except json.JSONDecodeError:
            result = {"status": "fail", "issues": ["Validator parse error"], "severity": "error"}
        result["stage"] = "llm_validator"
        validation_results[name] = result
        if result.get("severity") == "error":
            needs_regeneration.append(name)

    # Real pass-rate: R execution + metacore compliance, for ADaM programs that
    # cleared the deterministic gate and the LLM validator.
    gated_adam = {
        name: code for name, code in adam_programs.items()
        if validation_results.get(name, {}).get("status") != "fail"
    }
    r_results = run_all_adam_programs(gated_adam)
    real_pass_count = 0
    for name in gated_adam:
        exec_result = r_results.get(name, {})
        entry = validation_results.setdefault(name, {})
        entry["execution"] = exec_result
        if not exec_result.get("success"):
            entry["status"] = "fail"
            entry["stage"] = "r_execution"
            if name not in needs_regeneration:
                needs_regeneration.append(name)
            continue
        metacore_result = validate_metacore(name)
        entry["metacore"] = metacore_result
        if not metacore_result.get("success"):
            entry["status"] = "fail"
            entry["stage"] = "metacore_compliance"
            if name not in needs_regeneration:
                needs_regeneration.append(name)
            continue
        real_pass_count += 1

    total_adam = len(adam_programs)
    real_pass_rate = real_pass_count / total_adam if total_adam else 0.0
    print(f"validator: real pass rate (execution + metacore) = {real_pass_count}/{total_adam} ({real_pass_rate:.0%})")

    return {**state, "validation_results": validation_results, "needs_regeneration": needs_regeneration,
            "real_pass_rate": real_pass_rate, "completed": len(needs_regeneration) == 0, "current_node": "validator"}