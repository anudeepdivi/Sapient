"""Score spec DERIVATIONS by execution, and attribute each miss to spec vs codegen.

Same per-variable codegen runs twice: once on the pilot spec's derivations (control)
and once on the generated spec's (test). A derived variable that reproduces the
reference values is a correct derivation; one the control gets right but the test
gets wrong is a SPEC defect; one both get wrong is a CODEGEN (or reference) problem.

Usage: python scripts/score_derivations.py <DS> <control.log> <control_rates.json> <test.log> <test_rates.json>
(logs = stdout of gen_derivations.py; rates = SAPIENT_RATES_JSON from compare_reference.R)
"""
import json
import re
import sys

MATCH = 0.99
STATUS_RE = re.compile(r"^  ([A-Z][A-Z0-9]*)\s+(.+)$")


def statuses(log_path: str) -> dict[str, str]:
    text = open(log_path).read()
    block = text.split("per-variable coverage ===", 1)[-1].split("summary:", 1)[0]
    return {m.group(1): m.group(2).strip() for m in map(STATUS_RE.match, block.splitlines()) if m}


def load_rates(path: str) -> dict[str, float]:
    """jsonlite writes NaN (no comparable rows) as the string "NaN" - treat as no reference."""
    out = {}
    for var, rate in json.load(open(path)).items():
        try:
            if float(rate) == float(rate):
                out[var] = float(rate)
        except (TypeError, ValueError):
            pass
    return out


def derived(status: dict[str, str]) -> dict[str, str]:
    return {v: s for v, s in status.items() if not s.startswith("inherited")}


def main(ds, control_log, control_rates, test_log, test_rates):
    c_st, t_st = statuses(control_log), statuses(test_log)
    c_rate, t_rate = load_rates(control_rates), load_rates(test_rates)
    rows, counts = [], {}
    for var, st in sorted(derived(t_st).items()):
        rate = t_rate.get(var)
        if rate is None:
            verdict = "no reference column" if st == "generated" else "not produced (no reference column)"
        elif st != "generated":
            # the column may still exist (carried from SDTM/ADSL), but no derivation produced it
            verdict = "not produced (SPEC: unavailable source)" if st.startswith("unavailable") else "not produced (codegen failed)"
        elif rate >= MATCH:
            verdict = "correct"
        else:
            c = c_rate.get(var)
            if c is not None and c >= MATCH:
                verdict = "SPEC defect (control correct)"
            elif var not in c_st:
                verdict = "wrong (not in pilot spec)"
            else:
                verdict = "codegen/reference (control also wrong)"
        counts[verdict] = counts.get(verdict, 0) + 1
        rows.append((var, st.split(":")[0], None if rate is None else round(100 * rate), verdict))

    print(f"=== {ds}: derivations scored by execution (match >= {MATCH:.0%}) ===")
    for var, st, rate, verdict in rows:
        print(f"  {var:<10} {st:<22} {'-' if rate is None else f'{rate}%':>5}  {verdict}")
    scored = [r for r in rows if r[2] is not None]
    correct = sum(r[3] == "correct" for r in scored)
    print(f"summary: {counts}")
    print(f"derivation accuracy: {correct}/{len(scored)} derived vars with a reference column reproduce it")
    c_der = {v for v in derived(c_st) if v in c_rate}
    c_ok = sum(c_rate[v] >= MATCH and c_st[v] == "generated" for v in c_der)
    print(f"control (pilot spec): {c_ok}/{len(c_der)} derived vars with a reference column reproduce it")


if __name__ == "__main__":
    main(*sys.argv[1:6])
