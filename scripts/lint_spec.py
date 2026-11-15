"""Check a spec for structural defects, with no model call and no reference dataset.

Usage: python scripts/lint_spec.py ADLBC [--sdtm data/sdtm] [--json]
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import SDTM_SOURCE
from knowledge.adam_registry import resolve_class
from specs.lint import lint
from specs.metacore_loader import get_spec_rules


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dataset")
    ap.add_argument("--sdtm", default=SDTM_SOURCE)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    findings = lint(args.dataset, args.sdtm)
    if args.json:
        print(json.dumps(findings, indent=1))
        return 1 if any(f["severity"] == "error" for f in findings) else 0

    errors = [f for f in findings if f["severity"] == "error"]
    warns = [f for f in findings if f["severity"] == "warning"]
    print(f"=== SPEC LINT {args.dataset} "
          f"(class {resolve_class(args.dataset, {r['variable'].upper() for r in get_spec_rules(args.dataset)})}) ===")
    for f in errors + warns:
        mark = "ERROR  " if f["severity"] == "error" else "warning"
        print(f"  {mark} {f['variable']:<10} [{f['check']}] {f['detail']}")
    print(f"summary: {len(errors)} errors, {len(warns)} warnings "
          f"over {len(get_spec_rules(args.dataset))} spec variables")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
