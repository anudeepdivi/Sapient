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
        full_path = BASE_DIR / path
        if not full_path.exists():
            issues.append(f"read_xpt(\"{path}\") — file does not exist")
    return issues


def run_gate(code: str) -> dict:
    checks = {
        "ascii": check_ascii(code),
        "syntax": check_syntax(code),
        "package_allowlist": check_package_allowlist(code),
        "hardcoded_labels": check_hardcoded_labels(code),
        "input_files_exist": check_input_files_exist(code),
    }
    all_issues = [issue for issues in checks.values() for issue in issues]
    return {"passed": len(all_issues) == 0, "checks": checks, "issues": all_issues}
