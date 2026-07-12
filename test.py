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
from pathlib import Path
with open("data/lot_entries.json", "w") as f:
    json.dump(result["lot_entries"], f, indent=1)
Path("data/tlf_programs").mkdir(parents=True, exist_ok=True)
for stale in Path("data/tlf_programs").glob("*.R"):
    stale.unlink()
for name, code in result["tlf_programs"].items():
    Path(f"data/tlf_programs/{name}.R").write_text(code)
print("Pipeline completed:", result["completed"])
print("TLF skipped:", result.get("tlf_skipped"))
print("LoT entries generated:", len(result["lot_entries"]))
print("ADaM programs:", list(result["adam_programs"].keys()))
print("Validation results:", result["validation_results"])