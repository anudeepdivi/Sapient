from pathlib import Path

from config import BASE_DIR
from r_layer import rscript


def _check(script: str, dataset_name: str, adam_dir):
    return rscript.script(script, dataset_name,
                          Path(adam_dir).resolve() if adam_dir is not None else BASE_DIR / "data" / "adam")


def validate_metacore(dataset_name: str, adam_dir=None) -> dict:
    result = _check("validate_metacore.R", dataset_name, adam_dir)
    return {"dataset": dataset_name, "success": result.returncode == 0, "output": result.stdout, "error": result.stderr}


def check_conformance(dataset_name: str, adam_dir=None) -> dict:
    result = _check("check_conformance.R", dataset_name, adam_dir)
    findings = [l[2:] for l in result.stdout.splitlines() if l.startswith("- ")]
    return {"dataset": dataset_name, "clean": result.returncode == 0, "findings": findings}


def compare_reference(dataset_name: str, adam_dir=None) -> dict:
    result = _check("compare_reference.R", dataset_name, adam_dir)
    return {"dataset": dataset_name, "success": result.returncode == 0, "output": result.stdout, "error": result.stderr}
