from r_layer.deterministic_checks import (
    LIBRARY_CALL_PATTERN,
    check_ascii,
    check_hardcoded_labels,
    check_syntax,
)


def run_checks(code, rules):
    issues = list(check_ascii(code))
    issues += check_syntax(code)
    allowed = set(rules.get("packages_allowed", []))
    for pkg in LIBRARY_CALL_PATTERN.findall(code):
        if pkg not in allowed:
            issues.append(f"library({pkg}) not in sponsor package allowlist")
    issues += check_hardcoded_labels(code)
    return {"passed": not issues, "issues": issues}
