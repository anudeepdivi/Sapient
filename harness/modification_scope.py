"""TC-R-009 unnecessary-rewrite oracle.

Reconstructs the sanctioned result of the declared deltas by re-running
apply_deltas() on the base program, then diffs the submitted copy against
that reconstruction. Any line differing from the sanctioned result is
unauthorized churn — including behavior-preserving rewrites, extra stages
appended to the anchor line, comment-laundered edits, and reformats.
Stdlib difflib only; deterministic; no LLM.
"""
from difflib import SequenceMatcher

from harness.deltas import DeltaAnchorError, apply_deltas


def _norm(code):
    return [l.rstrip() for l in code.splitlines()]


def _changed_sets(a, b):
    changed_a, changed_b = set(), set()
    for tag, i1, i2, j1, j2 in SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag != "equal":
            changed_a.update(range(i1, i2))
            changed_b.update(range(j1, j2))
    return changed_a, changed_b


def modification_scope(base_code, mod_code, deltas, executed=None):
    base_lines, mod_lines = _norm(base_code), _norm(mod_code)
    try:
        sanctioned_lines = _norm(apply_deltas(base_code, deltas))
        applied = True
    except DeltaAnchorError:
        sanctioned_lines, applied = None, False

    act_base, act_mod = _changed_sets(base_lines, mod_lines)
    total_changed = len(act_base) + len(act_mod)

    if applied:
        san_base, san_mod = _changed_sets(base_lines, sanctioned_lines)
        dev_base, dev_mod = _changed_sets(sanctioned_lines, mod_lines)
    else:
        # anchors don't pin down a unique sanctioned edit: nothing is
        # attributable, so every actual change counts as unauthorized
        san_base, san_mod = set(), set()
        dev_base, dev_mod = act_base, act_mod
    unauthorized = len(dev_base) + len(dev_mod)

    return {
        "applied_as_declared": applied,
        "sanctioned_base_lines": sorted(san_base),
        "sanctioned_modified_lines": sorted(san_mod),
        "deviations_from_standard": sorted(dev_base),
        "deviations_in_modified": sorted(dev_mod),
        "total_changed_lines": total_changed,
        "required_change_precision": (
            max(0, total_changed - unauthorized) / total_changed
            if total_changed else 1.0),
        "unnecessary_modification_rate": (
            unauthorized / len(base_lines) if base_lines else 0.0),
        "all_deltas_covered": applied,
        "modification_scope_accuracy": (
            applied and unauthorized == 0
            and (executed is None or executed)),
    }
