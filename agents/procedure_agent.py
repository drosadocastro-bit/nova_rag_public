def run_procedure(question: str, context_docs: list[dict], llm_call_fn):
    """Return step-by-step procedures as structured JSON.

        Schema:
        {
            "steps": ["1. ...", "2. ..."],
            "why": ["why for step 1", "why for step 2"],
            "verification": ["verify step 1", "verify step 2"],
            "risks": ["risk 1", "risk 2"],
            "sources": ["manual.pdf"],
            "notes": "optional"
        }
    """
    if context_docs:
        context = "\n\n---\n\n".join(
            f"[Source: {d.get('source','unknown')}]\n{(d.get('text') or d.get('snippet') or '')}" for d in context_docs
        )
    else:
        context = ""

    prompt = f"""
You are a maintenance procedure extractor for vehicle service manuals.
Return ONLY compact JSON, no prose, no markdown, no extra keys.
Use this schema EXACTLY - do not add "cautions", "answer", "type", or other keys:
{{
    "steps": ["1. ... (source.pdf p42)", "2. ... (source.pdf p42)"],
    "why": ["... (source.pdf p42)", "... (source.pdf p42)"],
    "verification": ["... (source.pdf p42)", "... (source.pdf p42)"],
    "risks": ["... (source.pdf p42)"],
    "sources": [{{"source": "source.pdf", "page": 42}}],
    "notes": "optional"
}}
Rules:
- Return ONLY the JSON object above. No extra keys. No "cautions", "answer", "type" wrappers.
- PDF-only: use ONLY the information in Context. Do NOT add external steps, websites, phone numbers, or assumptions unless they are explicitly present in Context.
- If Context does not contain the procedure steps, return empty lists and explain the limitation in "notes".
- Keep steps concise and actionable.
- Every step must include at least one explicit citation in parentheses using (source.pdf p##).
- Align each entry in "why" and "verification" to the corresponding step index.
- Include risks only if manuals mention cautions or safety notes.

Context:
{context}

Question:
{question}
"""

    return llm_call_fn(prompt)
