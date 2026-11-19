"""Quickstart: one command from a fresh clone to a generated ADaM dataset, scored.

  1. checks the set-up and says exactly what is missing (Python, R, R packages, API key);
  2. fetches the public CDISC pilot data (r_layer/scripts/get_pilot_data.R);
  3. has the AI write the ADAE program one variable at a time from the official spec,
     runs it, and compares every value with the pilot's own ADAE.

The first run makes about 20-30 model calls (a few minutes on the free tier); every answer is
saved, so running it again makes none.

Usage: python scripts/quickstart.py           full quickstart
       python scripts/quickstart.py --check   only check the set-up
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

R_PACKAGES = ["admiral", "metacore", "metatools", "xportr", "tidyverse", "haven", "dplyr", "jsonlite",
              "pharmaversesdtm"]


def check() -> bool:
    problems = []
    print("Checking the set-up")
    if sys.version_info < (3, 10):
        problems.append(("Python 3.10 or newer", "install a newer Python, then recreate the virtual environment"))
    try:
        import dotenv  # noqa: F401
        import openai  # noqa: F401
    except ImportError as e:
        problems.append((f"Python package {e.name}", "pip install -r requirements.txt"))
    from config import NVIDIA_API_KEY, R_EXECUTABLE
    if not shutil.which(R_EXECUTABLE):
        problems.append(("R (Rscript on your PATH)", "install R from https://cran.r-project.org"))
    else:
        out = subprocess.run([R_EXECUTABLE, "-e", "cat(rownames(installed.packages()), sep='\\n')"],
                             capture_output=True, text=True).stdout.split()
        missing = [p for p in R_PACKAGES if p not in out]
        if missing:
            quoted = ", ".join(f'"{p}"' for p in missing)
            problems.append((f"R packages: {', '.join(missing)}",
                             "Rscript -e 'dir.create(Sys.getenv(\"R_LIBS_USER\"), recursive = TRUE, showWarnings = FALSE); "
                             ".libPaths(Sys.getenv(\"R_LIBS_USER\")); "
                             f"install.packages(c({quoted}), repos = \"https://cloud.r-project.org\")'"))
    if not NVIDIA_API_KEY:
        problems.append(("an NVIDIA Build API key", "get a free key at https://build.nvidia.com, then put "
                                                    "NVIDIA_API_KEY=<your key> in a file named .env here"))
    if not problems:
        print("  OK: Python, R, R packages and API key all found")
        return True
    for what, fix in problems:
        print(f"  MISSING {what}\n          fix: {fix}")
    return False


def main() -> int:
    os.chdir(ROOT)
    if not check():
        return 1
    if "--check" in sys.argv:
        return 0
    from config import R_EXECUTABLE
    print("\nFetching the public CDISC pilot data")
    if subprocess.run([R_EXECUTABLE, "r_layer/scripts/get_pilot_data.R"]).returncode != 0:
        print("Could not fetch the pilot data (see the R message above).")
        return 1
    print("\nWriting ADAE one variable at a time, then comparing it with the pilot's own ADAE")
    os.environ["SAPIENT_REFERENCE_DIR"] = "data/reference/pilot"
    os.environ.setdefault("SAPIENT_RUN_TAG", "quickstart-ADAE")
    from scripts.gen_derivations import main as build
    build("ADAE")
    print("\nDone. The program is data/adam/ADAE_pervar.R and the dataset data/adam_experiment/ADAE.xpt.\n"
          "Next: python scripts/gen_derivations.py ADSL, or draft a spec from the SAP with scripts/gen_spec.py.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
