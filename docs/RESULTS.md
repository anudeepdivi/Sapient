# Results

All results use the public **CDISC pilot study** (CDISCPILOT01, Alzheimer's disease, xanomeline vs placebo).

- **Inputs:** the pilot's own Statistical Analysis Plan (Appendix 9 of the public study report) and its SDTM data.
- **Answer key:** the pilot's official specification (Define-XML) and its own ADaM datasets. They are never shown to the AI.

Every number below can be re-run from this repository.

## 1. Writing the code from a specification

The AI writes the R program one variable at a time, from the official specification. Every value is then compared with the pilot's own dataset.

| Dataset (kind) | Variables reproduced exactly | Values matching overall |
|---|---|---|
| ADAE (adverse events) | **14 of 16** | **98.6%** |
| ADSL (one row per subject) | 18 of 28 | 84.0% |
| ADLBC (lab results) | 8 of 20 | 77.6% |
| ADTTE (time to event) | 3 of 5 | 95.2% |

Notes:
- **ADSL remaining gaps:**
  - HEIGHTBL and WEIGHTBL are within 0.1 of the pilot's values, which the pilot stores rounded.
  - SITEGR1's official rule only says "refer to SAP".
  - VISNUMEN, BMIBL and DURDIS follow the official spec's text; the pilot used rules the spec never states. VISNUMEN: the spec's rule (misspelt "PROTCOL COMPLETED") covers completers only, while the pilot takes the disposition visit for every subject. BMIBL: computed from height and weight rounded to 1 decimal, then rounded to 1 decimal. DURDIS: (days + 1) / 30.4375, rounded to 1 decimal. Each of these rules reproduces the pilot's values exactly. Rounding is sponsor-defined (CDISC has no rule), so it needs the sponsor's input, not the AI's guess.
  - The real code-generation misses: TRTEDT skips the spec's imputation (use the discontinuation date when the last dose date is missing), and TRT01A/TRT01AN follow a fixed instruction in our prompt (`TRT01A = ACTARM`) instead of the spec's `TRT01A = TRT01P`.
- **Two report-only checks** (added 2026-11-20; they flag, never block, and change nothing the AI sees) list for a person any variable that passed every check but is empty on every row, or has more than 2 decimals where the spec states no precision. Replayed from saved answers, they flag BMIBL and DURDIS on ADSL; TRT01PN, TRT01AN and RACEN (empty) on the AI-written ADSL spec; and PARAMN (empty) on ADLBC.
- **Three cheap checks** after each step, which add nothing to the AI's prompt, took ADSL from 13 of 26 to 18 of 28:
  - is a date really a date;
  - are the values in the spec's codelist;
  - does a compared text value actually occur in the data.

## 2. Writing the specification from the SAP

The SAP says **what** to analyse. A specification must also say **how** to compute each variable.

We test a specification the strict way: we generate code from it with the same code generator as in section 1, and compare the values with the pilot's datasets. If a variable is right with the official spec but wrong with ours, the error is in our spec.

**ADAE** (adverse events):

| Specification used | Variables exact | Values matching | Spec errors |
|---|---|---|---|
| Official (written by the pilot team) | 14 of 16 | 98.6% | – |
| AI, from the SAP only | 5 of 15 | 80.0% | 8 |
| AI, SAP + ADaM IG rules | 7 of 11 | 90.2% | 2 |
| **AI, SAP + IG rules + checks (latest)** | **9 of 11** | **97.7%** | **0** |

What made the difference:
- **ADaM Implementation Guide rules:** copy subject-level variables from ADSL, the standard first-occurrence flag algorithm, and dates converted with an imputation flag.
- **A date-format fix:** dates had come out exactly 3,653 days wrong, the gap between SAS's 1960 date origin and R's 1970 one.
- **A check that every column a spec cites exists** in a dataset it actually reads.

**Other datasets** (latest AI spec):

| Dataset | Variables exact (with an answer-key column) | Main remaining issue |
|---|---|---|
| ADSL | 5 of 11 | numeric codes (RACEN, TRT01PN) and one flag (DISCONFL) |
| ADLBC | 1 of 15 | the official lab spec is itself partly wrong (see the spec linter), so the AI often copies its mistakes |
| ADTTE | 1 of 1; most variables not produced | censoring needs an end-of-study date our ADSL lacks; 3 variables are marked **REVIEW** for a human instead of guessed |

**Variable names alone are a weak measure.** Scored on variable names, the AI's ADSL spec is no better than the standard ADaMIG list on its own (F1 0.70–0.79 vs 0.74). The SAP's value shows up in the **derivations**: the correct age bands (`<65, 65-80, >80`), the population definitions, and the treatment-emergent rule. Without the SAP, the AI invented these.

## 3. Mock shells

The SAP contains 24 display templates. The AI drafts each shell from the table title alone (taken from the SAP's own table list), and is scored against the real template, which it never sees.

| Measure | Title only | Title + SAP analysis sections |
|---|---|---|
| Correct analysis population | 58% | **92%** |
| Title wording (F1) | 0.96 | 0.97 |
| Statistics asked for (F1) | 0.83 | 0.85 |
| Row labels found | 46% | 47% |

## 4. What the guardrails caught

Example: ADSL, from the official specification. The AI had 39 variables to write, with up to 5 rounds per variable.

| Right first time | Fixed after the exact error was fed back | Never passed (left out for a person) |
|---|---|---|
| 19 | 15 | 5 |

The five left out were AVGDD, COMP24FL, COMP8FL, CUMDOSE and RFENDT. Nothing that failed a check reached the final dataset.

## 5. Cost

Measured on a free-tier model; one run each. `python scripts/run_report.py` prints these for any run.

| Step | Model calls | Prompt tokens | Model time |
|---|---|---|---|
| A specification | 1–3 per dataset | about 6k each | under 1 minute |
| ADSL program | about 50–70 | 130–210k | 4–6 minutes |
| ADAE program | 16–30 | 35–67k | 1–2 minutes |
| All 24 mock shells | 24 | about 122k | about 4.5 minutes |

Free-tier rate limits added waiting time on top of these.

## 6. How the AI should reach the tools: MCP vs code mode

Same job, same AI model (nemotron-3-ultra, temperature 0), same checks; only the way the AI reaches Sapient's functions changes. Four ADaM datasets (ADSL, ADAE, ADLBC, ADTTE), 20 target variables, 3 runs per design. Every design gets the same stopping rule: a variable is left for a person after 3 failed attempts, with a safety cap of 40 model calls.

The code and every result file are on the `bench/mcp-vs-code-mode` branch. `python bench/summarize.py` rebuilds this table from them.

| Design | Correct (of 20) | Prompt tokens | Steps |
|---|---|---|---|
| **Code mode:** the AI writes one program against a small API | **12.3 (10–14)** | **92k** | **21** |
| MCP, 8 task tools | 12.0 (11–13) | 160k | 42 |
| MCP, 8 task tools, several steps per call | 11.0 (10–12) | 147k | 34 |
| MCP, 8 task tools + 136 function tools behind search | 11.3 (11–12) | 164k | 41 |
| MCP, 8 task tools + 136 unused function tools on the menu | 11.3 (11–12) | 2.5M | 45 |
| MCP, 136 function tools on the menu | 8.7 (8–9) | 2.7M | 48 |
| MCP, 136 function tools behind keyword search | 8.7 (7–10) | 477k | 67 |
| MCP, 136 function tools behind ranked search (BM25), 1 run | 8.0 | 474k | 62 |
| MCP, 14 approved function tools | 7.7 (7–9) | 610k | 53 |
| MCP, 14 function tools with typed arguments, behind ranked search | 5.7 (3–7) | 477k | 66 |

Mean (and range) of 3 runs unless noted. The 8 task tools are `brief`, `get_spec_rule`, `get_admiral_signature`, `list_input_columns`, `get_conventions`, `describe_columns`, `run_step` and `status`; none of them is an admiral function. "Function tools" are one MCP tool per admiral function, with no free "run this R" tool and one `assign_column` tool for plain expressions.

What the tool list alone costs on every step, measured with one call per menu size:

| Tools on the menu | 8 | 25 | 50 | 144 |
|---|---|---|---|---|
| Prompt tokens per step | 1,015 | 6,908 | 18,508 | 53,148 |

What this shows:
- **A short MCP menu works.** Eight task tools scored 12.0 of 20.
- **Everything on the menu is paid for at every step.** The AI keeps no memory between steps, so it re-reads the menu and the whole conversation each time. Adding 136 tools it never used gave the same score at 16 times the tokens. Putting the same tools behind a search tool brought the cost back to 164k, and the AI never needed to search.
- **One tool per package function scored lower however it was offered** (5.7–8.7 of 20). Search cut its token cost but not its errors: a ranked search returned the exact function first for 11 of its 12 queries and the run still scored 8 of 20. The AI still builds the dataset one function at a time, passing every argument as a string, and each search is one more step.
- **Code mode ties the task tools on accuracy and wins on cost:** 12.3 against 12.0 of 20, at about 40% fewer tokens and half the steps. It is not more accurate, and its score varied from 10 to 14 between runs.
- **No patient-level data reached the AI** in any of these runs.
- **Not measured:** code mode whose functions call an MCP server. Our code mode called the same functions directly; the combination is expected to behave the same but has not been run.

## Withdrawn figures

These earlier claims were wrong. They're listed here because they show how the evaluation was corrected.

- **"94–98% value match":** these numbers were scored against a community dataset (`pharmaverseadam`) that is not the pilot's dataset. A comparison bug also skipped any value missing on only one side.
- **"Spec F1 0.77":** this mostly measured the standard variable list we gave the model.
- **The table-list benchmark:** it was scored against the SAP of a different study. It was retired.
- **The first MCP-vs-code-mode benchmark (v2): "142 tools cost 5.4 million tokens", "MCP 13.7 vs code mode 12 in every run".** In the 142-tool run the instructions told the AI to use `run_step`, so it never called one of the function tools; the designs had different turn limits (40 against 10); and the headline compared two versions of the API. It was rerun fairly as v3 (section 6).
- **The guardrail table "75 steps checked, 50 caught after running":** it mixed counts of code attempts with repeated failures of the same variable across rounds. Section 4 now counts variables.

## Not model output

These parts are hand-written scaffolding, not AI output:
- the default pipeline's ADSL/ADAE derivation templates;
- the five SDTM mapping programs (`sdtm.oak`, 98–100% match with `pharmaversesdtm`).
