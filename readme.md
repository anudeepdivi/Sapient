# Sapient

Clinical reporting automation pipeline that reads Statistical Analysis Plans and generates submission-ready R programs for ADaM datasets and TLF outputs.

---

## What it does

Given a SAP PDF, Sapient runs an agentic pipeline that:

1. Reads and chunks the SAP by clinical section boundaries
2. Embeds chunks into ChromaDB using PubMedBERT embeddings
3. Extracts study metadata — compound, therapeutic area, populations
4. Generates a structured List of Tables (LoT) — one entry per TLF
5. Generates mockshell blueprints for each TLF
6. Generates R programs for each ADaM dataset using admiral
7. Generates R programs for each TLF using rtables
8. Validates generated programs for admiral compliance and spec adherence

---

## Stack

- **Orchestration:** Python + LangGraph
- **LLM:** DiffusionGemma 26B A4B via NVIDIA Build API
- **Embeddings:** PubMedBERT (pritamdeka/PubMedBERT-mnli-snli-scinli-scitail-mednli-stsb)
- **Vector store:** ChromaDB (persistent)
- **Knowledge graph:** networkx (Phase 1), Neo4j (Phase 2)
- **Generated programs:** R — admiral, metacore, xportr, rtables
- **Caching:** SHA256 prompt hashing with JSON file store
- **API:** FastAPI (Phase 2)

---

## Public data sources

- SDTM: pharmaversesdtm (CRAN)
- ADaM: pharmaverseadam (CRAN)
- Raw data: pharmaverseraw (CRAN)
- CDISC pilot: github.com/cdisc-org/sdtm-adam-pilot-project
- TLF reference: github.com/atorus-research/CDISC_pilot_replication
- SAP: clinicaltrials.gov (NCT02616185)

---

## Phase 1 scope (current)

- SAP ingestion and chunking
- LoT generation from SAP
- Mockshell generation from LoT
- ADaM program generation using admiral templates
- TLF program generation using rtables
- LLM-based validation with compliance checking
- Prompt caching for consistency

## Phase 2 scope (planned)

- SDTM generation from raw data via sdtm.oak
- R program execution against pharmaverse SDTM data
- Output comparison against pharmaverseadam reference datasets
- Neo4j knowledge graph replacing networkx
- MCP server exposure
- FastAPI endpoints
- Internal R package knowledge graph integration

---

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Set environment variables in `.env`:
```
NVIDIA_API_KEY=your_key_here
HF_TOKEN=your_key_here
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_password
```

Ingest clinical implementation guides before first run:
```bash
python scripts/ingest_ig.py
```

Run the pipeline:
```bash
python main.py
```

---

## Project structure

```
sapient/
├── orchestration/     # LangGraph graph, state, agent nodes
├── knowledge/         # ChromaDB vector store, document parser
├── specs/             # metacore loader, define reader, LoT builder
├── templates/         # ADaM and TLF R code skeletons
├── r_layer/           # R script runner and validator
├── cache/             # Prompt hash cache
├── api/               # FastAPI app
├── scripts/           # Ingestion utilities
├── tests/             # Test suite
└── data/              # Input data (gitignored)
```

---

## Architecture decisions

- LLM generates R code using template functions, not clinical values — determinism by construction
- Temperature locked at 0, model version pinned, outputs cached by prompt hash
- Domain-aware chunking by clinical section boundaries, not token count
- BDS vs OCCDS classification encoded as lookup, not LLM reasoning
- metacore enforces spec compliance on all generated ADaM programs
- Two LLM roles planned: reasoning model for SAP comprehension, code model for generation

---

## Status

Phase 1 generation pipeline complete. Validation pass rate approximately 28% on current runs — primary failure modes are hardcoded treatment group labels in TLF column headers and intermittent non-ASCII characters in generated code. Phase 2 begins with R program execution and reference dataset comparison.