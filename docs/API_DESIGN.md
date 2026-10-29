# Sapient API: design (target: mid-January 2027)

**Status: design only. Nothing here is built yet.**

The goal is to let a statistical programmer point Sapient at their own study and use it in about five minutes. It should not require knowing how AI agents, MCP or prompts work.

## Why an API, and why it has to be designed carefully

We benchmarked three ways of giving an AI model access to Sapient's tools on four kinds of ADaM dataset (subject-level, adverse events, lab, time-to-event):

| Approach | Correct (of 20) | Tokens used | Patient rows sent to the AI |
|---|---|---|---|
| MCP, 6 hand-picked tools | 13.7 | 321k | none |
| MCP, every admiral function as a tool (142) | 10 | 5.4M | none |
| Code mode, first API version | 10 | 156k | yes, twice |
| **Code mode, redesigned API** | **12** | **105k** | **none, by design** |

The MCP and redesigned-code-mode rows are the average of 3 runs; the other two are single runs.

Code mode is the cheapest approach, but only when the API it calls is designed for an AI to use. The redesign changed four things, and they are this API's rules:

1. **One call gives the AI everything it needs.** `brief()` returns the spec rules, the verified conventions, the input columns and the allowed functions for the variables being derived. The AI doesn't have to discover them.
2. **Every return value says what it is.** Plain text or JSON is stated in the documentation, never left to guess. One ambiguous return type cost a full benchmark run.
3. **Patient-level rows never leave the API.** Data inspection returns column profiles: type, missing count, distinct count, and the common values of categorical columns.
4. **Errors say what to fix.** Every guardrail failure names the problem and the fix, for example "TRTSDT is text but the spec says a date; convert with `derive_vars_dt(new_vars_prefix = "TRTS")`".

## Who it's for

Statistical programmers and beginner-level software engineers in pharma. Every choice favours "easy to start" over "elegant":

- one install command;
- one config file;
- one command per job;
- a quickstart that runs on the public CDISC pilot study before you try your own;
- a setup check that says, in plain words, what is missing.

## How it will look

### 1. Install and check

```bash
pip install git+https://github.com/<owner>/Sapient
sapient check
```

`sapient check` reports, one line each:
- Python version;
- R installed;
- each required R package installed (`admiral`, `metacore`, `xportr`, ...);
- the API key set;
- the study config readable.

Each failing line comes with the exact command that fixes it.

### 2. Describe your study in one file

```yaml
# study.yaml
study: CDISCPILOT01
sap: docs/sap.pdf                  # the Statistical Analysis Plan
sdtm: data/sdtm/                   # folder of SDTM .xpt files
spec: specs/adam_define.xml        # optional: an existing spec (Define-XML or Excel)
r_package: admiral                 # or your in-house package
output: out/

datasets:
  ADSL:
    inputs: [DM, EX, DS, VS, MH, SV, QS, SC]
    population: ACTARMCD != "SCRNFAIL"     # the one study-specific line
  ADAE:
    inputs: [AE, ADSL]

model:
  provider: nvidia                 # any OpenAI-compatible endpoint
  name: nvidia/nemotron-3-ultra-550b-a55b
  api_key_env: NVIDIA_API_KEY
```

The datasets' inputs and population filter come from this file, not from code. This also closes the current portability gap, where study logic is hardcoded.

### 3. One command per job

| Command | What it does | Uses AI? |
|---|---|---|
| `sapient spec ADSL` | Drafts the ADSL spec from the SAP plus the ADaM IG conventions, then checks every column it cites | yes |
| `sapient lint ADSL` | Checks a spec for structural problems, with no AI | no |
| `sapient build ADSL` | Generates the R program variable by variable, runs it, and applies every guardrail | yes |
| `sapient report ADSL` | Shows cost (tokens, time) and what each guardrail caught | no |
| `sapient compare ADSL --reference ref/` | Compares a built dataset with a reference, cell by cell | no |

Every command writes plain files you can open: the spec as JSON or Excel, the R program, the dataset as `.xpt`, and a short report.

### 4. Or call it from Python (code mode)

```python
import sapient

study = sapient.Study("study.yaml")
print(study.brief("ADAE", ["ASTDT", "TRTEMFL"]))      # everything needed for these variables
result = study.run_step("ADAE", "ASTDT",
    'result <- result |> derive_vars_dt(new_vars_prefix = "AST", dtc = AESTDTC)')
print(result.ok, result.message)                       # True, "OK: ASTDT created and kept"
print(study.status("ADAE"))                            # accepted vs remaining variables
print(study.describe_columns("ADAE", ["AESEV"]))       # a profile, never patient rows
```

This is the same API an AI model uses in code mode, which is the point: a human and an AI work through the same well-documented functions.

## What it will not do (yet)

- Tables, listings and figures (TLFs);
- SDTM generation;
- a graphical interface;
- validated-environment (GxP) qualification. That remains the sponsor's process, and every output is a plain file that a programmer reviews.

## Build plan (on the user's signal; target mid-January 2027)

1. **Study config:** load `study.yaml` and replace the hardcoded inputs and population filters.
2. **Package skeleton:** the `sapient` command, with `check` first.
3. **Wrap the existing pieces** behind `spec`, `lint`, `build`, `report` and `compare`. These all exist today as scripts.
4. **Python API:** `Study`, `brief`, `run_step`, `status`, `describe_columns`, with result objects that have `.ok` and `.message`.
5. **Quickstart:** the CDISC pilot study end to end in about five minutes.
6. **Docs:** one page per command, written for statistical programmers.
