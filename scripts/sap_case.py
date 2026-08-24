"""Demo: extract requirements from a SAP fixture and optionally resolve
them through the existing harness. No LLM.

  python scripts/sap_case.py sap_fixtures/SAP_FX001.md --sections 9.3 --resolve
"""
import argparse
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

import yaml

from harness.adapter import SponsorEnv
from harness.resolver import resolve_case
from harness.sap_extract import extract_requirements


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("doc")
    p.add_argument("--sections", nargs="*", help="restrict to section ids")
    p.add_argument("--study-id", default="STUDY-FX001")
    p.add_argument("--resolve", action="store_true",
                   help="also run the extracted case through resolve_case()")
    args = p.parse_args()

    with open(args.doc) as f:
        text = f.read()
    env = SponsorEnv() if args.resolve else None
    report = extract_requirements(text, study_id=args.study_id,
                                  section_ids=args.sections, env=env)
    if args.resolve:
        results = resolve_case(report["case"], env)
        print(yaml.dump({"requirements": report["requirements"],
                         "conflicts": report["conflicts"],
                         "resolutions": results}, sort_keys=False))
    else:
        print(yaml.dump(report, sort_keys=False))


if __name__ == "__main__":
    main()
