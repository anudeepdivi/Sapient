# Sapient

Clinical reporting automation pipeline. Reads SAP PDFs, generates R programs for ADaM datasets and TLF outputs via LangGraph agentic pipeline.

**Read `project_context.md` before starting any task — it is the canonical plan (phases, architecture decisions, file map). readme.md is public-facing; do not edit it unless asked.**

## Hard rules
- NEVER write code without being explicitly asked, file by file
- The user owns architecture and domain logic decisions — confirm before restructuring
- No assumptions about next steps — ask if unclear
- Prefer minimal diffs over rewrites unless asked to rewrite
- Do not add new dependencies, services (Neo4j), or API endpoints — those are explicitly deferred; see project_context.md

## Stack
- Python + LangGraph orchestration
- NVIDIA Build API (OpenAI-compatible). Two roles in `config.py`: `REASONING_MODEL` and `CODEGEN_MODEL` — both currently `google/diffusiongemma-26b-a4b-it`. Temperature 0, models pinned, outputs cached by prompt hash (`cache/prompt_cache.py`)
- ChromaDB + PubMedBERT embeddings
- R: admiral, metacore, xportr, rtables
- No GPU locally; free-tier API only — never spend LLM calls on checks a deterministic tool can do

## Current priorities (in order — do the top unfinished one)
1. ~~Unblock R execution: build `specs/metacore_spec.rds`~~ — **Done.** The raw GitHub pilot repo only has old Define-XML v1, which `metacore::define_to_metacore()` can't parse. Used the Define-XML v2 for the same pilot study bundled in the installed `metacore` package instead (`specs/define/adam_define.xml`, built via `r_layer/scripts/build_metacore_spec.R`). Covers ADSL, ADADAS, ADLBC, ADTTE, ADAE.
2. **Deterministic validation gate** before the LLM validator node: R `parse()` syntax check, ASCII-only check, package allowlist (parse `library()` calls), hardcoded-treatment-label detection.
3. **Real pass-rate metric**: measure by R execution + metacore compliance (`r_layer/`), not LLM validator opinion. Note: `validator.py` already calls `run_all_adam_programs()` but discards the result except for a print — not yet wired into `validation_results`/pass-rate.
4. **LoT eval**: score generated LoT against the CDISC pilot's known TLF list (precision/recall).

## Known pitfalls (verified failure modes — check for these)
- Generated R code: hardcoded treatment labels, placeholder column headers, non-ASCII characters, syntax errors
- DiffusionGemma hallucinates package names in thinking mode — never trust `library()` calls without the allowlist check
- Free tier times out on some models (GLM 5.2); NVIDIA rotates models — model names live only in `config.py`
- The ~28% "pass rate" is LLM-validator opinion, not ground truth — don't optimize against it
- Changing a prompt template invalidates its cache entries — expect a slow full-regeneration run after prompt edits
- TLF comparison must diff pre-rendering data frames, never rendered RTF output
- ADSL and ADTTE do not fit the BDS/OCCDS lookup — see project_context.md before touching classification
- `chroma_store/chroma.sqlite3` is tracked in git but shouldn't be; don't commit changes to it

## Project structure
See project_context.md for full file-by-file map. Key dirs: `orchestration/nodes/` (agent nodes), `r_layer/` (R execution), `templates/` (prompt skeletons), `cache/` (prompt hash cache), `config.py` (all config — nothing hardcoded elsewhere).

## Cost awareness
Keep responses concise. Don't re-explain established context. Ask before large refactors.

## Working style
- Make the smallest possible diff — don't rewrite a file when a targeted edit will do
- Don't add comments explaining obvious code
- Don't add error handling, logging, or type hints unless asked
- Don't refactor unrelated code while fixing something else
- No preamble before code, no summary after unless something is genuinely ambiguous
- If a fix is one line, give one line — not a rewritten function
- Match existing code style in the file rather than imposing a different pattern
- Don't add print/debug statements unless explicitly asked
- Ask before touching more than one file per request
- When a task is done, update the "Current priorities" list above and the Phase 1 status in project_context.md — keep both truthful
