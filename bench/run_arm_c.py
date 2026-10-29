"""Arm C (code mode): the model sees the Sapient functions as a small Python API and
writes ONE program that calls them. The harness runs it in a subprocess and shows the
model only what the program printed. The model may revise the program and try again.

Generated code is checked before it runs: it may import only `api`, `json` and `re`,
and may not use file, eval/exec or dunder access (code mode needs a sandbox; this is
a minimal one, plus a timeout).

Usage: SAPIENT_BENCH_DATASET=ADAE python bench/run_arm_c.py  -> bench/results/arm_c[_<ds>].json
"""
import ast
import inspect
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "bench"))

from openai import OpenAI
from config import CODEGEN_MODEL, MAX_TOKENS, NO_THINKING, NVIDIA_API_KEY, NVIDIA_BASE_URL, TEMPERATURE
from orchestration.llm_retry import create_with_retry
from tools import DATASET, SCRATCH, TARGETS, Session

MAX_ROUNDS = 10
ALLOWED_IMPORTS = {"api", "json", "re"}
FORBIDDEN_NAMES = {"open", "eval", "exec", "compile", "__import__", "getattr", "setattr", "delattr",
                   "globals", "locals", "vars", "input", "breakpoint"}
RESULTS = BASE_DIR / "bench" / "results" / "v2"


def api_doc() -> str:
    import api
    lines = []
    for fn in api.API_FUNCTIONS:
        lines.append(f"api.{fn.__name__}{inspect.signature(fn)}\n    {inspect.getdoc(fn)}")
    return "\n".join(lines)


TASK = """You are building the ADaM dataset {dataset} in R with the admiral package.
Derive these variables: {targets}.
You do this by writing ONE Python program that uses this API (import it with `import api`):

{doc}

Every api function returns a plain-text string; only api.get_spec_rule returns JSON (parse it with json.loads).
Text you want to read (conventions, columns, signatures, errors) reaches you only if your program prints it.
Each R step passed to api.run_step must be one statement `result <- result |> ...` that creates the variable.
Start your first program with print(api.brief(<all targets>)). Your program can look things up, call api.run_step for several variables, and inspect results in code.
Only what your program prints is shown back to you, so print what you need (for example each run_step result).
I will run the program and show you its output. If some variables are not accepted yet, reply with a revised
program; it starts from the steps already accepted. When every target is accepted, reply with the single word DONE.
Reply with the program in one ```python block. Allowed imports: api, json, re."""


def sandbox_violation(code: str) -> str | None:
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return f"SyntaxError: {e}"
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            bad = [a.name for a in node.names if a.name.split(".")[0] not in ALLOWED_IMPORTS]
        elif isinstance(node, ast.ImportFrom):
            bad = [node.module] if (node.module or "").split(".")[0] not in ALLOWED_IMPORTS else []
        else:
            bad = []
        if bad:
            return f"import not allowed: {bad}"
        if isinstance(node, ast.Name) and node.id in FORBIDDEN_NAMES:
            return f"name not allowed: {node.id}"
        if isinstance(node, ast.Attribute) and node.attr.startswith("_"):
            return f"private attribute access not allowed: {node.attr}"
    return None


def extract_program(text: str) -> str | None:
    m = re.search(r"```(?:python)?\s*\n(.*?)```", text or "", re.S)
    return m.group(1) if m else None


def run() -> dict:
    os.environ["SAPIENT_RUN_TAG"] = f"bench-arm-C-{DATASET}"
    run_dir = Path(tempfile.mkdtemp(dir=SCRATCH, prefix="armc_"))
    state, previews = run_dir / "state.json", run_dir / "previews.txt"
    os.environ["SAPIENT_BENCH_STATE"], os.environ["SAPIENT_BENCH_PREVIEWS"] = str(state), str(previews)  # api_doc imports api
    env ={**os.environ, "SAPIENT_BENCH_STATE": str(state), "SAPIENT_BENCH_PREVIEWS": str(previews),
           "PYTHONPATH": str(BASE_DIR / "bench")}
    llm = OpenAI(base_url=NVIDIA_BASE_URL, api_key=NVIDIA_API_KEY, timeout=300.0, max_retries=0)
    started = time.monotonic()
    log = {"arm": "C", "dataset": DATASET, "model": CODEGEN_MODEL, "turns": [], "programs_run": 0,
           "sandbox_rejections": 0, "output_bytes_to_model": 0, "patient_data_bytes": 0}
    messages = [{"role": "user", "content": TASK.format(dataset=DATASET, targets=", ".join(TARGETS), doc=api_doc())}]
    log["api_doc_tokens_est"] = len(api_doc()) // 4
    for turn in range(1, MAX_ROUNDS + 1):
        resp = create_with_retry(llm, model=CODEGEN_MODEL, messages=messages, temperature=TEMPERATURE,
                                 max_tokens=MAX_TOKENS, extra_body=NO_THINKING)
        text = resp.choices[0].message.content or ""
        log["turns"].append({"turn": turn, "prompt_tokens": resp.usage.prompt_tokens,
                             "completion_tokens": resp.usage.completion_tokens})
        messages.append({"role": "assistant", "content": text})
        program = extract_program(text)
        print(f"turn {turn}: prompt={resp.usage.prompt_tokens} program={'yes' if program else 'no'}", flush=True)
        if program is None:
            log["final_message"] = text[:300]
            break
        violation = sandbox_violation(program)
        if violation:
            log["sandbox_rejections"] += 1
            feedback = f"Program rejected by the sandbox before running: {violation}"
        else:
            prog_file = run_dir / f"program_{turn}.py"
            prog_file.write_text(program)
            log["programs_run"] += 1
            r = subprocess.run([sys.executable, str(prog_file)], capture_output=True, text=True,
                               timeout=1800, cwd=BASE_DIR, env=env)
            feedback = (r.stdout[-8000:] + ("\nSTDERR:\n" + r.stderr[-2000:] if r.returncode else "")).strip()
            if previews.exists():
                log["patient_data_bytes"] += sum(len(p.encode()) for p in previews.read_text().split("\n\x00\n")
                                                 if p.strip() and p.strip() in feedback)
                previews.unlink()
        log["output_bytes_to_model"] += len(feedback.encode())
        done = state.exists() and all(t in json.loads(state.read_text()) for t in TARGETS)
        if done:
            log["final_message"] = "(all targets accepted)"
            break
        messages.append({"role": "user", "content": f"Program output:\n{feedback or '(no output)'}"})
    log["score"] = Session(state).score()
    log["wall_seconds"] = round(time.monotonic() - started, 1)
    log["n_turns"] = len(log["turns"])
    log["prompt_tokens_total"] = sum(t["prompt_tokens"] for t in log["turns"])
    log["completion_tokens_total"] = sum(t["completion_tokens"] for t in log["turns"])
    log["max_context_tokens"] = max((t["prompt_tokens"] for t in log["turns"]), default=0)
    return log


if __name__ == "__main__":
    result = run()
    RESULTS.mkdir(exist_ok=True)
    suffix = "" if DATASET == "ADAE" else f"_{DATASET.lower()}"
    (RESULTS / f"arm_c{suffix}.json").write_text(json.dumps(result, indent=1))
    print(json.dumps({k: v for k, v in result.items() if k != "turns"}, indent=1))
