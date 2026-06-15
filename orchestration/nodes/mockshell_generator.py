import json
import google.generativeai as genai
from orchestration.state import SapientState
from config import GEMINI_API_KEY, REASONING_MODEL

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel(REASONING_MODEL)


MOCKSHELL_PROMPT = """
You are an expert clinical programmer. Generate a mockshell blueprint for this TLF.

Return a JSON object with exactly these fields:
- table_number: string
- column_headers: list of strings
- row_structure: list of strings (row labels/categories)
- footnotes: list of strings
- display_format: string (e.g. "n (%)", "mean (SD)", "median (range)")
- sorting: string (how rows should be ordered)

Return JSON only. No explanation. No markdown.

TLF ENTRY:
{lot_entry}

STUDY METADATA:
{metadata}
"""


def run(state: SapientState) -> SapientState:
    metadata = json.dumps(state["study_metadata"], indent=2)
    mockshells = []

    for entry in state["lot_entries"]:
        prompt = MOCKSHELL_PROMPT.format(
            lot_entry=json.dumps(entry, indent=2),
            metadata=metadata
        )

        response = model.generate_content(prompt)
        raw = response.text.strip().replace("```json", "").replace("```", "")
        
        try:
            mockshell = json.loads(raw)
            mockshell["table_number"] = entry["table_number"]
            mockshells.append(mockshell)
        except json.JSONDecodeError:
            mockshells.append({
                "table_number": entry["table_number"],
                "error": "Failed to parse mockshell",
                "raw": raw
            })

    return {
        **state,
        "mockshells": mockshells,
        "current_node": "mockshell_generator"
    }