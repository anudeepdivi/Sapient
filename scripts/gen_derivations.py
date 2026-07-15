"""Per-variable derivation codegen experiment (replaces the whole-chain approach
that hit Nemotron's quality wall). One short LLM call per spec variable produces a
single pipe step; steps are dependency-ordered, executed incrementally against real
data, and failing steps regenerate alone with their specific error. Variables that
never pass are omitted and flagged — the program still builds from the passing set.

Usage: python scripts/gen_derivations.py ADSL
Outputs: data/adam/{ds}_pervar.R, data/adam_experiment/{ds}.xpt, coverage report.
"""
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from openai import OpenAI
from cache.prompt_cache import get_cached, set_cached
from config import (BASE_DIR, CODEGEN_FALLBACK_MODEL, CODEGEN_MODEL, MAX_TOKENS,
                    NVIDIA_API_KEY, NVIDIA_BASE_URL, R_EXECUTABLE, TEMPERATURE)
from knowledge.admiral_functions import signatures_block
from orchestration.llm_retry import create_with_retry
from r_layer.deterministic_checks import fix_quoted_symbol_args, run_gate, strip_markdown_fences
from specs.metacore_loader import get_spec_rules
from templates.adam_templates import ADAM_INPUTS, input_columns_block, render_footer, render_header

client = OpenAI(base_url=NVIDIA_BASE_URL, api_key=NVIDIA_API_KEY, timeout=180.0, max_retries=0)

# Class-keyed structural spine: population + spec-driven CT helper. Not dataset
# logic — the same 3 lines serve every dataset of the class.
SPINES = {
    "ADSL": '''ct_map <- function(dataset, variable) {
  md <- suppressWarnings(metacore::select_dataset(mc, dataset))
  cid <- md$value_spec$code_id[match(variable, md$value_spec$variable)]
  rows <- which(!is.na(cid) & md$codelist$code_id == cid)
  if (length(rows) == 0) return(setNames(numeric(0), character(0)))
  codes <- md$codelist$codes[[rows[1]]]
  if (is.null(codes) || !"code" %in% names(codes)) return(setNames(numeric(0), character(0)))
  setNames(suppressWarnings(as.numeric(codes$code)), codes$decode)
}

result <- dm |>
  filter(ACTARMCD != "SCRNFAIL", ARMCD != "SCRNFAIL", !grepl("SCREEN", toupper(ARM)))''',
}

STEP_PROMPT = """You write ONE step of an R derivation pipeline for ADaM dataset {dataset} (CDISC pilot study).

Already in scope:
- SDTM dataframes (lowercase) with these columns:
{input_columns}
- `result`: the {dataset} under construction. It starts from the columns of dm and gains one variable per step.
- Spec variables derived in OTHER steps (you may reference them; steps are reordered automatically): {pending}
- helper ct_map(dataset, variable): named numeric vector mapping decode labels -> numeric codes from the study spec codelists. Use it for numeric-code variables (e.g. unname(ct_map("{dataset}", "RACEN")[RACE])). NEVER hardcode treatment/arm/race label strings.
- admiral is loaded. Allowed admiral derivation functions (exact signatures):
{signatures}

Derive exactly this variable: {var} ({meta})
Spec derivation rule: "{derivation}"

OUTPUT CONSTRAINTS (a deterministic gate rejects violations):
- exactly ONE R statement, starting with `result <- result |>` and using the native pipe |>
- dplyr verbs and the allowed admiral functions only; no library(), no read_xpt, no other assignments
- reference only columns/variables listed above
- for dates use admiral::convert_dtc_to_dt or derive_vars_dt
- admiral arg SHAPES (syntax, not task logic): by_vars, new_vars, order take exprs() — e.g. by_vars = exprs(USUBJID), order = exprs(AESEQ), new_vars = exprs(TRT01PN = EXDOSE). filter_add takes a BARE condition, never exprs() — e.g. filter_add = EXSEQ == 1
- derive_vars_merged has exactly this shape: derive_vars_merged(result, dataset_add = <source sdtm df>, by_vars = exprs(USUBJID), new_vars = exprs(NEW = SRC), filter_add = <condition>) — the SOURCE domain goes in dataset_add (NOT dataset); there is NO `filter` or standalone `new_var` argument
Return ONLY the R code. No markdown, no comments, no explanation."""


def domain_gap(derivation: str, available: set[str]) -> str | None:
    doms = set(re.findall(r"\b([A-Z]{2})\.(?=[A-Z])", derivation or ""))
    missing = doms - available
    return ",".join(sorted(missing)) if missing else None


def gen_step(dataset, var, meta, derivation, pending, feedback):
    prompt = STEP_PROMPT.format(
        dataset=dataset, var=var, meta=meta, derivation=derivation,
        pending=", ".join(pending), input_columns=input_columns_block(dataset),
        signatures=signatures_block())
    if feedback:
        prompt += f"\n\nYOUR PREVIOUS ATTEMPT FAILED — fix this exact problem:\n{feedback}\nPrevious attempt:\n{feedback_code.get(var, '')}"
    key = hashlib.sha256(f"{CODEGEN_MODEL}\n{prompt}".encode()).hexdigest()
    cached = get_cached(key)
    if cached:
        return cached
    resp = create_with_retry(client, fallback_model=CODEGEN_FALLBACK_MODEL,
                             model=CODEGEN_MODEL,
                             messages=[{"role": "user", "content": prompt}],
                             temperature=TEMPERATURE, max_tokens=MAX_TOKENS)
    code = fix_quoted_symbol_args(strip_markdown_fences(resp.choices[0].message.content.strip()))
    set_cached(key, code)
    return code


def snippet_gate(code: str) -> str | None:
    if not code.strip().startswith("result <- result"):
        return "statement must start with `result <- result |>`"
    if code.count("<-") != 1:
        return "exactly one assignment (to result) is allowed"
    gate = run_gate(code)
    if not gate["passed"]:
        return "; ".join(gate["issues"])
    return None


def spec_deps(todo: dict) -> dict[str, set]:
    names = set(todo)
    return {var: {t for t in re.findall(r"\b[A-Z][A-Z0-9]{1,7}\b", deriv or "")
                  if t in names and t != var}
            for var, (meta, deriv) in todo.items()}


def topo_order(snippets: dict[str, str], spec_order: list[str]) -> list[str]:
    deps = {}
    for var, code in snippets.items():
        tokens = set(re.findall(r"\b[A-Z][A-Z0-9]{1,7}\b", code))
        deps[var] = {t for t in tokens if t in snippets and t != var}
    ordered, placed = [], set()
    pool = [v for v in spec_order if v in snippets]
    while pool:
        ready = [v for v in pool if deps[v] <= placed]
        if not ready:  # cycle — fall back to spec order for the remainder
            ordered.extend(pool)
            break
        ordered.extend(ready)
        placed.update(ready)
        pool = [v for v in pool if v not in placed]
    return ordered


def run_steps(dataset, snippets, spec_order, scratch):
    order = topo_order(snippets, spec_order)
    lines = [render_header(dataset), "", SPINES[dataset], "",
             ".status <- list()",
             ".try_step <- function(nm, f) {",
             "  out <- tryCatch(f(result), error = function(e) e)",
             "  if (inherits(out, 'error')) .status[[nm]] <<- paste0('ERROR: ', conditionMessage(out))",
             "  else if (!nm %in% names(out)) .status[[nm]] <<- 'ERROR: step ran but did not create the column'",
             "  else { .status[[nm]] <<- 'OK'; result <<- out }",
             "}"]
    for var in order:
        body = snippets[var].strip().replace("result <- result", "result", 1)
        lines.append(f".try_step({var!r}, function(result) {{\n{body}\n}})")
    lines.append("cat('\\n===STEP_STATUS===\\n'); cat(jsonlite::toJSON(.status, auto_unbox = TRUE))")
    driver = scratch / f"steps_{dataset}.R"
    driver.write_text("\n".join(lines))
    r = subprocess.run([R_EXECUTABLE, str(driver)], capture_output=True, text=True,
                       timeout=600, cwd=BASE_DIR)
    marker = "===STEP_STATUS==="
    if marker not in r.stdout:
        raise RuntimeError(f"step driver crashed:\n{r.stderr[-2000:]}")
    return json.loads(r.stdout.split(marker, 1)[1].strip()), order


feedback_code: dict[str, str] = {}


def main(dataset: str):
    scratch = BASE_DIR / "cache_store"
    scratch.mkdir(exist_ok=True)
    available = {v.upper() for v, _ in ADAM_INPUTS[dataset]} - {"ADSL"}
    rules = get_spec_rules(dataset)
    dm_cols = set(subprocess.run(
        [R_EXECUTABLE, "-e", f'cat(names(haven::read_xpt("{dict(ADAM_INPUTS[dataset])["dm"]}")))'],
        capture_output=True, text=True, timeout=60, cwd=BASE_DIR).stdout.split())

    status: dict[str, str] = {}
    todo, spec_order = {}, []
    for r in rules:
        var, deriv = r["variable"], r.get("derivation") or ""
        spec_order.append(var)
        meta = r.get("type", "?") + (f" len<={r['length']}" if r.get("length") else "") + \
               (f" CT:{{{'|'.join(r['ct'])}}}" if r.get("ct") else "")
        gap = domain_gap(deriv, available)
        if gap:
            status[var] = f"unavailable-source: no {gap} domain in study data"
        elif var in dm_cols and re.fullmatch(rf"DM\.{var}", deriv.strip()):
            status[var] = "inherited from DM"
        else:
            todo[var] = (meta, deriv)

    snippets: dict[str, str] = {}
    gate_err: dict[str, str] = {}
    exec_err = {v: None for v in todo}
    deps = spec_deps(todo)
    for rnd in range(1, 6):
        pending = sorted(todo)
        failing = {v for v in todo if v not in snippets or exec_err[v] is not None}
        for var in sorted(failing):
            if deps[var] & failing and var in snippets:
                continue  # blocked by a failing parent — keep snippet, retry via execution
            code = gen_step(dataset, var, *todo[var], pending=[p for p in pending if p != var],
                            feedback=gate_err.get(var) or exec_err.get(var))
            err = snippet_gate(code)
            if err:
                feedback_code[var] = code
                gate_err[var] = f"gate: {err}"
                snippets.pop(var, None)
                continue
            gate_err.pop(var, None)
            snippets[var] = code
        step_status, _ = run_steps(dataset, snippets, spec_order, scratch)
        for var in list(snippets):
            st = step_status.get(var, "ERROR: step not executed")
            if st == "OK":
                exec_err[var] = None
            else:
                feedback_code[var] = snippets[var]
                exec_err[var] = st
        done = [v for v in todo if v in snippets and exec_err[v] is None]
        print(f"round {rnd}: {len(done)} ok, {len(todo) - len(done)} failing")
        if len(done) == len(todo):
            break

    passing = {v for v in todo if v in snippets and exec_err[v] is None}
    for var in todo:
        if var in passing:
            status[var] = "generated"
        else:
            why = exec_err.get(var) or gate_err.get(var) or "no output"
            status[var] = f"failed after 5 rounds: {str(why)[:160]}"
    snippets = {v: snippets[v] for v in passing}

    order = topo_order(snippets, spec_order)
    footer = render_footer(dataset).replace("data/adam/", "data/adam_experiment/").replace(
        "metatools::check_variables(result, mc_ds)",
        "tryCatch(metatools::check_variables(result, mc_ds), error = function(e) message(conditionMessage(e)))")
    program = "\n\n".join([render_header(dataset), SPINES[dataset],
                           *[snippets[v] for v in order], footer])
    out = BASE_DIR / "data" / "adam" / f"{dataset}_pervar.R"
    out.write_text(program)
    (BASE_DIR / "data" / "adam_experiment").mkdir(exist_ok=True)
    r = subprocess.run([R_EXECUTABLE, str(BASE_DIR / "r_layer" / "scripts" / "run_adam.R"),
                        str(out), dataset], capture_output=True, text=True, timeout=600, cwd=BASE_DIR)
    built = "SUCCESS" in r.stdout

    print(f"\n=== {dataset} per-variable coverage ===")
    for var in spec_order:
        print(f"  {var:<10} {status.get(var, '?')}")
    counts = {}
    for s in status.values():
        counts[s.split(":")[0]] = counts.get(s.split(":")[0], 0) + 1
    print(f"summary: {counts}")
    print(f"assembled program executes: {built}")
    if not built:
        print(r.stdout[-500:], r.stderr[-1500:])
    if built:
        cmp = subprocess.run([R_EXECUTABLE, str(BASE_DIR / "r_layer" / "scripts" / "compare_reference.R"),
                              dataset, "data/adam_experiment"], capture_output=True, text=True,
                             timeout=300, cwd=BASE_DIR)
        print(cmp.stdout)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "ADSL")
