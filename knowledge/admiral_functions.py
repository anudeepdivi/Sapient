import json
import subprocess
from pathlib import Path
from config import R_EXECUTABLE, BASE_DIR
from r_layer.deterministic_checks import ALLOWED_DERIVE_FUNCTIONS

R_SCRIPTS_DIR = BASE_DIR / "r_layer" / "scripts"
CACHE_PATH = Path(__file__).parent / "admiral_signatures.json"


def get_signatures() -> dict[str, str]:
    if CACHE_PATH.exists():
        return json.loads(CACHE_PATH.read_text())
    result = subprocess.run(
        [R_EXECUTABLE, str(R_SCRIPTS_DIR / "list_admiral_signatures.R"), *sorted(ALLOWED_DERIVE_FUNCTIONS)],
        capture_output=True, text=True, timeout=120
    )
    sigs = {}
    for line in result.stdout.splitlines():
        line = line.strip()
        if line and "(" in line:
            sigs[line.split("(")[0].strip()] = line
    CACHE_PATH.write_text(json.dumps(sigs, indent=1))
    return sigs


def signatures_block() -> str:
    return "\n".join(get_signatures().values())
