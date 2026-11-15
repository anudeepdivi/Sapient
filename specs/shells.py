"""Generate mock shells for the pilot SAP's 24 display templates, two arms:
  title  - the table title only (what the pipeline's mockshell node effectively sees)
  sap    - title + the SAP's analysis sections (§6-§11)
Inputs come from the SAP body only: titles from the §13.1.1 table list, never the
§13.2 templates themselves (those are the eval target, scripts/eval_shells.py).

Command line: scripts/gen_shells.py
"""
import json
import re
import subprocess
from pathlib import Path

import llm
from config import BASE_DIR, CODEGEN_FALLBACK_MODEL, CODEGEN_MODEL
from specs.sap import SAP_FILE, sap_sections

OUT_DIR = BASE_DIR / "data/mockshells"
LIST_RE = re.compile(r"(?m)^\s*\d+\.\s+(.+?)\(\s*Template\s+(\d+)\s*\)", re.S)

SHELL_PROMPT = """You are an expert clinical programmer. Design the mock shell for this table.
Return a JSON object with exactly these fields:
- title: string
- population: string (the analysis population the table is based on)
- column_headers: list of strings
- row_structure: list of strings (row labels/categories, in display order)
- footnotes: list of strings
- display_format: string (e.g. "n (%)", "mean (SD)", "median (range)")
Return JSON only. No explanation. No markdown.

TABLE: {title}
{sap_block}"""


def table_titles() -> dict[int, str]:
    """Template number -> first table title that uses it, from SAP §13.1.1."""
    text = subprocess.run(["pdftotext", "-layout", str(SAP_FILE), "-"],
                          capture_output=True, text=True).stdout
    start = text.rfind("13.1.1.")  # the body list, not the table-of-contents entry
    block = text[start:text.find("13.1.2.", start)]
    titles = {}
    for title, num in LIST_RE.findall(block):
        titles.setdefault(int(num), " ".join(title.split()))
    return titles


def sap_block() -> str:
    body = [f"[{n} {t}] {b}" for n, t, b in sap_sections()
            if 6 <= int(n.split(".")[0]) <= 11 and b]
    return "STUDY SAP (analysis sections):\n" + "\n".join(body)


def generate(arm: str) -> Path:
    context = sap_block() if arm == "sap" else ""
    shells = []
    for num, title in sorted(table_titles().items()):
        prompt = SHELL_PROMPT.format(title=title, sap_block=context)
        content = llm.complete(prompt, CODEGEN_MODEL, thinking=False, fallback=CODEGEN_FALLBACK_MODEL,
                               timeout=300.0).text
        try:
            shell = json.loads(content.strip().replace("```json", "").replace("```", ""))
        except json.JSONDecodeError:
            shell = {"error": "unparseable", "raw": content[:500]}
        shells.append({"template": num, **shell})
        print(f"template {num}: {'ok' if 'error' not in shell else 'PARSE ERROR'}")
    OUT_DIR.mkdir(exist_ok=True)
    out = OUT_DIR / f"{arm}.json"
    out.write_text(json.dumps(shells, indent=1))
    return out
