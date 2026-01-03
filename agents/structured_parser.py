import json
from typing import Tuple


def parse_structured(raw: str) -> Tuple[bool, object]:
    """Attempt to parse JSON from the LLM response.

    Returns (ok, parsed_or_raw). If parsing fails, ok=False and parsed_or_raw=raw.
    """
    try:
        return True, json.loads(raw)
    except Exception:
        return False, raw


def force_valid_json(raw, schema_hint: str, llm_call_fn, model_name: str):
    """Try to parse; on failure, re-prompt once to fix JSON structure.

    Always returns a dict when possible; otherwise returns the raw string.
    """
    if isinstance(raw, dict):
        return raw
    ok, parsed = parse_structured(raw) if isinstance(raw, str) else (False, raw)
    if ok:
        return parsed

    correction_prompt = (
        "Your previous reply was not valid JSON. "
        "Fix it to match this schema exactly and return ONLY JSON, nothing else:\n"
        f"{schema_hint}\n"
        "If a field is unknown, use empty list/string and confidence 0.0."
    )
    fixed = llm_call_fn(correction_prompt)
    ok2, parsed2 = parse_structured(fixed) if isinstance(fixed, str) else (False, fixed)
    return parsed2 if ok2 else raw
