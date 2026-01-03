# agents/agent_router.py

def route_task(query: str):
    q = query.lower()

    # Procedures / steps
    if any(k in q for k in [
        "steps", "procedure", "how to", "measure",
        "maintenance", "check"
    ]):
        return {
            "agent": "procedure",
            "model": "llama",
            "rag": True
        }

    # Troubleshooting / fault
    if any(k in q for k in [
        "alarm", "fault", "error", "failure",
        "no output", "intermittent"
    ]):
        return {
            "agent": "troubleshoot",
            "model": "llama",
            "rag": True
        }

    # Default safe mode
    return {
        "agent": "analysis",
        "model": "llama",
        "rag": False
    }
