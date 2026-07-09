# Sapient — Project Context

Canonical project description: goals, constraints, phase plan, architecture decisions, and file-by-file layout. readme.md is the public-facing summary; when the two disagree, this file wins.

## What Sapient is

Clinical reporting automation pipeline. Given a Statistical Analysis Plan (SAP) PDF, an agentic LangGraph pipeline generates submission-style R programs for ADaM datasets (admiral) and TLF outputs (rtables), validates them, and executes them against pharmaverse SDTM data.

Pipeline flow: SAP ingestion → LoT generation → mockshell generation → ADaM program generation → TLF program generation → validation → R execution.

## Constraints (these drive every decision)

- Solo developer
- No local GPU (Arch Linux, Intel integrated graphics) — all LLM calls via hosted APIs, embeddings run on CPU
- Free-tier APIs only (NVIDIA Build; rate limits and model rotation are real risks — GLM 5.2 already times out on current tier)
- Deadline: January 2027

Implications: generation speed is nearly irrelevant (outputs are cached by prompt hash, each program is generated once), so prefer slow-but-reliable models for codegen. Never burn LLM quota on checks a deterministic tool can do.

## Phase plan

### Phase 1 — Generation pipeline (current)
- SAP ingestion, domain-aware chunking, ChromaDB embedding
- LoT generation from SAP (hardest node)
- Mockshell generation from LoT
- ADaM program generation (admiral templates), TLF program generation (rtables)
- LLM-based validation, prompt caching

**Status:** runs end-to-end. Validation pass rate ~28% (measured by LLM validator only — not ground truth). Failure modes: hardcoded treatment labels, placeholder column headers, non-ASCII characters, R syntax errors. `specs/metacore_spec.rds` now exists, unblocking R execution (see below); the deterministic gate and real pass-rate metric are still outstanding.

**Phase 1 exit criteria (in priority order):**
1. ~~Unblock R execution: build `specs/metacore_spec.rds`~~ — **Done.** Source is `specs/define/adam_define.xml`, a Define-XML v2 for the CDISC pilot study bundled with the installed `metacore` package (the pilot GitHub repo itself only has an old Define-XML v1 that `metacore::define_to_metacore()` can't parse). Built via `r_layer/scripts/build_metacore_spec.R`. Covers ADSL, ADADAS, ADLBC, ADTTE, ADAE.
2. Deterministic validation gate BEFORE the LLM validator: R `parse()` syntax check, ASCII check, package allowlist (parse `library()` calls against installed packages), hardcoded-treatment-label detection. Free-tier quota only goes to programs that pass the cheap checks.
3. Pass rate measured by actual R execution + metacore compliance, not LLM opinion. `orchestration/nodes/validator.py` already invokes `r_layer/runner.py::run_all_adam_programs()` per run but currently only prints the result — not yet folded into `validation_results` or a pass-rate number.

### Phase 2a — Feedback loop (critical path)
- Execute generated ADaM programs against pharmaversesdtm data
- Compare outputs against pharmaverseadam reference datasets (`admiral::expect_dfs_equal()`)
- LoT eval: score generated LoT against the CDISC pilot's known TLF list (precision/recall) — first-class metric for the hardest node
- TLF comparison compares pre-rendering result data frames, NOT rendered RTF/output files (the Atorus pilot replication doesn't render through rtables; rendered-output diffs are a format mismatch)

### Phase 2b — Infrastructure (only after 2a metrics justify it)
- SDTM generation from raw data via sdtm.oak
- FastAPI endpoints, MCP server exposure
- Internal R package knowledge graph integration
- Neo4j: **deferred indefinitely.** networkx with persistence handles current scale; Neo4j is ops burden for a solo dev with no demonstrated query need. Revisit only with concrete evidence.

### Phases 3–5 — Not yet scoped
Placeholder: hardening, multi-study support, production API (`api/main.py` targets "Phase 5 production"). Must be scoped before Phase 2b begins — an undefined back half is the main schedule risk against Jan 2027.

## Architecture decisions

- **LLM generates R code via template functions, not clinical values** — determinism by construction. Temperature 0, model pinned, outputs cached by SHA256 prompt hash. Note: changing a prompt template invalidates its cache entries by design.
- **Two model roles** (`REASONING_MODEL` for SAP comprehension/LoT/mockshells/validation, `CODEGEN_MODEL` for ADaM/TLF R code), defined in `config.py`. Both currently point to `google/diffusiongemma-26b-a4b-it` on NVIDIA Build. A/B results: DiffusionGemma fastest (1–4s/call) but hallucinates packages in thinking mode; Gemma 4 31B slow (40–120s) but reliable. **Direction:** reliable model for CODEGEN_MODEL (caching amortizes slowness; hallucinated packages are a permanent correctness tax), long-context model for REASONING_MODEL. Keep an ordered fallback model list — free-tier models get rotated.
- **BDS vs OCCDS classification is a lookup, not LLM reasoning.** Known taxonomy gaps to handle: ADSL is neither (subject-level, own template); ADTTE is formally BDS but needs its own template family (CNSR, censoring derivations, EVNTDESC); unknown/custom dataset names must flag for human review, never silently default. The lookup buys the program skeleton; derivation logic (baseline flags, LOCF, visit windowing, criterion flags) remains LLM territory — that's the real variance.
- **LoT is the critical fan-out point** — everything downstream inherits its errors silently. Required mitigations: (a) coverage check — validate the LoT covers the SAP, not just that entries have fields ("which analyses in the SAP have no LoT entry?"); (b) human sign-off gate on the LoT before downstream generation — cheapest QC point in the pipeline; (c) explicit LoT-entry → required-ADaM-dataset → required-SDTM-domain mapping in the knowledge graph, so missing intermediate datasets fail loudly.
- **Deterministic checks run before LLM checks**, always (see Phase 1 exit criteria).
- **metacore enforces spec compliance** on all generated ADaM programs.
- **Domain-aware chunking** by clinical section boundaries, not token count. PubMedBERT embeddings for SAP chunks; if the same store later retrieves admiral docs or R code, eval a code-oriented embedding model first — don't assume PubMedBERT transfers.

## Public data sources

- SDTM: pharmaversesdtm (CRAN) · ADaM: pharmaverseadam (CRAN) · Raw: pharmaverseraw (CRAN)
- CDISC pilot: github.com/cdisc-org/sdtm-adam-pilot-project (source of Define.xml for the metacore spec, and the reference LoT for evals)
- TLF reference: github.com/atorus-research/CDISC_pilot_replication
- SAP: clinicaltrials.gov (NCT02616185)

## Repo hygiene

- `data/` is gitignored, never committed
- `chroma_store/chroma.sqlite3` is currently tracked in git — it should be gitignored (pending cleanup)

## Folder structure

```
sapient/
├── orchestration/
│   ├── graph.py, state.py
│   └── nodes/ (sap_reader, lot_generator, mockshell_generator,
│               adam_generator, tlf_generator, validator)
├── knowledge/     (graph_store, vector_store, document_parser)
├── specs/         (metacore_loader, define_reader, lot_builder)
├── templates/     (adam_templates, tlf_templates)
├── r_layer/       (runner, validator, scripts/)
├── cache/         (prompt_cache)
├── api/           (main — placeholder until production phase)
├── scripts/       (ingestion utilities)
├── tests/
├── data/          (gitignored)
├── config.py, main.py, requirements.txt
```

## File-by-file description

**orchestration/state.py** — LangGraph state schema. TypedDict flowing between every node: study ID, SAP content, knowledge graph reference, LoT entries, mockshells, generated programs, validation results, error flags.

**orchestration/graph.py** — Builds the LangGraph StateGraph: nodes, edges, conditional routing. Entry is SAP ingestion, exit is validated TLF programs.

**orchestration/nodes/sap_reader.py** — Chunks the SAP PDF by clinical section boundaries, embeds chunks into ChromaDB, extracts study metadata (study ID, compound, therapeutic area, primary endpoint, populations). Uses REASONING_MODEL.

**orchestration/nodes/lot_generator.py** — Reads knowledge graph + SAP chunks, extracts endpoints and analysis requirements, generates structured LoT — one entry per TLF with table number, title, population, data source, statistical method. Uses REASONING_MODEL. Hardest node in the pipeline.

**orchestration/nodes/mockshell_generator.py** — Generates a mockshell blueprint per LoT entry: column headers, row structure, footnotes, display conventions. Uses REASONING_MODEL.

**orchestration/nodes/adam_generator.py** — Takes LoT entries, metacore spec, and admiral function knowledge; generates R code per ADaM dataset from admiral templates. Uses CODEGEN_MODEL, temperature 0, prompt-cache-first.

**orchestration/nodes/tlf_generator.py** — Takes mockshells, ADaM datasets, LoT entries; generates R programs per TLF. Uses CODEGEN_MODEL, same caching.

**orchestration/nodes/validator.py** — Reviews generated R programs: metacore compliance, admiral function usage, population flag consistency. Flags issues into state for regeneration or human review. (Deterministic gate to be added upstream of this node — see Phase 1 exit criteria.)

**knowledge/graph_store.py** — Knowledge graph on networkx. Nodes are study artifacts (SAP sections, ADaM datasets, SDTM domains, TLFs, population flags); edges are relationships.

**knowledge/vector_store.py** — ChromaDB wrapper: embedding and retrieval of SAP chunks, ADaM specs, legacy code. Domain-aware chunking, PubMedBERT embeddings.

**knowledge/document_parser.py** — Parses SAP/protocol PDFs and ADaM specs: splits by section headers, tags section types (endpoints, populations, statistical methods, censoring rules), returns structured chunks with metadata.

**specs/metacore_loader.py** — Loads ADaM specs into metacore objects from Define.xml (CDISC pilot) or custom Excel specs. Returns one metacore object per dataset.

**specs/define_reader.py** — Reads Define.xml, converts to metacore-compatible format. Wraps metacore `read_xml()`.

**specs/lot_builder.py** — Builds structured LoT objects from agent output. Validates entry completeness (table number, title, population, data source). Coverage-vs-SAP check belongs here (planned).

**templates/adam_templates.py** — Skeleton of a valid admiral program: library calls, metacore checks, derivation blocks, xportr export. Agent fills derivation-specific sections.

**templates/tlf_templates.py** — TLF program skeletons: table structure, footnote placement, output conventions.

**r_layer/runner.py** — Executes generated R scripts via subprocess; returns structured success/failure with stdout/stderr/exit code.

**r_layer/validator.py** — Runs R validation scripts: metacore checks, reference dataset comparison, hash comparison.

**r_layer/scripts/run_adam.R** — Sources a generated ADaM program, runs it against SDTM input, saves the output dataset.

**r_layer/scripts/build_metacore_spec.R** — One-off build script: `metacore::define_to_metacore()` on `specs/define/adam_define.xml`, saved via `save_metacore()` to `specs/metacore_spec.rds`. Re-run only if the source Define.xml changes.

**specs/define/adam_define.xml** — Define-XML v2 for the CDISC pilot ADaM datasets (ADSL, ADADAS, ADLBC, ADTTE, ADAE), sourced from the installed `metacore` package's example data, not the pilot GitHub repo (which only has an incompatible Define-XML v1).

**r_layer/scripts/validate_metacore.R** — Runs metacore checks on a generated ADaM dataset against the spec; reports variable-level failures.

**r_layer/scripts/compare_reference.R** — Compares a generated ADaM dataset against pharmaverseadam reference via `admiral::expect_dfs_equal()`.

**cache/prompt_cache.py** — SHA256 prompt hashing and cache store. Cache hit returns the stored program; misses store output with hash key, model version, timestamp. Primary consistency mechanism.

**api/main.py** — FastAPI placeholder (POST /study, /generate/lot, /generate/adam, /generate/tlf, GET /study/{id}/status). Production target is a later phase; do not build it out yet.

**config.py** — All configuration: model names (pinned), API keys from env, paths, ChromaDB settings, cache settings, R executable path. Nothing hardcoded elsewhere.

**main.py** — Entry point: runs the full pipeline for a given study ID and SAP path.

**tests/** — Test suite: sap_reader, lot_generator, adam_generator, validator.

**data/** — Raw input, SDTM, generated ADaM, SAP PDFs, pharmaverseadam references. Gitignored.
