from pathlib import Path

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
metatools::check_variables(dataset, mc)
# Export
xportr::xportr_write(dataset, path = "data/adam/{dataset}.xpt")
"""

# Known SDTM/ADaM inputs per ADaM dataset: (variable_name, file_path).
# Paths are real, case-correct locations, not LLM-authored — this is what
# makes wrong-case/wrong-directory filename bugs impossible by construction.
# Only datasets listed here get the deterministic header/footer treatment;
# any other dataset falls back to the full LLM-authored ADAM_SKELETON.
ADAM_INPUTS = {
    "ADSL": [("dm", "data/sdtm/DM.xpt"), ("ex", "data/sdtm/EX.xpt"), ("ds", "data/sdtm/DS.xpt"),
             ("vs", "data/sdtm/VS.xpt"), ("mh", "data/sdtm/MH.xpt"), ("sv", "data/sdtm/SV.xpt")],
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


# Hand-written derivation bodies (hybrid plan): datasets listed here skip the
# LLM entirely — the body is spliced between the deterministic header/footer.
DETERMINISTIC_DERIVATIONS = {
    "ADSL": Path(__file__).parent / "derivations" / "ADSL.R",
    "ADAE": Path(__file__).parent / "derivations" / "ADAE.R",
}

_input_columns_cache = {}


def input_columns_block(dataset: str) -> str:
    import subprocess
    from config import R_EXECUTABLE, BASE_DIR
    if dataset not in _input_columns_cache:
        lines = []
        for var, path in ADAM_INPUTS[dataset]:
            full = BASE_DIR / path
            if full.exists():
                r = subprocess.run(
                    [R_EXECUTABLE, "-e", f'cat(names(haven::read_xpt("{path}")), sep=", ")'],
                    capture_output=True, text=True, timeout=60, cwd=BASE_DIR)
                cols = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else "?"
                lines.append(f"{var}: {cols}")
            else:
                lines.append(f"{var}: (produced upstream at run time)")
        _input_columns_cache[dataset] = "\n".join(lines)
    return _input_columns_cache[dataset]


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
        f'mc_ds <- metacore::select_dataset(mc, "{dataset}")\n'
        "# Metacore compliance check\n"
        "metatools::check_variables(result, mc_ds)\n"
        "# Deterministic type/length/format coercion to spec (format-layer conformance)\n"
        "result <- result |>\n"
        f'  xportr::xportr_type(mc_ds, domain = "{dataset}") |>\n'
        f'  xportr::xportr_length(mc_ds, domain = "{dataset}") |>\n'
        f'  xportr::xportr_format(mc_ds, domain = "{dataset}")\n'
        "# Export\n"
        f'xportr::xportr_write(result, path = "data/adam/{dataset}.xpt", domain = "{dataset}")'
    )