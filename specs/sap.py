"""Read the study SAP: its numbered sections, with the table of contents skipped."""
import re
from pathlib import Path

import fitz

from config import SAP_DIR

# The SAP of the study the eval target describes (CDISC pilot CSR Appendix 9).
SAP_FILE = SAP_DIR / "cdiscpilot01_sap.pdf"

# Numbered heading on its own line ("9.2."), title on the next line.
SAP_HEADING_RE = re.compile(r"^(\d+(?:\.\d+)*)\.\s*$")
SAP_STOP_TITLES = ("references", "attachments")  # display templates/appendices follow


def sap_sections(path: Path = SAP_FILE) -> list[tuple[str, str, str]]:
    """(number, title, text) for each numbered SAP section, TOC pages skipped."""
    sections, last = [], ()
    for page in fitz.open(path):
        text = page.get_text()
        if text.count(".....") > 5:  # table-of-contents page
            continue
        lines = text.split("\n")
        for i, line in enumerate(lines):
            m = SAP_HEADING_RE.match(line)
            if m and i + 1 < len(lines) and lines[i + 1].strip()[:1].isalpha():
                num = tuple(int(x) for x in m.group(1).split("."))
                if num > last:  # out-of-order numbers are list items, not headings
                    title = lines[i + 1].strip()
                    if title.lower() in SAP_STOP_TITLES:
                        return [(n, t, " ".join(" ".join(b).split())) for n, t, b in sections]
                    last = num
                    sections.append((m.group(1), title, []))
                    continue
            if sections and not (sections[-1][2] == [] and line.strip() == sections[-1][1]):
                sections[-1][2].append(line)
    return [(n, t, " ".join(" ".join(b).split())) for n, t, b in sections]
