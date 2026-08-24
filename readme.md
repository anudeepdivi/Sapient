# Sapient

Sapient is an AI assistant for clinical statistical programming. It reads a study's Statistical Analysis Plan (SAP) and produces the R programs that create submission-ready analysis datasets and the tables, listings, and figures built from them.

A useful way to picture it: a very fast junior statistical programmer who

- reads the SAP and works out which analyses are needed,
- drafts the dataset specifications and the R programs (using familiar tools: `admiral` and the pharmaverse packages),
- runs every program and checks its output against the written rules,
- and **stops and asks a human whenever it is not sure**.

It also works in a second mode that matters even more in practice: operating *inside* a company's existing library of validated standard programs   reusing them wherever possible and changing only what the new study truly requires.

---

## The golden rule: the AI never invents clinical data

Language models are good at writing code and bad at being trusted with numbers. Sapient takes advantage of the first and removes the second risk:

- The model's only job is to write R code. It never generates a clinical value.
- Every actual number comes from running that R code deterministically on real trial data.
- The model version is pinned, creativity is switched off (temperature 0), and every response is cached   so the same inputs always produce the same outputs.

This is the design goal: **consistency by construction**.

---

## Mode 1: from SAP to programs

```
SAP ──▶ which analyses are needed ──▶ dataset specifications ──▶ R programs ──▶ run + verify
        (AI plans this)              (AI drafts, rules check)    (AI drafts)     (deterministic)
```

The AI handles the steps that need reading and judgment; software handles every step that needs exactness. Each stage's work is checked before the next stage starts, so mistakes are caught where they happen instead of surfacing months later in a table.

## Mode 2: working inside your existing library (the harness)

Clinical programming groups already own libraries of **validated** standard programs. Rewriting those from scratch is waste and risky. Sapient therefore behaves like a well-briefed team member:

| Situation | What Sapient does |
|---|---|
| An approved standard already fits the study | Reuses it unchanged |
| The study differs slightly (e.g., a different safety population definition) | Applies the smallest possible edit **to a copy**. The original standard is never touched |
| It genuinely cannot tell two approved standards apart | Stops and asks a human, laying out the evidence it never guesses |
| No program exists for something the study needs | Drafts a proposal, builds and tests it, then **halts for human sign-off** before anything enters the library |

And because "it ran fine" is not proof of correctness, Sapient verifies edits the way a reviewer would:

- **Before vs after:** the edited program's output is compared record-by-record, cell-by-cell against the original standard's output, proving that *only* the intended values changed.
- **Nothing extra:** the diff between the submitted copy and the officially sanctioned edit is checked, catching gratuitous rewrites even when they behave identically.
- **Only the right files:** when a change targets one shared function, the audit proves every other module stayed byte-for-byte untouched.

Every one of these behaviors is enforced by automated test cases including deliberately planted wrong implementations (a rewrite that corrupts a derived flag; an unnecessary regeneration of unrelated modules) that execute perfectly and *must still be caught*.

---

## Guardrails

1. **Real names only.** Models like to invent plausible-sounding dataset, variable, and function names. Sapient only allows names that exist in the official CDISC standards or in the target R package itself; anything else is flagged for review, never silently used.
2. **Cheap checks before expensive ones.** Deterministic validation (syntax, allowed packages, forbidden shortcuts such as hard-coded treatment labels) runs before any AI involvement. Failures never reach the model.
3. **Conformance like Pinnacle 21.** Variable type, length, format, and controlled terminology are compiled from the study specification and checked mechanically on the built dataset, with terminology enforced against the free public CDISC CT.
4. **Rules, not examples.** At zero creativity the model copies worked examples blindly including their mistakes. So prompts carry machine-checkable constraints (real function signatures, real input columns, spec rules), not templates to imitate.
5. **Human gates at the points of judgment.** Approval of new capabilities, resolution of ambiguity, anything unverifiable all escalate.

---

## Results (public CDISC pilot study)

Everything is measured against publicly available references the CDISC pilot study, the `pharmaverseadam`/`pharmaversesdtm` community datasets, and a publicly registered SAP none of which is fed to the generator as input.

- **Dataset specifications** drafted from the SAP agree with the pilot's official specification on roughly **3 out of 4 variables on average** (about 0.77 F1, across all four ADaM structure types) up from 0.31 before grounding on the public ADaM implementation guide.
- **Generated analysis datasets** (ADSL, ADAE) match the community reference dataset **cell-for-cell at 94–98%**, with the remaining gaps traced to contradictions *inside the reference itself* (it deviates from the pilot specification) rather than to coding errors.
- **Upstream SDTM mapping** agrees at **98–100%** across five domains, closing the chain end-to-end: raw data → SDTM → ADaM.
- One honest negative result: an earlier benchmark for planning the table list turned out to be unscorable the ground truth contained information the SAP never had. It was retired rather than gamed, and that layer is being redesigned around verifiable criteria.

---

## Trying it

Requirements: Python 3, R (`Rscript` on PATH), and a free NVIDIA Build API key.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
printf 'NVIDIA_API_KEY=your_key_here\nHF_TOKEN=your_key_here\n' > .env

# automated test suite no API calls, no data needed
python -m unittest discover -s tests

# see mode 2 end-to-end: resolve a requirement, apply a delta, execute it
python scripts/harness_case.py tests/cases/TC-R-006.yaml --apply
```

R packages used: `admiral`, `metacore`, `xportr`, `rtables`, `sdtm.oak` (+ `dplyr`, `testthat` for the harness suite).

---

## What lives where

| Folder | In one sentence |
|---|---|
| `orchestration/` | The step-by-step pipeline connecting the stages above |
| `harness/` | Mode 2: reuse/delta decisions, verification, human escalation |
| `sponsor_r_env/` | A small make-believe company library used to exercise Mode 2 safely |
| `knowledge/` | The vocabularies and extracted metadata that keep the model grounded |
| `specs/`, `templates/` | Specification handling and code scaffolding |
| `r_layer/` | Everything R: execution, deterministic checks, output comparison |
| `tests/` | The automated suite (55 tests, no network access) |
| `data/` | Input/reference data (not part of the repository) |

---

## Status

- The generation pipeline runs end-to-end with real R execution and conformance checking.
- Mode 2 (the harness) is implemented and verified: reuse, minimal deltas with preservation proof, capability lifecycle gated on human approval, and ambiguity escalation plus module-level operation (change one shared function, prove nothing else moved).
- Next: measuring the weakest layer (extracting analysis requirements from SAP text) before building more generation on top of it, and deepening module-level reuse.

## References

- [CDISC CORE](https://www.cdisc.org/core) and the [CDISC Rules Engine](https://github.com/cdisc-org/cdisc-rules-engine) open, machine-readable conformance rules (the open counterpart to Pinnacle 21 checks).
- [Pinnacle 21 ADaM validation checks](https://www.pinnacle21.com/blog/how-does-pinnacle-21-implement-adam-validation-checks).
- [Automation in clinical trial statistical programming, a scoping review](https://www.medrxiv.org/content/10.64898/2025.12.24.25342988v2.full)   documents why guardrails matter (21–50% hallucination rates on clinical LLM tasks).
- [Using LLMs to generate clinical trial tables and figures](https://arxiv.org/pdf/2409.12046) (arXiv:2409.12046).
- Public data: pharmaverse packages, CDISC SDTM/ADaM pilot project, CDISC ADaMIG and Controlled Terminology.
