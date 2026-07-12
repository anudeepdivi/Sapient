ADAM_SKELETON = """
library(admiral)
library(metacore)
library(xportr)
library(tidyverse)
library(haven)

# Load spec
mc <- metacore::load_metacore("specs/metacore_spec.rds")
# Load SDTM
sdtm <- haven::read_xpt("data/sdtm/{dataset}.xpt")

# --- Derivations go here ---

# Metacore compliance check
metacore::check_variables(dataset, mc)
# Export
xportr::xportr_write(dataset, path = "data/adam/{dataset}.xpt")
"""

# Known SDTM/ADaM inputs per ADaM dataset: (variable_name, file_path).
# Paths are real, case-correct locations, not LLM-authored — this is what
# makes wrong-case/wrong-directory filename bugs impossible by construction.
# Only datasets listed here get the deterministic header/footer treatment;
# any other dataset falls back to the full LLM-authored ADAM_SKELETON.
ADAM_INPUTS = {
    "ADSL": [("dm", "data/sdtm/DM.xpt"), ("ex", "data/sdtm/EX.xpt"), ("ds", "data/sdtm/DS.xpt")],
    "ADAE": [("sdtm", "data/sdtm/AE.xpt"), ("adsl", "data/adam/ADSL.xpt")],
}


def render_header(dataset: str) -> str:
    inputs = ADAM_INPUTS[dataset]
    load_lines = "\n".join(f'{var} <- haven::read_xpt("{path}")' for var, path in inputs)
    return (
        "library(admiral)\n"
        "library(metacore)\n"
        "library(xportr)\n"
        "library(tidyverse)\n"
        "library(haven)\n\n"
        "# Load spec\n"
        'mc <- metacore::load_metacore("specs/metacore_spec.rds")\n'
        "# Load SDTM\n"
        f"{load_lines}"
    )


ADMIRAL_TEMPLATE_FILES = {
    "ADSL": "ad_adsl.R",
    "ADAE": "ad_adae.R",
}

_admiral_template_cache = {}


def get_admiral_template(dataset: str) -> str:
    import subprocess
    from config import R_EXECUTABLE
    if dataset not in _admiral_template_cache:
        template_file = ADMIRAL_TEMPLATE_FILES[dataset]
        result = subprocess.run(
            [R_EXECUTABLE, "-e",
             f'cat(readLines(system.file("templates", "{template_file}", package = "admiral")), sep = "\\n")'],
            capture_output=True, text=True, timeout=30
        )
        _admiral_template_cache[dataset] = result.stdout
    return _admiral_template_cache[dataset]


def render_footer(dataset: str) -> str:
    return (
        "# Metacore compliance check\n"
        "metacore::check_variables(result, mc)\n"
        "# Export\n"
        f'xportr::xportr_write(result, path = "data/adam/{dataset}.xpt", domain = "{dataset}")'
    )