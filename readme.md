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

Every run records what each guardrail caught, along with tokens and time (`python scripts/run_report.py`). Example, ADSL from the official specification:

| Generated steps checked by the gate | Rejected by the gate | Execution failures caught | Recovered via error feedback | Never passed (left out of the dataset) |
|---|---|---|---|---|
| 60 | 5 | 34 | 3 | 7 |

Nothing that failed a check reached the final dataset.

---

## Results (public CDISC pilot study)

Inputs are the pilot study's own SAP (Appendix 9 of the public CDISC pilot study report) and its SDTM data. The pilot's official specification and the `pharmaverseadam`/`pharmaversesdtm` community datasets are used only as scoring references, never as generator input.

- **Dataset specifications from the SAP** (ADSL, ADAE). The honest comparison is against a no-model baseline: the standard ADaMIG variable list alone. Variable-name F1 vs the pilot specification:

  | | Standard list alone | Model, no SAP | Model + SAP |
  |---|---|---|---|
  | ADSL | 0.744 | 0.719 | **0.792** |
  | ADAE | 0.598 | 0.885 | 0.833 |

  Variable names are the wrong yardstick for what the SAP adds. Without the SAP, derivations are placeholders or invented ("per SAP age cut-points"; a made-up "+30 day" treatment-emergent window). With it, they carry the study's actual rules: age bands `<65, 65-80, >80`, the safety/ITT/efficacy population definitions, and the SAP's treatment-emergence rule. Next step: score derivations by executing them, not by name overlap.
- **Derivations scored by running them.** The same code generator is run from three specifications: the pilot's official one, one the model wrote from the SAP alone, and one it wrote from the SAP plus ADaM Implementation Guide conventions. Every derived variable is compared cell-by-cell against the **CDISC pilot's own ADaM datasets**, which were built from this same SAP and specification.

  | | Official spec | Model spec: SAP only | Model spec: SAP + IG conventions |
  |---|---|---|---|
  | ADAE derivations reproduced exactly | **13 / 16** | 5 / 15 | 7 / 11 |
  | ADAE cell agreement | **98.4%** | 80.0% | **90.2%** |
  | ADAE specification defects | – | 8 | **2** |
  | ADSL derivations reproduced exactly | 13 / 26 | 4 / 18 | 5 / 17 |
  | ADSL cell agreement | 75.8% | 54.0% | 67.8% |

  The denominators differ because each specification decides which variables to derive rather than copy.

  Swapping specifications while keeping the code generator fixed shows where each error comes from. **The SAP says *what* to analyse; a specification must also say *how*.** Most of the *how* is standardised in the ADaM Implementation Guides: copy subject-level variables from ADSL, the first-occurrence flag algorithm, date conversion with an imputation flag. Adding those conventions cut ADAE specification defects from 8 to 2. For example, all three first-occurrence flags went from 0–24% to 99–100%.

  The two remaining ADAE defects are dates that come out exactly 3,653 days off: the gap between the SAS and R date origins. ADSL's remaining misses are mostly code-generation gaps (treatment dates, dose, baseline measures) that persist even with the official specification.
- **Mock shells.** Shells for the SAP's 24 display templates are generated from the table titles in the SAP's own table list. They are scored against the real templates, which are never shown to the generator. Giving the model the SAP's analysis sections raises population accuracy from 58% to **92%**. Titles (0.97 F1), statistics (0.85 F1) and row labels (47% recall) are similar with and without the SAP.
- **Earlier figures were overstated and have been withdrawn.** The earlier 94–98% value-match numbers had three problems: they were scored against `pharmaverseadam`, which is not the pilot's dataset and lacks most derived variables; a comparison bug silently dropped any variable with a one-sided missing value; and they covered fewer variables.
- **Scaffolding, not generation:** the default pipeline currently builds ADSL/ADAE from hand-written derivation templates, and SDTM is mapped by hand-written `sdtm.oak` programs (98–100% across five domains vs `pharmaversesdtm`). These close the raw → SDTM → ADaM chain but are not model output.
- **Cost** is metered per call (tokens, time, retries) on a free-tier model:

  | Step | Calls | Prompt tokens | Model time |
  |---|---|---|---|
  | Specification | 1 per dataset | about 6k | under 1 minute |
  | ADSL code | about 50 | about 130k | under 4 minutes |
  | ADAE code | 16–30 | 35–67k | 1–2 minutes |
  | All 24 mock shells | 24 | about 122k | about 4.5 minutes |
- One honest negative result: an earlier table-list benchmark was scored against a study whose SAP was not the one fed to the model. It was retired rather than gamed. Now that the matched SAP is in place, it can be rebuilt on verifiable ground.

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
| `tests/` | The automated suite (117 tests, no network access) |
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
