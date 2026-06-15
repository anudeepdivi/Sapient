import fitz
from pathlib import Path


IG_SECTION_HEADERS = [
    "dataset", "variable", "derivation", "assumption",
    "population", "timing", "controlled terminology",
    "relationship", "domain", "class"
]


def parse_ig_pdf(pdf_path: str) -> list[dict]:
    doc = fitz.open(pdf_path)
    chunks = []
    current_section = "general"
    buffer = []

    for page in doc:
        text = page.get_text()
        for line in text.split("\n"):
            line_lower = line.lower().strip()
            is_header = any(h in line_lower for h in IG_SECTION_HEADERS)

            if is_header and buffer:
                chunks.append({
                    "section": current_section,
                    "text": "\n".join(buffer).strip()
                })
                buffer = []
                current_section = line.strip()

            buffer.append(line)

    if buffer:
        chunks.append({
            "section": current_section,
            "text": "\n".join(buffer).strip()
        })

    return [c for c in chunks if len(c["text"]) > 100]