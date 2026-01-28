# NIC Flask App Rebranding & Generalization Plan

## Overview
Transform from **"Vehicle Maintenance Assistant"** → **"NIC (Nova Intelligent Copilot)"** domain-neutral system with multi-domain question generation

---

## Changes Needed

### 1. Flask App Rebranding (nova_flask_app.py)

**Change all vehicle-specific references:**

| Old | New | Reason |
|-----|-----|--------|
| "Vehicle maintenance question" | "Technical documentation query" | Generic |
| "vehicle-maintenance" | "maintenance" or "technical-docs" | Neutral |
| "vehicle" (domain detect) | "auto-detect" or "multi-domain" | Scalable |
| "vehicle_index.faiss" | "nic_index.faiss" | Generic |
| "vehicle_docs.jsonl" | "nic_docs.jsonl" | Generic |
| Lines 238, 259 error msgs | Generic technical query msg | UX improvement |

---

## 2. Multi-Domain Question Generation

**Create file:** `test_questions_multidomains.json`

Generate common technical questions that work across all domains:

### Automotive (Current)
```json
{
  "domain": "automotive",
  "questions": [
    "How do I check the alternator voltage?",
    "What's the charging system specification?",
    "How do I diagnose a starter motor problem?"
  ]
}
```

### HVAC
```json
{
  "domain": "hvac",
  "questions": [
    "How do I check the compressor pressure?",
    "What's the refrigerant specification?",
    "How do I diagnose a thermostat problem?"
  ]
}
```

### Medical/Aerospace/Nuclear
Similar pattern with domain-specific terms

### Universal Pattern Questions (Test Generalization)
```json
{
  "domain": "universal",
  "pattern": "How to diagnose [SUBSYSTEM]?",
  "questions": [
    "How do I diagnose a power supply problem?",
    "How do I check component specifications?",
    "What's the procedure for maintenance?"
  ]
}
```

---

## 3. Qwen 4B Theoretical Performance

**For potato hardware testing:**

| Model | Params | VRAM | Speed (t/s) | Quality |
|-------|--------|------|-------------|---------|
| Qwen 0.5B | 500M | 1GB | 50+ | Low |
| **Qwen 4B** | 4B | 4GB | 20-30 | Medium |
| Llama2 7B | 7B | 7GB | 10-15 | High |
| Current (14B) | 14B | 14GB | 5-10 | Very High |

**Qwen 4B will:**
- ✅ Run on 4GB VRAM (laptop/edge devices)
- ✅ Show speed improvement (~2x faster than 14B)
- ⚠️ Potential accuracy trade-off (~80-90% vs 95%+)
- ✅ Perfect for potato hardware baseline testing

---

## 4. Implementation Order

### Phase 1: Flask App Rebranding (15 min)
- [ ] Update error messages (lines 238, 259)
- [ ] Change domain detection logic (line 332-333)
- [ ] Rename vector DB references (lines 623-624)
- [ ] Update metrics/labels (line 450)

### Phase 2: Multi-Domain Questions (20 min)
- [ ] Create `test_questions_multidomains.json`
- [ ] Generate 50-100 common technical questions
- [ ] Categorize by domain

### Phase 3: Qwen 4B Setup (prep)
- [ ] Test Qwen 4B download
- [ ] Benchmark against current models
- [ ] Document performance metrics

---

## 5. Specific Code Changes

### Error Messages (BEFORE → AFTER)

**Line 238:**
```python
# BEFORE
"Empty question. Please provide a vehicle-maintenance question."

# AFTER
"Empty question. Please provide a technical documentation query."
```

**Line 259:**
```python
# BEFORE
"Empty question. Please provide a vehicle-maintenance question."

# AFTER
"Empty question. Please ask about system diagnostics, specifications, or maintenance procedures."
```

### Domain Detection (BEFORE → AFTER)

**Lines 332-333:**
```python
# BEFORE
if "vehicle" in first_source.lower():
    domain = "vehicle"

# AFTER
# Auto-detect domain from source path or filename
domain_map = {
    "automotive": ["vehicle", "car", "truck"],
    "hvac": ["hvac", "cooling", "heating"],
    "aerospace": ["aircraft", "avionics"],
    "medical": ["hospital", "medical"],
    "nuclear": ["reactor", "nuclear"]
}

detected_domain = "unknown"
source_lower = first_source.lower()
for domain, keywords in domain_map.items():
    if any(kw in source_lower for kw in keywords):
        detected_domain = domain
        break
domain = detected_domain
```

### Vector DB Paths (BEFORE → AFTER)

**Lines 623-624:**
```python
# BEFORE
index_path = BASE_DIR / "vector_db" / "vehicle_index.faiss"
docs_path = BASE_DIR / "vector_db" / "vehicle_docs.jsonl"

# AFTER
index_path = BASE_DIR / "vector_db" / "nic_index.faiss"
docs_path = BASE_DIR / "vector_db" / "nic_docs.jsonl"
```

---

## 6. Multi-Domain Test Questions (Sample)

```json
{
  "universal_diagnostic": [
    "How do I check if the [COMPONENT] is functioning correctly?",
    "What are the normal specifications for [SUBSYSTEM]?",
    "How do I diagnose a [COMPONENT] failure?",
    "What's the procedure to replace [COMPONENT]?"
  ],
  "automotive": [
    "How do I check the alternator voltage?",
    "What's the battery specification?",
    "How do I diagnose a starter motor problem?",
    "What's the tire pressure specification?"
  ],
  "hvac": [
    "How do I check the compressor pressure?",
    "What's the refrigerant specification?",
    "How do I diagnose a thermostat problem?",
    "What's the indoor unit temperature specification?"
  ],
  "aerospace": [
    "How do I check the hydraulic pressure?",
    "What's the avionics power specification?",
    "How do I diagnose a landing gear problem?"
  ],
  "medical": [
    "How do I check the device calibration?",
    "What's the sensor accuracy specification?",
    "How do I diagnose a sensor failure?"
  ],
  "nuclear": [
    "How do I check the coolant temperature?",
    "What's the pressure vessel specification?",
    "How do I diagnose a pump failure?"
  ]
}
```

---

## 7. Why This Matters

### For Your Project
- ✅ NIC becomes **domain-agnostic** → marketable to any industry
- ✅ Tests **generalization** → proves RAG works across domains
- ✅ Supports **edge deployment** → Qwen 4B on potato hardware
- ✅ Scalable **question dataset** → better evaluation

### For Qwen 4B Testing
- ✅ Universal questions test model generalization
- ✅ Multiple domains validate robustness
- ✅ Speed metrics show potato-hardware viability
- ✅ Accuracy drop quantifiable vs. baseline

---

## Ready to Implement?

This refactoring:
1. Takes ~30-45 minutes
2. Costs zero breaking changes (fully backward compatible)
3. Enables multi-domain evaluation
4. Prepares for Qwen 4B performance testing

Want me to:
- [ ] Execute all Flask app changes?
- [ ] Generate comprehensive multi-domain test questions?
- [ ] Create Qwen 4B benchmark template?
- [ ] Do all three?

