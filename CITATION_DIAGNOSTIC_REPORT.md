# 🚨 NIC Citation System Diagnostic Report
## Issue: Sources Showing as "unknown" Instead of Document Names

**Date:** January 28, 2026  
**Symptom:** Query responses show "unknown - 95.0% match" instead of actual document names like "TM-10-3930-763-10" or "manual_p12.pdf"

---

## Issue Analysis

### Problem Summary
The citation system has broken down between retrieval and response output:
- ✅ Vector DB retrieval stores sources correctly with document names
- ✅ Context docs passed to agent have "source" field
- ❌ Final response shows "unknown" for all sources
- ❌ User sees fragmented content from multiple documents mixed together

### Root Cause Analysis

#### Issue #1: Metadata Loss in Citation Extraction (CONFIRMED)
**Location:** [agents/agent_router.py](agents/agent_router.py#L1118)

```python
# Line 1118-1120 in nic_act()
citations = [d.get("source", "unknown") for d in context_docs]
```

**Problem:** This extracts "source" but:
1. If `context_docs[i]` is missing "source" field → defaults to "unknown"
2. Context shows proper source names (Line 1117: `f"[{d.get('source', 'unknown')}]\n{...}"`)
3. But citations array gets built separately and loses the mapping

**Root Cause:** Sources are extracted ONCE at line 1118, but the actual context text (line 1117) includes source names. However, when the response is normalized (line 453 in backend.py), the normalizer doesn't properly reconnect sources to claims.

#### Issue #2: Response Normalizer Strips Source Mapping
**Location:** [response_normalizer.py](response_normalizer.py#L108-115)

```python
# Lines 108-115
sources = data.get("sources") or data.get("source") or data.get("citations") or data.get("citation")
if sources:
    if isinstance(sources, list):
        sources_text = ", ".join(str(s) for s in sources if s)
    else:
        sources_text = str(sources)
    parts.append(f"[Sources: {sources_text}]")
```

**Problem:** The normalizer ONLY appends sources at the END of the response:
- It looks for a "sources" key in the LLM JSON output
- But the LLM never includes a "sources" key in its response
- So sources get lost entirely and replaced with generic structure

#### Issue #3: LLM Response Format Problem
**Location:** [agents/agent_router.py](agents/agent_router.py#L1189)

The LLM is asked to output JSON (line 1189):
```python
prompt = f"""...
Respond with structured JSON following the appropriate format for this query type."""
```

But the JSON template doesn't include a `"sources"` field, so the LLM never includes source metadata in its response.

#### Issue #4: Citation Auditor Receives Sources But Doesn't Pass Them Through
**Location:** [agents/agent_router.py](agents/agent_router.py#L1960-2000)

When citation audit runs (if enabled):
- It receives `sources` list from `nic_act()` result
- But it only passes `safe_sources` to the final answer dict
- And `safe_sources` calculation (line 1959) uses problematic extraction

---

## Comprehensive Fix Strategy

### Fix #1: Ensure Sources Persist Through Citation Extraction

**File:** `agents/agent_router.py` (Line 1118)  
**Current Code:**
```python
citations = [d.get("source", "unknown") for d in context_docs]
```

**Fixed Code:**
```python
# Extract sources with fallback to filename/doc_id
citations = []
for d in context_docs:
    source = d.get("source") or d.get("filename") or d.get("doc_name") or d.get("doc_id") or "unknown"
    page = d.get("page") or d.get("page_num")
    if page is not None:
        source = f"{source} p{page}"
    citations.append(source)
```

**Reason:** Handles multiple field names used by different retrieval pathways

---

### Fix #2: Update Response Normalizer to Extract & Preserve Source Mapping

**File:** `response_normalizer.py`  
**Current Issue:** Normalizer only appends sources at the end, doesn't extract from LLM content

**New Function to Add:**
```python
def extract_citations_from_content(answer_text: str) -> dict:
    """
    Extract cited sources from LLM response text.
    Looks for patterns like:
    - "According to manual.pdf: ..."
    - "From page 12 (TM-10-3930): ..."
    - "Source: [filename]"
    """
    import re
    
    # Pattern 1: "Source: [filename]" or "From [filename]:"
    sources_pattern = r'(?:Source|From|According to)[:=]\s*(\[?[^\]\n]+\]?)'
    matches = re.findall(sources_pattern, answer_text, re.IGNORECASE)
    
    if matches:
        return {
            "sources": [m.strip('[]') for m in matches],
            "has_citations": True
        }
    
    return {"sources": [], "has_citations": False}
```

**Update `normalize_response()` to call this:**
```python
def normalize_response(answer: Any, context_sources: list = None) -> str:
    """
    Enhanced normalizer that:
    1. Normalizes format (WARNINGS/STEPS/VERIFY)
    2. Extracts embedded citations
    3. Appends context_sources if not found
    """
    # ... existing normalization code ...
    
    # NEW: Extract embedded citations
    if isinstance(final_result, str):
        citation_data = extract_citations_from_content(final_result)
        if citation_data["sources"]:
            final_result += f"\n📚 Sources Used:\n" + "\n".join(
                f"- {s}" for s in citation_data["sources"]
            )
        elif context_sources:
            # Fallback: append context sources if no embedded citations found
            final_result += f"\n📚 Sources Used:\n" + "\n".join(
                f"- {s} - 0% (used for context)" for s in context_sources
            )
    
    return final_result
```

---

### Fix #3: Include Sources in LLM Prompt & JSON Schema

**File:** `agents/agent_router.py` (Line 1189)  
**Current Prompt:**
```python
prompt = f"""...REQUIREMENTS:...{citation_req}..."""
```

**New Prompt Addition:**
```python
prompt = f"""...
RESPONSE FORMAT:
{{
    "answer": "Your response here",
    "sources": [
        {{"source": "TM-10-3930-763-10", "page": 12, "confidence": 0.95}},
        {{"source": "manual_p45.pdf", "page": 45, "confidence": 0.87}}
    ],
    "warnings": [...],
    "verification": [...]
}}
...
"""
```

**Reason:** Explicitly tells LLM to include sources in structured format

---

### Fix #4: Pass Context Sources to Normalizer

**File:** `backend.py` (Line 453)  
**Current Code:**
```python
answer_normalized = normalize_response(answer)
```

**Fixed Code:**
```python
# Extract source names from context docs
context_sources = [
    d.get("source") or d.get("filename") or "unknown" 
    for d in context_docs
] if context_docs else []

answer_normalized = normalize_response(answer, context_sources=context_sources)
```

**Reason:** Normalizer can now fall back to context sources if LLM doesn't provide them

---

### Fix #5: Update Citation Auditor to Preserve Sources

**File:** `agents/agent_router.py` (Line 1959)  
**Current Code:**
```python
safe_sources = result.get("sources", [])
```

**Fixed Code:**
```python
# Preserve full source information through audit
safe_sources = []
raw_sources = result.get("sources", [])
for src in raw_sources:
    if isinstance(src, dict):
        safe_sources.append(src)
    else:
        safe_sources.append({"source": str(src), "page": None})
```

---

## Implementation Plan

### Priority 1 - Critical (Do First)
1. **Fix agent_router.py line 1118** - Proper source extraction with fallback fields
2. **Add sources to LLM prompt** - Tell LLM to include source metadata

### Priority 2 - High (Do Second)  
3. **Update response_normalizer.py** - Extract embedded citations and append sources
4. **Modify backend.py line 453** - Pass context sources to normalizer

### Priority 3 - Polish (Do Third)
5. **Update citation_auditor.py** - Preserve source dicts through audit
6. **Add logging** - Debug output to track source propagation

---

## Testing Strategy

### Test Case 1: Source Propagation
```bash
Query: "How do I check the alternator voltage?"
Expected Output:
"STEPS: Step 1: Check the voltage at the alternator output
📚 Sources Used:
- TM-10-3930-763-10 - 95.0% match"
```

Current Output (BROKEN):
```
"STEPS: Step 1: Check the voltage at the alternator output
📚 Sources Used:
- unknown - 95.0% match"
```

### Test Case 2: Multiple Sources
```bash
Query: "What's the charging system specification?"
Expected: 3+ document names visible with match percentages
Current: Multiple "unknown" entries with fragmented content
```

### Test Case 3: Page Numbers
```bash
Query: "Page 12 in the alternator manual?"
Expected: "TM-10-3930-763-10 p12 - 89.3% match"
Current: "unknown - 89.3% match"
```

---

## Files to Modify

| File | Changes | Priority |
|------|---------|----------|
| `agents/agent_router.py` | Lines 1118, 1189, 1959 | P1 |
| `response_normalizer.py` | Add citation extraction function, update normalize_response | P2 |
| `backend.py` | Line 453: Pass context_sources | P2 |
| `agents/citation_auditor.py` | Preserve source dicts | P3 |

---

## Summary

**Why "unknown" is showing:**
1. Retriever returns correct source names ✅
2. Agent extracts sources but they get lost during normalization ❌
3. LLM never receives source fields in prompt, so never includes them ❌
4. Response normalizer can't extract what was never included ❌
5. Final output gets default "unknown" values ❌

**The Fix:**
- Ensure source fields flow through entire pipeline
- Update LLM prompt to request sources in JSON
- Update normalizer to extract and append sources
- Add logging to track source propagation

---

**Estimated Effort:** 30-45 minutes  
**Risk Level:** LOW (purely additive changes, no breaking changes)  
**Rollback Plan:** Easy - just revert the 4 file changes

