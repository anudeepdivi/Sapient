import subprocess
from pathlib import Path
from config import R_EXECUTABLE, BASE_DIR

R_SCRIPTS_DIR = BASE_DIR / "r_layer" / "scripts"

def run_adam_program(dataset_name: str, program_code: str) -> dict:
    program_path = BASE_DIR / "data" / "adam" / f"{dataset_name}_generated.R"
    program_path.parent.mkdir(parents=True, exist_ok=True)
    program_path.write_text(program_code)

    result = subprocess.run(
        [R_EXECUTABLE, str(R_SCRIPTS_DIR / "run_adam.R"), str(program_path), dataset_name],
        capture_output=True,
        text=True,
        timeout=120
    )
    return {
        "dataset": dataset_name,
        "success": result.returncode == 0,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "returncode": result.returncode
    }

def run_all_adam_programs(adam_programs: dict) -> dict:
    results = {}
    for dataset_name, code in adam_programs.items():
        results[dataset_name] = run_adam_program(dataset_name, code)
    return results