def run_summarize(question: str, context_docs: list[dict], llm_call_fn):
    """Return a summarized version of the context as structured JSON.

    Schema:
    {
      "bullets": ["..."],
      "sources": ["manual.pdf"],
      "notes": "optional"
    }
    """
    if context_docs:
        context = "\n\n---\n\n".join(f"[Source: {d.get('source','unknown')}]\n{d.get('text','')}" for d in context_docs)
    else:
        context = ""

    prompt = f"""
You are a technical assistant that summarizes relevant manual content.
Return ONLY compact JSON, no prose, no markdown.
Use this schema exactly:
{{
  "bullets": ["..."],
  "sources": ["manual.pdf"],
  "notes": "optional"
}}
Rules:
- If unknown, use empty list/string ("").
- Do not add extra keys.
- Keep bullets short and relevant.

Context:
{context}

Question:
{question}
"""

    return llm_call_fn(prompt)
