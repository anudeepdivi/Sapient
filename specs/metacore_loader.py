import subprocess
from config import R_EXECUTABLE, BASE_DIR

R_SCRIPTS_DIR = BASE_DIR / "r_layer" / "scripts"


def get_spec_variables(dataset_name: str) -> list[str]:
    result = subprocess.run(
        [R_EXECUTABLE, str(R_SCRIPTS_DIR / "list_spec_variables.R"), dataset_name],
        capture_output=True, text=True, timeout=30
    )
    return [v for v in result.stdout.splitlines() if v]
