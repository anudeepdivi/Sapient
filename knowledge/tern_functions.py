"""Real tern/rtables function signatures for grounding TLF code generation — the
same constraint pattern as knowledge/admiral_functions.py. The TLF generator was
hallucinating a non-existent rtables DSL (item(), make_table(), bestis()); grounding
on these real signatures forbids that. Extend TERN_FUNCTIONS + re-run to refresh.
"""
import json
import subprocess
from pathlib import Path
from config import R_EXECUTABLE, BASE_DIR

R_SCRIPTS_DIR = BASE_DIR / "r_layer" / "scripts"
CACHE_PATH = Path(__file__).parent / "tern_signatures.json"

# rtables layout verbs + tern clinical-analysis functions that cover the pilot LoT
# tables (demographics, disposition, AE summaries, counts). Kept small and real:
# every name here must resolve in the tern or rtables namespace.
TERN_FUNCTIONS = [
    # rtables layout
    "basic_table", "split_cols_by", "split_rows_by", "add_colcounts",
    "add_overall_col", "analyze", "summarize_row_groups", "build_table",
    "append_topleft",
    # tern analysis
    "analyze_vars", "count_occurrences", "count_occurrences_by_grade",
    "summarize_num_patients", "count_patients_with_event",
    "count_patients_with_flags", "count_values", "estimate_proportion",
]


def get_signatures() -> dict[str, str]:
    if CACHE_PATH.exists():
        return json.loads(CACHE_PATH.read_text())
    result = subprocess.run(
        [R_EXECUTABLE, str(R_SCRIPTS_DIR / "list_tern_signatures.R"), *TERN_FUNCTIONS],
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
