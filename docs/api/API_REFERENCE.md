# API Reference

Complete API documentation for the NIC RAG system. All endpoints follow REST conventions and return JSON responses.

---

## Table of Contents

1. [Base URL](#base-url)
2. [Authentication](#authentication)
3. [Endpoints](#endpoints)
   - [POST /api/ask](#post-apiask)
   - [GET /api/status](#get-apistatus)
   - [POST /api/retrieve](#post-apiretrieve)
4. [Response Schemas](#response-schemas)
5. [Error Handling](#error-handling)
6. [Rate Limiting](#rate-limiting)
7. [Example Requests](#example-requests)

---

## Base URL

```
http://127.0.0.1:5000
```

Default local development server. For production deployments, configure with environment variables:
- `FLASK_HOST` - Server host (default: 127.0.0.1)
- `FLASK_PORT` - Server port (default: 5000)

---

## Authentication

### Optional Token Authentication

NIC supports optional API token authentication for production deployments.

**Environment Variables:**
```bash
# Enable token requirement
NOVA_REQUIRE_TOKEN=1

# Set API token
NOVA_API_TOKEN=your_secure_token_here
```

**Request Header:**
```
X-API-TOKEN: your_secure_token_here
```

**Authentication Response:**
- `403 Forbidden` - Missing or invalid token when `NOVA_REQUIRE_TOKEN=1`
- Token authentication uses constant-time comparison to prevent timing attacks

**Default Behavior:**
- Authentication is **disabled** by default (`NOVA_REQUIRE_TOKEN=0`)
- Suitable for local development and air-gapped environments
- Enable for production or multi-user deployments

---

## Endpoints

### POST /api/ask

Submit a question to the RAG system and receive a grounded answer with citations.

#### Request

**URL:** `/api/ask`

**Method:** `POST`

**Headers:**
```
Content-Type: application/json
X-API-TOKEN: <token>  (if NOVA_REQUIRE_TOKEN=1)
```

**Body Schema:**
```json
{
  "question": "string (required, max 5000 chars)",
  "mode": "string (optional, default: 'Auto')",
  "fallback": "string (optional, e.g., 'retrieval-only')"
}
```

**Parameters:**
- `question` (required): User question, 1-5000 characters
- `mode` (optional): Query mode - `"Auto"` (default), `"Vision"`, or other supported modes
- `fallback` (optional): Fallback strategy if primary mode fails (e.g., `"retrieval-only"`)

#### Response

**Success Response (200 OK):**
```json
{
  "answer": {
    "response_type": "string",
    "text": "string",
    "citations": ["string"],
    "source_documents": ["string"]
  },
  "confidence": "string (e.g., '85.0%')",
  "retrieval_score": "number (0.0-1.0)",
  "traced_sources": [
    {
      "source": "string",
      "page": "number or null",
      "confidence": "number",
      "snippet": "string"
    }
  ],
  "model_used": "string",
  "session_id": "string",
  "session_active": "boolean",
  "audit_status": "string ('enabled' or 'disabled')",
  "effective_safety": "string ('strict' or 'standard')"
}
```

**Refusal Response (200 OK):**

For invalid inputs or edge cases, the system returns a structured refusal:
```json
{
  "answer": {
    "response_type": "refusal",
    "reason": "string",
    "policy": "string",
    "message": "string",
    "question": "string"
  },
  "confidence": "0.0%",
  "model_used": "none",
  "session_id": "string",
  "session_active": "boolean",
  "audit_status": "disabled",
  "effective_safety": "strict"
}
```

**Error Response (400/403/500):**
```json
{
  "error": "string (error description)"
}
```

#### Response Fields

| Field | Type | Description |
|-------|------|-------------|
| `answer` | object | Main response containing answer text and citations |
| `answer.response_type` | string | Type of response: `"answer"`, `"refusal"`, `"abstention"` |
| `answer.text` | string | Generated answer text (when available) |
| `answer.citations` | array | List of source citations with page numbers |
| `answer.source_documents` | array | Source document names |
| `confidence` | string | System confidence in the answer (0-100%) |
| `retrieval_score` | number | Average retrieval confidence (0.0-1.0) |
| `traced_sources` | array | Detailed source metadata with snippets |
| `model_used` | string | LLM model name or "auto" |
| `session_id` | string | Current session identifier |
| `session_active` | boolean | Whether session tracking is active |
| `audit_status` | string | Citation audit status |
| `effective_safety` | string | Safety mode in effect |

#### Expected Response Times

| Scenario | Expected Latency | Notes |
|----------|------------------|-------|
| Cache hit | 50-200ms | Cached retrieval results |
| Cache miss (retrieval only) | 200-800ms | Vector search + BM25 fusion |
| Full RAG pipeline | 2-8 seconds | Retrieval + LLM generation |
| Vision mode | 5-15 seconds | Image processing + generation |
| Abstention (low confidence) | 300-1000ms | Skips LLM generation |

*Times measured on CPU inference with llama3.2:8b model*

#### Input Validation

The system automatically rejects:
- Empty questions
- Questions > 5000 characters
- Script injection attempts (`<script>`, SQL keywords)
- Symbol-only or emoji-only input
- Extremely repetitive text (same word 50+ times)

Rejections return HTTP 200 with `response_type: "refusal"` for graceful handling.

---

### GET /api/status

Health check endpoint for system status monitoring.

#### Request

**URL:** `/api/status`

**Method:** `GET`

**Headers:** None required

#### Response

**Success Response (200 OK):**
```json
{
  "ollama": true,
  "ollama_status": "string (connection details)",
  "index_loaded": true
}
```

**Error Response (200 OK with error status):**
```json
{
  "ollama": false,
  "ollama_status": "error",
  "index_loaded": false
}
```

#### Response Fields

| Field | Type | Description |
|-------|------|-------------|
| `ollama` | boolean | Ollama service connectivity |
| `ollama_status` | string | Detailed Ollama connection status |
| `index_loaded` | boolean | FAISS vector index availability |

#### Use Cases

- Startup validation
- Health monitoring
- Load balancer readiness checks
- Diagnostic troubleshooting

**Expected Response Time:** < 500ms

---

### POST /api/retrieve

Direct retrieval endpoint for fetching relevant documents without LLM generation.

#### Request

**URL:** `/api/retrieve`

**Method:** `POST`

**Headers:**
```
Content-Type: application/json
```

**Body Schema:**
```json
{
  "query": "string (required)",
  "k": "number (optional, default: 6, max: 100)"
}
```

**Parameters:**
- `query` (required): Search query text
- `k` (optional): Number of documents to retrieve (default: 6, max: 100)

#### Response

**Success Response (200 OK):**
```json
[
  {
    "text": "string (first 200 chars of document)",
    "source": "string (document name)",
    "confidence": "number (0.0-1.0, rounded to 2 decimals)"
  }
]
```

**Empty Query Response (200 OK):**
```json
[]
```

**Error Response (500):**
```json
{
  "error": "string (error description)"
}
```

#### Response Fields

| Field | Type | Description |
|-------|------|-------------|
| `text` | string | Document snippet (truncated to 200 chars) |
| `source` | string | Source document filename |
| `confidence` | number | Retrieval confidence score (0.0-1.0) |

#### Use Cases

- Debug retrieval quality
- Inspect source documents
- Validate hybrid search results
- Build custom RAG pipelines

**Expected Response Time:** 200-800ms

---

## Response Schemas

### Answer Object Schema

```typescript
interface Answer {
  response_type: "answer" | "refusal" | "abstention";
  text?: string;                    // Present for answers
  citations?: string[];             // Present for answers
  source_documents?: string[];      // Present for answers
  reason?: string;                  // Present for refusals
  policy?: string;                  // Present for refusals
  message?: string;                 // Present for refusals/abstentions
  question?: string;                // Echo of input question
}
```

### Traced Source Schema

```typescript
interface TracedSource {
  source: string;        // Document filename
  page: number | null;   // Page number (null if not applicable)
  confidence: number;    // Retrieval confidence (0.0-1.0)
  snippet: string;       // First 150 chars of content
}
```

---

## Error Handling

### HTTP Status Codes

| Code | Meaning | When Used |
|------|---------|-----------|
| 200 | OK | Successful request (includes structured refusals) |
| 400 | Bad Request | Encoding errors or malformed JSON |
| 403 | Forbidden | Authentication failure |
| 500 | Internal Server Error | Unexpected server errors |

### Error Response Format

```json
{
  "error": "descriptive error message"
}
```

### Common Errors

| Error Message | Cause | Solution |
|--------------|-------|----------|
| `"Unauthorized"` | Missing/invalid API token | Provide valid `X-API-TOKEN` header |
| `"Server encoding error"` | Unicode/emoji encoding issues | Use standard ASCII text |
| `"Empty question"` | Empty or whitespace-only input | Provide a valid question |
| `"Input too long"` | Question exceeds 5000 chars | Shorten the question |
| `"Malformed input"` | Detected injection attempt | Remove special characters/scripts |

### Structured Refusals vs. Errors

NIC returns HTTP 200 with `response_type: "refusal"` for:
- Input validation failures
- Policy violations
- Out-of-scope queries
- Safety-triggered rejections

This allows clients to handle rejections gracefully without error-handling logic.

---

## Rate Limiting

**Current Status:** Not implemented

**Recommendation for Production:**
- Implement rate limiting at reverse proxy layer (nginx, Caddy)
- Suggested limit: 60 requests/minute per IP for `/api/ask`
- No limit for `/api/status` (health checks)

**Example nginx Configuration:**
```nginx
limit_req_zone $binary_remote_addr zone=api:10m rate=60r/m;

location /api/ask {
    limit_req zone=api burst=10 nodelay;
    proxy_pass http://127.0.0.1:5000;
}
```

---

## Example Requests

### 1. Basic Query (curl)

```bash
curl -X POST http://127.0.0.1:5000/api/ask \
  -H "Content-Type: application/json" \
  -d '{
    "question": "How do I check the oil level?"
  }'
```

### 2. Query with Authentication (curl)

```bash
curl -X POST http://127.0.0.1:5000/api/ask \
  -H "Content-Type: application/json" \
  -H "X-API-TOKEN: your_secure_token_here" \
  -d '{
    "question": "What is the recommended tire pressure?"
  }'
```

### 3. Query with Mode Selection (curl)

```bash
curl -X POST http://127.0.0.1:5000/api/ask \
  -H "Content-Type: application/json" \
  -d '{
    "question": "What does this warning light mean?",
    "mode": "Vision",
    "fallback": "retrieval-only"
  }'
```

### 4. Health Check (curl)

```bash
curl http://127.0.0.1:5000/api/status
```

### 5. Direct Retrieval (curl)

```bash
curl -X POST http://127.0.0.1:5000/api/retrieve \
  -H "Content-Type: application/json" \
  -d '{
    "query": "engine oil specifications",
    "k": 10
  }'
```

### 6. Python Example

```python
import requests

# Basic query
response = requests.post(
    "http://127.0.0.1:5000/api/ask",
    json={"question": "How often should I change the oil?"}
)
result = response.json()

print(f"Answer: {result['answer']['text']}")
print(f"Confidence: {result['confidence']}")
print(f"Sources: {result['answer']['citations']}")
```

### 7. Python with Authentication

```python
import requests

headers = {
    "X-API-TOKEN": "your_secure_token_here"
}

response = requests.post(
    "http://127.0.0.1:5000/api/ask",
    headers=headers,
    json={"question": "What is the engine coolant capacity?"}
)
result = response.json()
```

### 8. JavaScript (fetch) Example

```javascript
fetch('http://127.0.0.1:5000/api/ask', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
  },
  body: JSON.stringify({
    question: 'How do I reset the maintenance reminder?'
  })
})
.then(response => response.json())
.then(data => {
  console.log('Answer:', data.answer.text);
  console.log('Confidence:', data.confidence);
  console.log('Sources:', data.answer.citations);
});
```

---

## Integration Notes

### Session Management

- Sessions are automatically created on first query
- `session_id` persists across requests (stateful on server)
- Sessions track conversation history for context
- No explicit session creation/destruction API

### Confidence Gating

NIC implements confidence gating to prevent hallucinations:
- Retrieval score < 0.6 → System abstains, returns extractive fallback
- No LLM generation for low-confidence queries
- Prevents fabricated answers when relevant sources aren't found

### Citation Audit

When enabled (`NOVA_CITATION_AUDIT=1`):
- LLM-generated answers are validated against source documents
- Citations are verified for accuracy
- Unverifiable claims are flagged or removed
- Adds 1-3 seconds to response time

### Hybrid Retrieval

Enabled by default (`NOVA_HYBRID_SEARCH=1`):
- Combines vector similarity (FAISS) with BM25 lexical search
- Improves recall for exact terms, part numbers, diagnostic codes
- Results are fused and reranked using Maximal Marginal Relevance (MMR)

---

## Performance Characteristics

### Latency Breakdown (Average)

| Component | Time | Percentage |
|-----------|------|------------|
| Input validation | 5-10ms | <1% |
| Retrieval (hybrid) | 200-800ms | 10-15% |
| LLM generation | 2-6s | 70-85% |
| Citation audit | 500ms-2s | 10-20% |
| Response formatting | 10-50ms | <1% |

### Throughput

- Single request: 2-8 seconds end-to-end
- Sequential requests: ~0.2-0.5 QPS (queries per second)
- No concurrent request handling (single-threaded Flask)
- For production: Deploy with gunicorn/waitress for concurrency

**Recommended Production Setup:**
```bash
waitress-serve --host=0.0.0.0 --port=5000 --threads=4 nova_flask_app:app
```

### Memory Usage

| Component | Memory |
|-----------|--------|
| FAISS index (10k docs) | ~200-500 MB |
| Embedding model | ~400 MB |
| LLM model (8B params) | 4-6 GB |
| Application overhead | ~200 MB |
| **Total** | **~5-7 GB** |

For lower memory usage:
- Use smaller LLM (1B-3B params): ~1-2 GB
- Disable cross-encoder: Save ~400 MB
- Disable vision: Save ~500 MB

---

## Security Considerations

### Input Sanitization

- Automatic filtering of script injection attempts
- SQL keyword detection
- Maximum input length enforcement
- Emoji/symbol-only rejection

### Authentication

- Optional token-based auth with constant-time comparison
- Protects against timing attacks
- Recommended for production deployments

### Content Security

- Security headers on all responses (CSP, X-Frame-Options, etc.)
- No user-supplied content reflected without sanitization
- All responses are JSON (no HTML rendering in API)

### Air-Gap Compliance

- No external API calls during inference
- All models run locally
- No telemetry or analytics
- Suitable for classified/restricted networks

---

## Troubleshooting

### "Ollama connection failed"

**Symptom:** `/api/status` returns `ollama: false`

**Solutions:**
1. Verify Ollama is running: `ollama list`
2. Check Ollama server: `curl http://127.0.0.1:11434/api/tags`
3. Ensure model is pulled: `ollama pull llama3.2:8b`
4. Review Ollama logs for errors

### "Index not loaded"

**Symptom:** `/api/status` returns `index_loaded: false`

**Solutions:**
1. Build index: `python ingest_vehicle_manual.py`
2. Verify index files exist: `vector_db/vehicle_index.faiss`
3. Check file permissions
4. Review startup logs for FAISS errors

### Slow Response Times

**Symptoms:** Queries take > 15 seconds

**Solutions:**
1. Use smaller LLM model (3B instead of 8B)
2. Reduce retrieval k parameter (default: 12 → 6)
3. Disable citation audit: `NOVA_CITATION_AUDIT=0`
4. Enable retrieval cache: `NOVA_ENABLE_RETRIEVAL_CACHE=1`
5. Use native engine: `NOVA_USE_NATIVE_LLM=1`

### High Memory Usage

**Symptoms:** System using > 8 GB RAM

**Solutions:**
1. Disable vision: `NOVA_DISABLE_VISION=1`
2. Disable cross-encoder: `NOVA_DISABLE_CROSS_ENCODER=1`
3. Use smaller embedding model
4. Reduce batch size: `NOVA_EMBED_BATCH_SIZE=16`

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2024-01 | Initial API reference |

---

**See Also:**
- [User Guide](../USER_GUIDE.md)
- [Troubleshooting Guide](../TROUBLESHOOTING.md)
- [System Architecture](../architecture/SYSTEM_ARCHITECTURE.md)
- [Configuration Guide](../deployment/CONFIGURATION.md)
