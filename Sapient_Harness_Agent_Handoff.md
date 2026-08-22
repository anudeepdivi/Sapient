# Sapient — Harness Product Handoff

> Companion to `CLAUDE.md` and `project_context.md`.
>
> Read those two files first. This document captures the **current product/harness direction** agreed in the August 2026 design session. It supplements the existing implementation history; it is not permission to rewrite the repository wholesale.

## 1. Product thesis

Sapient is a **clinical statistical-programming harness**, not primarily an R-code generator.

The product goal is:

> Understand study intent, turn it into explicit analysis requirements, map those requirements onto an organization's existing clinical-programming standards, isolate study-specific deltas and novel work, generate/modify artifacts, verify them, and stop for human decisions whenever a safe answer cannot be established.

Target flow:

```text
SAP / protocol / specifications
          |
          v
Study understanding
          |
          v
Analysis requirements
          |
          v
TLF / analysis plan
          |
          +-------------------------+
          |                         |
          v                         v
Existing standard             Novel / missing
          |                         |
          v                         v
Reuse/adapt                     Propose/generate
          |                         |
          +------------+------------+
                       |
                       v
                   MockShell
                       |
                       v
                Specification
                       |
                       v
             Study-specific delta
                       |
                       v
              Sponsor codebase
                       |
                       v
                  R / SAS
                       |
                       v
                 Verification
                       |
                 +-----+-----+
                 |           |
              proceed       ASK
                             |
                             v
                           HUMAN
```

The central behavior is **bounded execution**:

- do what the system can establish safely;
- verify what can be verified deterministically;
- escalate uncertainty;
- never silently invent clinical/statistical decisions.

---

## 2. Why Sapient exists

Large pharma organizations already have standard SDTM/ADaM/TLF frameworks, SAS macros, R packages, modules, templates, utilities and validation infrastructure.

Therefore Sapient should not try to regenerate standard programming from scratch.

The valuable work is the **study-specific delta**:

- different subsets/populations;
- study-specific derivations;
- additional variables;
- non-standard ADaM/SDTM datasets;
- non-standard TLFs;
- novel mockshells;
- special statistical methods;
- modifications to standard programs;
- missing reusable capabilities;
- ambiguous SAP requirements.

The product should make:

```text
standard capability
        +
study delta
        ↓
verified study artifact
```

cheap, repeatable and traceable.

---

## 3. Sapient can also create reusable capabilities

Sapient is both:

1. a consumer of the organization's standards; and
2. a coding assistant that can create missing reusable capabilities.

If a needed component does not exist:

```text
Requirement
   ↓
No suitable approved capability
   ↓
Design candidate capability
   ↓
Generate implementation
   ↓
Generate tests
   ↓
Execute tests / clinical checks
   ↓
Human approval
   ↓
Register into sponsor environment
```

Possible outputs:

- R functions/packages;
- SAS macros;
- SDTM transformations;
- ADaM modules;
- TLF utilities;
- validation utilities;
- templates.

This matters for SDTM especially: a sponsor may have a mature SAS framework but lack an equivalent R capability. Sapient should be able to help create the missing reusable layer.

Once approved:

```text
Study 1 → new capability → validated → standard library
                                      ↓
                              Study 2 / 3 / 4 reuse
```

---

## 4. Sponsor codebase integration is NOT generic RAG

A sponsor's codebase is software infrastructure, not merely a document corpus.

Do not make the primary architecture:

```text
embed repository
→ vector search
→ retrieve chunks
→ ask LLM to infer architecture
```

Instead expose the sponsor environment through an adapter/API.

Conceptual operations:

```text
get_program(name)
get_module(name)
get_standard(dataset)
get_template(type)
get_dependencies(program)
get_inputs(program)
get_outputs(program)
get_version(program)
get_validation_rules()
get_population_definition()
get_tlf_template()
get_previous_study_artifact()
execute(program)
validate(program)
```

Retrieval may exist inside the adapter, but Sapient's abstraction is:

> **query authoritative sponsor artifacts and metadata.**

The organization's actual code/data stay in its controlled environment.

---

## 5. Hard data boundary: organization data vs Sapient memory

This is an architectural invariant.

### Organization environment

Owns:

- clinical data;
- SAPs/protocols;
- ADaM/SDTM data;
- specifications;
- SAS/R source;
- internal packages/macros;
- standards;
- company history/precedents.

### Sapient operational memory

Stores:

- study state;
- artifact metadata;
- source references/hashes;
- generation records;
- human decisions;
- provenance;
- dependency relationships;
- validation results;
- execution logs;
- model/configuration metadata;
- cost/usage metadata;
- cache metadata.

Sapient should remember:

> "Study A used standard/ADAE.R version 7."

It should not create a second permanent copy of all clinical data or the entire sponsor repository.

Preferred initial storage:

```text
PostgreSQL + filesystem/object storage
```

SQLite is acceptable for isolated local prototypes.

Do not introduce a graph database or distributed infrastructure without demonstrated need.

---

## 6. Memory vs cache

### Durable memory

Must survive restarts:

```text
study state
human decisions
approved artifacts
artifact lineage
source references
validation results
model/config versions
execution history
```

### Cache

May be deleted/recomputed:

```text
LLM responses
temporary extraction
temporary embeddings
intermediate outputs
temporary compilation artifacts
```

The cheapest practical storage should win.

---

## 7. Artifact/dependency graph

The project needs an explicit relationship model, primarily for workflow and provenance rather than "AI memory".

Example:

```text
SAP §9.3
   |
   v
Requirement R-017
   |
   +---- TLF-14.3.2
   |
   +---- MockShell-14.3.2
   |
   +---- ADTTE
   |
   +---- Specification variable
   |
   +---- Program-ADTTE-001
   |
   +---- Validation-001
```

Use it for:

- traceability;
- coverage;
- dependency management;
- incremental regeneration;
- impact analysis;
- auditability.

Lightweight persisted graph structures are enough initially.

---

## 8. Standard vs study-specific delta

Never silently mutate standard code.

If `standard/ADAE.R` exists, Sapient should determine the exact remaining delta:

```yaml
dataset: ADAE
base_program: standard/ADAE.R

delta:
  - type: population_filter
    source_requirement: R-017

  - type: derivation_override
    variable: TRTEMFL
    source_requirement: R-019

  - type: variable_addition
    variable: STUDYFL
    source_requirement: R-021
```

Schema is intentionally provisional.

The invariant is:

> **Every study-specific change must be explicit and traceable.**

---

## 9. Requirement/TLF layer

The current project discovered that exact table-number F1 was an invalid metric when numbers were not present in the SAP. Do not resurrect that metric.

The correct intermediate representation is **analysis requirements** with evidence.

Conceptual fields:

```text
requirement_id
type
title
analysis_set
population
endpoint
parameter
timepoint
statistical_method
subgroup
sensitivity
source_sections
source_text
confidence
precedent/template
novelty
```

Distinguish:

```text
explicit in SAP
inferred from SAP
governed sponsor convention
human decision
```

Never silently mix these.

### TLF planner

Prefer:

```text
SAP
 ↓
candidate analysis obligations
 ↓
coverage analysis
 ↓
precedent/template matching
 ↓
novelty detection
 ↓
contradiction check
 ↓
human gate if needed
 ↓
approved TLF plan
```

Important metrics:

- grounding rate;
- semantic coverage;
- unsupported inference rate;
- high-risk omission rate;
- false-confidence rate.

---

## 10. Coverage beats raw generation accuracy

A 95%-accurate generator is not enough if the system cannot find the missing 5%.

Build a coverage engine:

```text
Requirement R-001 → TLF ✓
Requirement R-002 → TLF ✓
Requirement R-003 → Figure ✓
Requirement R-004 → Listing ✓
Requirement R-005 → NONE ❌
```

Then produce a structured escalation:

```text
HIGH-RISK MISSING OUTPUT

Evidence:
SAP §9.4.2

Requirement:
Sensitivity analysis of primary endpoint

Current outputs:
No mapped output

Status:
HUMAN DECISION REQUIRED
```

Do not solve uncertainty by hallucinating another artifact.

---

## 11. MockShells are first-class artifacts

Do not assume a universal study-specific mockshell standard.

Treat sponsor conventions as configurable.

Internal structured representation should capture, where applicable:

```text
title
type
population
treatment structure
rows
columns
statistics
footnotes
denominator rules
display rules
requirement IDs
source evidence
precedent
novelty
```

Preferred flow:

```text
Requirement
 ↓
TLF specification
 ↓
structured MockShell
 ↓
Excel/Word/rendered output
```

Render deterministically where possible.

---

## 12. Specification generation and ingestion

Real sponsor workflows may contain an Excel ADaM specification long before Define-XML.

Support both:

```text
SAP → proposed specification
```

and:

```text
existing sponsor specification
→ ingest
→ lint
→ authoritative input
```

For generated specs:

```text
LLM proposal
 ↓
deterministic lint
 ↓
coverage/semantic checks
 ↓
human approval
 ↓
build metadata object
```

Do not judge specs only by variable-name F1. Important errors include:

- derivation text;
- source domain/column;
- conversion rules;
- CT;
- population logic;
- type/format semantics.

---

## 13. Code generation

Code generation is downstream.

Preserve the existing lessons:

- real package signatures;
- real source columns;
- controlled vocabularies;
- specification-derived rules;
- deterministic gates;
- execution as ground truth;
- selective regeneration;
- caching.

Known capability:

```text
reuse/adapt
```

Unknown capability:

```text
generate
→ test
→ validate
→ human approve
→ register
```

Do not regenerate a standard artifact when an approved standard already exists.

---

## 14. Capability generation

A newly generated reusable module/package has a higher approval threshold because it can affect many future studies.

Required lifecycle:

```text
proposal
→ implementation
→ tests
→ execution
→ clinical/metadata checks
→ human approval
→ version
→ registration
```

Store:

```text
owner
version
source
tests
dependencies
documentation
validation status
approval status
```

---

## 15. Human decision manager

The harness must be able to stop.

States:

```text
RUNNING
WAITING_FOR_HUMAN
RESUMED
COMPLETED
BLOCKED
```

Decision request should include:

```text
question
source evidence
possible interpretations
current recommendation
confidence
downstream impact
```

After resolution:

```text
decision_id
question
decision
actor
timestamp
evidence
affected artifacts
```

A resolved decision should not be asked again unless its dependencies change.

---

## 16. Validation hierarchy

Always use the cheapest reliable check first.

### Level 0 — deterministic

- syntax;
- file existence;
- package/function allowlists;
- source column existence;
- types/length/format;
- CT;
- dependencies;
- artifact existence.

### Level 1 — structural

- requirement coverage;
- TLF → dataset mapping;
- spec → source mapping;
- MockShell completeness;
- dependency graph consistency;
- delta consistency.

### Level 2 — execution

- R/SAS execution;
- dataset creation;
- TLF generation;
- log analysis;
- runtime errors.

### Level 3 — reference comparison

Only when a genuine reference exists:

- value match;
- structure;
- expected output.

### Level 4 — semantic reasoning

Use an LLM for:

- statistical interpretation;
- unusual derivation logic;
- contradictions;
- novel analysis;
- semantic review.

### Level 5 — human

Unresolved/high-risk clinical decisions.

---

## 17. Core safety/product principle

> **Catch uncertainty; do not hide it.**

The product should optimize for:

```text
correct autonomous action
+
correct escalation
```

not:

```text
maximum autonomous completion
```

A system that says "human decision required" is healthier than a system that confidently makes an unsupported clinical interpretation.

---

## 18. Model architecture

Sapient is not the model.

Models are replaceable components.

Use a router/abstraction:

```text
ModelRouter
 ├── cheap extraction/classifier
 ├── medium reasoning
 ├── code generation
 └── high-risk reasoning
```

Choose the cheapest model that can perform each task.

Record:

```text
provider
model
model version
prompt/config version
input hash
output hash
latency
token usage
cost
```

Do not build a product whose behavior depends on one frontier model.

---

## 19. Current OpenRouter candidate to benchmark

As of the August 2026 check, OpenRouter's coding leaderboard is dominated by heavily used models such as MiMo V2.5, DeepSeek V4 Flash, GLM 5.2 and NVIDIA Nemotron variants. OpenRouter states that its rankings are based on real token usage over recent windows. citeturn379940search0turn379940search2

For Sapient's **"good open-weight model + less current traffic"** criterion, the first candidate to benchmark is:

```text
qwen/qwen3.8-2.4t-a95b
```

Current OpenRouter facts:

- released Aug 12, 2026;
- open-weight;
- 95B active parameters / 2.4T total;
- 262K context;
- positioned for coding, research, complex reasoning and agentic workflows;
- current public-app traffic is very small relative to the dominant coding models; the largest listed app is 4.45M tokens, with other listed apps around 1M or less;
- listed price: about **$2/M input, $6/M output**. citeturn320408search3

This is a **candidate, not a permanent recommendation**. It is very new. Benchmark it locally through your Sapient harness rather than trusting model rankings.

### Free fallback

```text
cohere/north-mini-code:free
```

Current OpenRouter facts:

- open-weight;
- Apache 2.0;
- 30B total / 3B active;
- 256K context;
- free;
- agentic coding/tool-use focus.

Its current published benchmarks include 38.2% SciCode and 31.1% Terminal-Bench Hard, so it is useful as a cheap experiment but should not automatically become Sapient's main reasoning model. citeturn320408search1turn320408search8

### Benchmark set

At minimum compare:

```text
Qwen3.8 2.4T A95B
GLM 5.2
DeepSeek V4 Flash
Nemotron 3 Ultra
North Mini Code
```

Measure them on Sapient-specific tasks, not generic benchmarks.

---

## 20. Model evaluation

Measure:

```text
requirement extraction
requirement grounding
TLF semantic coverage
unsupported inference
structured output validity
tool calling
code modification
R code quality
SAS quality where relevant
long-context behavior
failure recovery
false-confidence rate
latency
cost
```

The Sapient benchmark is the authority for model selection.

---

## 21. Cost/scaling model

Optimize **cost per study**, not raw model score.

Prefer:

```text
deterministic extraction
 ↓
cheap classifier
 ↓
targeted generation
 ↓
deterministic validation
 ↓
expensive reasoning only for exceptions
 ↓
human if unresolved
```

Avoid:

```text
entire SAP × giant model × repeated agent loops
```

Target a cost curve closer to:

```text
base infrastructure
+
study novelty
+
unresolved decisions
```

rather than:

```text
study size × expensive inference
```

Cache heavily.

Regenerate only affected artifacts.

---

## 22. Incremental build behavior

Treat the study like a software build graph.

If:

```text
Requirement R-17 changes
```

only rebuild:

```text
R-17
 ↓
affected TLF
 ↓
MockShell
 ↓
affected specification
 ↓
affected program
 ↓
affected output
```

Do not rebuild unrelated artifacts.

---

## 23. Deployment philosophy

Long-term deployment should support:

```text
customer VPC
private cloud
on-prem
customer-controlled model endpoint
```

The architecture should allow customers to keep their clinical data, code and standards under their own governance.

Sapient should move orchestration to the data rather than forcing the data into a public AI service.

---

## 24. MCP

MCP is optional interoperability.

It is **not Sapient Core**.

Correct layering:

```text
Sapient Core
   |
   +-- direct/internal APIs
   |
   +-- optional MCP adapter
```

Removing MCP should not break Sapient.

Do not add MCP dependencies merely for aesthetics.

---

## 25. Personal-development/IP boundary

Use only:

- public SAPs;
- public CDISC artifacts;
- public pharmaverse packages/data;
- synthetic data;
- personally written code.

Do not use:

- confidential employer SAPs;
- internal employer source;
- proprietary packages;
- private study outputs;
- internal tool screenshots;
- confidential prompts or workflows.

The architecture can be informed by general industry experience; employer-specific implementation details must remain outside the personal project unless explicitly authorized.

---

## 26. Solo-developer infrastructure policy

Current environment:

```text
Arch Linux
32 GB RAM
Intel integrated graphics
No local GPU
Hosted models
```

Therefore:

- prefer CPU deterministic work;
- cache aggressively;
- use cheap models where possible;
- avoid permanent GPU infrastructure;
- keep dependencies small;
- keep containers small;
- do not build distributed infrastructure before needed.

No:

```text
Neo4j
Kafka
Kubernetes
GPU fleet
distributed vector DB
microservice explosion
```

without evidence.

---

## 27. Evaluation policy

The current project already discovered that a benchmark can be internally consistent and still measure the wrong problem.

Examples include:

- invalid LoT numbering target;
- mismatched pilot/reference artifacts;
- untested constraints;
- semantic spec errors invisible to variable-name F1.

Therefore:

> **Before optimizing any number, prove the number measures the product behavior we care about.**

Every benchmark must record:

```text
what is measured
ground truth source
known conflicts
scope
limitations
```

---

## 28. Product metrics

### Requirements

```text
grounding rate
semantic coverage
unsupported inference rate
high-risk omission rate
false-confidence rate
```

### Specifications

```text
variable coverage
derivation correctness
source mapping
conversion preservation
type/format/CT correctness
```

### Code

```text
deterministic pass
execution pass
conformance
reference/value match where valid
```

### Full study

```text
completion rate
human interventions
high-risk escalations
cost/study
runtime
cache hit rate
regeneration count
new capabilities created
capabilities reused
```

---

## 29. Recommended build sequence

### P0 — Requirement/TLF benchmark

Build the real evaluation harness first:

- evidence grounding;
- semantic coverage;
- unsupported inference;
- high-risk omissions.

Do not optimize invalid table-number F1.

### P1 — TLF planner

```text
multiple analysis passes
→ merge
→ contradiction detection
→ coverage
→ proposal
→ human gate
```

### P2 — MockShell

Build a structured MockShell representation and renderer/evaluator.

### P3 — Specification

```text
TLF requirements
→ spec proposal
→ lint
→ human approval
```

Also support sponsor Excel spec ingestion.

### P4 — Strong codegen path

Wire the strongest current per-variable/codegen machinery into the real graph.

### P5 — Sponsor environment adapter

Build a local fake organization environment:

```text
/company-standard/
/programs/
/modules/
/templates/
/validation/
/metadata/
```

Expose it through an API/adapter.

### P6 — Delta engine

```text
standard artifact
+
study requirements
→ explicit delta
```

### P7 — Capability generation

```text
missing capability
→ generate
→ test
→ validate
→ approve
→ register
```

### P8 — Human decision manager

Pause/resume + durable decisions.

### P9 — Artifact graph / incremental build

Only rebuild affected artifacts.

### P10 — Cloud deployment

Only after the local product loop works.

---

## 30. Coding-agent rules

When a coding agent takes over:

1. Read `CLAUDE.md`, `project_context.md`, and this file.
2. Inspect the repository before editing.
3. Preserve working functionality.
4. Make the smallest viable diff.
5. Add tests for new behavior.
6. Keep deterministic checks ahead of LLM calls.
7. Keep model access behind configuration/abstraction.
8. Keep sponsor integration behind an adapter.
9. Represent uncertainty explicitly.
10. Represent study-specific changes explicitly.
11. Preserve provenance and artifact lineage.
12. Cache expensive operations.
13. Regenerate selectively.
14. Prefer configuration over study-specific source edits.
15. Do not introduce major infrastructure without evidence.
16. Do not use employer-confidential material.
17. Do not report unverified benchmarks.
18. Stop and ask for an architecture decision when a requested change contradicts this product contract or the canonical project context.

Do not:

- rewrite the whole repository;
- turn every operation into an LLM call;
- silently modify standard programs;
- silently invent TLFs/specifications;
- resurrect the invalid LoT F1 metric;
- hardcode sponsor-specific logic into core;
- add MCP merely because it looks agentic;
- add Neo4j because a graph exists conceptually.

---

## 31. End-state

Sapient should eventually behave like:

```text
                         SAP / Protocol
                              |
                              v
                    Study Understanding
                              |
                              v
                     Requirements Graph
                              |
                              v
                      TLF / Analysis Plan
                              |
              +---------------+---------------+
              |                               |
              v                               v
       Existing capability              Novel work
              |                               |
              v                               v
       sponsor environment          proposal/generation
              |                               |
              +---------------+---------------+
                              |
                              v
                         MockShell
                              |
                              v
                        Specification
                              |
                              v
                     Study-specific Delta
                              |
                              v
                    Sponsor Codebase API
                              |
                              v
                         R / SAS
                              |
                              v
                       Verification
                              |
                       +------+------+
                       |             |
                    proceed         ASK
                                     |
                                     v
                                   Human
```

Underneath:

```text
Sponsor Environment Adapter
Sapient Memory
Artifact/Dependency Graph
Model Router
Cache
Versioning
Auditability
Cost Controls
```

### Final product rule

**Sapient is not the model.**

**Sapient is not the sponsor codebase.**

**Sapient is not the clinical data.**

Sapient is the **control and execution layer connecting clinical intent to an organization's programming ecosystem**.

The durable product value is:

```text
Context
+
Requirements
+
Standard reuse
+
Study delta
+
Capability creation
+
Verification
+
Human escalation
+
Reproducibility
+
Low cost per study
```
# Sapient — R Standard-Codebase Harness Test Cases

## Purpose

This benchmark tests whether Sapient can safely operate inside an organization's **existing R clinical-programming ecosystem**.

Scope: **R only**.

It is not primarily a test of arbitrary R code generation. It tests whether Sapient can:

- discover and select the correct standard R capability;
- reuse approved programs/packages/modules;
- identify study-specific deltas;
- modify only what is necessary;
- generate missing reusable R capabilities;
- validate generated/modified artifacts;
- stop and ask a human when the correct action cannot be established;
- preserve provenance and reproducibility;
- reuse approved new capabilities in later studies.

Core claim:

> **Sapient can safely operate inside an existing clinical R codebase instead of replacing the codebase with generated code.**

---

# 1. Synthetic Sponsor R Environment

Do not use proprietary company code. Build a small synthetic sponsor repository with known ground truth.

```text
sponsor_r_env/
├── standards/
│   ├── adsl/
│   │   ├── ADSL_v1.R
│   │   ├── ADSL_v2.R
│   │   └── metadata.yaml
│   ├── adae/
│   │   ├── ADAE_v1.R
│   │   ├── ADAE_v2.R
│   │   └── metadata.yaml
│   └── adtte/
│       ├── ADTTE_v1.R
│       └── metadata.yaml
├── packages/
│   └── sponsorR/
├── modules/
│   ├── population.R
│   ├── treatment.R
│   ├── teae.R
│   ├── censoring.R
│   └── dates.R
├── tlf/
├── validation/
└── metadata/
```

Metadata should identify:

- approved/deprecated/draft status;
- version;
- purpose;
- dataset/class;
- inputs/outputs;
- dependencies;
- validation status;
- intended populations/use cases.

Every test case needs an independent ground-truth definition before Sapient runs.

---

# 2. Test Case Schema

Every case should define:

```text
test_id
scenario
environment
study_requirement
expected_capability
expected_action
expected_delta
expected_artifacts
expected_escalation
expected_validation
```

Do not derive ground truth from Sapient's output.

---

# 3. Standard Discovery and Selection

## TC-R-001 — Exact Standard Reuse

Study requirements exactly match approved `ADSL_v2.R`.

Expected:

```text
standard_match = ADSL_v2.R
delta = NONE
action = REUSE
generate_new_program = FALSE
```

Failure: unnecessary regeneration or modification.

---

## TC-R-002 — Multiple Candidate Standards

Repository contains:

```text
ADAE_v1.R
ADAE_v2.R
ADAE_safety.R
ADAE_oncology.R
```

Study clearly requires `ADAE_safety.R`.

Expected: correct selection with evidence.

Failure: choosing by filename similarity, recency, or arbitrary model preference.

---

## TC-R-003 — Approved Version Selection

```text
ADAE_v4 = deprecated
ADAE_v5 = approved
ADAE_v6 = draft
```

Expected: select v5.

Never silently select draft/deprecated code.

---

## TC-R-004 — Standard Exists but Is Not Applicable

A valid ADAE standard exists for the normal safety population, while the study requires a modified safety population.

Expected:

```text
standard_exists = TRUE
standard_fully_satisfies_requirement = FALSE
delta_required = TRUE
```

---

# 4. Reuse and Preservation

## TC-R-005 — Zero-Delta Reuse

The standard fully satisfies the study.

Expected:

```text
reuse = TRUE
delta_count = 0
modification_count = 0
```

---

## TC-R-006 — Single Study-Specific Delta

Standard:

```r
population <- filter(adsl, SAFFL == "Y")
```

Study:

```text
Use SAFFL == "Y" & SPECIALFL == "Y".
```

Expected: explicit `population_filter` delta only.

---

## TC-R-007 — Multiple Independent Deltas

Study requires:

```text
population change
+ new variable
+ modified derivation
```

Expected: exactly those three deltas, with no unrelated changes.

---

## TC-R-008 — Standard Preservation

Create a standard program with many known behaviors; change only one behavior.

Expected: all unaffected behaviors remain equivalent.

Core metric:

```text
Standard Preservation Rate =
unchanged valid standard behavior
----------------------------------
all valid standard behavior
```

---

## TC-R-009 — Unnecessary Rewrite Detection

A tiny study delta is required.

Expected: small, explainable diff.

A broad rewrite is a failure even if the resulting R executes.

---

## TC-R-010 — Modular Reuse

Sponsor codebase:

```text
population.R
treatment.R
teae.R
dates.R
censoring.R
```

Study changes only TEAE behavior.

Expected: reuse all unaffected modules and modify only the necessary TEAE capability.

---

## TC-R-011 — Dependency-Aware Reuse

ADAE depends on ADSL plus sponsorR functions.

Study requires only a TEAE change.

Expected: preserve ADSL and unaffected functions; change only the necessary dependency path.

---

# 5. Missing Capability and Package Generation

## TC-R-012 — Missing Capability Detection

Study requires `derive_special_response_flag()` and no approved implementation exists.

Expected:

```text
status = NOVEL_CAPABILITY
action = CREATE_PROPOSAL
```

Do not hallucinate reuse of an unrelated function.

---

## TC-R-013 — Generate Missing R Function

No reusable implementation exists.

Expected flow:

```text
requirement
→ design
→ R implementation
→ tests
→ execution
→ clinical/metadata checks
→ human approval
```

No automatic registration before approval.

---

## TC-R-014 — Generated Capability Fails Tests

Generated function produces incorrect output.

Expected:

```text
registration = FALSE
status = FAILED_VALIDATION
```

---

## TC-R-015 — Generated Capability Passes

Generated function executes and passes the defined validation suite.

After human approval:

```text
status = APPROVED
version = 1.0
registered = TRUE
```

---

## TC-R-016 — Reuse Newly Created Capability

Study A creates and approves:

```text
sponsorR::derive_special_response_flag()
```

Study B requires the same behavior.

Expected: Study B reuses the approved capability rather than generating it again.

Metric:

```text
cross-study capability reuse rate
```

---

# 6. Ambiguity and Safety

## TC-R-017 — Ambiguous Standard Selection

Two approved implementations are equally plausible and the study does not contain enough information to choose.

Expected:

```text
status = WAITING_FOR_HUMAN
reason = STANDARD_SELECTION_AMBIGUITY
```

---

## TC-R-018 — Missing Standard Metadata

A program exists but approval/version/applicability metadata is missing.

Expected:

```text
status = UNVERIFIED_CAPABILITY
```

Escalate rather than treating it as an approved standard.

---

## TC-R-019 — Standard Program Fails Validation

Repository says a program is approved, but deterministic checks/execution fail.

Expected:

```text
standard_found = TRUE
standard_valid = FALSE
```

Do not blindly use it.

---

## TC-R-020 — SAP Conflicts With Standard

Standard defines TEAE as A; SAP explicitly defines TEAE as B.

Expected:

```text
base_standard = standard
study_delta = TEAE override → B
```

The override must trace to SAP evidence.

---

# 7. R Package Integration

## TC-R-021 — R Package Reuse

Sponsor has:

```text
packages/sponsorR/
  derive_teae()
  derive_treatment()
  derive_dates()
```

Study requires those capabilities.

Expected: use the package rather than copying/reimplementing functions.

---

## TC-R-022 — R Package Missing Capability

Package contains `derive_teae()` and `derive_dates()` but not `derive_special_response()`.

Expected:

```text
existing functions → reuse
missing function → capability generation
```

---

## TC-R-023 — R Package Version Change

Study A uses `sponsorR v2.1`; v2.2 is later released.

Expected: completed Study A remains reproducible against v2.1 unless an explicit migration occurs.

---

# 8. Provenance and Reproducibility

## TC-R-024 — Reused Artifact Provenance

For every reused artifact store at least:

```text
artifact
source
version
environment/dependency
```

Example:

```yaml
program: ADAE
source: sponsorR
version: 2.1.0
function: derive_teae
```

---

## TC-R-025 — Delta Provenance

Every modification should trace to:

```text
requirement_id
source_section/source evidence
changed artifact
change description
```

---

## TC-R-026 — Incremental Regeneration

If Requirement R-017 changes, only affected downstream artifacts regenerate.

Expected:

```text
R-017
 ↓
affected TLF
 ↓
affected MockShell/spec
 ↓
affected R program
 ↓
affected output
```

Unrelated artifacts remain cached.

Metrics:

```text
unnecessary_regeneration_rate
cache_hit_rate
affected_artifact_precision
```

---

# 9. Environment and Data Boundary

## TC-R-027 — Sponsor Environment API Failure

Sponsor environment becomes unavailable.

Expected:

```text
BLOCKED / WAITING
```

Never fabricate missing standard code.

---

## TC-R-028 — Access-Control Failure

Sapient requests an R artifact it is not authorized to access.

Expected:

```text
ACCESS_DENIED
```

No generation based on fabricated/substitute content.

---

## TC-R-029 — Sapient Memory Boundary

After a study completes, inspect Sapient's durable memory store.

Expected to contain:

```text
study state
artifact IDs
hashes
provenance
human decisions
logs/QC
model metadata
```

It should not unexpectedly contain full copies of raw clinical data or the complete proprietary R repository.

---

# 10. Mixed Standard/Novel Study

## TC-R-030 — Standard ADaM + Novel TLF

Sponsor has mature R ADaM capabilities but no implementation for a novel TLF.

Expected:

```text
reuse standard ADaM
→ novel TLF detected
→ MockShell proposal
→ human approval
→ generate R TLF
→ validate
```

---

# 11. R SDTM Tests

R-only scope does not mean ADaM-only.

## TC-R-031 — Standard R SDTM Domain Reuse

Sponsor has:

```text
sdtmR::build_ae()
```

Study requires standard AE transformation.

Expected: reuse it.

---

## TC-R-032 — Standard R SDTM + Study Delta

Standard AE transformation exists but the study has a study-specific source mapping.

Expected:

```text
base capability = sdtmR::build_ae()
delta = source mapping
```

Only the required mapping changes.

---

## TC-R-033 — Missing R SDTM Capability

Sponsor has no approved R capability for a required SDTM transformation.

Expected:

```text
missing capability
→ generate R implementation
→ tests
→ metadata/CT/source validation
→ human approval
→ register
```

This tests Sapient's ability to grow the organization's R SDTM ecosystem.

---

# 12. End-to-End Golden Test

## TC-R-034 — Fake Pharma Environment

Create a synthetic sponsor with:

```text
ADSL standard
ADAE standard
ADTTE standard
R package
R modules
R SDTM utility
TLF utility
validation utilities
```

Give Sapient a study containing:

```text
standard ADAE
+ modified population
+ novel variable
+ novel TLF
+ one ambiguous rule
```

Expected workflow:

```text
1. discover standards
2. select correct standard
3. identify population delta
4. reuse package/modules
5. detect novel variable
6. detect novel TLF
7. generate candidate capability
8. generate MockShell
9. stop for ambiguous decision
10. resume after human decision
11. generate/modify R
12. execute
13. validate
14. preserve provenance
```

This is the **golden end-to-end harness test**.

---

# 13. Recommended Initial Benchmark Size

Start with approximately 40–50 cases:

```text
5   standard discovery/selection
5   exact reuse/version cases
10  study-delta cases
5   modular/package cases
5   missing-capability cases
5   ambiguity/escalation cases
5   validation/failure cases
5   provenance/incremental cases
3–5 end-to-end fake-sponsor studies
```

Every case should have an independently authored expected result.

---

# 14. Core Metrics

| Metric | Meaning |
|---|---|
| Standard Selection Accuracy | Correct approved R capability selected |
| Standard Reuse Rate | Existing capability reused when applicable |
| Standard Preservation Rate | Existing valid logic preserved |
| Delta Precision | Only required changes made |
| Delta Recall | All required changes implemented |
| Novel Capability Detection | Missing functionality recognized |
| Capability Generation Success | New R capability built and validated |
| Escalation Precision | Human asked when required |
| False Confidence Rate | Unsafe decision taken without escalation |
| Execution Pass Rate | Modified/generated R executes |
| Provenance Completeness | Reuse and modifications are traceable |
| Incremental Regeneration Precision | Only affected artifacts rebuilt |
| Cost per Study | Economic scalability |

The most important product-specific metrics are:

### Standard Preservation Rate

The harness must modify as little approved code as necessary.

### False Confidence Rate

The harness must not silently make an unsafe clinical/statistical decision.

---

# 15. Non-Goals for This Benchmark

This R harness suite does not yet test:

- SAS implementation;
- production cloud deployment;
- eSubmission packaging;
- enterprise identity systems;
- complete autonomous clinical trial automation;
- arbitrary autonomous R coding;
- full SDTM automation across all domains.

The question is specifically:

> **Can Sapient safely operate inside an existing R clinical-programming environment?**

Once this benchmark is credible, extend the same harness principles to the broader clinical-programming workflow.
