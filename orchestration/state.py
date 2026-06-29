from typing import TypedDict, Optional, Any
from pathlib import Path


class SapientState(TypedDict):
    # Study Identity
    study_id: str
    sap_path: str

    # SAP Ingestion
    sap_chunks: Optional[list[dict]]        # chunked SAP sections with metadata
    study_metadata: Optional[dict]          # compound, TA, primary endpoint, populations
    knowledge_graph: Optional[Any]          # networkx graph, Neo4j in phase 2
    lot_entries: Optional[list[dict]]       # one entry per TLF
    mockshells: Optional[list[dict]]        # one mockshell blueprint per TLF
    adam_programs: Optional[dict[str, str]] # dataset_name -> R code
    tlf_programs: Optional[dict[str, str]]  # table_number -> R code
    validation_results: Optional[dict]      # program_name -> pass/fail/issues
    needs_regeneration: Optional[list[str]] # programs flagged for retry
    
    # Pipeline Control
    current_node: str
    errors: list[str]
    completed: bool