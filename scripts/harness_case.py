"""Run one harness test case YAML end-to-end.

Usage:
  python scripts/harness_case.py tests/cases/TC-R-006.yaml --apply
  python scripts/harness_case.py tests/cases/TC-R-012.yaml --novel-flow [--generator llm]
"""
import argparse
import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

import yaml

from config import HARNESS_STATE_DIR
from harness.adapter import SponsorEnv
from harness.capabilities import implement, propose, validate
from harness.deltas import apply_deltas, materialize
from harness.resolver import resolve_case
from harness.r_executor import run_r_file


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case_file")
    parser.add_argument("--apply", action="store_true",
                        help="apply detected deltas to a copy and execute it")
    parser.add_argument("--novel-flow", action="store_true",
                        help="drive missing capabilities through generation/validation "
                             "(stops at human approval)")
    parser.add_argument("--generator", default=None, help="stub | llm")
    parser.add_argument("--state-dir", default=str(HARNESS_STATE_DIR))
    args = parser.parse_args()

    with open(args.case_file) as f:
        case = yaml.safe_load(f)
    env = SponsorEnv()
    results = resolve_case(case, env, args.state_dir)
    for result in results:
        print(json.dumps(result, indent=1, default=str))

    requirements = {r.get("requirement_id"): r
                    for r in case["study_requirement"]["requirements"]}
    for result in results:
        if args.apply and result.get("action") == "APPLY_DELTA":
            rel = f"standards/{result['dataset'].lower()}/{result['standard_match']}"
            modified = apply_deltas(env.read_program(rel), result["deltas"])
            path = materialize(env, rel, modified,
                               case["study_requirement"]["study_id"], args.state_dir)
            print(f"materialized: {path}")
            executed = run_r_file(path, cwd=env.root)
            print("execution:", "success" if executed["success"] else "FAILED")
            if not executed["success"]:
                print(executed["stderr"])
        if args.novel_flow and result.get("action") == "CREATE_PROPOSAL":
            for name in result["missing_capabilities"]:
                requirement = requirements[result["requirement_id"]]
                proposal = propose(name, requirement, env, args.state_dir,
                                   generator=args.generator)
                proposal = implement(proposal, env, args.state_dir,
                                     generator=args.generator)
                proposal = validate(proposal, env, args.state_dir)
                print(f"{name}: status={proposal['status']} "
                      "(registration requires human approval)")


if __name__ == "__main__":
    main()
