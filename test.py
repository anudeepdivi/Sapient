from orchestration.graph import pipeline
state = {
    "study_id": "TEST001",
    "sap_path": "data/sap/SAP_001.pdf",
    "sap_chunks": [],
    "study_metadata": {},
    "knowledge_graph": None,
    "lot_entries": [],
    "mockshells": [],
    "adam_programs": {},
    "tlf_programs": {},
    "validation_results": {},
    "needs_regeneration": [],
    "current_node": "",
    "errors": [],
    "completed": False
}
result = pipeline.invoke(state)
import json
with open("data/lot_entries.json", "w") as f:
    json.dump(result["lot_entries"], f, indent=1)
print("Pipeline completed:", result["completed"])
print("LoT entries generated:", len(result["lot_entries"]))
print("ADaM programs:", list(result["adam_programs"].keys()))
print("Validation results:", result["validation_results"])