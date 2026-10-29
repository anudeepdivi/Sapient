"""Arm A: the model reaches Sapient's tools through a real MCP server (stdio).

Records, per run: turns, tool calls, prompt tokens per turn (the context the model
re-reads every turn), tool-definition size, tool-result bytes, patient-level bytes
(rows returned by preview_rows), wall time, and the target score.

Usage: python bench/run_arm_a.py   -> bench/results/arm_a.json
"""
import json
import os
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
PATIENT_DATA_TOOLS = {"preview_rows"}
HARNESS_ONLY = {"score_run"}
RESULTS = BASE_DIR / "bench" / "results"

TASK = f"""You are building the ADaM dataset {DATASET} in R with the admiral package, using the tools provided.
Derive these variables, in a sensible order: {', '.join(TARGETS)}.
For each variable: read its spec rule, check the conventions and any admiral signature you need, then call run_step
with one statement `result <- result |> ...` that creates it. If run_step returns an error, fix the code and call
run_step again. A variable is done when run_step returns OK. When every target is done, reply with the single word DONE."""


def openai_tools(mcp_tools) -> list[dict]:
    return [{"type": "function", "function": {"name": t.name, "description": t.description or "",
                                              "parameters": t.input_schema}}
            for t in mcp_tools if t.name not in HARNESS_ONLY]


async def run(arm: str = "A", server_args: list[str] | None = None) -> dict:
    os.environ["SAPIENT_RUN_TAG"] = f"bench-arm-{arm}"
    llm = OpenAI(base_url=NVIDIA_BASE_URL, api_key=NVIDIA_API_KEY, timeout=300.0, max_retries=0)
    params = StdioServerParameters(command=sys.executable,
                                   args=server_args or [str(BASE_DIR / "bench" / "mcp_server.py")], cwd=str(BASE_DIR))
    started = time.monotonic()
    log = {"arm": arm, "model": CODEGEN_MODEL, "turns": [], "tool_calls": {}, "tool_result_bytes": 0,
           "patient_data_bytes": 0}
    async with Client(params, read_timeout_seconds=900) as mcp:
        tools = openai_tools((await mcp.list_tools()).tools)
        log["n_tools"] = len(tools)
        log["tool_definition_tokens_est"] = len(json.dumps(tools)) // 4
        messages = [{"role": "user", "content": TASK}]
        for turn in range(1, MAX_TURNS + 1):
            resp = create_with_retry(llm, model=CODEGEN_MODEL, messages=messages, tools=tools,
                                     temperature=TEMPERATURE, max_tokens=MAX_TOKENS, extra_body=NO_THINKING)
            msg = resp.choices[0].message
            calls = msg.tool_calls or []
            log["turns"].append({"turn": turn, "prompt_tokens": resp.usage.prompt_tokens,
                                 "completion_tokens": resp.usage.completion_tokens,
                                 "tools": [c.function.name for c in calls]})
            print(f"turn {turn}: prompt={resp.usage.prompt_tokens} tools={[c.function.name for c in calls]}", flush=True)
            if not calls:
                log["final_message"] = (msg.content or "")[:300]
                break
            messages.append(msg.model_dump(exclude_none=True))
            for c in calls:
                name = c.function.name
                log["tool_calls"][name] = log["tool_calls"].get(name, 0) + 1
                try:
                    result = await mcp.call_tool(name, json.loads(c.function.arguments or "{}"))
                    text = "\n".join(getattr(x, "text", "") for x in result.content)
                except Exception as e:  # malformed arguments are the model's error; report back, keep going
                    text = f"TOOL ERROR: {e}"
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


if __name__ == "__main__":
    result = anyio.run(run)
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "arm_a.json").write_text(json.dumps(result, indent=1))
    print(json.dumps({k: v for k, v in result.items() if k != "turns"}, indent=1))
