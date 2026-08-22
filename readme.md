# Sapient

An agentic pipeline that reads clinical study documents and generates the R programs that produce submission-ready analysis datasets and outputs. Given a Statistical Analysis Plan, Sapient plans the List of Tables, generates ADaM dataset specifications, and generates the R programs that build those datasets and the tables, listings, and figures (TLFs) derived from them.

The design goal is **consistency by construction**: the language model never generates clinical values - it generates R code that runs deterministically, so the same inputs produce the same outputs on every run.

Sapient is also growing beyond one-shot generation into a **clinical statistical-programming harness**: a control layer that operates *inside* an organization's existing codebase - reusing approved standard programs where they satisfy the study, isolating study-specific changes as explicit traceable deltas, generating only genuinely missing capabilities, verifying by execution, and stopping for a human whenever a safe interpretation cannot be established.

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

## The sponsor-environment harness

Clinical programming organizations already hold libraries of validated standard programs; regenerating what exists is waste, and the real value is the **study-specific delta**. The harness layer (`harness/`) works against a sponsor-style codebase - exercised here through a committed synthetic sponsor environment (`sponsor_r_env/`: versioned ADaM standard programs with approval and validation metadata, a shared-module registry, and validation rules):

- **Deterministic resolution, no model calls.** Each study requirement is dispatched by metadata comparison: exact match with an approved standard → `REUSE`; a declared difference the standard's anchors cover → `APPLY_DELTA`; no approved implementation → `NOVEL_CAPABILITY` proposal; two equally valid approved standards → `WAITING_FOR_HUMAN`.
- **Deltas never mutate standards.** A detected delta is applied to a copy (every anchor must match exactly once), executed under Rscript, and traced to its source requirement and SAP section.
- **Generated capabilities pass a gated lifecycle.** Proposal → implementation → deterministic checks + a testthat suite → execution - then a hard stop at human approval before anything registers into the environment registry. Failed validation blocks registration outright.
- **Ambiguity escalates instead of guessing.** When approved candidates are indistinguishable, a structured decision request (question, evidence, interpretations, downstream impact) is recorded; a resolved decision is never asked twice.
- **Standard preservation is measured, not assumed.** The modified program's persisted output frame is compared key-level and cell-level against the unmodified standard's - Standard Preservation Rate, Intended Change Recall, and Unintended Change Rate. A program that executes perfectly but silently corrupts a derivation fails, even though it runs clean.

The repository's automated suite (22 tests) verifies all of the above end-to-end, including two deliberately bad deltas that *execute* and must fail: one that over-restricts the population, and one whose population change is perfect but that quietly overwrites a derived flag on every retained record.

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

Evaluated against the public CDISC pilot study (the metacore specification is held out as an evaluation target, never used as a generation input).

**Specification generation** - variable-set F1 against the pilot Define-XML specification, across all four ADaM structural classes. Grounding on the public ADaMIG standard skeleton lifted the average from a 0.31 baseline to ~0.77:

| Dataset | Class | Precision | Recall | F1 |
|---------|-------|-----------|--------|-----|
| ADSL | Subject-level | 0.89 | 0.63 | 0.74 |
| ADAE | Occurrence (OCCDS) | 0.73 | 0.66 | 0.69 |
| ADADAS | Basic data structure (BDS) | 0.76 | 0.78 | 0.77 |
| ADLBC | Basic data structure (BDS) | 0.81 | 0.72 | 0.76 |
| ADTTE | Time-to-event | 0.81 | 0.96 | 0.88 |

**List-of-Tables generation** — this benchmark was **retired after inspection**: the pilot TLF list we had been scoring against was assembled from another repository's program *filenames*, while the study's SAP contains no table numbers at all - so exact table-number F1 measured information the input never carried, and no prompt improvement can recover it. The layer is being redesigned around what can be verified instead: requirements grounded in cited SAP text, semantic coverage of the SAP's stated analyses, explicit unsupported-inference flagging, and human sign-off - with table numbering assigned downstream by convention rather than extracted.

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
- **Harness:** filesystem/YAML sponsor-environment adapter; stdlib `unittest`; base-R frame comparators; no model calls in resolution or preservation checking

---

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

R is also required (`Rscript` on PATH): the pipeline uses `admiral`, `metacore`, `xportr`, `rtables`, `sdtm.oak`; the harness suite needs `dplyr` and `testthat`.

Set credentials in `.env`:

```
NVIDIA_API_KEY=your_key_here
HF_TOKEN=your_key_here
```

Run the automated test suite (no API calls, no data needed):

```bash
python -m unittest discover -s tests
```

Ingest the CDISC implementation guides once before the first run, then run the pipeline:

```bash
python scripts/ingest_ig.py
python test.py
```

Drive a sponsor-environment case end-to-end (resolve → apply delta → execute; or drive a missing capability to its approval gate):

```bash
python scripts/harness_case.py tests/cases/TC-R-006.yaml --apply
python scripts/harness_case.py tests/cases/TC-R-012.yaml --novel-flow
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
├── harness/           # sponsor-env adapter, resolver, deltas, capability lifecycle, preservation oracle
├── sponsor_r_env/     # synthetic sponsor R environment: standards, module registry, validation rules
├── knowledge/         # vector store, ADaM registry, ADaMIG standard, package signatures
├── specs/             # metacore loader, spec-rule extraction, generation
├── templates/         # code skeletons and derivation bodies
├── r_layer/           # R runner, validator, deterministic checks, conformance, preservation comparator
├── cache/             # prompt-hash cache
├── scripts/           # generation + evaluation + harness-case entrypoints
├── tests/             # unittest suite; declarative test-case ground truth in tests/cases/
└── data/              # input / reference data (gitignored)
```

---

## Status and roadmap

The generation pipeline runs end-to-end, with a deterministic validation gate, real R execution, and conformance checking. Specification generation - the core research problem - is the strongest result at ~0.77 average F1 across all ADaM classes.

The loop is closed: a generated specification can drive the full grounding, validation, and conformance path (selected with an environment variable), with controlled terminology enforced from the public NCI-EVS CT regardless of what the generated specification carries.

The SDTM layer runs raw → SDTM across all five available raw domains at 98–100% value-match, and generated ADaM datasets value-match their references at 94–98%. The full chain also closes end-to-end: an environment switch points ADaM generation at the *generated* SDTM instead of the reference export, and the chain-built ADSL is identical to the reference-fed build (94.4%) while ADAE holds 97.2% when records are keyed by event identity (its sequence numbers are assigned in a different order than the reference  an alignment artifact, not a value error).

The harness layer is in place and verified: standard discovery, reuse, explicit delta application with execution-level preservation checking, capability generation gated on human approval, and ambiguity escalation all run against the synthetic sponsor environment under a 22-test automated suite.

Next, the weakest layer gets its measurement before its generator: an evaluation framework for analysis-requirement/TLF extraction built on verifiable grounding metrics (cited-evidence rate, semantic coverage, unsupported-inference rate) - applying the same discipline that retired the table-number benchmark, this time by design rather than after the fact.

## References

Prior art and standards this work draws on or is positioned against:

- **CDISC Open Rules Engine (CORE) & CDISC 360i** - open-source, machine-readable conformance rules and standards-driven automation from study design through results. The authoritative source for ADaM variable metadata and controlled terminology. <https://www.cdisc.org/core>
- **CDISC Rules Engine** (open source, Python, YAML rules) - the conformance-checking engine behind CORE; the open counterpart to the checks Pinnacle 21 encodes. <https://github.com/cdisc-org/cdisc-rules-engine>
- **Pinnacle 21 - ADaM validation checks** - how the standard ADaM conformance findings (type, length, controlled terminology, define.xml consistency) are implemented in practice. <https://www.pinnacle21.com/blog/how-does-pinnacle-21-implement-adam-validation-checks>
- **Automation in Clinical Trial Statistical Programming: a scoping review (2020–2025), medRxiv** - survey of TLF generation, validation frameworks, metadata-driven ADaM/SDTM generation, and where AI/ML fits; documents the 21–50% hallucination rates on clinical LLM tasks. <https://www.medrxiv.org/content/10.64898/2025.12.24.25342988v2.full>
- **Using Large Language Models to Generate Clinical Trial Tables and Figures, arXiv:2409.12046** - LLM-based TLF generation from analysis datasets. <https://arxiv.org/pdf/2409.12046>

**Public data & standards:** pharmaverse (`pharmaversesdtm`, `pharmaverseadam`, `pharmaverseraw`), the CDISC SDTM/ADaM pilot project, the atorus-research CDISC pilot replication, and the CDISC ADaMIG / SDTMIG / Controlled Terminology standards.
