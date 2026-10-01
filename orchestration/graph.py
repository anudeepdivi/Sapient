from langgraph.graph import StateGraph, END
from config import MAX_REGENERATIONS
from orchestration.state import SapientState
from orchestration.nodes import (
    sap_reader,
    lot_generator,
    mockshell_generator,
    adam_generator,
    adam_executor,
    tlf_generator,
    validator,
)


def should_regenerate(state: SapientState) -> str:
    if state.get("needs_regeneration") and not state.get("completed") and state.get("regen_count", 0) < MAX_REGENERATIONS:
        return "regenerate"
    if state.get("needs_regeneration") and not state.get("completed"):
        # The cap ends the loop with work outstanding. Name it, so the run does not stop
        # looking like a finished run that happened to produce nothing.
        print(f"graph: regeneration cap ({MAX_REGENERATIONS}) reached, ending with "
              f"unfinished work: {sorted(set(state.get('needs_regeneration') or []))}")
    return "done"

def build_graph() -> StateGraph:
    graph = StateGraph(SapientState)

    # ── Register Nodes ────────────────────────────────────────
    graph.add_node("sap_reader", sap_reader.run)
    graph.add_node("lot_generator", lot_generator.run)
    graph.add_node("mockshell_generator", mockshell_generator.run)
    graph.add_node("adam_generator", adam_generator.run)
    graph.add_node("adam_executor", adam_executor.run)
    graph.add_node("tlf_generator", tlf_generator.run)
    graph.add_node("validator", validator.run)

    # ── Define Edges ──────────────────────────────────────────
    graph.set_entry_point("sap_reader")
    graph.add_edge("sap_reader", "lot_generator")
    graph.add_edge("lot_generator", "mockshell_generator")
    graph.add_edge("mockshell_generator", "adam_generator")
    graph.add_edge("adam_generator", "adam_executor")
    graph.add_edge("adam_executor", "tlf_generator")
    graph.add_edge("tlf_generator", "validator")

    # ── Conditional Routing ───────────────────────────────────
    graph.add_conditional_edges(
    "validator",
    should_regenerate,
    {
        "regenerate": "adam_generator",
        "done": END,
    }
)

    return graph.compile()


# singleton
pipeline = build_graph()