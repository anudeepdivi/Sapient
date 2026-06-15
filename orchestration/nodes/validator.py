import json
import google.generativeai as genai
from orchestration.state import SapientState
from config import GEMINI_API_KEY, REASONING_MODEL

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel(REASONING_MODEL)


VALIDATOR_PROMPT = """
You are an expert clinical programmer reviewing R code for compliance.

Check this program for:
1. Correct admiral function usage
2. Metacore spec compliance
3. Population flag consistency with LoT entry
4. No hardcoded values
5. Proper xportr export at the end

Return a JSON object with:
- status: "pass" or "fail"
- issues: list of strings (empty if pass)
- severity: "none", "warning", or "error"

JSON only. No explanation. No markdown.

LOT ENTRY:
{lot_entry}

R PROGRAM:
{program}
"""


def run(state: SapientState) -> SapientState:
    validation_results = {}
    needs_regeneration = []

    all_programs = {
        **state.get("adam_programs", {}),
        **state.get("tlf_programs", {})
    }

    lot_map = {
        e["table_number"]: e for e in state["lot_entries"]
    }

    for name, code in all_programs.items():
        lot_entry = lot_map.get(name, {})

        prompt = VALIDATOR_PROMPT.format(
            lot_entry=json.dumps(lot_entry, indent=2),
            program=code
        )

        response = model.generate_content(prompt)
        raw = response.text.strip().replace("```json", "").replace("```", "")

        try:
            result = json.loads(raw)
        except json.JSONDecodeError:
            result = {"status": "fail", "issues": ["Validator parse error"], "severity": "error"}

        validation_results[name] = result

        if result.get("severity") == "error":
            needs_regeneration.append(name)

    return {
        **state,
        "validation_results": validation_results,
        "needs_regeneration": needs_regeneration,
        "completed": len(needs_regeneration) == 0,
        "current_node": "validator"
    }