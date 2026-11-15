import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from config import BASE_DIR
from r_layer import rscript
from r_layer.validator import validate_metacore
from study import parents as study_parents


def run_adam_program(dataset_name: str, program_code: str, adam_dir=None,
                     parent_inputs=None, timeout=120) -> dict:
    output_dir = Path(adam_dir).resolve() if adam_dir is not None else BASE_DIR / "data" / "adam"
    parents = parent_inputs or {}
    missing = study_parents(dataset_name) - parents.keys()
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
            for name in study_parents(dataset_name):
                shutil.copyfile(parents[name], inputs / f"{name}.xpt")
            execution = rscript.script("run_adam.R", program_path, dataset_name, outputs, inputs,
                                       timeout=timeout)
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
        ready = [name for name in pending if not (study_parents(name) & pending.keys())]
        if not ready:
            for name in pending:
                results[name] = {"dataset": name, "success": False, "stage": "blocked",
                                 "accepted_path": None, "issues": ["Unresolved dependency cycle"]}
            break
        for name in ready:
            parents = {parent: results[parent]["accepted_path"] for parent in study_parents(name)
                       if results.get(parent, {}).get("success")}
            results[name] = run_adam_program(name, pending.pop(name), adam_dir=adam_dir,
                                            parent_inputs=parents)
    return results
