from langgraph.graph import StateGraph, END
from orchestration.state import SapientState
from orchestration.nodes import (
    sap_reader,
    lot_generator,
    mockshell_generator,
    adam_generator,
    tlf_generator,
    validator,
)


def should_regenerate(state: SapientState) -> str:
    if state.get("needs_regeneration") and not state.get("completed") and state.get("regen_count", 0) < 3:
        return "regenerate"
    return "done"

def build_graph() -> StateGraph:
    graph = StateGraph(SapientState)

    # ── Register Nodes ────────────────────────────────────────
    graph.add_node("sap_reader", sap_reader.run)
    graph.add_node("lot_generator", lot_generator.run)
    graph.add_node("mockshell_generator", mockshell_generator.run)
    graph.add_node("adam_generator", adam_generator.run)
    graph.add_node("tlf_generator", tlf_generator.run)
    graph.add_node("validator", validator.run)

    # ── Define Edges ──────────────────────────────────────────
    graph.set_entry_point("sap_reader")
    graph.add_edge("sap_reader", "lot_generator")
    graph.add_edge("lot_generator", "mockshell_generator")
    graph.add_edge("mockshell_generator", "adam_generator")
    graph.add_edge("adam_generator", "tlf_generator")
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