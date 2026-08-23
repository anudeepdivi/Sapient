import os
import subprocess
import tempfile
from pathlib import Path

from config import R_EXECUTABLE


def run_r_file(path, cwd=None, timeout=120, env=None, args=None):
    result = subprocess.run(
        [R_EXECUTABLE, "--vanilla", str(path), *[str(a) for a in (args or [])]],
        capture_output=True, text=True, timeout=timeout,
        cwd=str(cwd) if cwd else None,
        env={**os.environ, **env} if env else None,
    )
    return {
        "success": result.returncode == 0,
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def run_r_script(code, name="program", cwd=None, timeout=120):
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / f"{name}.R"
        path.write_text(code)
        return run_r_file(path, cwd=cwd, timeout=timeout)
