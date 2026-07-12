"""Score a generated spec against the CDISC pilot Define.xml spec (eval target, not input).

Usage: python scripts/eval_spec.py ADSL [proposed|approved]
"""
import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from specs.metacore_loader import get_spec_variables


def evaluate(dataset: str, which: str = "proposed") -> dict:
    spec_path = BASE_DIR / f"specs/{which}/{dataset}.json"
    generated = {v["variable"].upper() for v in json.loads(spec_path.read_text())}
    reference = {v.upper() for v in get_spec_variables(dataset)}
    tp = generated & reference
    precision = len(tp) / len(generated) if generated else 0.0
    recall = len(tp) / len(reference) if reference else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "dataset": dataset,
        "precision": round(precision, 3),
        "recall": round(recall, 3),
        "f1": round(f1, 3),
        "missed": sorted(reference - generated),
        "spurious": sorted(generated - reference),
    }


if __name__ == "__main__":
    which = sys.argv[2] if len(sys.argv) > 2 else "proposed"
    print(json.dumps(evaluate(sys.argv[1], which), indent=2))
