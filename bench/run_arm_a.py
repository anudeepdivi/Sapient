"""MCP arms: the model reaches Sapient's tools through a real MCP server (stdio).

  A        the task-sized tools (brief, run_step, ...)
  A136     the same tools and prompt, with a tool per admiral function alongside
  F14      function-sized tools only (the functions the gate allows) + assign_column; no run_step
  FALL     as F14, with every exported admiral function on the menu
  FSEARCH  as FALL, but function tools are found with search_tools and offered only after that
  FBM25    as FSEARCH, with the ranked search (BM25 over name, description and argument names)
  ASEARCH  arm A's tools and prompt, with the function tools behind the ranked search
  AMULTI   arm A with run_steps (several steps per call) in place of run_step
  FTYPED   gate-approved function tools only, typed arguments, behind the ranked search; + assign_column
  MENU     no run: one call per menu size, recording the prompt tokens the tool list costs each step

Records, per run: turns, every tool call and its outcome, prompt tokens per turn (the context
the model re-reads every turn), menu size, tool-result bytes, wall time, and the target score.

Usage: python bench/run_arm_a.py [ARM]   -> bench/results/<SAPIENT_BENCH_RESULTS>/arm_<arm>[_<ds>].json
"""
import json
import os
import random
import re
import sys
import time
from pathlib import Path

import anyio

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "bench"))

from mcp import Client, StdioServerParameters
from openai import OpenAI
from config import CODEGEN_MODEL, MAX_TOKENS, NO_THINKING, NVIDIA_API_KEY, NVIDIA_BASE_URL, TEMPERATURE
from orchestration.llm_retry import create_with_retry
from tools import DATASET, TARGETS

MAX_TURNS = 40
PATIENT_DATA_TOOLS = set()  # v2: no tool returns patient rows
HARNESS_ONLY = {"score_run"}
RESULTS = BASE_DIR / "bench" / "results" / os.getenv("SAPIENT_BENCH_RESULTS", "v3")
MODEL = os.getenv("SAPIENT_BENCH_MODEL", CODEGEN_MODEL)

CLOSE_RULE = ("A variable that fails 3 times is closed and left for a person: do not retry it, move on. "
              "When every target is done or closed, reply with the single word DONE.")
TASK = f"""You are building the ADaM dataset {DATASET} in R with the admiral package, using the tools provided.
Derive these variables, in a sensible order: {', '.join(TARGETS)}.
Start with brief() for all targets. For each variable, call run_step
with one statement `result <- result |> ...` that creates it. If run_step returns an error, fix the code and call
run_step again. A variable is done when run_step returns OK. {CLOSE_RULE}"""
TASK_F = f"""You are building the ADaM dataset {DATASET} in R with the admiral package, using the tools provided.
Derive these variables, in a sensible order: {', '.join(TARGETS)}.
Start with brief() for all targets. Create each variable with the tools provided: an admiral function tool, or
assign_column for a plain R expression. If a tool returns an error, fix the call and try again.
A variable is done when a tool returns OK for it. {CLOSE_RULE}"""
TASK_F_SEARCH = TASK_F + """
The admiral function tools are not listed up front: call search_tools to find the ones you need. The tools it
returns can be called from your next step on."""
TASK_A_SEARCH = TASK + """
There is also one tool per admiral function (named admiral_<function>), not listed up front: call search_tools
if you would rather use one than write the statement yourself. The tools it returns can be called from your
next step on."""
SEARCH_ARMS = {"FSEARCH", "FBM25", "ASEARCH", "FTYPED"}
TASK_MULTI = f"""You are building the ADaM dataset {DATASET} in R with the admiral package, using the tools provided.
Derive these variables, in a sensible order: {', '.join(TARGETS)}.
Start with brief() for all targets. Then call run_steps with every step you can write, each one statement
`result <- result |> ...` that creates its variable; steps that depend on each other may go in the same call.
Resend only the steps that failed, fixed. A variable is done when run_steps returns OK for it. {CLOSE_RULE}"""
TASK_F_TYPED = TASK_F_SEARCH + """
Function tool arguments are typed: give columns as lists, new variables as name -> expression maps, and text as
plain text (the server adds R's quotes)."""

ARMS = {  # arm -> (server file, SAPIENT_BENCH_B_MODE, task)
    "A": ("mcp_server.py", "", TASK),
    "A136": ("mcp_server_b.py", "pad", TASK),
    "F14": ("mcp_server_b.py", "f14", TASK_F),
    "FALL": ("mcp_server_b.py", "fall", TASK_F),
    "FSEARCH": ("mcp_server_b.py", "fsearch", TASK_F_SEARCH),
    "FBM25": ("mcp_server_b.py", "fbm25", TASK_F_SEARCH),
    "ASEARCH": ("mcp_server_b.py", "padsearch", TASK_A_SEARCH),
    "AMULTI": ("mcp_server.py", "multi", TASK_MULTI),
    "FTYPED": ("mcp_server_b.py", "ftyped", TASK_F_TYPED),
}


def openai_tools(mcp_tools) -> list[dict]:
    return [{"type": "function", "function": {"name": t.name, "description": t.description or "",
                                              "parameters": t.input_schema}}
            for t in mcp_tools if t.name not in HARNESS_ONLY]


def server_params(server_file: str, mode: str) -> StdioServerParameters:
    return StdioServerParameters(command=sys.executable, args=[str(BASE_DIR / "bench" / server_file)],
                                 cwd=str(BASE_DIR),  # the server needs SAPIENT_BENCH_DATASET
                                 env={**os.environ, "SAPIENT_BENCH_B_MODE": mode})


async def run(arm: str = "A") -> dict:
    server_file, mode, task = ARMS[arm]
    os.environ["SAPIENT_RUN_TAG"] = f"bench-arm-{arm}-{DATASET}"
    llm = OpenAI(base_url=NVIDIA_BASE_URL, api_key=NVIDIA_API_KEY, timeout=300.0, max_retries=0)
    started = time.monotonic()
    log = {"arm": arm, "dataset": DATASET, "model": MODEL, "turns": [], "tool_calls": {}, "calls": [],
           "tools_loaded": [], "tool_result_bytes": 0, "patient_data_bytes": 0}
    async with Client(server_params(server_file, mode), read_timeout_seconds=900) as mcp:
        all_tools = {t["function"]["name"]: t for t in openai_tools((await mcp.list_tools()).tools)}
        # search arms: function tools stay off the menu until search_tools returns them
        menu = [n for n in all_tools if not (arm in SEARCH_ARMS and n.startswith("admiral_"))]
        log["n_tools"] = len(menu)
        log["n_tools_server"] = len(all_tools)
        log["tool_definition_tokens_est"] = len(json.dumps([all_tools[n] for n in menu])) // 4
        messages = [{"role": "user", "content": task}]
        for turn in range(1, MAX_TURNS + 1):
            resp = create_with_retry(llm, model=MODEL, messages=messages, tools=[all_tools[n] for n in menu],
                                     temperature=TEMPERATURE, max_tokens=MAX_TOKENS, extra_body=NO_THINKING)
            msg = resp.choices[0].message
            calls = msg.tool_calls or []
            log["turns"].append({"turn": turn, "prompt_tokens": resp.usage.prompt_tokens,
                                 "completion_tokens": resp.usage.completion_tokens,
                                 "menu_size": len(menu), "tools": [c.function.name for c in calls]})
            print(f"turn {turn}: prompt={resp.usage.prompt_tokens} tools={[c.function.name for c in calls]}", flush=True)
            if not calls:
                log["final_message"] = (msg.content or "")[:300]
                break
            messages.append(msg.model_dump(exclude_none=True))
            for c in calls:
                name = c.function.name
                log["tool_calls"][name] = log["tool_calls"].get(name, 0) + 1
                try:
                    if name not in menu:
                        raise ValueError(f"{name} is not an available tool")
                    result = await mcp.call_tool(name, json.loads(c.function.arguments or "{}"))
                    text = "\n".join(getattr(x, "text", "") for x in result.content)
                except Exception as e:  # malformed arguments are the model's error; report back, keep going
                    text = f"TOOL ERROR: {e}"
                if name == "search_tools":
                    found = [n for n in re.findall(r"^(admiral_\w+):", text, re.M) if n in all_tools and n not in menu]
                    menu.extend(found)
                    log["tools_loaded"].extend(found)
                log["calls"].append({"turn": turn, "tool": name, "args": (c.function.arguments or "")[:300],
                                     "outcome": text[:300]})
                log["tool_result_bytes"] += len(text.encode())
                if name in PATIENT_DATA_TOOLS:
                    log["patient_data_bytes"] += len(text.encode())
                messages.append({"role": "tool", "tool_call_id": c.id, "content": text})
        score = await mcp.call_tool("score_run", {})
        log["score"] = json.loads(score.content[0].text)
    log["wall_seconds"] = round(time.monotonic() - started, 1)
    log["n_turns"] = len(log["turns"])
    log["prompt_tokens_total"] = sum(t["prompt_tokens"] for t in log["turns"])
    log["completion_tokens_total"] = sum(t["completion_tokens"] for t in log["turns"])
    log["max_context_tokens"] = max((t["prompt_tokens"] for t in log["turns"]), default=0)
    return log


async def measure_menus() -> list[dict]:
    """What the tool list alone costs per step: one call per menu size, reading the prompt tokens the API reports."""
    llm = OpenAI(base_url=NVIDIA_BASE_URL, api_key=NVIDIA_API_KEY, timeout=300.0, max_retries=0)
    async with Client(server_params("mcp_server_b.py", "pad"), read_timeout_seconds=900) as mcp:
        tools = openai_tools((await mcp.list_tools()).tools)
    base = [t for t in tools if not t["function"]["name"].startswith("admiral_")]
    extra = sorted((t for t in tools if t["function"]["name"].startswith("admiral_")), key=lambda t: t["function"]["name"])
    random.Random(0).shuffle(extra)
    rows = []
    for menu in (None, base, base + extra[:17], base + extra[:42], base + extra):
        kwargs = {"tools": menu} if menu else {}
        resp = create_with_retry(llm, model=MODEL, messages=[{"role": "user", "content": TASK}],
                                 temperature=TEMPERATURE, max_tokens=8, extra_body=NO_THINKING, **kwargs)
        rows.append({"n_tools": len(menu or []), "prompt_tokens": resp.usage.prompt_tokens})
        print(rows[-1], flush=True)
    return rows


if __name__ == "__main__":
    arm = sys.argv[1] if len(sys.argv) > 1 else "A"
    RESULTS.mkdir(exist_ok=True)
    if arm == "MENU":
        (RESULTS / "menu_sizes.json").write_text(json.dumps({"model": MODEL, "sizes": anyio.run(measure_menus)}, indent=1))
        sys.exit()
    result = anyio.run(run, arm)
    suffix = "" if DATASET == "ADAE" else f"_{DATASET.lower()}"
    (RESULTS / f"arm_{arm.lower()}{suffix}.json").write_text(json.dumps(result, indent=1))
    print(json.dumps({k: v for k, v in result.items() if k != "turns"}, indent=1))
