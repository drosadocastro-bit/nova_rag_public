# User Guide

Complete guide for end users of the NIC RAG system. Learn how to ask questions effectively, interpret responses, and get the most value from the system.

---

## Table of Contents

1. [Getting Started](#getting-started)
2. [Example Queries](#example-queries)
3. [Understanding Confidence Scores](#understanding-confidence-scores)
4. [Citation Format](#citation-format)
5. [When the System Abstains](#when-the-system-abstains)
6. [Best Practices](#best-practices)
7. [Response Structure](#response-structure)
8. [Getting Better Results](#getting-better-results)
9. [Common Use Cases](#common-use-cases)
10. [Limitations](#limitations)

---

## Getting Started

### What is NIC?

NIC is an **offline RAG (Retrieval-Augmented Generation) system** designed for safety-critical environments. It answers questions by:
1. Finding relevant information in its document corpus (vehicle manuals)
2. Using that information to generate accurate, cited answers
3. Abstaining when confidence is low to prevent hallucinations

### Key Principles

| Principle | What it Means |
|-----------|--------------|
| **Grounded Answers** | All answers are based on actual documents, with citations |
| **Human-on-the-Loop** | Advisory only—you make the final decisions |
| **Confidence Gating** | System abstains rather than guessing when uncertain |
| **Offline Operation** | Works without internet (air-gapped environments) |
| **Auditable** | Every answer includes source citations for verification |

### Quick Start

**Web Interface:**
1. Open browser to `http://localhost:5000`
2. Type your question in the text box
3. Click "Ask" or press Enter
4. Review answer and citations

**API:**
```bash
curl -X POST http://127.0.0.1:5000/api/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "How do I check the oil level?"}'
```

---

## Example Queries

### Good Questions (High Success Rate)

These questions work well with NIC:

**1. Direct Factual Questions**
```
Q: What is the engine oil capacity?
A: The engine oil capacity is 4.5 quarts (4.3 liters) including the filter.
   [Citation: Vehicle Owner's Manual, Page 127]
```

**2. Procedural Questions**
```
Q: How do I change the air filter?
A: To change the cabin air filter:
   1. Open the glove box
   2. Remove the glove box stops on both sides
   3. Lower the glove box door
   4. Remove the old filter by sliding it out
   5. Insert the new filter with the arrow pointing toward the fan
   [Citation: Maintenance Schedule, Pages 45-46]
```

**3. Diagnostic Questions**
```
Q: What does the check engine light mean?
A: The check engine light indicates an emissions-related issue has been 
   detected by the onboard diagnostics system. Common causes include:
   - Loose or missing gas cap
   - Faulty oxygen sensor
   - Catalytic converter issues
   [Citation: Warning Lights Guide, Page 12]
```

**4. Specification Lookups**
```
Q: What is the recommended tire pressure?
A: The recommended tire pressure is 32 PSI for the front tires and 
   30 PSI for the rear tires when cold.
   [Citation: Tire Information Label, Page 234]
```

### Questions That May Not Work Well

**1. Vague Questions**
```
❌ "How does it work?"
✓ "How does the brake system work?"

❌ "What should I do?"
✓ "What should I do if the engine overheats?"
```

**2. Out-of-Scope Questions**
```
❌ "What's the weather today?" (not in corpus)
❌ "How do I cook pasta?" (unrelated domain)
❌ "Tell me a joke" (not informational)
```

**3. Multi-Part Questions**
```
❌ "How do I change the oil, rotate tires, and replace the battery?"
✓ Ask three separate questions for better results
```

---

## Understanding Confidence Scores

Every answer includes a **confidence score** (0-100%) indicating system certainty.

### Confidence Ranges

| Score | Meaning | Action |
|-------|---------|--------|
| **80-100%** | High confidence | Trust answer, verify via citations |
| **60-79%** | Medium confidence | Answer provided, review carefully |
| **40-59%** | Low confidence | Extractive fallback or abstention |
| **0-39%** | Very low confidence | System abstains |

### Example Responses by Confidence

**High Confidence (85%):**
```json
{
  "answer": "The oil capacity is 4.5 quarts.",
  "confidence": "85.0%",
  "citations": ["Owner's Manual, Page 127"]
}
```
→ **Action:** Trust answer, can optionally verify citation

**Medium Confidence (65%):**
```json
{
  "answer": "The brake fluid should be checked monthly or every 1,000 miles.",
  "confidence": "65.0%",
  "citations": ["Maintenance Guide, Page 89"]
}
```
→ **Action:** Answer likely correct, strongly recommend verifying

**Low Confidence (45%) - Abstention:**
```json
{
  "answer": {
    "response_type": "abstention",
    "message": "I cannot provide a confident answer. Here are relevant excerpts:",
    "extractive_fallback": ["Quote from page 45...", "Quote from page 78..."]
  },
  "confidence": "45.0%"
}
```
→ **Action:** Review excerpts manually, consult original documents

### What Affects Confidence?

| Factor | Impact |
|--------|--------|
| **Query matches corpus** | ↑ Higher confidence |
| **Multiple consistent sources** | ↑ Higher confidence |
| **Technical terminology** | ↑ Higher confidence (if in corpus) |
| **Vague/ambiguous query** | ↓ Lower confidence |
| **Out-of-scope query** | ↓ Lower confidence |
| **Contradictory sources** | ↓ Lower confidence |

---

## Citation Format

All answers include citations to source documents for verification.

### Citation Structure

**Standard Format:**
```
[Source Document Name, Page XX]
```

**Examples:**
```
[Vehicle Owner's Manual, Page 127]
[Maintenance Schedule, Pages 45-46]
[Emergency Procedures Guide, Page 8]
```

### Verifying Citations

**Why Verify:**
- Confirms answer accuracy
- Provides additional context
- Required for safety-critical decisions
- Builds trust in the system

**How to Verify:**
1. Note the cited source and page number
2. Locate the original document
3. Turn to the specified page
4. Confirm the information matches

**Example:**
```
Answer: "Change oil every 5,000 miles or 6 months."
Citation: [Maintenance Schedule, Page 23]

→ Open Maintenance Schedule PDF
→ Go to page 23
→ Verify: "Oil change interval: 5,000 miles / 6 months"
```

### Multiple Citations

When multiple sources are cited:
```
Answer: "Recommended tire rotation interval is 5,000-7,500 miles."
Citations:
  - [Owner's Manual, Page 234]
  - [Maintenance Guide, Page 56]
  - [Tire Care Booklet, Page 12]
```

This indicates:
- Information is well-documented
- Multiple sources agree
- Higher reliability

---

## When the System Abstains

### What is Abstention?

**Abstention:** The system chooses NOT to generate an answer because confidence is too low. This prevents hallucinations.

### Why Abstention Happens

1. **Out-of-Scope Query:** Question not related to vehicle maintenance
2. **Information Not in Corpus:** Topic not covered in available documents
3. **Ambiguous Query:** Question is too vague to answer confidently
4. **Contradictory Information:** Sources provide conflicting information

### Abstention Response Format

```json
{
  "answer": {
    "response_type": "abstention",
    "reason": "low_confidence",
    "message": "I cannot provide a confident answer to this question.",
    "extractive_fallback": [
      "Excerpt from relevant page 1...",
      "Excerpt from relevant page 2..."
    ]
  },
  "confidence": "35.0%"
}
```

### What to Do When System Abstains

**Option 1: Refine Your Question**
```
Original: "How do I fix it?"
Refined: "How do I fix a flat tire?"
```

**Option 2: Review Extractive Fallback**
```
System provides relevant excerpts from documents.
Review manually to find your answer.
```

**Option 3: Consult Original Documents**
```
Use citations to locate relevant sections in source PDFs.
```

**Option 4: Try Alternative Phrasing**
```
Original: "What's the deal with the brakes?"
Alternative: "How often should brake pads be replaced?"
```

---

## Best Practices

### 1. Be Specific

✓ **Good:** "What type of oil does the 2023 model use?"  
❌ **Vague:** "What oil should I use?"

### 2. Use Proper Terminology

✓ **Good:** "How do I replace the cabin air filter?"  
❌ **Unclear:** "How do I change the thing that cleans air?"

### 3. One Question at a Time

✓ **Good:** Ask separately: "Oil capacity?" then "Oil type?"  
❌ **Complex:** "What's the oil capacity, type, and change interval?"

### 4. Verify Safety-Critical Information

✓ **Always verify citations for:**
- Brake system procedures
- Tire specifications
- Fluid requirements
- Electrical system work
- Towing capacities

### 5. Use the Right Mode

| Mode | When to Use |
|------|-------------|
| Auto (default) | Most questions |
| Vision | Questions about images (dashboard lights, diagrams) |

### 6. Check Confidence Scores

- High (>80%): Trust, but still verify for critical tasks
- Medium (60-79%): Verify carefully
- Low (<60%): System abstains, review excerpts manually

### 7. Provide Context

✓ **Good:** "How do I reset the oil change reminder on a 2023 model?"  
❌ **Lacks context:** "How do I reset it?"

---

## Response Structure

### Complete Response Anatomy

```json
{
  // Main answer object
  "answer": {
    "response_type": "answer",           // answer | refusal | abstention
    "text": "The answer text here...",
    "citations": [                        // Source references
      "Manual, Page 45",
      "Guide, Page 78"
    ],
    "source_documents": [                 // Document names
      "vehicle_manual.pdf",
      "maintenance_guide.pdf"
    ]
  },
  
  // Confidence metrics
  "confidence": "85.0%",                  // Overall confidence
  "retrieval_score": 0.87,                // How well docs matched query
  
  // Source tracing
  "traced_sources": [                     // Detailed source info
    {
      "source": "vehicle_manual.pdf",
      "page": 45,
      "confidence": 0.92,
      "snippet": "First 150 chars of text..."
    }
  ],
  
  // Metadata
  "model_used": "llama3.2:8b",           // LLM model
  "session_id": "abc-123",                // Session tracking
  "audit_status": "enabled",              // Citation audit on/off
  "effective_safety": "strict"            // Safety mode
}
```

### Response Types

**1. Normal Answer (`response_type: "answer"`)**
- Question answered successfully
- Includes text, citations, confidence
- Use answer as advisory information

**2. Abstention (`response_type: "abstention"`)**
- System chose not to answer (low confidence)
- Provides extractive fallback (relevant quotes)
- Review quotes manually or rephrase question

**3. Refusal (`response_type: "refusal"`)**
- Input rejected (invalid format, out-of-scope, etc.)
- Includes reason and guidance
- Correct input and resubmit

---

## Getting Better Results

### Strategies for Success

**1. Use Domain Language**
```
✓ "coolant temperature sensor"
❌ "the water hot thingy"
```

**2. Specify the Vehicle Component**
```
✓ "What is the torque spec for the oil drain plug?"
❌ "What torque should I use?"
```

**3. Break Down Complex Questions**
```
Complex: "How do I diagnose and fix an engine that won't start?"

Better:
1. "What are common causes of a no-start condition?"
2. "How do I check if the battery is dead?"
3. "How do I test the starter motor?"
```

**4. Learn What's in the Corpus**
```
System knows: Vehicle maintenance, repairs, specifications
System doesn't know: Driving directions, weather, other domains
```

**5. Use Hybrid Search Advantages**
```
Hybrid search (default) excels at:
- Part numbers: "Where is part #12345?"
- Diagnostic codes: "What does code P0171 mean?"
- Exact terminology: "serpentine belt routing diagram"
```

### Troubleshooting Poor Results

| Problem | Solution |
|---------|----------|
| Too many abstentions | Be more specific, use domain terms |
| Wrong answers | Verify confidence scores, check citations |
| No results | Topic may not be in corpus, try related queries |
| Slow responses | Expected (2-8s), see Performance Guide for tuning |

---

## Common Use Cases

### 1. Maintenance Reminders

**Query:** "When should I change the transmission fluid?"  
**Expected:** Service interval with citation  
**Confidence:** High (if in corpus)

### 2. Troubleshooting

**Query:** "Why is my battery light on?"  
**Expected:** Possible causes and recommended actions  
**Confidence:** Medium to High

### 3. Specifications

**Query:** "What is the towing capacity?"  
**Expected:** Exact specification with citation  
**Confidence:** Very High

### 4. Procedures

**Query:** "How do I bleed the brake system?"  
**Expected:** Step-by-step instructions  
**Confidence:** High

### 5. Part Identification

**Query:** "Where is the PCV valve located?"  
**Expected:** Location description, possibly with diagram reference  
**Confidence:** Medium to High

---

## Limitations

### What NIC Can't Do

1. **Answer Questions Outside the Corpus**
   - Only knows what's in the loaded documents
   - Cannot access external information
   - No real-time data (weather, traffic, etc.)

2. **Make Decisions for You**
   - Advisory only—you retain authority
   - Verify all safety-critical information
   - Consult professionals for complex repairs

3. **Guarantee 100% Accuracy**
   - Confidence gating reduces errors
   - Always verify citations for critical tasks
   - LLM may occasionally misinterpret sources

4. **Answer Multi-Domain Questions**
   - Focused on vehicle maintenance
   - Off-topic questions will be rejected or abstain

5. **Update Itself**
   - No internet access by design
   - Corpus is static until manually updated
   - Cannot learn from new information

### When to Consult a Professional

**Always consult a certified mechanic for:**
- Brake system repairs
- Steering/suspension work
- Electrical system diagnostics (complex)
- Transmission rebuilds
- Engine internal repairs
- Safety recalls
- Airbag system work

**NIC is advisory only. You are responsible for final decisions.**

---

## Frequently Asked Questions

**Q: Can I trust the answers?**  
A: Answers are grounded in source documents with citations. Always verify citations for safety-critical tasks. High confidence (>80%) answers are generally reliable.

**Q: Why does the system say "I cannot answer"?**  
A: Confidence gating prevents hallucinations. When the system isn't confident, it abstains rather than guessing. This is a safety feature.

**Q: How do I get faster responses?**  
A: See [Performance Benchmarks](evaluation/PERFORMANCE_BENCHMARKS.md) for optimization options. Expected latency is 2-8 seconds.

**Q: Can I add new documents?**  
A: Yes, but requires rebuilding the index. See [Troubleshooting Guide](TROUBLESHOOTING.md) for index rebuild procedures.

**Q: What if citations are wrong?**  
A: Report the issue. The citation audit (when enabled) validates citations, but it's not perfect. Always verify critical information.

**Q: Does this work offline?**  
A: Yes, completely. All models run locally, no internet required.

---

## Support Resources

- **API Reference:** [docs/api/API_REFERENCE.md](api/API_REFERENCE.md)
- **Troubleshooting:** [docs/TROUBLESHOOTING.md](TROUBLESHOOTING.md)
- **Configuration:** [docs/deployment/CONFIGURATION.md](deployment/CONFIGURATION.md)
- **FAQ:** [docs/FAQ.md](FAQ.md)

---

**Remember:** NIC is a tool to assist you. Always verify safety-critical information and consult professionals when needed.
