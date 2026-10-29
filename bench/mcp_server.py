"""MCP server exposing the Sapient benchmark tools over stdio (arm A).

`score_run` is for the benchmark harness only; the runner never offers it to the model.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mcp.server.mcpserver import MCPServer
from tools import Session

session = Session()
server = MCPServer("sapient-adam")


@server.tool()
def get_spec_rule(variable: str) -> str:
    """Return the study specification for one ADAE variable: type, length, format, codelist and derivation text."""
    return session.get_spec_rule(variable)


@server.tool()
def get_admiral_signature(function_name: str) -> str:
    """Return the exact argument signature of an allowed admiral R function."""
    return session.get_admiral_signature(function_name)


@server.tool()
def list_input_columns() -> str:
    """List the SDTM input datasets and their columns, and the columns `result` (the ADAE under construction) starts with."""
    return session.list_input_columns()


@server.tool()
def get_conventions() -> str:
    """Return the verified admiral conventions for dates, flags and occurrence flags."""
    return session.get_conventions()


@server.tool()
def run_step(variable: str, code: str) -> str:
    """Execute one R step `result <- result |> ...` that creates `variable`, after the steps already accepted.
    Returns OK (the step is kept) or the exact error / check failure."""
    return session.run_step(variable, code)


@server.tool()
def preview_rows(columns: str, n: int = 5) -> str:
    """Show the first n rows of the dataset built so far, for comma-separated columns."""
    return session.preview_rows(columns, n)


@server.tool()
def score_run() -> str:
    """Benchmark harness only: build the dataset and score the targets."""
    import json
    return json.dumps(session.score())


if __name__ == "__main__":
    server.run("stdio")
