"""Real sdtm.oak function signatures for grounding SDTM code generation — the same
constraint pattern as knowledge/admiral_functions.py (ADaM) and tern_functions.py (TLF).
sdtm.oak's mapping-algorithm API is small; ground on all of it.
"""
import json
import subprocess
from pathlib import Path
from config import R_EXECUTABLE, BASE_DIR

R_SCRIPTS_DIR = BASE_DIR / "r_layer" / "scripts"
CACHE_PATH = Path(__file__).parent / "oak_signatures.json"

OAK_FUNCTIONS = [
    "assign_ct", "assign_no_ct", "assign_datetime", "hardcode_ct", "hardcode_no_ct",
    "condition_add", "derive_seq", "derive_study_day", "derive_blfl",
    "generate_oak_id_vars", "create_iso8601", "ct_map", "read_ct_spec",
    "oak_cal_ref_dates", "cal_min_max_date", "generate_sdtm_supp",
]


def get_signatures() -> dict[str, str]:
    if CACHE_PATH.exists():
        return json.loads(CACHE_PATH.read_text())
    result = subprocess.run(
        [R_EXECUTABLE, str(R_SCRIPTS_DIR / "list_oak_signatures.R"), *OAK_FUNCTIONS],
        capture_output=True, text=True, timeout=120
    )
    sigs = {}
    for line in result.stdout.splitlines():
        line = line.strip()
        if line and "(" in line and "NOT A REAL" not in line:
            sigs[line.split("(")[0].strip()] = line
    CACHE_PATH.write_text(json.dumps(sigs, indent=1))
    return sigs


def signatures_block() -> str:
    return "\n".join(get_signatures().values())


if __name__ == "__main__":
    print(signatures_block())
