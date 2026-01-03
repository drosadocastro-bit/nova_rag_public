def run_troubleshoot(question: str, context_docs: list[dict], llm_call_fn, diagrams: list[dict] = None):
    """Return troubleshooting guidance as structured JSON with optional diagram references.

        Schema:
        {
            "likely_causes": ["..."],
            "rationale": ["brief why for cause 1", "brief why for cause 2"],
            "next_steps": ["1. ...", "2. ..."],
            "verification": ["verify step 1", "verify step 2"],
            "fallback": ["if not resolved do ..."],
            "confidence": 0.0,
            "sources": ["manual.pdf"],
            "reference_diagrams": [{"pdf": "...", "page": 1, "caption": "..."}],
            "notes": "optional"
        }
    """
    if context_docs:
        def _fmt(d: dict) -> str:
            src = d.get("source", "unknown")
            page = d.get("page")
            header = f"[Source: {src}{f' (pg. {page})' if page is not None else ''}]"
            body = (d.get("text") or d.get("snippet") or "").strip()
            return f"{header}\n{body}"

        context = "\n\n---\n\n".join(_fmt(d) for d in context_docs)
    else:
        context = ""
    
    # Add diagram references to context if available
    diagram_context = ""
    if diagrams:
        diagram_context = "\n\nRELEVANT SIGNAL PATH DIAGRAMS:\n"
        for d in diagrams:
            pdf = d.get("pdf_name", "unknown")
            page = d.get("page", "?")
            caption = d.get("caption_guess", "Diagram")
            diagram_context += f"- {pdf} page {page}: {caption[:100]}\n"

    prompt = f"""
You are a vehicle troubleshooting assistant, using the manuals as ground truth.
Return ONLY compact JSON, no prose, no markdown.
Use this schema exactly:
{{
    "likely_causes": ["..."],
    "rationale": ["brief why for cause 1", "brief why for cause 2"],
    "next_steps": ["1. ...", "2. ..."],
    "verification": ["verify step 1", "verify step 2"],
    "fallback": ["if not resolved do ..."],
    "confidence": 0.0,
    "sources": ["manual.pdf"],
    "reference_diagrams": [{{"pdf": "...", "page": 1, "caption": "..."}}],
    "notes": "optional"
}}
Rules:
- If unknown, use empty list/string ("") and confidence 0.0.
- Do not add extra keys.
- Keep next_steps concise and actionable.
- Align rationale to likely_causes by index; align verification to next_steps by index.
- Use fallback only if manuals specify an alternate path.
- Include reference_diagrams if diagrams are provided; reference them in next_steps.
- Critical: Every item in likely_causes, rationale, next_steps, and verification MUST be directly supportable by the provided context text.
- To make validation possible, reuse the manuals' exact terminology and identifiers (alarm description text, component names, table/figure IDs like "Figure FO6-4", and phrases like "maintenance limit in Adaptation Data").
- Avoid generic paraphrases. If you cannot ground a claim in the context wording, omit it.

Context:
{context}
{diagram_context}

Problem / Update:
{question}
"""

    return llm_call_fn(prompt)
