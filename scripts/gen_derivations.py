"""Per-variable ADaM code generation for one dataset: generate and check each step, assemble
the accepted ones into a program, run it, and compare the result with the reference.

Usage: python scripts/gen_derivations.py ADSL     (SAPIENT_SPEC_RDS selects the spec)
Outputs: data/adam/{ds}_pervar.R, data/adam_experiment/{ds}.xpt, coverage report.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from adam.derivations import derive, program
from config import BASE_DIR
from r_layer.runner import run_adam_program
from r_layer.validator import compare_reference
from study import ADAM_PREFIX, DATASETS


def main(dataset: str):
    status, snippets, spec_order = derive(dataset)
    code = program(dataset, snippets, spec_order)
    (BASE_DIR / "data" / "adam" / f"{dataset}_pervar.R").write_text(code)
    (BASE_DIR / "data" / "adam_experiment").mkdir(exist_ok=True)
    parents = {name: BASE_DIR / ADAM_PREFIX / f"{name}.xpt" for name in DATASETS[dataset].parents}
    r = run_adam_program(dataset, code, adam_dir=BASE_DIR / "data" / "adam_experiment",
                         parent_inputs=parents, timeout=600)
    built = r["success"]

    print(f"\n=== {dataset} per-variable coverage ===")
    for var in spec_order:
        print(f"  {var:<10} {status.get(var, '?')}")
    counts = {}
    for s in status.values():
        counts[s.split(":")[0]] = counts.get(s.split(":")[0], 0) + 1
    print(f"summary: {counts}")
    print(f"assembled program executes: {built}")
    if not built:
        print(r["stdout"][-500:], r["stderr"][-1500:], r.get("metacore"), r.get("error"))
    if built:
        print(compare_reference(dataset, BASE_DIR / "data" / "adam_experiment")["output"])


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "ADSL")
