"""Arm A's server plus one MCP tool per exported admiral function - the "wrap the
whole package" approach. Each function tool takes the function's own arguments
(R expressions as strings) plus `creates_variable`, builds
`result <- result |> fn(...)`, and runs it through the same guarded run_step.

SAPIENT_BENCH_B_MODE selects the menu:
  pad      arm A's tools unchanged, with every function tool alongside (arm A136)
  f14      function tools only for the functions the gate allows, plus assign_column; no run_step
  fall     as f14, but every exported function
  fsearch  as fall, plus search_tools; the runner offers a function tool only after a search returns it
  fbm25    as fsearch, with the ranked search (BM25 over tool name, description and argument names)
  padsearch  arm A's tools unchanged, with every function tool behind the ranked search (arm ASEARCH)
  ftyped   function tools for the gate-approved functions only, with TYPED arguments (lists of columns, named
           expressions, text the server quotes itself, true/false, choices), behind the ranked search; plus
           assign_column; no run_step (arm FTYPED)
"""
import inspect
import json
import keyword
import math
import os
import re
import sys
from typing import Annotated, Literal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mcp_server import server, session
from knowledge.admiral_functions import get_signatures
from pydantic import Field
from templates.adam_templates import ADAM_INPUTS
from tools import DATASET

MODE = os.getenv("SAPIENT_BENCH_B_MODE", "pad")
CATALOG = json.loads((Path(__file__).resolve().parent / "admiral_catalog.json").read_text())
ENTRIES = [e for e in CATALOG if e["name"].isidentifier()  # drops operators such as %>%
           and (MODE not in ("f14", "ftyped") or e["name"] in get_signatures())]


def make_tool(fn_name: str, args: list[str]):
    args = [args] if isinstance(args, str) else args  # jsonlite unboxes one-argument lists to a string
    params = [a for a in dict.fromkeys(args) if a != "dataset" and a.isidentifier() and not keyword.iskeyword(a)]

    def handler(creates_variable: str, **kwargs) -> str:
        def call(values: dict) -> str:
            given = ", ".join(f"{k} = {v}" for k, v in values.items() if v not in (None, ""))
            return session.run_step(creates_variable, f"result <- result |> {fn_name}({given})")

        # R has no argument types, so the server cannot know which values are text. When R's own error
        # shows a bare word should have been text, quote it and run again; only the last result counts.
        failures_before = session.failures.get(creates_variable.upper(), 0)
        values = dict(kwargs)
        out = call(values)
        for _ in values:
            missing = re.search(r"object '(\w+)' not found", out)
            typed = re.search(r"Argument `(\w+)` must be [^\n]*<character>", out)
            fix = [k for k, v in values.items() if isinstance(v, str) and re.fullmatch(r"\w+", v) and
                   ((missing and v == missing.group(1)) or (typed and k == typed.group(1)))]
            if not fix:
                break
            session.failures[creates_variable.upper()] = failures_before
            values.update({k: f'"{values[k]}"' for k in fix})
            out = call(values)
        return out

    sig = [inspect.Parameter("creates_variable", inspect.Parameter.KEYWORD_ONLY, annotation=str)]
    sig += [inspect.Parameter(p, inspect.Parameter.KEYWORD_ONLY, default=None, annotation=str | None) for p in params]
    handler.__signature__ = inspect.Signature(sig, return_annotation=str)
    handler.__annotations__ = {"creates_variable": str, **{p: str | None for p in params}, "return": str}
    handler.__name__ = fn_name
    return handler


def split_args(signature: str) -> list[tuple[str, bool]]:
    """(argument, has a default) from "fn(a, b = 1, c = f(x, y))"."""
    inner, parts, depth, cur = signature[signature.index("(") + 1:signature.rindex(")")], [], 0, ""
    for ch in inner:
        depth += ch in "([{" and 1 or (ch in ")]}" and -1 or 0)
        if ch == "," and depth == 0:
            parts.append(cur); cur = ""
        else:
            cur += ch
    parts.append(cur)
    return [(p.split("=")[0].strip(), "=" in p) for p in parts if p.strip()]


INPUTS = tuple(name for name, _ in ADAM_INPUTS[DATASET])
APPROVED = tuple(get_signatures())
COLUMN_LIST = {"by_vars", "source_vars", "order", "keep_source_vars", "constant_by_vars", "subject_keys"}
NAMED = {"new_vars", "set_values_to", "missing_values", "args"}
TEXT = {"true_value", "false_value", "missing_value", "date_imputation", "time_imputation", "in_unit", "out_unit",
        "type", "age_unit", "new_vars_prefix", "duplicate_msg", "relationship"}
CHOICES = {"mode": ("first", "last"), "highest_imputation": ("n", "h", "m", "s", "D", "M", "Y"),
           "flag_imputation": ("auto", "date", "time", "both", "none"),
           "check_type": ("warning", "error", "message", "none"), "dataset_add": INPUTS, "dataset_ref": INPUTS,
           "derivation": APPROVED}
FLAGS = {"flag_all", "preserve", "floor_in", "add_one", "trunc_out", "keep_nas", "ignore_seconds_flag",
         "ignore_time_for_trt_end"}


def typed_arg(arg: str):
    """(JSON type for the model, how the value becomes R code)."""
    if arg in COLUMN_LIST:
        return (Annotated[list[str], Field(description='columns or expressions, e.g. ["USUBJID", "desc(AESEQ)"]')],
                lambda v: f"exprs({', '.join(v)})")
    if arg in NAMED:
        wrap = "params" if arg == "args" else "exprs"
        return (Annotated[dict[str, str], Field(description='new name -> R expression, e.g. {"TRTSDT": "EXSTDT"}')],
                lambda v: f"{wrap}({', '.join(k if k == x else f'{k} = {x}' for k, x in v.items())})")
    if arg == "parameters":
        return (Annotated[list[str], Field(description="PARAMCD values as plain text")],
                lambda v: "c(" + ", ".join(json.dumps(x) for x in v) + ")")
    if arg in CHOICES:
        quote = arg not in ("dataset_add", "dataset_ref", "derivation")
        return Literal[CHOICES[arg]], (lambda v: json.dumps(v)) if quote else (lambda v: v)
    if arg in TEXT:
        return (Annotated[str, Field(description="plain text; the server adds the R quotes")], lambda v: json.dumps(v))
    if arg in FLAGS:
        return bool, lambda v: "TRUE" if v else "FALSE"
    if arg == "end_window":
        return int, str
    return (Annotated[str, Field(description="a column name or an R expression, written bare")], lambda v: v)


def make_typed_tool(fn_name: str, signature: str):
    args = [(a, has_default) for a, has_default in split_args(signature) if a != "dataset"]
    kinds = {a: typed_arg(a) for a, _ in args}

    def handler(creates_variable: str, **kwargs) -> str:
        given = ", ".join(f"{k} = {kinds[k][1](v)}" for k, v in kwargs.items() if v not in (None, "", [], {}))
        return session.run_step(creates_variable, f"result <- result |> {fn_name}({given})")

    sig = [inspect.Parameter("creates_variable", inspect.Parameter.KEYWORD_ONLY, annotation=str)]
    sig += [inspect.Parameter(a, inspect.Parameter.KEYWORD_ONLY, annotation=kinds[a][0]) for a, d in args if not d]
    sig += [inspect.Parameter(a, inspect.Parameter.KEYWORD_ONLY, default=None, annotation=kinds[a][0] | None)
            for a, d in args if d]
    handler.__signature__ = inspect.Signature(sig, return_annotation=str)
    handler.__annotations__ = {p.name: p.annotation for p in sig} | {"return": str}
    handler.__name__ = fn_name
    return handler


for entry in ENTRIES if MODE == "ftyped" else []:
    name = entry["name"]
    server.add_tool(make_typed_tool(name, get_signatures()[name]), name=f"admiral_{name}",
                    description=(entry["title"] or name) +
                    f". Applies admiral::{name} to `result` (the dataset is passed for you). Arguments are typed: "
                    "lists of columns, named expressions, plain text (quoted for you), true/false or a fixed choice. "
                    "Also give the variable the call creates.")

for entry in ENTRIES if MODE != "ftyped" else []:
    name = entry["name"]
    server.add_tool(make_tool(name, entry["args"]), name=f"admiral_{name}",
                    description=(entry["title"] or name) +
                    f". Applies admiral::{name} to `result` (the dataset is passed for you). "
                    "Arguments are pasted into the call as R code, so a text value needs its own quotes "
                    'inside the string (send "\\"AST\\"", not "AST"); column names and expressions stay bare. '
                    "Also give the variable the call creates.")

if MODE not in ("pad", "padsearch"):
    server.remove_tool("run_step")
    session.submit_hint = ("call the admiral_<function> tool for the function you need, or assign_column for a plain "
                           "R expression. Each returns text starting with 'OK' when the step is kept; anything else "
                           "is the exact error or failed check, with what to fix.")

    @server.tool()
    def assign_column(variable: str, expression: str) -> str:
        """Create one variable from a single R expression over existing columns, for example if_else(...)
        or case_when(...). Returns OK (the step is kept) or the exact error / check failure."""
        return session.run_step(variable, f"result <- result |> mutate({variable} = {expression})")


def _words(text: str) -> set[str]:
    return {w.rstrip("s") for w in re.findall(r"[a-z0-9]+", text.lower())}


def _hits(query: set[str], words: set[str]) -> int:
    """Query words found among `words`; "flag" also matches "flagging"."""
    return sum(any(q == w or (min(len(q), len(w)) >= 4 and (q.startswith(w) or w.startswith(q))) for w in words)
               for q in query)


INDEX = [(f"admiral_{e['name']}", e["title"] or e["name"], _words(e["name"]), _words(e["title"] or ""))
         for e in ENTRIES]

if MODE == "fsearch":
    @server.tool()
    def search_tools(query: str) -> str:
        """Find admiral function tools by keyword, for example "impute date" or "first record flag".
        Returns up to 5 matching tool names, each with a one-line description. The tools returned
        can be called from your next step on."""
        q = _words(query)
        scored = sorted((-(2 * _hits(q, in_name) + _hits(q, in_title)), tool, title)
                        for tool, title, in_name, in_title in INDEX)
        hits = [f"{tool}: {title}" for score, tool, title in scored if score < 0][:5]
        return "\n".join(hits) or "No matching tools. Try other keywords."


def _stems(text: str) -> list[str]:
    """Lower-case words with their endings cut, so merge/merged/merging and flag/flags/flagging meet."""
    out = []
    for w in re.findall(r"[a-z0-9]+", text.lower()):
        for end in ("ing", "ed", "es", "s"):
            if w.endswith(end) and len(w) - len(end) >= 3:
                w = w[:-len(end)]
                break
        w = w.rstrip("e") if len(w) > 3 else w
        out.append(w[:-1] if len(w) > 3 and w[-1] == w[-2] else w)
    return out


def _arg_text(args) -> str:
    return " ".join([args] if isinstance(args, str) else list(args))


# One document per tool: name (counted three times), description, argument names.
DOCS = [(f"admiral_{e['name']}", e["title"] or e["name"],
         3 * _stems(e["name"]) + _stems(e["title"] or "") + _stems(_arg_text(e["args"]))) for e in ENTRIES]
AVG_LEN = sum(len(d) for _, _, d in DOCS) / len(DOCS)
DOC_FREQ = {}
for _, _, doc in DOCS:
    for term in set(doc):
        DOC_FREQ[term] = DOC_FREQ.get(term, 0) + 1


def bm25(query: str, k1: float = 1.5, b: float = 0.75) -> list[tuple[float, str, str]]:
    terms = set(_stems(query))
    named = set(re.findall(r"[a-z0-9_]+", query.lower().replace("admiral_", "")))
    ranked = []
    for tool, title, doc in DOCS:
        score = 0.0
        for t in terms:
            tf = doc.count(t)
            if tf:
                idf = math.log(1 + (len(DOCS) - DOC_FREQ[t] + 0.5) / (DOC_FREQ[t] + 0.5))
                score += idf * tf * (k1 + 1) / (tf + k1 * (1 - b + b * len(doc) / AVG_LEN))
        if tool.removeprefix("admiral_") in named:  # a query that gives a function's exact name gets it first
            score += 1000
        if score:
            ranked.append((-score, tool, title))
    return sorted(ranked)


if MODE in ("fbm25", "padsearch", "ftyped"):
    @server.tool()
    def search_tools(query: str) -> str:
        """Find admiral function tools. The search ranks tools by their name, description and argument
        names, so a function name ("derive_vars_merged") or a few words on what you need ("impute partial
        date", "flag first record per subject") both work. Returns the 5 best tool names, each with a
        one-line description. The tools returned can be called from your next step on."""
        hits = [f"{tool}: {title}" for _, tool, title in bm25(query)[:5]]
        return "\n".join(hits) or "No matching tools. Try other words."

if __name__ == "__main__":
    server.run("stdio")
