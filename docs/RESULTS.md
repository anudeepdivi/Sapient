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
  - VISNUMEN, BMIBL and DURDIS are genuine code-generation misses.
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

Example: ADSL, from the official specification.

| Steps checked | Rejected before running | Caught after running | Fixed by feeding the error back | Never passed (left out) |
|---|---|---|---|---|
| 75 | 5 | 50 | 15 | 5 |

Nothing that failed a check reached the final dataset.

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

Same job, same AI model, same checks; only the way the AI calls the tools differs. Four datasets, 20 target variables. The code is on the `bench/mcp-vs-code-mode` branch.

| Approach | Correct (of 20) | Prompt tokens | Patient rows sent to the AI |
|---|---|---|---|
| MCP, 6 hand-picked tools | 13 | 171k | none |
| MCP, all 142 admiral functions as tools | 10 | **5.4 million** | none |
| Code mode, first API | 8 | 156k | yes, twice |
| MCP, 6 tools, redesigned API | 13 | 146k | none |
| **Code mode, redesigned API** | **12** | **113k** | **none, by design** |

- **MCP with everything plugged in:** it re-read about 48k tokens of tool descriptions on every turn, and on two of the four datasets it ran out of turns.
- **The redesigned API** gives the AI one call with everything it needs, returns column summaries instead of patient rows, and adds a progress check.
- These are single runs; repeats are in progress.

## Withdrawn figures

These earlier claims were wrong. They're listed here because they show how the evaluation was corrected.

- **"94–98% value match":** these numbers were scored against a community dataset (`pharmaverseadam`) that is not the pilot's dataset. A comparison bug also skipped any value missing on only one side.
- **"Spec F1 0.77":** this mostly measured the standard variable list we gave the model.
- **The table-list benchmark:** it was scored against the SAP of a different study. It was retired.

## Not model output

These parts are hand-written scaffolding, not AI output:
- the default pipeline's ADSL/ADAE derivation templates;
- the five SDTM mapping programs (`sdtm.oak`, 98–100% match with `pharmaversesdtm`).
