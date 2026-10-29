"""Run report: cost and guardrail activity per run tag, from the two event logs.

  cache_store/llm_usage.jsonl       - every real (non-cached) LLM call (orchestration/llm_retry.py)
  cache_store/guardrail_events.jsonl - every gate / execution outcome (scripts/gen_derivations.py)

Cached calls cost nothing and are not in llm_usage; guardrails still run on cached code.

Usage: python scripts/run_report.py [TAG_SUBSTRING ...] [--price-in USD_PER_M --price-out USD_PER_M]
"""
import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
USAGE = BASE_DIR / "cache_store/llm_usage.jsonl"
EVENTS = BASE_DIR / "cache_store/guardrail_events.jsonl"

# deterministic_gate rejection detail -> the check that caught it
GATE_CHECKS = [("shape", r"must start with|exactly one assignment"), ("syntax", r"SYNTAX|syntax"),
               ("non-ascii", r"non-ASCII"), ("package", r"package not installed"),
               ("hardcoded label", r"hardcoded"), ("missing input file", r"does not exist"),
               ("disallowed function", r"not in allowed list"), ("quoted symbol", r"bare symbol")]


def read(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.open()] if path.exists() else []


def wanted(tag: str, filters: list[str]) -> bool:
    return not filters or any(f in tag for f in filters)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tags", nargs="*")
    ap.add_argument("--price-in", type=float)
    ap.add_argument("--price-out", type=float)
    a = ap.parse_args()

    llm = defaultdict(lambda: {"calls": 0, "prompt": 0, "completion": 0, "seconds": 0.0,
                               "retries": 0, "models": set()})
    for r in read(USAGE):
        if not wanted(r["tag"], a.tags):
            continue
        x = llm[r["tag"] or "(untagged)"]
        x["calls"] += 1
        x["prompt"] += r["prompt_tokens"] or 0
        x["completion"] += r["completion_tokens"] or 0
        x["seconds"] += r["wall_seconds"]
        x["retries"] += r["attempts"] - 1
        x["models"].add(r["model"])

    print("## Cost (real model calls; cached calls are free and not counted)\n")
    print("| run | calls | prompt tok | completion tok | wall time (incl. rate-limit waits) | rate-limit retries | models |" +
          (" est. USD |" if a.price_in is not None else ""))
    print("|---|---|---|---|---|---|---|" + ("---|" if a.price_in is not None else ""))
    for tag, x in sorted(llm.items()):
        cost = ""
        if a.price_in is not None:
            usd = x["prompt"] / 1e6 * a.price_in + x["completion"] / 1e6 * (a.price_out or 0)
            cost = f" {usd:.3f} |"
        print(f"| {tag} | {x['calls']} | {x['prompt']:,} | {x['completion']:,} | "
              f"{x['seconds'] / 60:.1f} min | {x['retries']} | {', '.join(sorted(x['models']))} |{cost}")

    runs = defaultdict(list)
    for e in read(EVENTS):
        if wanted(e["tag"], a.tags):
            runs[e["tag"] or "(untagged)"].append(e)
    if not runs:
        return
    print("\n## Guardrails (what each check caught before anything was accepted)\n")
    print("| run | gate checks | gate rejections | execution failures caught | "
          "recovered by feedback | never passed | rejections by check | execution failures by check |")
    print("|---|---|---|---|---|---|---|---|")
    for tag, evs in sorted(runs.items()):
        gate = [e for e in evs if e["guardrail"] == "deterministic_gate"]
        rej = [e for e in gate if e["outcome"] == "rejected"]
        ex_fail = [e for e in evs if e["guardrail"] == "execution" and e["outcome"] == "failed"]
        by_var = defaultdict(list)
        for e in sorted(evs, key=lambda e: e["round"]):
            by_var[e["variable"]].append(e["outcome"])
        recovered = sum(1 for o in by_var.values() if o[-1] == "passed" and
                        any(x in ("rejected", "failed") for x in o))
        never = sum(1 for o in by_var.values() if o[-1] != "passed")
        checks = defaultdict(int)
        for e in rej:
            checks[next((n for n, pat in GATE_CHECKS if re.search(pat, e["detail"])), "other")] += 1
        ex_kinds = defaultdict(int)
        for e in ex_fail:
            m = re.match(r"ERROR: (TYPE|VALUES|LITERAL):", e["detail"])
            ex_kinds[m.group(1).lower() if m else "runtime error"] += 1
        print(f"| {tag} | {len(gate)} | {len(rej)} | {len(ex_fail)} | {recovered} | {never} | "
              f"{', '.join(f'{k} {v}' for k, v in sorted(checks.items())) or '-'} | "
              f"{', '.join(f'{k} {v}' for k, v in sorted(ex_kinds.items())) or '-'} |")


if __name__ == "__main__":
    main()
