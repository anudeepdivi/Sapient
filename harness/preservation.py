"""TC-R-008 standard-preservation oracle.

Executes an unmodified standard and a delta-modified copy, persists each
frame via the standard's SAPIENT_STD_OUTPUT saveRDS contract, diffs them
key-level and cell-level (r_layer/scripts/compare_preservation.R), and
scores the handoff metrics. Deterministic, R-only, no LLM.
"""
from pathlib import Path

from config import BASE_DIR
from harness.deltas import apply_deltas, materialize
from harness.r_executor import run_r_file

COMPARE_SCRIPT = BASE_DIR / "r_layer" / "scripts" / "compare_preservation.R"
DEFAULT_KEY_COLUMNS = ["USUBJID", "AETERM", "AESTDT"]


def compare_programs(env, standard_rel, base_code, mod_code, study_id, state_dir,
                     key_cols=None):
    key_cols = key_cols or DEFAULT_KEY_COLUMNS
    out_dir = Path(state_dir) / "preservation" / study_id
    out_dir.mkdir(parents=True, exist_ok=True)
    base_rds = out_dir / "base.rds"
    mod_rds = out_dir / "modified.rds"

    base_run = run_r_file(env.program_path(standard_rel), cwd=env.root,
                          env={"SAPIENT_STD_OUTPUT": str(base_rds)})
    mod_path = materialize(env, standard_rel, mod_code, study_id, state_dir)
    mod_run = run_r_file(mod_path, cwd=env.root,
                         env={"SAPIENT_STD_OUTPUT": str(mod_rds)})
    if not (base_run["success"] and mod_run["success"]):
        return {"executed": False, "base_run": base_run, "mod_run": mod_run}

    compare_run = run_r_file(COMPARE_SCRIPT,
                             args=[base_rds, mod_rds, ",".join(key_cols)])
    parsed = _parse_compare(compare_run["stdout"])
    parsed["executed"] = True
    parsed["compare_success"] = compare_run["success"]
    parsed["base_run"] = base_run
    parsed["mod_run"] = mod_run
    return parsed


def run_preservation(env, standard_rel, deltas, study_id, state_dir, key_cols=None):
    base_code = env.read_program(standard_rel)
    return compare_programs(env, standard_rel, base_code,
                            apply_deltas(base_code, deltas),
                            study_id, state_dir, key_cols)


def compute_metrics(compare, expected_removed, expected_added):
    removed_exact = sorted(compare["removed"]) == sorted(expected_removed)
    added_exact = sorted(compare["added"]) == sorted(expected_added)
    return {
        "standard_preservation_rate": 1.0 if compare["preserved_identical"] else 0.0,
        "intended_change_recall": 1.0 if (removed_exact and added_exact) else 0.0,
        "unintended_change_rate": (
            len(compare["cell_diffs"]) / compare["total_compared_cells"]
            if compare["total_compared_cells"] else 0.0
        ),
        "schema_equal": compare["schema_equal"],
        "removed_exact": removed_exact,
        "added_exact": added_exact,
    }


def _parse_compare(stdout):
    parsed = {
        "schema_equal": False, "removed": [], "added": [],
        "preserved_identical": False, "preserved_count": 0,
        "total_compared_cells": 0, "cell_diffs": [],
    }
    for raw_line in stdout.splitlines():
        parts = raw_line.strip().split(" ", 1)
        tag, value = parts[0], (parts[1].strip() if len(parts) > 1 else "")
        if tag == "SCHEMA_EQUAL":
            parsed["schema_equal"] = value == "TRUE"
        elif tag == "REMOVED":
            parsed["removed"] = [k for k in value.split(";") if k]
        elif tag == "ADDED":
            parsed["added"] = [k for k in value.split(";") if k]
        elif tag == "PRESERVED_IDENTICAL":
            parsed["preserved_identical"] = value == "TRUE"
        elif tag == "PRESERVED_COUNT":
            parsed["preserved_count"] = int(value)
        elif tag == "TOTAL_COMPARED_CELLS":
            parsed["total_compared_cells"] = int(value)
        elif tag == "CELL_DIFF":
            parsed["cell_diffs"].append(value)
    return parsed
