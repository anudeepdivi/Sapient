from pathlib import Path

from config import SDTM_SOURCE

ADAM_SKELETON = """
library(admiral)
library(metacore)
library(xportr)
library(tidyverse)
library(haven)

# Load spec
mc <- metacore::load_metacore(Sys.getenv("SAPIENT_SPEC_RDS", unset = "specs/metacore_spec.rds"))
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
    "ADSL": [("dm", f"{SDTM_SOURCE}/DM.xpt"), ("ex", f"{SDTM_SOURCE}/EX.xpt"), ("ds", f"{SDTM_SOURCE}/DS.xpt"),
             ("vs", f"{SDTM_SOURCE}/VS.xpt"), ("mh", f"{SDTM_SOURCE}/MH.xpt"), ("sv", f"{SDTM_SOURCE}/SV.xpt")],
    "ADAE": [("sdtm", f"{SDTM_SOURCE}/AE.xpt"), ("adsl", "data/adam/ADSL.xpt")],
    "ADLBC": [("sdtm", f"{SDTM_SOURCE}/LB.xpt"), ("adsl", "data/adam/ADSL.xpt")],
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
        'mc <- metacore::load_metacore(Sys.getenv("SAPIENT_SPEC_RDS", unset = "specs/metacore_spec.rds"))\n'
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
        # type coercion always applies; length/format need spec metadata a generated
        # spec may not carry yet, so they degrade gracefully (closed loop stays runnable).
        f'result <- xportr::xportr_type(result, mc_ds, domain = "{dataset}")\n'
        # length derives from the data (SAS-ism; R has no fixed char length), so a
        # generated spec need not author it; format matters only for dates (deterministic).
        f'result <- tryCatch(xportr::xportr_length(result, mc_ds, domain = "{dataset}", length_source = "data"), error = function(e) result)\n'
        f'result <- tryCatch(xportr::xportr_format(result, mc_ds, domain = "{dataset}"), error = function(e) result)\n'
        "# Export\n"
        f'xportr::xportr_write(result, path = "data/adam/{dataset}.xpt", domain = "{dataset}")'
    )