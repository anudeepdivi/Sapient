import json
import re
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
REFERENCE_PATH = BASE_DIR / "data/reference/pilot_lot.json"


def normalize(table_number: str) -> str:
    parts = re.split(r"[-.]", str(table_number).strip().lstrip("tT").lstrip("-. "))
    try:
        return ".".join(str(int(p)) for p in parts if p != "")
    except ValueError:
        return str(table_number).strip()


def evaluate(lot_entries: list[dict]) -> dict:
    reference = {normalize(t) for t in json.loads(REFERENCE_PATH.read_text())["tables"]}
    generated = {normalize(e["table_number"]) for e in lot_entries if e.get("table_number")}
    tp = generated & reference
    precision = len(tp) / len(generated) if generated else 0.0
    recall = len(tp) / len(reference)
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "precision": round(precision, 3),
        "recall": round(recall, 3),
        "f1": round(f1, 3),
        "n_generated": len(generated),
        "n_reference": len(reference),
        "matched": sorted(tp),
        "missed": sorted(reference - generated),
        "spurious": sorted(generated - reference),
    }


if __name__ == "__main__":
    lot_path = Path(sys.argv[1]) if len(sys.argv) > 1 else BASE_DIR / "data/lot_entries.json"
    result = evaluate(json.loads(lot_path.read_text()))
    print(json.dumps(result, indent=2))
