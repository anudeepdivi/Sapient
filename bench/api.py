"""Code-mode API (arm C): the same Sapient functions as the MCP arms, as plain Python
calls a generated program imports with `import api`. State persists in
SAPIENT_BENCH_STATE between program runs; preview output is also logged to
SAPIENT_BENCH_PREVIEWS so the harness can measure patient-level data reaching the model.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from tools import Session

_session = Session(Path(os.environ["SAPIENT_BENCH_STATE"]))


def get_spec_rule(variable: str) -> str:
    """Spec for one variable: type, length, format, codelist and derivation text (JSON)."""
    return _session.get_spec_rule(variable)


def get_admiral_signature(function_name: str) -> str:
    """Exact argument signature of an allowed admiral R function."""
    return _session.get_admiral_signature(function_name)


def list_input_columns() -> str:
    """SDTM input datasets and their columns, plus the columns `result` starts with."""
    return _session.list_input_columns()


def get_conventions() -> str:
    """Verified admiral conventions for dates, flags and occurrence flags."""
    return _session.get_conventions()


def run_step(variable: str, code: str) -> str:
    """Execute one R step `result <- result |> ...` creating `variable`, after the steps already
    accepted. Returns "OK: ..." (the step is kept) or the exact error / check failure."""
    return _session.run_step(variable, code)


def preview_rows(columns: str, n: int = 5) -> str:
    """First n rows of the dataset built so far, for comma-separated columns."""
    out = _session.preview_rows(columns, n)
    with open(os.environ["SAPIENT_BENCH_PREVIEWS"], "a") as f:
        f.write(out + "\n\x00\n")
    return out


def accepted() -> list[str]:
    """Variables whose steps have been accepted so far."""
    return list(_session.accepted)


API_FUNCTIONS = [get_spec_rule, get_admiral_signature, list_input_columns, get_conventions,
                 run_step, preview_rows, accepted]
