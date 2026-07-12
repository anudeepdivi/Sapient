import subprocess
from pathlib import Path
from config import R_EXECUTABLE, BASE_DIR

R_SCRIPTS_DIR = BASE_DIR / "r_layer" / "scripts"

def validate_metacore(dataset_name: str) -> dict:
    result = subprocess.run(
        [R_EXECUTABLE, str(R_SCRIPTS_DIR / "validate_metacore.R"), dataset_name],
        capture_output=True,
        text=True,
        timeout=60
    )
    return {"dataset": dataset_name, "success": result.returncode == 0, "output": result.stdout, "error": result.stderr}

def check_conformance(dataset_name: str) -> dict:
    result = subprocess.run(
        [R_EXECUTABLE, str(R_SCRIPTS_DIR / "check_conformance.R"), dataset_name],
        capture_output=True, text=True, timeout=60
    )
    findings = [l[2:] for l in result.stdout.splitlines() if l.startswith("- ")]
    return {"dataset": dataset_name, "clean": result.returncode == 0, "findings": findings}


def compare_reference(dataset_name: str) -> dict:
    result = subprocess.run(
        [R_EXECUTABLE, str(R_SCRIPTS_DIR / "compare_reference.R"), dataset_name],
        capture_output=True,
        text=True,
        timeout=60
    )
    return {"dataset": dataset_name, "success": result.returncode == 0, "output": result.stdout, "error": result.stderr}