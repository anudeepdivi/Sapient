"""Code-mode API (arm C): the same Sapient functions as the MCP arms, as plain Python
calls a generated program imports with `import api`. State persists in
SAPIENT_BENCH_STATE between program runs; preview output is also logged to
SAPIENT_BENCH_PREVIEWS (v1 only) so the harness can measure patient-level data reaching the model.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from tools import Session

_session = Session(Path(os.environ["SAPIENT_BENCH_STATE"]))


def get_spec_rule(variable: str) -> str:
    """Returns a JSON string: spec for one variable (type, length, format, codelist, derivation text)."""
    return _session.get_spec_rule(variable)


def get_admiral_signature(function_name: str) -> str:
    """Returns plain text: the exact argument signature of an allowed admiral R function."""
    return _session.get_admiral_signature(function_name)


def list_input_columns() -> str:
    """Returns plain text: SDTM input datasets and their columns, plus the columns `result` starts with."""
    return _session.list_input_columns()


def get_conventions() -> str:
    """Returns plain text: verified admiral conventions for dates, flags and occurrence flags."""
    return _session.get_conventions()


def run_step(variable: str, code: str) -> str:
    """Execute one R step `result <- result |> ...` creating `variable`, after the steps already
    accepted. Returns "OK: ..." (the step is kept) or the exact error / check failure."""
    return _session.run_step(variable, code)


def brief(variables: str) -> str:
    """Returns plain text: everything needed to derive the given comma-separated variables
    (spec rules, verified conventions, input columns, allowed admiral signatures). Print it."""
    return _session.brief(variables)


def describe_columns(columns: str) -> str:
    """Returns plain text: type, missing count, distinct count and common values of
    low-cardinality text columns. Never returns patient-level rows."""
    return _session.describe_columns(columns)


def status() -> str:
    """Returns plain text: accepted targets and remaining targets."""
    return _session.status()


def accepted() -> list[str]:
    """Variables whose steps have been accepted so far."""
    return list(_session.accepted)


API_FUNCTIONS = [brief, get_spec_rule, get_admiral_signature, list_input_columns, get_conventions,
                 describe_columns, run_step, status, accepted]
