"""TLF comparison harness (Phase 2a). Extracts each generated TLF's pre-rendering
data frame (never rendered output) and compares:
- against data/reference/tlf/<table>.csv when a reference frame exists
- otherwise records the frame's SHA256 in data/tlf_frames/hashes.json for
  run-to-run consistency verification.

Usage: python scripts/eval_tlf.py   (expects data/adam/*_generated TLF programs on disk)
"""
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import BASE_DIR
from r_layer import rscript

FRAMES_DIR = BASE_DIR / "data/tlf_frames"
REF_DIR = BASE_DIR / "data/reference/tlf"
PROGRAMS_DIR = BASE_DIR / "data/tlf_programs"


def evaluate() -> dict:
    results = {}
    hashes = {}
    for program in sorted(PROGRAMS_DIR.glob("*.R")):
        table = program.stem
        proc = rscript.script("extract_tlf_frame.R", program, table, timeout=120)
        if proc.returncode != 0:
            results[table] = {"status": "extract_fail", "error": proc.stdout.strip()[-300:] or proc.stderr.strip()[-300:]}
            continue
        frame = FRAMES_DIR / f"{table}.csv"
        content = frame.read_bytes()
        hashes[table] = hashlib.sha256(content).hexdigest()
        ref = REF_DIR / f"{table}.csv"
        if ref.exists():
            results[table] = {"status": "match" if content == ref.read_bytes() else "mismatch"}
        else:
            results[table] = {"status": "hashed", "sha256": hashes[table][:16]}
    FRAMES_DIR.mkdir(parents=True, exist_ok=True)
    (FRAMES_DIR / "hashes.json").write_text(json.dumps(hashes, indent=1))
    return results


if __name__ == "__main__":
    print(json.dumps(evaluate(), indent=1))
