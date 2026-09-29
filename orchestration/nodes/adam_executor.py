from orchestration.state import SapientState
from r_layer.runner import run_all_adam_programs
from r_layer.deterministic_checks import run_gate
from templates.adam_templates import ADAM_INPUTS


def run(state: SapientState) -> SapientState:
    """Execute the ADaM programs and record what this run accepted.

    Runs before tlf_generator so TLF generation can require current-run
    acceptance. A canonical XPT left on disk by an earlier run is not
    acceptance and is deliberately not consulted here.
    """
    adam_programs = state.get("adam_programs") or {}
    supported = {name: code for name, code in adam_programs.items() if name in ADAM_INPUTS}
    gated = {name: code for name, code in supported.items() if run_gate(code)["passed"]}

    r_results = run_all_adam_programs(gated)
    accepted_adam = {name: result["accepted_path"]
                     for name, result in r_results.items() if result.get("success")}

    needs_regeneration = list(state.get("needs_regeneration") or [])
    # A buildable dataset the gate rejected was never attempted; flag it here so
    # tlf_generator sees it as retryable rather than as never-attempted.
    for name in set(supported) - set(gated):
        if name not in needs_regeneration:
            needs_regeneration.append(name)
    for name, result in r_results.items():
        if not result.get("success") and name not in needs_regeneration:
            needs_regeneration.append(name)

    print(f"adam_executor: accepted {len(accepted_adam)}/{len(gated)} "
          f"({', '.join(sorted(accepted_adam)) or 'none'})")
    return {**state, "adam_execution": r_results, "accepted_adam": accepted_adam,
            "needs_regeneration": needs_regeneration, "current_node": "adam_executor"}
