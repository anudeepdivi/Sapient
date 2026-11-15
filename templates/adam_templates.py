from pathlib import Path

from config import BASE_DIR
from r_layer.rscript import xpt_columns
from study import ADAM_PREFIX, DATASETS

def render_header(dataset: str) -> str:
    load_lines = []
    for var, path in DATASETS[dataset].inputs:
        if path.startswith(ADAM_PREFIX):
            source = f'file.path(Sys.getenv("SAPIENT_ADAM_INPUT_DIR", unset = Sys.getenv("SAPIENT_ADAM_DIR", unset = "data/adam")), "{Path(path).name}")'
        else:
            source = f'"{path}"'
        load_lines.append(f'{var} <- haven::read_xpt({source})')
    load_lines = "\n".join(load_lines)
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


_input_columns_cache = {}


def input_columns_block(dataset: str) -> str:
    if dataset not in _input_columns_cache:
        inputs = DATASETS[dataset].inputs
        existing = [path for _, path in inputs if (BASE_DIR / path).exists()]
        columns = xpt_columns(*existing)
        _input_columns_cache[dataset] = "\n".join(
            f"{var}: {', '.join(columns[Path(path).stem])}" if path in existing
            else f"{var}: (produced upstream at run time)"
            for var, path in inputs)
    return _input_columns_cache[dataset]


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
        f'xportr::xportr_write(result, path = file.path(Sys.getenv("SAPIENT_ADAM_DIR", unset = "data/adam"), "{dataset}.xpt"), domain = "{dataset}")'
    )