"""Build the benchmark tables from the result files, so no number is copied by hand.

Usage: python bench/summarize.py [RESULTS_DIR ...]      (default: v3 v3_run2 v3_run3)
       python bench/summarize.py --json ...             machine-readable

One row per arm: totals over the four datasets for each run, then the mean and range
across runs. A run that is missing a dataset is reported as incomplete, never averaged.
"""
import json
import sys
from pathlib import Path

RESULTS = Path(__file__).resolve().parent / "results"
ARMS = ["A", "AMULTI", "C", "ASEARCH", "FTYPED", "F14", "FSEARCH", "FBM25", "A136", "FALL"]
LABELS = {"A": "MCP, 8 task tools", "C": "Code mode", "F14": "MCP, 14 function tools",
          "FSEARCH": "MCP, 136 function tools behind keyword search",
          "AMULTI": "MCP, 8 task tools, several steps per call",
          "FTYPED": "MCP, 14 approved function tools, typed, behind ranked search",
          "FBM25": "MCP, 136 function tools behind ranked search (BM25)",
          "ASEARCH": "MCP, 8 task tools + 136 function tools behind ranked search", "A136": "MCP, 8 task tools + 136 unused function tools",
          "FALL": "MCP, 136 function tools on the menu"}
DATASETS = ["ADAE", "ADSL", "ADLBC", "ADTTE"]
CAPS = {}  # the safety cap is 40 model calls in every arm


def load(run_dir: str, arm: str, dataset: str) -> dict | None:
    suffix = "" if dataset == "ADAE" else f"_{dataset.lower()}"
    path = RESULTS / run_dir / f"arm_{arm.lower()}{suffix}.json"
    return json.loads(path.read_text()) if path.exists() else None


def run_totals(run_dir: str, arm: str) -> dict | None:
    files = {ds: load(run_dir, arm, ds) for ds in DATASETS}
    if any(f is None for f in files.values()):
        return None
    cap = CAPS.get(arm, 40)
    return {
        "correct": sum(f["score"]["targets_correct"] for f in files.values()),
        "correct_by_dataset": {ds: f["score"]["targets_correct"] for ds, f in files.items()},
        "closed": sum(len(f["score"].get("closed", [])) for f in files.values()),
        "prompt_tokens": sum(f["prompt_tokens_total"] for f in files.values()),
        "completion_tokens": sum(f["completion_tokens_total"] for f in files.values()),
        "steps": sum(f["n_turns"] for f in files.values()),
        "hit_cap": [ds for ds, f in files.items() if f["n_turns"] >= cap and "final_message" not in f],
        "first_step_prompt": files["ADAE"]["turns"][0]["prompt_tokens"],
        "menu": files["ADAE"].get("n_tools"),
        "function_tool_calls": sum(n for f in files.values() for tool, n in f.get("tool_calls", {}).items()
                                   if tool.startswith("admiral_")),
        "searches": sum(f.get("tool_calls", {}).get("search_tools", 0) for f in files.values()),
        "wall_seconds": round(sum(f["wall_seconds"] for f in files.values())),
        "model": files["ADAE"]["model"],
    }


def spread(values: list) -> str:
    mean = sum(values) / len(values)
    text = f"{mean:,.1f}" if mean < 100 else f"{mean / 1000:,.0f}k"
    if len(set(values)) == 1:
        return text
    low, high = min(values), max(values)
    return f"{text} ({low}–{high})" if high < 100 else f"{text} ({low / 1000:,.0f}k–{high / 1000:,.0f}k)"


def main(argv: list[str]) -> None:
    as_json = "--json" in argv
    run_dirs = [a for a in argv if not a.startswith("--")] or ["v3", "v3_run2", "v3_run3"]
    table = {}
    for arm in ARMS:
        runs = {r: run_totals(r, arm) for r in run_dirs}
        table[arm] = {"label": LABELS[arm], "runs": {r: t for r, t in runs.items() if t},
                      "incomplete": [r for r, t in runs.items() if t is None]}
    if as_json:
        print(json.dumps(table, indent=1))
        return
    print(f"| Arm | Menu | First step (tokens) | Correct of 20 | Prompt tokens | Steps | Left for a person | Hit the safety cap | Runs |")
    print("|---|---|---|---|---|---|---|---|---|")
    for arm, row in table.items():
        runs = list(row["runs"].values())
        if not runs:
            print(f"| {row['label']} | – | – | – | – | – | – | – | 0 (missing: {', '.join(row['incomplete'])}) |")
            continue
        capped = sum(bool(r["hit_cap"]) for r in runs)
        print(f"| {row['label']} | {runs[0]['menu'] or 'none'} | {runs[0]['first_step_prompt']:,} "
              f"| {spread([r['correct'] for r in runs])} | {spread([r['prompt_tokens'] for r in runs])} "
              f"| {spread([r['steps'] for r in runs])} | {spread([r['closed'] for r in runs])} "
              f"| {capped} of {len(runs)} runs | {len(runs)}"
              + (f" (missing: {', '.join(row['incomplete'])})" if row["incomplete"] else "") + " |")
    print("\n| Arm | " + " | ".join(DATASETS) + " | Function-tool calls | Searches |")
    print("|---|" + "---|" * (len(DATASETS) + 2))
    for arm, row in table.items():
        runs = list(row["runs"].values())
        if runs:
            cells = [spread([r["correct_by_dataset"][ds] for r in runs]) for ds in DATASETS]
            print(f"| {row['label']} | " + " | ".join(cells) +
                  f" | {spread([r['function_tool_calls'] for r in runs])} | {spread([r['searches'] for r in runs])} |")
    sizes = RESULTS / run_dirs[0] / "menu_sizes.json"
    if sizes.exists():
        print("\nWhat the tool list alone costs on every step (one call per menu size):")
        for row in json.loads(sizes.read_text())["sizes"]:
            print(f"  {row['n_tools']:>4} tools: {row['prompt_tokens']:>7,} prompt tokens")


if __name__ == "__main__":
    main(sys.argv[1:])
