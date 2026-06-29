import json
from openai import OpenAI
from orchestration.state import SapientState
from config import NVIDIA_API_KEY, NVIDIA_BASE_URL, REASONING_MODEL, TEMPERATURE, MAX_TOKENS

client = OpenAI(base_url=NVIDIA_BASE_URL, api_key=NVIDIA_API_KEY, timeout=60.0)

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
    print(f"mockshell_generator: starting, {len(state['lot_entries'])} entries")
    metadata = json.dumps(state["study_metadata"], indent=2)
    mockshells = []
    for entry in state["lot_entries"]:
        print(f"mockshell_generator: generating for {entry['table_number']}")
        prompt = MOCKSHELL_PROMPT.format(
            lot_entry=json.dumps(entry, indent=2),
            metadata=metadata
        )
        response = client.chat.completions.create(
            model=REASONING_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=TEMPERATURE,
            max_tokens=MAX_TOKENS
        )
        print(f"mockshell_generator: response received for {entry['table_number']}")
        content = response.choices[0].message.content
        if not content:
            mockshells.append({"table_number": entry["table_number"], "error": "Empty response", "raw": ""})
            continue
        raw = content.strip().replace("```json", "").replace("```", "")
        try:
            mockshell = json.loads(raw)
            mockshell["table_number"] = entry["table_number"]
            mockshells.append(mockshell)
        except json.JSONDecodeError:
            mockshells.append({"table_number": entry["table_number"], "error": "Failed to parse mockshell", "raw": raw})
    return {**state, "mockshells": mockshells, "current_node": "mockshell_generator"}