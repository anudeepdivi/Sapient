"""Draft a dataset spec from the SAP for a person to review, or mark a reviewed draft approved.

Usage:
    python scripts/gen_spec.py ADSL            # propose -> specs/proposed/ADSL.json
    python scripts/gen_spec.py ADSL --approve  # mark human-approved -> specs/approved/ADSL.json
    python scripts/eval_spec.py ADSL           # score approved/proposed spec vs Define.xml spec
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from specs.drafting import approve, propose

if __name__ == "__main__":
    dataset = sys.argv[1]
    print(approve(dataset) if "--approve" in sys.argv else propose(dataset))
