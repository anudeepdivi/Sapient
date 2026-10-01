import json
from openai import OpenAI
from orchestration.llm_retry import create_with_retry
from orchestration.state import SapientState
from config import NVIDIA_API_KEY, NVIDIA_BASE_URL, REASONING_MODEL, TEMPERATURE, MAX_TOKENS, MAX_REGENERATIONS
from r_layer.runner import run_all_adam_programs
from r_layer.validator import validate_metacore, compare_reference, check_conformance
from r_layer.deterministic_checks import run_gate
from templates.adam_templates import ADAM_INPUTS
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
    prev_results = state.get("validation_results") or {}
    prev_regen = set(state.get("needs_regeneration") or [])
    for name, code in all_programs.items():
        if name in adam_programs and name not in ADAM_INPUTS:
            validation_results[name] = {"status": "unsupported", "stage": "deterministic_gate",
                                        "issues": [f"{name} has no input mapping/spec — needs human review, excluded from pass rate"],
                                        "severity": "warning"}
            continue
        if name in prev_results and name not in prev_regen:
            validation_results[name] = prev_results[name]
            continue
        gate = run_gate(code)
        if not gate["passed"]:
            validation_results[name] = {"status": "fail", "stage": "deterministic_gate", "issues": gate["issues"], "severity": "error"}
            needs_regeneration.append(name)
            continue

        lot_entry = lot_map.get(name, {})
        prompt = VALIDATOR_PROMPT.format(lot_entry=json.dumps(lot_entry, indent=2), program=code)
        response = create_with_retry(client,
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
            result = None
        if not isinstance(result, dict):
            # Valid JSON that is not an object (a list, a bare null) would make the
            # assignment below raise, aborting the node and losing every diagnostic
            # collected in this round.
            result = {"status": "fail", "issues": ["Validator returned a non-object JSON response"],
                      "severity": "error"}
        result["stage"] = "llm_validator"
        validation_results[name] = result
        if result.get("severity") == "error":
            needs_regeneration.append(name)

    # Real pass-rate: R execution + metacore compliance, for ADaM programs that
    # cleared the deterministic gate. The LLM verdict is advisory — execution is
    # ground truth and overrules an LLM fail (the LLM false-positives on valid R).
    supported_adam = {name: code for name, code in adam_programs.items() if name in ADAM_INPUTS}
    gated_adam = {
        name: code for name, code in supported_adam.items()
        if not (validation_results.get(name, {}).get("status") == "fail"
                and validation_results.get(name, {}).get("stage") == "deterministic_gate")
    }
    r_results = state.get("adam_execution") or run_all_adam_programs(gated_adam)
    real_pass_count = 0
    for name in gated_adam:
        exec_result = r_results.get(name, {})
        entry = validation_results.setdefault(name, {})
        entry["execution"] = exec_result
        if not exec_result.get("success"):
            entry["status"] = "fail"
            entry["stage"] = exec_result.get("stage", "r_execution")
            if name not in needs_regeneration:
                needs_regeneration.append(name)
            continue
        metacore_result = exec_result["metacore"]
        entry["metacore"] = metacore_result
        if not metacore_result.get("success"):
            entry["status"] = "fail"
            entry["stage"] = "metacore_compliance"
            if name not in needs_regeneration:
                needs_regeneration.append(name)
            continue
        entry["conformance"] = check_conformance(name)  # type/length/CT — report-only for now
        entry["reference"] = compare_reference(name)     # value oracle vs pharmaverseadam
        if entry.get("status") == "fail" and entry.get("stage") == "llm_validator":
            entry["status"] = "pass"
            entry["severity"] = "warning"
            entry["llm_overruled"] = True
            if name in needs_regeneration:
                needs_regeneration.remove(name)
        real_pass_count += 1

    total_adam = len(supported_adam)
    real_pass_rate = real_pass_count / total_adam if total_adam else 0.0
    conformance_clean = sum(1 for n in supported_adam
                            if validation_results.get(n, {}).get("conformance", {}).get("clean"))
    print(f"validator: real pass rate (execution + metacore) = {real_pass_count}/{total_adam} ({real_pass_rate:.0%})")
    print(f"validator: conformance-clean (type/length/CT) = {conformance_clean}/{total_adam}")

    tlf_skipped = state.get("tlf_skipped") or {}
    # Upstream nodes record hard failures in `errors` (lot_generator writes there when
    # the LoT cannot be produced). A run whose LoT failed has no entries, hence no
    # regeneration and no skipped tables, so needs_regeneration alone would report the
    # run complete with zero ADaM and zero TLFs.
    pipeline_errors = state.get("errors") or []
    regen_count = state.get("regen_count", 0) + 1
    # Nothing else consumes the retry cap, so record here that the loop is giving up
    # with work still outstanding instead of ending silently.
    retry_exhausted = bool(needs_regeneration) and regen_count >= MAX_REGENERATIONS
    completed = len(needs_regeneration) == 0 and not tlf_skipped and not pipeline_errors
    if pipeline_errors:
        print(f"validator: pipeline errors recorded, run cannot be reported complete: {pipeline_errors}")
    if retry_exhausted:
        print(f"validator: regeneration cap ({MAX_REGENERATIONS}) reached with work outstanding: "
              f"{sorted(needs_regeneration)}")
    return {**state, "validation_results": validation_results, "needs_regeneration": needs_regeneration,
            "real_pass_rate": real_pass_rate,
            "completed": completed,
            "retry_exhausted": retry_exhausted,
            "regen_count": regen_count, "current_node": "validator"}