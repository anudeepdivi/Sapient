"""Deterministic Sapient functions every benchmark arm uses: MCP tools in arms A/B,
a plain Python API in arm C. Same functions underneath, so the arms differ only in
how the model reaches them.

Task: derive TARGETS for ADAE from the pilot (official) spec, starting from the ADAE
spine (AE + ADSL variables). Accepted steps persist in a Session; score() builds the
dataset and value-matches the targets against the CDISC pilot's own ADAE.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "scripts"))

import gen_derivations as g
from config import R_EXECUTABLE
from knowledge.admiral_functions import get_signatures, signatures_block
from r_layer.runner import run_adam_program
from specs.metacore_loader import get_spec_rules
from knowledge.adam_registry import classify
from templates.adam_templates import ADAM_INPUTS, input_columns_block, render_footer, render_header

# TTE has no spine in the main pipeline; the benchmark adds one here only (one row per
# safety-population subject, ADSL variables carried), leaving the pipeline untouched.
ADAM_INPUTS.setdefault("ADTTE", [("adsl", "data/adam/ADSL.xpt"), ("adae", "data/adam/ADAE.xpt")])
g.SPINES.setdefault("ADTTE", '''result <- adsl |>
  filter(SAFFL == "Y") |>
  dplyr::transmute(STUDYID, SITEID, USUBJID, AGE, AGEGR1, AGEGR1N, RACE, RACEN, SEX, SAFFL,
                   TRTSDT, TRTEDT, TRTP = TRT01P, TRTA = TRT01A, TRTAN = TRT01AN)''')

# Target variables per dataset (one per ADaM class). SAPIENT_BENCH_DATASET selects one.
TASKS = {
    "ADSL": ["TRTSDT", "AGEGR1", "SAFFL", "EFFFL", "DISCONFL"],          # SUBJECT
    "ADAE": ["ASTDT", "AENDT", "ASTDY", "TRTEMFL", "AOCCFL"],            # OCCDS
    "ADLBC": ["PARAMCD", "AVAL", "ADT", "ADY", "ABLFL"],                 # BDS
    "ADTTE": ["PARAMCD", "STARTDT", "ADT", "CNSR", "AVAL"],             # TTE
}
DATASET = os.getenv("SAPIENT_BENCH_DATASET", "ADAE")
TARGETS = TASKS[DATASET]
REFERENCE_DIR = "data/reference/pilot"
SCRATCH = BASE_DIR / "cache_store" / "bench"
# v3 (2026-11-15): the same stopping rule in every arm. A variable is closed after this many
# failed steps and left for a person; the turn/round caps in the runners remain only as safety.
MAX_ATTEMPTS = 3


class Session:
    """One benchmark run's state: the steps accepted so far."""

    def __init__(self, state_file: Path | None = None):
        self.rules = {r["variable"]: r for r in get_spec_rules(DATASET)}
        self.spec_order = list(self.rules)
        # code mode runs each program in a fresh process, so accepted steps persist on disk
        self.state_file = state_file
        self.accepted: dict[str, str] = json.loads(state_file.read_text()) if state_file and state_file.exists() else {}
        self.attempts_file = state_file.with_suffix(".attempts.json") if state_file else None
        self.failures: dict[str, int] = (json.loads(self.attempts_file.read_text())
                                         if self.attempts_file and self.attempts_file.exists() else {})
        self.submit_hint = ("run_step(variable, code) returns text starting with 'OK' when the step is kept; "
                            "anything else is the exact error or failed check, with what to fix.")
        SCRATCH.mkdir(parents=True, exist_ok=True)

    # ---- tools exposed to the model ----
    def get_spec_rule(self, variable: str) -> str:
        r = self.rules.get(variable.upper())
        if not r:
            return f"No spec rule for {variable}. Spec variables: {', '.join(self.spec_order)}"
        return json.dumps({k: r.get(k) for k in ("variable", "type", "length", "format", "ct", "derivation")})

    def get_admiral_signature(self, function_name: str) -> str:
        sig = get_signatures().get(function_name)
        return sig or f"{function_name} is not an allowed admiral function. Allowed: {', '.join(get_signatures())}"

    def list_input_columns(self) -> str:
        spine = sorted(g.spine_columns(DATASET, SCRATCH))
        return (input_columns_block(DATASET) +
                f"\n`result` starts as the ADAE spine with columns: {', '.join(spine)}")

    def get_conventions(self) -> str:
        return g.ADMIRAL_CONVENTIONS + g.CLASS_CONVENTIONS.get(classify(DATASET) or "", "")

    def run_step(self, variable: str, code: str) -> str:
        """Execute one `result <- result |> ...` step after the accepted ones; keep it if it passes."""
        variable = variable.upper()
        if variable not in self.rules:
            return self._failed(variable, f"ERROR: {variable} is not a variable in the spec. Each step must create one "
                                          "spec variable; do intermediate work inside that step.")
        if variable in self.closed:
            return (f"CLOSED: {variable} failed {MAX_ATTEMPTS} times and is left for a person. "
                    "Move on to the remaining variables.")
        err = g.snippet_gate(code)
        if err:
            return self._failed(variable, f"REJECTED by deterministic gate: {err}")
        snippets = {**self.accepted, variable: code}
        status, _ = g.run_steps(DATASET, snippets, self.spec_order, SCRATCH,
                                {v: g.check_spec(r) for v, r in self.rules.items()})
        st = (status or {}).get(variable, "ERROR: step not executed")
        if st == "OK":
            self.accepted[variable] = code
            if self.state_file:
                self.state_file.write_text(json.dumps(self.accepted))
            return f"OK: {variable} created and kept. Accepted so far: {', '.join(self.accepted)}"
        return self._failed(variable, st)

    def run_steps(self, steps: list[dict]) -> str:
        """Several {variable, code} steps in one execution; each is kept or fails on its own."""
        lines, todo = [], {}
        for step in steps:
            variable, code = str(step.get("variable", "")).upper(), str(step.get("code", ""))
            if variable not in self.rules:
                lines.append(f"{variable}: " + self._failed(variable, f"ERROR: {variable} is not a variable in the "
                             "spec. Each step must create one spec variable; do intermediate work inside that step."))
            elif variable in self.closed:
                lines.append(f"{variable}: CLOSED: failed {MAX_ATTEMPTS} times and is left for a person. Move on.")
            elif err := g.snippet_gate(code):
                lines.append(f"{variable}: " + self._failed(variable, f"REJECTED by deterministic gate: {err}"))
            else:
                todo[variable] = code
        if todo:
            status, _ = g.run_steps(DATASET, {**self.accepted, **todo}, self.spec_order, SCRATCH,
                                    {v: g.check_spec(r) for v, r in self.rules.items()})
            status = status or {}  # R writes an empty status list as []
            failed_now = {v for v in todo if status.get(v) != "OK"}
            for variable, code in todo.items():
                st = status.get(variable, "ERROR: step not executed")
                upstream = [v for v in failed_now - {variable} if re.search(rf"\b{v}\b", st)]
                if st == "OK":
                    self.accepted[variable] = code
                    lines.append(f"{variable}: OK, created and kept.")
                elif upstream:  # failed only because a step it needs failed in this same call: not counted
                    lines.append(f"{variable}: NOT COUNTED: it needs {', '.join(upstream)}, which failed in this call. "
                                 f"Resend it with the fix. ({st[:300]})")
                else:
                    lines.append(f"{variable}: " + self._failed(variable, st))
            if self.state_file:
                self.state_file.write_text(json.dumps(self.accepted))
        return "\n".join(lines + [f"Accepted so far: {', '.join(self.accepted) or 'none'}"])

    @property
    def closed(self) -> list[str]:
        return [v for v, n in self.failures.items() if n >= MAX_ATTEMPTS and v not in self.accepted]

    def _failed(self, variable: str, message: str) -> str:
        self.failures[variable] = self.failures.get(variable, 0) + 1
        if self.attempts_file:
            self.attempts_file.write_text(json.dumps(self.failures))
        if self.failures[variable] >= MAX_ATTEMPTS:
            message += (f"\nCLOSED: {variable} has now failed {MAX_ATTEMPTS} times and is left for a person. "
                        "Move on to the remaining variables.")
        return message

    def brief(self, variables: str) -> str:
        """Everything needed to derive the given comma-separated variables, in one text block:
        their spec rules, the verified conventions, the input columns and the allowed admiral signatures."""
        names = [v.strip().upper() for v in variables.split(",") if v.strip()]
        return "\n\n".join([
            "SPEC RULES:\n" + "\n".join(self.get_spec_rule(v) for v in names),
            "CONVENTIONS (verified against the installed package):\n" + self.get_conventions(),
            "INPUTS:\n" + self.list_input_columns(),
            "ALLOWED ADMIRAL FUNCTIONS:\n" + signatures_block(),
            "SUBMITTING: " + self.submit_hint])

    def describe_columns(self, columns: str) -> str:
        """Profile of comma-separated columns in the dataset built so far: type, rows, missing,
        distinct count, and the most common values of low-cardinality text columns only.
        Never returns patient-level rows."""
        cols = [c.strip().upper() for c in columns.split(",") if c.strip()]
        r_cols = "c(" + ", ".join(json.dumps(c) for c in cols) + ")"
        profile = (f"for (v in intersect({r_cols}, names(result))) {{ x <- result[[v]]; nd <- length(unique(x)); "
                   "cat(sprintf('%s: %s, %d rows, %d missing, %d distinct', v, class(x)[1], length(x), sum(is.na(x)), nd)); "
                   "if (is.character(x) && nd <= 30 && !grepl('ID$|DTC$', v)) "
                   "cat(' | values:', paste(head(names(sort(table(x), decreasing = TRUE)), 10), collapse = ', ')); cat('\\n') }")
        program = "\n\n".join([render_header(DATASET), g.spine(DATASET), *self._ordered(), profile])
        f = SCRATCH / "describe.R"
        f.write_text(program)
        out = subprocess.run([R_EXECUTABLE, str(f)], capture_output=True, text=True, timeout=300, cwd=BASE_DIR)
        return out.stdout.strip()[-4000:] or out.stderr.strip()[-1500:]

    def status(self) -> str:
        """Which target variables are accepted and which remain."""
        done = [t for t in TARGETS if t in self.accepted]
        closed = [t for t in TARGETS if t in self.closed]
        left = [t for t in TARGETS if t not in done and t not in closed]
        return (f"accepted: {', '.join(done) or 'none'} | closed (left for a person): {', '.join(closed) or 'none'}"
                f" | remaining: {', '.join(left) or 'none'}")

    # ---- harness only (not a tool) ----
    def _ordered(self) -> list[str]:
        return [self.accepted[v] for v in g.topo_order(self.accepted, self.spec_order)]

    def score(self) -> dict:
        return {**self._score(), "closed": [t for t in TARGETS if t in self.closed],
                "failed_attempts": {t: self.failures.get(t, 0) for t in TARGETS}}

    def _score(self) -> dict:
        footer = render_footer(DATASET).replace(
            "metatools::check_variables(result, mc_ds)",
            "tryCatch(metatools::check_variables(result, mc_ds), error = function(e) message(conditionMessage(e)))")
        program = "\n\n".join([render_header(DATASET), g.spine(DATASET), *self._ordered(), footer])
        out_dir = SCRATCH / "adam"
        out_dir.mkdir(exist_ok=True)
        parents = {Path(p).stem: BASE_DIR / p for _, p in ADAM_INPUTS[DATASET] if p.startswith("data/adam/")}
        built = run_adam_program(DATASET, program, adam_dir=out_dir, parent_inputs=parents, timeout=600)
        if not built["success"]:
            return {"built": False, "targets_correct": 0, "rates": {}}
        rates_file = Path(tempfile.mkstemp(suffix=".json", dir=SCRATCH)[1])
        subprocess.run([R_EXECUTABLE, str(BASE_DIR / "r_layer/scripts/compare_reference.R"), DATASET, str(out_dir)],
                       capture_output=True, text=True, timeout=300, cwd=BASE_DIR,
                       env={**os.environ, "SAPIENT_REFERENCE_DIR": REFERENCE_DIR, "SAPIENT_RATES_JSON": str(rates_file)})
        rates = {v: r for v, r in json.loads(rates_file.read_text() or "{}").items() if v in TARGETS}
        rates_file.unlink()
        ok = [v for v in TARGETS if isinstance(rates.get(v), (int, float)) and rates[v] >= 0.99]
        return {"built": True, "targets_correct": len(ok), "correct": ok,
                "rates": {v: rates.get(v) for v in TARGETS}}


# API v2 (2026-10-29): brief / describe_columns / status replace preview_rows, which
# returned patient rows. v1 results are in bench/results/, v2 in bench/results/v2/.
TOOL_NAMES = ["brief", "get_spec_rule", "get_admiral_signature", "list_input_columns",
              "get_conventions", "describe_columns", "run_step", "status"]
