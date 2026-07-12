import re
import subprocess
from pathlib import Path
from config import R_EXECUTABLE, BASE_DIR

HARDCODED_LABEL_PATTERN = re.compile(
    r'"(placebo|active|drug\s*[a-z0-9]*|treatment\s*[a-z0-9]*|control|n\s*=\s*\d+)"',
    re.IGNORECASE,
)
LIBRARY_CALL_PATTERN = re.compile(r'library\(\s*([A-Za-z0-9._]+)\s*\)')
READ_XPT_PATTERN = re.compile(r'read_xpt\(\s*["\']([^"\']+)["\']\s*\)')
DERIVE_CALL_PATTERN = re.compile(r'\b((?:derive_|restrict_)[A-Za-z0-9_]+)\s*\(')
ALLOWED_DERIVE_FUNCTIONS = {
    "derive_vars_merged", "derive_var_merged_exist_flag",
    "derive_vars_dt", "derive_vars_dtm",
    "derive_var_age_years", "derive_vars_duration",
    "derive_param_computed", "derive_extreme_records",
    "derive_var_extreme_flag", "restrict_derivation",
    "derive_param_exist_flag",
}

_installed_packages_cache = None


def _installed_packages() -> set[str]:
    global _installed_packages_cache
    if _installed_packages_cache is None:
        result = subprocess.run(
            [R_EXECUTABLE, "-e", 'cat(rownames(installed.packages()), sep="\\n")'],
            capture_output=True, text=True, timeout=30
        )
        _installed_packages_cache = set(result.stdout.split())
    return _installed_packages_cache


def check_ascii(code: str) -> list[str]:
    non_ascii = [c for c in code if ord(c) > 127]
    if non_ascii:
        return [f"non-ASCII characters found: {set(non_ascii)}"]
    return []


def check_syntax(code: str) -> list[str]:
    check = subprocess.run(
        [R_EXECUTABLE, "--vanilla", "-e",
         'x <- readLines("stdin"); tryCatch({parse(text=x); cat("OK")}, '
         'error=function(e) cat("SYNTAX_ERROR:", conditionMessage(e)))'],
        input=code, capture_output=True, text=True, timeout=30
    )
    if "SYNTAX_ERROR" in check.stdout:
        return [check.stdout.strip()]
    if check.returncode != 0 and "OK" not in check.stdout:
        return [f"syntax check failed: {check.stderr.strip()}"]
    return []


def check_package_allowlist(code: str) -> list[str]:
    installed = _installed_packages()
    issues = []
    for pkg in LIBRARY_CALL_PATTERN.findall(code):
        if pkg not in installed:
            issues.append(f"library({pkg}) — package not installed")
    return issues


def check_hardcoded_labels(code: str) -> list[str]:
    matches = HARDCODED_LABEL_PATTERN.findall(code)
    if matches:
        return [f"hardcoded treatment/count literal(s) found: {sorted(set(matches))}"]
    return []


def check_input_files_exist(code: str) -> list[str]:
    issues = []
    for path in READ_XPT_PATTERN.findall(code):
        if path.startswith("data/adam/"):
            continue  # pipeline output, produced at run time
        full_path = BASE_DIR / path
        if not full_path.exists():
            issues.append(f"read_xpt(\"{path}\") — file does not exist")
    return issues


def check_derive_function_allowlist(code: str) -> list[str]:
    issues = []
    for fn in DERIVE_CALL_PATTERN.findall(code):
        if fn not in ALLOWED_DERIVE_FUNCTIONS:
            issues.append(f"{fn}() — admiral function not in allowed list")
    return issues


QUOTED_SYMBOL_ARG_PATTERN = re.compile(
    r'\b(new_var|new_var_unit|age_var|start_date|end_date|dtc)\s*=\s*["\']'
)


def fix_quoted_symbol_args(code: str) -> str:
    return re.sub(
        r'\b(new_var|new_var_unit|age_var|start_date|end_date|dtc)\s*=\s*["\']([A-Za-z][A-Za-z0-9_.]*)["\']',
        r'\1 = \2', code)


def check_quoted_symbol_args(code: str) -> list[str]:
    return [f'{arg} = "..." — this admiral argument takes a bare symbol, not a quoted string'
            for arg in QUOTED_SYMBOL_ARG_PATTERN.findall(code)]


def run_gate(code: str) -> dict:
    checks = {
        "ascii": check_ascii(code),
        "syntax": check_syntax(code),
        "package_allowlist": check_package_allowlist(code),
        "hardcoded_labels": check_hardcoded_labels(code),
        "input_files_exist": check_input_files_exist(code),
        "derive_function_allowlist": check_derive_function_allowlist(code),
        "quoted_symbol_args": check_quoted_symbol_args(code),
    }
    all_issues = [issue for issues in checks.values() for issue in issues]
    return {"passed": len(all_issues) == 0, "checks": checks, "issues": all_issues}
