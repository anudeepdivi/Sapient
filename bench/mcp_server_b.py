"""Arm B: arm A's tools plus one MCP tool per exported admiral function - the
"wrap the whole package" approach. Each tool takes the function's own arguments
(R expressions as strings) plus `creates_variable`, builds
`result <- result |> fn(...)`, and runs it through the same guarded run_step.
"""
import inspect
import json
import keyword
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mcp_server import server, session

CATALOG = json.loads((Path(__file__).resolve().parent / "admiral_catalog.json").read_text())


def make_tool(fn_name: str, args: list[str]):
    args = [args] if isinstance(args, str) else args  # jsonlite unboxes one-argument lists to a string
    params = [a for a in dict.fromkeys(args) if a != "dataset" and a.isidentifier() and not keyword.iskeyword(a)]

    def handler(creates_variable: str, **kwargs) -> str:
        given = ", ".join(f"{k} = {v}" for k, v in kwargs.items() if v not in (None, ""))
        return session.run_step(creates_variable, f"result <- result |> {fn_name}({given})")

    sig = [inspect.Parameter("creates_variable", inspect.Parameter.KEYWORD_ONLY, annotation=str)]
    sig += [inspect.Parameter(p, inspect.Parameter.KEYWORD_ONLY, default=None, annotation=str | None) for p in params]
    handler.__signature__ = inspect.Signature(sig, return_annotation=str)
    handler.__annotations__ = {"creates_variable": str, **{p: str | None for p in params}, "return": str}
    handler.__name__ = fn_name
    return handler


for entry in CATALOG:
    name = entry["name"]
    if not name.isidentifier():  # operators such as %>%
        continue
    server.add_tool(make_tool(name, entry["args"]), name=f"admiral_{name}",
                    description=(entry["title"] or name) +
                    f". Applies admiral::{name} to `result` (the dataset is passed for you); "
                    "give other arguments as R expressions, and the variable the call creates.")

if __name__ == "__main__":
    server.run("stdio")
