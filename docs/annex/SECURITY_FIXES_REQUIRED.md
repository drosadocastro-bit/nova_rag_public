# Security Fixes Required - Action Plan

**Priority:** 🔴 HIGH - These fixes should be implemented before production deployment

---

## 1. Upgrade Waitress to Fix CVEs

### Issue
`waitress==2.1.2` has two known CVEs:
- CVE-2024-49768: DoS vulnerability 
- CVE-2024-49769: HTTP pipelining race condition

### Fix
Update `requirements.txt`:

```diff
- waitress==2.1.2
+ waitress==3.0.1
```

### Testing
After upgrade, test the server:
```bash
pip install -r requirements.txt
python nova_flask_app.py
# Verify server starts and handles requests correctly
```

---

## 2. Fix XSS Vulnerability in Frontend

### Issue
Multiple uses of `innerHTML` without HTML escaping in `static/app.js` could allow XSS attacks.

### Fix
Add HTML escaping utility and use it consistently:

```javascript
// Add this function at the top of app.js
function escapeHtml(unsafe) {
    if (typeof unsafe !== 'string') {
        unsafe = String(unsafe);
    }
    return unsafe
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

// Update formatAnswer function to escape all dynamic content
function formatAnswer(answer) {
    if (typeof answer === 'string') {
        return escapeHtml(answer);
    }
    if (typeof answer === 'object' && answer !== null) {
        if (answer.response_type === 'refusal') {
            return `⚠️ <strong>${escapeHtml(answer.reason || 'Request Declined')}</strong><br><br>${escapeHtml(answer.message || 'Unable to process this request.')}`;
        }
        
        // Escape all user-controlled fields in diagnostic responses
        if (answer.response && answer.response.analysis) {
            const analysis = answer.response.analysis;
            let html = '<div class="diagnostic-response">';
            
            if (analysis.probable_causes && analysis.probable_causes.length > 0) {
                html += '<div class="probable-causes"><strong>🔍 Probable Causes:</strong><ol>';
                for (const cause of analysis.probable_causes) {
                    html += `<li>`;
                    html += `<strong>${escapeHtml(cause.cause_type)}</strong> (${escapeHtml(cause.probability)}% probability)`;
                    if (cause.description) {
                        html += `<br><span class="cause-description">${escapeHtml(cause.description)}</span>`;
                    }
                    html += `</li>`;
                }
                html += '</ol></div>';
            }
            // ... continue escaping other fields
        }
        
        // For retrieval fallback responses
        if (answer.notes && answer.summary) {
            let html = '<div class="retrieval-fallback-response">';
            html += `<div class="fallback-notice"><strong>⚠️ ${escapeHtml(answer.notes)}</strong></div>`;
            html += '<div class="fallback-summary">';
            
            if (Array.isArray(answer.summary)) {
                for (const excerpt of answer.summary) {
                    html += `<div class="fallback-excerpt"><blockquote>${escapeHtml(excerpt)}</blockquote></div>`;
                }
            }
            html += '</div>';
            return html;
        }
    }
    return escapeHtml(String(answer));
}
```

### Files to Update
- `static/app.js` - Add escapeHtml function and apply to all innerHTML assignments

### Testing
Test with potentially malicious input:
```javascript
// Test cases to try in the UI:
"<script>alert('XSS')</script>"
"<img src=x onerror=alert('XSS')>"
"'; DROP TABLE users; --"
```

All should be displayed as text, not executed as code.

---

## 3. Secure Pickle Deserialization

### Issue
Using `pickle.load()` without verification could allow code execution if files are tampered with.

### Fix Option A: Add HMAC Verification (Quick Fix)

Create a new file `secure_cache.py`:

```python
import pickle
import hmac
import hashlib
import os
from pathlib import Path

# Get secret key from environment - REQUIRED for security
SECRET_KEY = os.environ.get('NOVA_CACHE_SECRET')
if not SECRET_KEY:
    # Generate a random secret key and warn user
    import secrets
    SECRET_KEY = secrets.token_hex(32)
    import warnings
    warnings.warn(
        "No NOVA_CACHE_SECRET set! Generated temporary key for this session. "
        "Set NOVA_CACHE_SECRET environment variable for persistent cache verification."
    )

def _compute_hmac(data: bytes) -> bytes:
    """Compute HMAC-SHA256 of data."""
    return hmac.new(SECRET_KEY.encode(), data, hashlib.sha256).digest()

def secure_pickle_dump(obj, filepath: Path):
    """Dump object to pickle with HMAC signature."""
    # Serialize object
    data = pickle.dumps(obj)
    # Compute HMAC
    signature = _compute_hmac(data)
    # Write signature + data
    with open(filepath, 'wb') as f:
        f.write(len(signature).to_bytes(4, 'big'))
        f.write(signature)
        f.write(data)

def secure_pickle_load(filepath: Path):
    """Load pickle with HMAC verification."""
    with open(filepath, 'rb') as f:
        # Read signature length
        sig_len = int.from_bytes(f.read(4), 'big')
        # Read signature
        stored_signature = f.read(sig_len)
        # Read data
        data = f.read()
    
    # Verify HMAC
    expected_signature = _compute_hmac(data)
    if not hmac.compare_digest(stored_signature, expected_signature):
        raise ValueError(f"HMAC verification failed for {filepath}. File may be tampered!")
    
    # Deserialize
    return pickle.loads(data)
```

Then update usage in `cache_utils.py`:

```python
from secure_cache import secure_pickle_dump, secure_pickle_load

# Replace pickle.dump calls
def cache_retrieval(func: Callable) -> Callable:
    # ...
    try:
        _retrieval_cache_file.parent.mkdir(parents=True, exist_ok=True)
        secure_pickle_dump(_retrieval_cache, _retrieval_cache_file)
    except Exception:
        pass
    # ...

# Replace pickle.load calls
def load_retrieval_cache():
    # ...
    if _retrieval_cache_file.exists():
        try:
            _retrieval_cache = secure_pickle_load(_retrieval_cache_file)
            print(f"[Cache] Loaded {len(_retrieval_cache)} retrieval cache entries")
        except Exception as e:
            print(f"[Cache] Failed to load retrieval cache: {e}")
```

### Fix Option B: Replace with JSON (Recommended Long-term)

For simple data structures, use JSON instead:

```python
import json

# cache_utils.py - Replace pickle with JSON
def cache_retrieval(func: Callable) -> Callable:
    # ...
    try:
        _retrieval_cache_file_json = _retrieval_cache_file.with_suffix('.json')
        with open(_retrieval_cache_file_json, 'w') as f:
            json.dump(_retrieval_cache, f)
    except Exception:
        pass
    # ...

def load_retrieval_cache():
    # ...
    _retrieval_cache_file_json = _retrieval_cache_file.with_suffix('.json')
    if _retrieval_cache_file_json.exists():
        try:
            with open(_retrieval_cache_file_json, 'r') as f:
                _retrieval_cache = json.load(f)
            print(f"[Cache] Loaded {len(_retrieval_cache)} retrieval cache entries")
        except Exception as e:
            print(f"[Cache] Failed to load retrieval cache: {e}")
```

### Files to Update
- `cache_utils.py` - Replace pickle.dump/load
- `backend.py` - Replace pickle.dump/load for search history

### Testing
```bash
# Test cache functionality
python -c "from cache_utils import load_retrieval_cache; load_retrieval_cache()"
# Should load without errors
```

---

## 4. Add Security Headers

### Issue
Missing Content Security Policy and other security headers.

### Fix
Update `nova_flask_app.py`:

```python
@app.after_request
def set_security_headers(response):
    """Add security headers to all responses."""
    # Content Security Policy
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "font-src 'self'; "
        "connect-src 'self'; "
        "frame-ancestors 'none';"
    )
    # Prevent MIME sniffing
    response.headers['X-Content-Type-Options'] = 'nosniff'
    # Prevent clickjacking
    response.headers['X-Frame-Options'] = 'DENY'
    # XSS protection (legacy browsers)
    response.headers['X-XSS-Protection'] = '1; mode=block'
    # HSTS (if using HTTPS)
    # response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    return response
```

Add this before the route definitions in `nova_flask_app.py`.

### Testing
```bash
curl -I http://localhost:5000/
# Check response headers include CSP, X-Frame-Options, etc.
```

---

## 5. Use Constant-Time Token Comparison

### Issue
String comparison for API tokens is vulnerable to timing attacks.

### Fix
Update `nova_flask_app.py`:

```python
import hmac

def _check_auth():
    if not REQUIRE_TOKEN:
        return True
    token = request.headers.get("X-API-TOKEN", "")
    if not API_TOKEN:
        return False
    # Use constant-time comparison to prevent timing attacks
    return hmac.compare_digest(token, API_TOKEN)
```

### Testing
```bash
# Test with valid token
curl -H "X-API-TOKEN: your-token" http://localhost:5000/api/status

# Test with invalid token
curl -H "X-API-TOKEN: wrong-token" http://localhost:5000/api/status
```

---

## Implementation Priority

1. **Day 1 (Critical):**
   - [ ] Upgrade waitress to 3.0.1
   - [ ] Fix XSS in app.js with HTML escaping

2. **Week 1 (High):**
   - [ ] Add HMAC to pickle or migrate to JSON
   - [ ] Add security headers
   - [ ] Fix token comparison timing

3. **Week 2 (Testing):**
   - [ ] Add unit tests for all security fixes
   - [ ] Run security scan (bandit, safety)
   - [ ] Penetration testing for XSS, CSRF

---

## Verification Checklist

After implementing fixes:

- [ ] All dependencies updated and tested
- [ ] XSS test cases pass (malicious input rendered as text)
- [ ] HMAC verification working for cache files
- [ ] Security headers present in HTTP responses
- [ ] API token comparison uses constant-time comparison
- [ ] No new security warnings from `pip-audit` or `safety`
- [ ] Code review of changes completed
- [ ] Documentation updated with security notes

---

## Additional Recommendations

### Enable Dependency Scanning

Add to GitHub Actions or run locally:

```bash
# Install security tools
pip install pip-audit safety

# Check for known vulnerabilities
pip-audit
safety check --json

# Static security analysis
pip install bandit
bandit -r . -f json -o security-report.json
```

### Rate Limiting

Consider adding rate limiting to API endpoints:

```python
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"]
)

@app.route("/api/ask", methods=["POST"])
@limiter.limit("10 per minute")
def api_ask():
    # ... existing code
```

### Input Validation

Add stronger input validation:

```python
def validate_question(question: str) -> bool:
    """Validate question meets security requirements.
    
    Note: Pattern matching is not sufficient for comprehensive XSS prevention.
    This is defense-in-depth; primary protection is HTML escaping in the frontend.
    Consider using a library like bleach for more robust validation.
    """
    # Max length
    if len(question) > 5000:
        return False
    
    # Basic validation - suspicious patterns (defense in depth only)
    # Primary XSS defense is HTML escaping in frontend via escapeHtml()
    suspicious = ['<script', 'javascript:', 'onerror=', 'onclick=', 'onload=']
    q_lower = question.lower()
    if any(pattern in q_lower for pattern in suspicious):
        return False
    
    return True
```

---

**Last Updated:** January 3, 2026  
**Status:** Awaiting Implementation
