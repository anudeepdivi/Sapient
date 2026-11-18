"""Real function signatures of the R packages the generators write against, extracted from
the installed namespaces. Generated code is grounded on these instead of on the model's
memory of an API (it invented rtables verbs such as item() and make_table()).

Swapping a package for an in-house one means adding an entry here; the signatures are
cached in knowledge/<package>_signatures.json (delete the file to refresh).
"""
import json
from pathlib import Path

from r_layer import rscript

# The admiral derivations generated ADaM code may call; the deterministic gate rejects any other.
ALLOWED_DERIVE_FUNCTIONS = {
    "derive_vars_merged", "derive_var_merged_exist_flag",
    "derive_vars_dt", "derive_vars_dtm",
    "derive_var_age_years", "derive_vars_duration",
    "derive_param_computed", "derive_extreme_records",
    "derive_var_extreme_flag", "restrict_derivation",
    "derive_param_exist_flag",
    "derive_vars_dtm_to_dt", "derive_vars_dy", "derive_var_trtemfl",
}

# package -> (R namespaces to resolve from, in order; functions to ground on)
PACKAGES = {
    "admiral": ("admiral", sorted(ALLOWED_DERIVE_FUNCTIONS)),
    # rtables layout verbs + tern clinical-analysis functions that cover the pilot tables
    "tern": ("tern,rtables", [
        "basic_table", "split_cols_by", "split_rows_by", "add_colcounts",
        "add_overall_col", "analyze", "summarize_row_groups", "build_table",
        "append_topleft",
        "analyze_vars", "count_occurrences", "count_occurrences_by_grade",
        "summarize_num_patients", "count_patients_with_event",
        "count_patients_with_flags", "count_values", "estimate_proportion",
    ]),
    # sdtm.oak's mapping-algorithm API is small; ground on all of it
    "oak": ("sdtm.oak", [
        "assign_ct", "assign_no_ct", "assign_datetime", "hardcode_ct", "hardcode_no_ct",
        "condition_add", "derive_seq", "derive_study_day", "derive_blfl",
        "generate_oak_id_vars", "create_iso8601", "ct_map", "read_ct_spec",
        "oak_cal_ref_dates", "cal_min_max_date", "generate_sdtm_supp",
    ]),
}


def get_signatures(package: str) -> dict[str, str]:
    cache = Path(__file__).parent / f"{package}_signatures.json"
    if cache.exists():
        return json.loads(cache.read_text())
    namespaces, functions = PACKAGES[package]
    result = rscript.script("list_signatures.R", namespaces, *functions, timeout=120)
    signatures = {}
    for line in result.stdout.splitlines():
        line = line.strip()
        if line and "(" in line and "NOT A REAL" not in line:
            signatures[line.split("(")[0].strip()] = line
    cache.write_text(json.dumps(signatures, indent=1))
    return signatures


def signatures_block(package: str) -> str:
    return "\n".join(get_signatures(package).values())
