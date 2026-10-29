# Sapient

**AI help for clinical statistical programming, built so you can check every step.**

Sapient reads a study's Statistical Analysis Plan (SAP), drafts the ADaM dataset specifications, and writes the R programs that build the datasets, using `admiral` and the pharmaverse packages. It runs every program, checks the output, and stops to ask a person whenever it is unsure.

It is meant for statistical programmers who want to see exactly what AI can and can't do on real clinical work, measured honestly on a public study.

---

## How it fits the work you already do

Sapient doesn't replace the usual process. It speeds up the translation steps and leaves the judgement and sign-off with people.

| Step you know | What Sapient does | Who decides |
|---|---|---|
| Read the SAP | Finds the sections that define populations, baselines, windows and treatment-emergence | – |
| Write the ADaM spec | Drafts it from the SAP plus the ADaM Implementation Guide, then checks that every column it cites exists | **You approve the spec** |
| Program the datasets | Writes the R code one variable at a time, runs it, and fixes its own errors from the exact message | – |
| QC | Compares every value with a reference, cell by cell, and reports what didn't match | **You review the differences** |
| Reuse company standards | Reuses an approved standard program, or edits **a copy** when the study differs | **You sign off anything new** |

## The golden rule: the AI never invents a number

- The AI's only job is to **write R code**. It never produces a clinical value.
- Every number comes from **running that code on the trial data**.
- Settings are fixed and every AI answer is saved, so the same inputs give the same outputs.

## Guardrails: the food inspector in the kitchen

Think of the AI as a fast junior programmer. Around it sit simple, cheap checks that don't use AI:

1. **Real names only.** Dataset, variable and function names must exist in CDISC standards or in the installed R package.
2. **Checked before it runs:** syntax, allowed packages, no hard-coded treatment labels.
3. **Checked after it runs:**
   - Is a date really a date?
   - Are the values in the spec's codelist?
   - Does a value the code compares against actually occur in the data?
4. **Conformance checks**, like Pinnacle 21's: type, length, format and controlled terminology, taken from the spec.
5. **People decide** anything ambiguous or new.

Every run records what each check caught, plus the time and AI usage (`python scripts/run_report.py`). Nothing that fails a check reaches the final dataset.

## Results at a glance

These are measured on the public CDISC pilot study and compared with the pilot's own datasets. Full numbers are in [docs/RESULTS.md](docs/RESULTS.md).

- **From the official spec,** the AI's code reproduces **98.6%** of adverse-event (ADAE) values exactly, and 84.0% of the subject-level (ADSL) ones.
- **Specs written by the AI** from the SAP plus ADaM Implementation Guide rules reached **97.7%** on ADAE, with no spec errors left.
- **The hard parts are honest:** lab and time-to-event datasets are much weaker. Where the AI can't find a valid source, it marks the variable **REVIEW** for a person instead of guessing.
- **Cost:** a dataset takes minutes of AI time on a free-tier model.
- **Corrected along the way:** several early numbers turned out to be wrong and were withdrawn. They're listed in the results document with the reasons.

## MCP or code mode?

MCP (Model Context Protocol) is a standard way to plug tools into an AI. "Code mode" gives the AI a small, documented API and lets it write one program that uses it. We tested both on the same job, over four kinds of ADaM dataset:

- **MCP with a few hand-picked tools** works well.
- **MCP with everything plugged in** cost about **30× more** for worse results. The AI re-reads every tool's description on every step.
- **Code mode** is the cheapest, but **only with a carefully designed API.** With our redesigned API it matched MCP's accuracy at lower cost, and never sent patient rows to the AI.

Details: [docs/RESULTS.md](docs/RESULTS.md), section 6. The benchmark code is on the `bench/mcp-vs-code-mode` branch.

---

## Try it

You need:
- Python 3;
- R, with `Rscript` on your PATH;
- a free [NVIDIA Build](https://build.nvidia.com) API key.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
printf 'NVIDIA_API_KEY=your_key_here\nHF_TOKEN=your_key_here\n' > .env

# the automated tests: no AI calls, no data needed
python -m unittest discover -s tests

# reuse a company standard program and apply a small study-specific edit to a copy
python scripts/harness_case.py tests/cases/TC-R-006.yaml --apply
```

R packages: `admiral`, `metacore`, `xportr`, `rtables`, `sdtm.oak`, plus `dplyr` and `testthat` for the tests.

**Coming in January 2027:** one install command, one study config file, and one command per job (`sapient spec ADSL`, `sapient build ADAE`), with a five-minute quickstart on the CDISC pilot. Design: [docs/API_DESIGN.md](docs/API_DESIGN.md).

## What lives where

| Folder | What's in it |
|---|---|
| `scripts/` | The tools you run: spec drafting (`gen_spec.py`), code generation (`gen_derivations.py`), scoring and reports |
| `r_layer/` | Everything R: running programs, checks, value comparison |
| `knowledge/` | The reference material that keeps the AI grounded: CDISC terminology, ADaM standards, R function signatures |
| `harness/` | Working inside a company's existing library of standard programs |
| `sponsor_r_env/` | A small make-believe company library used to test that safely |
| `specs/`, `templates/` | Specification handling and program scaffolding |
| `orchestration/` | The end-to-end pipeline that connects the steps |
| `tests/` | The automated tests (117, no internet needed) |
| `docs/` | [Results](docs/RESULTS.md) and the [API design](docs/API_DESIGN.md) |

## Words you'll see

| Term | Meaning |
|---|---|
| **Model / AI model** | The AI that writes the R code (here an open model on NVIDIA's free tier) |
| **Token** | The unit AI usage is counted and billed in, roughly ¾ of a word. Fewer tokens means cheaper and faster. |
| **Prompt** | The text sent to the AI: instructions plus the facts it needs |
| **Temperature 0** | The setting that makes the AI give the same answer to the same question |
| **MCP** | Model Context Protocol: a standard way to connect tools to an AI |
| **Code mode** | Giving the AI an API and letting it write a program, instead of calling tools one at a time |
| **Guardrail** | An automatic check that rejects bad output before it's used |
| **Spec** | The ADaM dataset specification: each variable, its type and how it's derived |
| **IG** | CDISC's ADaM Implementation Guide |
| **Value match** | The share of cells in our dataset that equal the reference dataset's |

## Status

- Working:
  - spec drafting from the SAP;
  - code generation one variable at a time;
  - all the guardrails;
  - value comparison with the pilot's own datasets;
  - reuse of company standard programs.
- Weaker: lab (BDS) and time-to-event (TTE) datasets.
- Not yet: tables, listings and figures, and AI-generated SDTM programs.
- Next: the beginner-friendly API and command line (January 2027), then testing on a real study. **If you have one, get in touch.**

## References

- [CDISC CORE](https://www.cdisc.org/core) and the [CDISC Rules Engine](https://github.com/cdisc-org/cdisc-rules-engine): open conformance rules.
- [Pinnacle 21 ADaM validation checks](https://www.pinnacle21.com/blog/how-does-pinnacle-21-implement-adam-validation-checks).
- [Automation in clinical trial statistical programming, a scoping review](https://www.medrxiv.org/content/10.64898/2025.12.24.25342988v2.full): why guardrails matter.
- [Using LLMs to generate clinical trial tables and figures](https://arxiv.org/pdf/2409.12046) (arXiv:2409.12046).
- Data: the pharmaverse packages, the [CDISC SDTM/ADaM pilot project](https://github.com/cdisc-org/sdtm-adam-pilot-project), and CDISC ADaMIG and Controlled Terminology.
