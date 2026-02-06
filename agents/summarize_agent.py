def run_summarize(question: str, context_docs: list[dict], llm_call_fn):
    """Return a summarized version of the context as structured JSON.

    Schema:
    {
      "bullets": ["... (source.pdf p42)"],
      "sources": [{"source": "manual.pdf", "page": 42}],
      "notes": "optional"
    }
    """
    if context_docs:
        def _fmt(d: dict) -> str:
            src = d.get("source", "unknown")
            page = d.get("page")
            header = f"[Source: {src}{f' (p. {page})' if page is not None else ''}]"
            body = (d.get("text") or d.get("snippet") or "").strip()
            return f"{header}\n{body}"
        context = "\n\n---\n\n".join(_fmt(d) for d in context_docs)
    else:
        context = ""

    prompt = f"""
You are a technical assistant that summarizes relevant manual content.
Return ONLY compact JSON, no prose, no markdown.
Use this schema exactly:
{{
  "bullets": ["... (source.pdf p42)", "... (source.pdf p43)"],
  "sources": [{{"source": "manual.pdf", "page": 42}}],
  "notes": "optional"
}}
Rules:
- If unknown, use empty list/string ("").
- Do not add extra keys.
- Keep bullets short and relevant.
- CRITICAL: Every bullet MUST include an explicit citation in parentheses: (source.pdf p##)
- CRITICAL: Only summarize information that appears in the provided Context.
- Do NOT add external knowledge, assumptions, or generic information.
- NEVER add generic safety disclaimers, warnings not in Context, or elaboration not in Context.
- NEVER append phrases like "consult manual", "refer to manual", or defensive statements.
- If value is specific (PSI, torque, degrees), extract ONLY the value and citation; strip generic elaboration.
- If the context does not answer the question, return empty bullets and note the limitation.

Context:
{context}

Question:
{question}
"""

    return llm_call_fn(prompt)
