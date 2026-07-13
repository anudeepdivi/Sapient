# Sapient

An agentic pipeline that reads clinical study documents and generates the R programs that produce submission-ready analysis datasets and outputs. Given a Statistical Analysis Plan, Sapient plans the List of Tables, generates ADaM dataset specifications, and generates the R programs that build those datasets and the tables, listings, and figures (TLFs) derived from them.

The design goal is **consistency by construction**: the language model never generates clinical values - it generates R code that runs deterministically, so the same inputs produce the same outputs on every run.

---

## The pipeline

```
SAP (+ Protocol) ──▶ List of Tables ──▶ Mockshells ──▶ ADaM spec ──▶ ADaM programs ──▶ TLF programs ──▶ outputs
                        (reasoning)                     (reasoning)      (mechanical)      (mechanical)
        └── domain-aware RAG over SAP sections ──┘        │                  │
                                                   metacore spec        admiral / rtables
```

Every stage is either a **reasoning stage** (planning the List of Tables, authoring dataset specifications - the model must comprehend the study) or a **mechanical stage** (generating code from a specification - deterministic given clean upstream metadata). Mechanical stages inherit the reasoning stages' errors silently, so the accuracy of the whole system is set upstream. The two hardest, highest-leverage problems are therefore **List-of-Tables generation** and **specification generation** - and specification generation is the novel contribution, since generating ADaM programs *from* a specification is already well understood.

---

## Methodology

Four principles do most of the work, each a response to a failure mode we measured.

**1. The model writes code, not values.** Temperature is locked at 0, the model version is pinned, and every output is cached by a hash of its prompt. Clinical values come out of deterministic R execution, not the model. This is the consistency guarantee.

**2. Controlled vocabularies over free generation.** Left to free-form generation, the models hallucinate - inventing ADaM dataset names, variable names, and function calls (a documented 21–50% hallucination rate on clinical LLM tasks). Sapient bounds every such choice to a real vocabulary: dataset names come from a controlled ADaM registry, standard variables from the public CDISC ADaMIG structure, and function calls from signatures extracted directly from the target R package's namespace. Anything off-vocabulary is flagged for human review rather than silently generated. (Extracting function signatures from the package namespace also makes the system package-agnostic - point it at an internal ADaM package instead of `admiral` and it re-grounds automatically, with no knowledge graph required.)

**3. Rules-first conformance.** The durable error class in generated clinical code is not derivation logic - it is *conformance*: variable type, length, format, and controlled terminology. Sapient precompiles these rules, injects them into the code-generation prompt as constraints, checks the built dataset against them deterministically (the same class of rules a Pinnacle 21 / CDISC CORE validator encodes), and coerces types at write time with `xportr` (length is derived from the data, since R - unlike SAS - has no fixed character length). Controlled terminology is validated against the free, versioned CDISC CT published by NCI-EVS, independent of the specification's own codelists - so terminology is enforced even for a generated specification that carries none. Dictionary-coded variables (MedDRA, WHODrug) are validated against the dictionary named in the SAP, not an enumerated list.

**4. Constraints over exemplars.** At temperature 0 the model *transcribes* a worked example or reference template rather than reasoning from it - copying arguments and columns that do not apply. So prompts ground the model on machine-checkable constraints (real function signatures, the actual input columns available, the specification's type and terminology rules) and a deterministic repair-and-regenerate loop, rather than on templates to imitate.

A validation gate enforces these deterministically *before* any expensive check: R syntax, ASCII-only, package allowlist, no hardcoded treatment labels, input-file existence, allowed-function list, and quoted-symbol repair. Gate failures never reach the model.

---

## Results

Evaluated against the public CDISC pilot study (the metacore specification and TLF list are held out as evaluation targets, never used as generation inputs).

**Specification generation** - variable-set F1 against the pilot Define-XML specification, across all four ADaM structural classes. Grounding on the public ADaMIG standard skeleton lifted the average from a 0.31 baseline to ~0.77:

| Dataset | Class | Precision | Recall | F1 |
|---------|-------|-----------|--------|-----|
| ADSL | Subject-level | 0.89 | 0.63 | 0.74 |
| ADAE | Occurrence (OCCDS) | 0.73 | 0.66 | 0.69 |
| ADADAS | Basic data structure (BDS) | 0.76 | 0.78 | 0.77 |
| ADLBC | Basic data structure (BDS) | 0.81 | 0.72 | 0.76 |
| ADTTE | Time-to-event | 0.81 | 0.96 | 0.88 |

**List-of-Tables generation** - F1 ~0.5–0.64 against the pilot's known TLF list. Precision is high; recall is the ceiling, and it is partly fundamental - a real submission LoT is part convention (the standard safety and disposition tables) and part study-specific enumeration that the SAP implies rather than states.

**ADaM program generation** - for the datasets exercised end-to-end, generated programs execute against pharmaverse SDTM data, pass metacore variable and conformance checks (type / length / controlled terminology), and are then **value-matched** against `pharmaverseadam` (per-variable cell agreement on key-joined records - a stricter bar than execution-and-conformance):

| Dataset | Cell agreement | Notes |
|---------|---------------|-------|
| ADSL | 94.4% | every common variable 100% except AGEGR1 |
| ADAE | 97.8% | AGEGR1, plus small date-imputation-flag gaps |

The residual gaps are largely **eval-target conflicts, not derivation errors**: `pharmaverseadam` itself deviates from the pilot study's Define-XML specification (its AGEGR1 age bands and ADURU unit casing contradict the spec's codelists - where the two disagree, code generated *from the spec* cannot match both). Value-match and conformance-to-spec are therefore reported side by side.

**SDTM generation** - the same pattern one layer upstream: raw EDC-shaped data (`pharmaverseraw`) mapped to SDTM with `sdtm.oak`, controlled terminology fed from the same NCI-EVS CT layer in oak's `ct_spec` format, value-matched against `pharmaversesdtm`:

| Domain | Cell agreement | Notes |
|--------|---------------|-------|
| DS | 100.0% | |
| EX | 100.0% | |
| VS | 99.9% | 29,635 / 29,643 records aligned |
| DM | 98.9% | RFPENDTC's true source (SV) has no raw form |
| AE | 98.3% | reference AESEQ ordering is internally inconsistent |

DM is derived from the *generated* EX and DS, so the raw → SDTM chain closes end-to-end. Remaining gaps are structural ceilings of the public raw data (variables whose source domain or column was never collected), documented per domain.

One methodological finding worth stating plainly: on these tasks the **reasoning model, not the prompt, was the accuracy ceiling** - a weaker model truncated and hallucinated variable names (one dataset scored 0.20 vs 0.77 on a stronger model with an identical prompt).

---

## Evaluation targets (all public, legally clean)

- **SDTM input:** `pharmaversesdtm` (CRAN)
- **ADaM reference values:** `pharmaverseadam` (CRAN)
- **Specification & TLF list ground truth:** CDISC SDTM/ADaM pilot project
- **TLF reference:** atorus-research CDISC pilot replication
- **SAP:** publicly registered, clinicaltrials.gov (NCT02616185)

Specifications and outputs are scored against these; none of them is used as a generation input.

---

## Stack

- **Orchestration:** Python + LangGraph
- **Models (NVIDIA Build API, OpenAI-compatible):** a reasoning model for study comprehension and planning, a code model (Mistral Nemotron) for R and specification generation. Temperature 0, pinned, cached by prompt hash.
- **Retrieval:** ChromaDB with PubMedBERT embeddings, chunked on clinical-section boundaries
- **Generated programs:** R - `admiral`, `metacore`, `metatools`, `xportr`, `rtables`
- **Conformance:** metacore/metatools checks + a deterministic type/length/controlled-terminology checker derived from the study specification

---

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Set credentials in `.env`:

```
NVIDIA_API_KEY=your_key_here
HF_TOKEN=your_key_here
```

Ingest the CDISC implementation guides once before the first run, then run the pipeline:

```bash
python scripts/ingest_ig.py
python test.py
```

Generate and score a specification for a single dataset:

```bash
python scripts/gen_spec.py ADSL          # propose  -> specs/proposed/ADSL.json
python scripts/gen_spec.py ADSL --approve # sign off -> specs/approved/ADSL.json
python scripts/eval_spec.py ADSL          # score vs pilot Define-XML
```

---

## Project structure

```
sapient/
├── orchestration/     # LangGraph graph, state, agent nodes
├── knowledge/         # vector store, ADaM registry, ADaMIG standard, package signatures
├── specs/             # metacore loader, spec-rule extraction, generation
├── templates/         # code skeletons and derivation bodies
├── r_layer/           # R runner, validator, deterministic checks, conformance
├── cache/             # prompt-hash cache
├── scripts/           # generation + evaluation entrypoints
└── data/              # input / reference data (gitignored)
```

---

## Status and roadmap

The generation pipeline runs end-to-end, with a deterministic validation gate, real R execution, and conformance checking. Specification generation - the core research problem - is the strongest result at ~0.77 average F1 across all ADaM classes.

The loop is closed: a generated specification can drive the full grounding, validation, and conformance path (selected with an environment variable), with controlled terminology enforced from the public NCI-EVS CT regardless of what the generated specification carries.

The SDTM layer runs raw → SDTM across all five available raw domains at 98–100% value-match, and generated ADaM datasets value-match their references at 94–98%. The full chain also closes end-to-end: an environment switch points ADaM generation at the *generated* SDTM instead of the reference export, and the chain-built ADSL is identical to the reference-fed build (94.4%) while ADAE holds 97.2% when records are keyed by event identity (its sequence numbers are assigned in a different order than the reference — an alignment artifact, not a value error).

Near-term work, in order:

- Have the generation prompt author derivations reliably enough to replace the current deterministic derivation scaffolding (for both the ADaM and SDTM layers - the function-signature grounding for both is already in place).
- **TLF generation** grounded on real `tern`/`rtables` signatures - the earlier free-form prompt produced programs that hallucinated a nonexistent table API (0/29 executed), the clearest demonstration yet of the controlled-vocabulary principle.
- Score derivation and type correctness, not only variable presence; extend LoT recall.

Deferred by design: a Neo4j knowledge graph (package signature extraction covers the package-swap use case more cheaply), FastAPI / MCP exposure, and CRF-annotation-to-SDTM mapping.

---

## References

Prior art and standards this work draws on or is positioned against:

- **CDISC Open Rules Engine (CORE) & CDISC 360i** - open-source, machine-readable conformance rules and standards-driven automation from study design through results. The authoritative source for ADaM variable metadata and controlled terminology. <https://www.cdisc.org/core>
- **CDISC Rules Engine** (open source, Python, YAML rules) - the conformance-checking engine behind CORE; the open counterpart to the checks Pinnacle 21 encodes. <https://github.com/cdisc-org/cdisc-rules-engine>
- **Pinnacle 21 - ADaM validation checks** - how the standard ADaM conformance findings (type, length, controlled terminology, define.xml consistency) are implemented in practice. <https://www.pinnacle21.com/blog/how-does-pinnacle-21-implement-adam-validation-checks>
- **Automation in Clinical Trial Statistical Programming: a scoping review (2020–2025), medRxiv** - survey of TLF generation, validation frameworks, metadata-driven ADaM/SDTM generation, and where AI/ML fits; documents the 21–50% hallucination rates on clinical LLM tasks. <https://www.medrxiv.org/content/10.64898/2025.12.24.25342988v2.full>
- **Using Large Language Models to Generate Clinical Trial Tables and Figures, arXiv:2409.12046** - LLM-based TLF generation from analysis datasets. <https://arxiv.org/pdf/2409.12046>

**Public data & standards:** pharmaverse (`pharmaversesdtm`, `pharmaverseadam`, `pharmaverseraw`), the CDISC SDTM/ADaM pilot project, the atorus-research CDISC pilot replication, and the CDISC ADaMIG / SDTMIG / Controlled Terminology standards.
