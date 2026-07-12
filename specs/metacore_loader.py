import json
import subprocess
from config import R_EXECUTABLE, BASE_DIR

R_SCRIPTS_DIR = BASE_DIR / "r_layer" / "scripts"

_spec_rules_cache = {}


def get_spec_variables(dataset_name: str) -> list[str]:
    result = subprocess.run(
        [R_EXECUTABLE, str(R_SCRIPTS_DIR / "list_spec_variables.R"), dataset_name],
        capture_output=True, text=True, timeout=30
    )
    return [v for v in result.stdout.splitlines() if v]


def get_spec_rules(dataset_name: str) -> list[dict]:
    """Precompiled conformance rules per variable: type, length, format, CT values.
    Sourced from the metacore spec (built from Define-XML) — this is the ground truth
    for the format/type/controlled-terminology error class."""
    if dataset_name not in _spec_rules_cache:
        result = subprocess.run(
            [R_EXECUTABLE, str(R_SCRIPTS_DIR / "extract_spec_rules.R"), dataset_name],
            capture_output=True, text=True, timeout=60
        )
        try:
            _spec_rules_cache[dataset_name] = json.loads(result.stdout.strip())
        except json.JSONDecodeError:
            _spec_rules_cache[dataset_name] = []
    return _spec_rules_cache[dataset_name]


def spec_rules_block(dataset_name: str) -> str:
    """Compact one-line-per-variable rendering for a codegen prompt.
    e.g.  TRT01P  text len<=20  CT:{Placebo|Xanomeline Low Dose|Xanomeline High Dose}"""
    lines = []
    for r in get_spec_rules(dataset_name):
        parts = [r["variable"], r.get("type", "?")]
        if r.get("length"):
            parts.append(f"len<={r['length']}")
        if r.get("format"):
            parts.append(f"fmt:{r['format']}")
        ct = r.get("ct")
        if ct:
            vals = "|".join(ct)
            parts.append(f"CT:{{{vals}}}")
        lines.append("  ".join(parts))
    return "\n".join(lines)
