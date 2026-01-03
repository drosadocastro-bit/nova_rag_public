"""
Response Format Normalizer
===========================
Ensures all NIC responses follow the consistent WARNINGS/STEPS/VERIFY prose template
instead of mixed JSON outputs that confuse RAGAS evaluators.

Converts JSON-formatted responses to the canonical format.
"""

import json
import re
from typing import Any

def normalize_response(answer: Any) -> str:
    """
    Normalize LLM output to consistent WARNINGS/STEPS/VERIFY format.
    
    Args:
        answer: Raw LLM response (str or dict)
        
    Returns:
        Normalized prose-format string
    """
    # If already prose (contains WARNINGS: or STEPS:), pass through
    if isinstance(answer, str):
        if "WARNINGS:" in answer or "STEPS:" in answer or "VERIFY:" in answer:
            return answer
        # Try parsing as JSON
        try:
            answer = json.loads(answer)
        except (json.JSONDecodeError, ValueError):
            # Not JSON, just clean whitespace
            return answer.strip()
    
    # Handle dict responses
    if isinstance(answer, dict):
        return _dict_to_prose(answer)
    
    return str(answer).strip()


def _dict_to_prose(data: dict) -> str:
    """Convert JSON dict to WARNINGS/STEPS/VERIFY prose format."""
    parts = []
    
    # Extract warnings/cautions/safety
    warnings = []
    for key in ["warnings", "warning", "cautions", "caution", "safety"]:
        if key in data:
            val = data[key]
            if isinstance(val, list):
                warnings.extend(val)
            elif isinstance(val, dict):
                warnings.append(val.get("warning", val.get("message", str(val))))
            elif val:
                warnings.append(str(val))
    
    if warnings:
        warnings_text = "; ".join(str(w) for w in warnings if w)
        parts.append(f"WARNINGS: {warnings_text}")
    
    # Extract steps/procedure
    steps = []
    for key in ["steps", "step", "procedure", "process"]:
        if key in data:
            val = data[key]
            if isinstance(val, list):
                for i, step in enumerate(val, 1):
                    if isinstance(step, dict):
                        desc = step.get("description", step.get("step", step.get("action", str(step))))
                        steps.append(f"Step {i}: {desc}")
                    else:
                        steps.append(f"Step {i}: {step}")
            elif isinstance(val, dict):
                for k, v in val.items():
                    steps.append(f"{k}: {v}")
            elif val:
                steps.append(str(val))
    
    if steps:
        steps_text = "; ".join(steps)
        parts.append(f"STEPS: {steps_text}")
    
    # Extract verification/testing/expected results
    verify = []
    for key in ["verify", "verification", "test", "expected", "expected_result"]:
        if key in data:
            val = data[key]
            if isinstance(val, list):
                verify.extend(str(v) for v in val if v)
            elif isinstance(val, dict):
                verify.append(val.get("expected", val.get("result", str(val))))
            elif val:
                verify.append(str(val))
    
    if verify:
        verify_text = "; ".join(verify)
        parts.append(f"VERIFY: {verify_text}")
    
    # Extract answer/result/output if no steps found
    if not steps and not parts:
        for key in ["answer", "result", "output", "response", "message"]:
            if key in data and data[key]:
                val = data[key]
                if isinstance(val, str):
                    return val
                elif isinstance(val, dict):
                    return _dict_to_prose(val)
                return str(val)
    
    # Add sources/citations
    sources = data.get("sources") or data.get("source") or data.get("citations") or data.get("citation")
    if sources:
        if isinstance(sources, list):
            sources_text = ", ".join(str(s) for s in sources if s)
        else:
            sources_text = str(sources)
        parts.append(f"[Sources: {sources_text}]")
    
    return " | ".join(parts) if parts else json.dumps(data, indent=2)


# Example usage / test cases
if __name__ == "__main__":
    # Test Case 1: JSON with steps
    json_response = {
        "warnings": ["High voltage present", "Wear safety glasses"],
        "steps": [
            {"step": 1, "description": "Turn off power"},
            {"step": 2, "description": "Test voltage with multimeter"}
        ],
        "verify": "Voltage should read 0V",
        "sources": ["manual.pdf p12"]
    }
    
    print("Test 1 - JSON with steps:")
    print(normalize_response(json_response))
    print()
    
    # Test Case 2: Already formatted prose
    prose_response = "WARNINGS: Fuel under pressure | STEPS: Check fuel pump; Test pressure | VERIFY: 40-50 PSI"
    print("Test 2 - Already prose:")
    print(normalize_response(prose_response))
    print()
    
    # Test Case 3: Nested JSON
    nested_json = {
        "output": {
            "answer": "The torque specification is 85-95 ft-lbs",
            "source": "Table 7-1"
        }
    }
    print("Test 3 - Nested answer:")
    print(normalize_response(nested_json))
    print()
    
    # Test Case 4: Simple answer
    simple_answer = {"answer": "Check battery voltage first"}
    print("Test 4 - Simple answer:")
    print(normalize_response(simple_answer))
