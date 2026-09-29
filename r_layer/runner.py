import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from config import R_EXECUTABLE, BASE_DIR
from r_layer.validator import validate_metacore
from templates.adam_templates import ADAM_INPUTS

R_SCRIPTS_DIR = BASE_DIR / "r_layer" / "scripts"


def _parents(dataset_name):
    return {Path(path).stem for _, path in ADAM_INPUTS.get(dataset_name, [])
            if path.startswith("data/adam/")}


def run_adam_program(dataset_name: str, program_code: str, adam_dir=None,
                     parent_inputs=None, timeout=120) -> dict:
    output_dir = Path(adam_dir).resolve() if adam_dir is not None else BASE_DIR / "data" / "adam"
    parents = parent_inputs or {}
    missing = _parents(dataset_name) - parents.keys()
    if missing:
        return {"dataset": dataset_name, "success": False, "stage": "blocked",
                "accepted_path": None, "stdout": "", "stderr": "",
                "issues": [f"No accepted parent: {name}" for name in sorted(missing)]}
    attempts = output_dir / ".attempts"
    attempts.mkdir(parents=True, exist_ok=True)
    attempt = Path(tempfile.mkdtemp(prefix=f"{dataset_name}-", dir=attempts))
    program_path = attempt / f"{dataset_name}_generated.R"
    program_path.write_text(program_code)
    result = {"dataset": dataset_name, "success": False, "stage": "r_execution",
              "accepted_path": None, "attempt_dir": str(attempt),
              "stdout": "", "stderr": "", "returncode": None}
    try:
        with tempfile.TemporaryDirectory(prefix="work-", dir=attempt) as workspace:
            work = Path(workspace)
            inputs, outputs = work / "inputs", work / "outputs"
            inputs.mkdir()
            outputs.mkdir()
            for name in _parents(dataset_name):
                shutil.copyfile(parents[name], inputs / f"{name}.xpt")
            execution = subprocess.run(
                [R_EXECUTABLE, str(R_SCRIPTS_DIR / "run_adam.R"), str(program_path),
                 dataset_name, str(outputs), str(inputs)],
                capture_output=True, text=True, timeout=timeout, cwd=BASE_DIR)
            result.update(stdout=execution.stdout, stderr=execution.stderr,
                          returncode=execution.returncode)
            if execution.returncode == 0:
                result["stage"] = "metacore_compliance"
                result["metacore"] = validate_metacore(dataset_name, adam_dir=outputs)
                if result["metacore"]["success"]:
                    result["stage"] = "publication"
                    target = output_dir / f"{dataset_name}.xpt"
                    (outputs / target.name).replace(target)
                    result.update(success=True, stage="accepted", accepted_path=str(target))
    except subprocess.TimeoutExpired as error:
        result["stdout"] = (error.stdout or b"").decode(errors="replace") if isinstance(error.stdout, bytes) else error.stdout or ""
        result["stderr"] = (error.stderr or b"").decode(errors="replace") if isinstance(error.stderr, bytes) else error.stderr or ""
        result["error"] = f"Timed out after {error.timeout} seconds"
    except OSError as error:
        result["error"] = str(error)
    (attempt / "result.json").write_text(json.dumps(result, indent=2))
    return result


def run_all_adam_programs(adam_programs: dict, adam_dir=None) -> dict:
    results = {}
    pending = dict(adam_programs)
    while pending:
        ready = [name for name in pending if not (_parents(name) & pending.keys())]
        if not ready:
            for name in pending:
                results[name] = {"dataset": name, "success": False, "stage": "blocked",
                                 "accepted_path": None, "issues": ["Unresolved dependency cycle"]}
            break
        for name in ready:
            parents = {parent: results[parent]["accepted_path"] for parent in _parents(name)
                       if results.get(parent, {}).get("success")}
            results[name] = run_adam_program(name, pending.pop(name), adam_dir=adam_dir,
                                            parent_inputs=parents)
    return results
