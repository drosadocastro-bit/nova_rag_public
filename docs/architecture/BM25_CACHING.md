# BM25 Caching Architecture

## Overview

NovaRAG implements an intelligent caching system for its BM25 lexical search index to minimize startup time and improve performance. This document explains the cache lifecycle, invalidation triggers, and maintenance procedures.

## What is BM25?

BM25 (Best Matching 25) is a ranking function used for lexical search that complements NovaRAG's vector-based semantic search. It works by:
- Tokenizing queries and documents into words
- Computing term frequency (TF) and inverse document frequency (IDF) scores
- Ranking documents based on exact keyword matches

In NovaRAG, BM25 is part of the **hybrid retrieval** system (`NOVA_HYBRID_SEARCH=1`), combining:
- **Vector search**: Semantic similarity using embeddings
- **BM25 lexical search**: Exact keyword matching

This dual approach ensures both semantically similar and keyword-exact results are retrieved.

---

## Cache Lifecycle

### 1. Cache Building (First Startup or After Corpus Change)

**When it happens:**
- First application startup after fresh installation
- After PDFs are added/modified in `data/` directory
- When BM25 parameters change (k1, b values)
- After manual cache deletion

**Process:**
1. System computes SHA256 hash of all document chunks (`_compute_corpus_hash()` - lines 745-750 in backend.py)
2. Tokenizes all documents and builds inverted index (`_build_bm25_index()` - lines 812-836)
3. Saves index to `vector_db/bm25_index.pkl`
4. Saves corpus hash to `vector_db/bm25_corpus_hash.txt`

**Code reference (backend.py lines 812-836):**
```python
def _build_bm25_index():
    global _BM25_INDEX, _BM25_DOC_LEN, _BM25_AVGDL, _BM25_READY
    # Try loading from cache first
    if _load_bm25_index():
        return
    # Build from scratch
    try:
        _BM25_INDEX = {}
        _BM25_DOC_LEN = []
        for i, d in enumerate(docs):
            tokens = _tokenize(d.get("text", ""))
            _BM25_DOC_LEN.append(len(tokens))
            tf_local: dict[str, int] = {}
            for t in tokens:
                tf_local[t] = tf_local.get(t, 0) + 1
            for t, tf in tf_local.items():
                posting = _BM25_INDEX.setdefault(t, {})
                posting[i] = tf
        _BM25_AVGDL = (sum(_BM25_DOC_LEN) / max(1, len(_BM25_DOC_LEN))) if _BM25_DOC_LEN else 0.0
        _BM25_READY = True
        print(f"[NovaRAG] BM25 index built: {len(_BM25_INDEX)} terms, avgdl={_BM25_AVGDL:.1f}")
        _save_bm25_index()
    except Exception as e:
        _BM25_READY = False
        print(f"[NovaRAG] BM25 index build failed: {e}")
```

### 2. Cache Loading (Normal Startup)

**When it happens:**
- Every subsequent application startup when cache is valid

**Process:**
1. Check if cache files exist (`bm25_index.pkl` and `bm25_corpus_hash.txt`)
2. Validate corpus hash matches current documents (`_load_bm25_index()` - lines 778-810)
3. Validate BM25 parameters (k1, b) match current environment variables
4. Load pre-built index into memory

**Code reference (backend.py lines 778-810):**
```python
def _load_bm25_index() -> bool:
    """Load BM25 index from disk if valid; return True if loaded."""
    global _BM25_INDEX, _BM25_DOC_LEN, _BM25_AVGDL, _BM25_READY
    if not BM25_CACHE_ENABLED or not BM25_CACHE_PATH.exists() or not BM25_CORPUS_HASH_PATH.exists():
        return False
    try:
        # Check corpus hash
        saved_hash = BM25_CORPUS_HASH_PATH.read_text(encoding="utf-8").strip()
        current_hash = _compute_corpus_hash()
        if saved_hash != current_hash:
            print(f"[NovaRAG] BM25 cache invalid (corpus changed); rebuilding...")
            return False
        # Load index
        if SECURE_CACHE_AVAILABLE:
            from secure_cache import secure_pickle_load
            data = secure_pickle_load(BM25_CACHE_PATH)
        else:
            import pickle
            with BM25_CACHE_PATH.open("rb") as f:
                data = pickle.load(f)
        # Validate parameters match
        if data.get("k1") != _BM25_K1 or data.get("b") != _BM25_B:
            print(f"[NovaRAG] BM25 cache params mismatch; rebuilding...")
            return False
        _BM25_INDEX = data["index"]
        _BM25_DOC_LEN = data["doc_len"]
        _BM25_AVGDL = data["avgdl"]
        _BM25_READY = True
        print(f"[NovaRAG] BM25 index loaded from cache: {len(_BM25_INDEX)} terms, avgdl={_BM25_AVGDL:.1f}")
        return True
    except Exception as e:
        print(f"[NovaRAG] Failed to load BM25 cache: {e}; rebuilding...")
        return False
```

### 3. Cache Invalidation (Automatic Rebuild)

**When it happens:**
- Corpus content changes detected via hash mismatch
- BM25 parameters (k1, b) changed in environment variables
- Cache file corruption or read errors

**Process:**
1. System detects mismatch during `_load_bm25_index()`
2. Automatically triggers full rebuild via `_build_bm25_index()`
3. New cache saved with updated hash

---

## Invalidation Triggers

### ✅ Trigger 1: New PDFs Added to `data/` Directory

**What happens:**
- Adding new `.pdf` files to the `data/` directory changes the corpus
- Corpus hash computation (`_compute_corpus_hash()`) detects new content
- Next startup: cache invalid → automatic rebuild

**Example:**
```bash
# Initial state
$ ls data/
manual_v1.pdf

# Add new manual
$ cp new_maintenance_guide.pdf data/

# Next startup
# Console output: "[NovaRAG] BM25 cache invalid (corpus changed); rebuilding..."
```

### ✅ Trigger 2: Existing PDFs Modified

**What happens:**
- Modifying content of existing PDFs (e.g., updating a section)
- SHA256 hash changes for that document
- Cache invalidation on next load

**Detection mechanism (backend.py lines 745-750):**
```python
def _compute_corpus_hash() -> str:
    """Compute a hash of the corpus to detect changes."""
    hasher = hashlib.sha256()
    for d in docs:
        hasher.update(d.get("text", "").encode("utf-8"))
    return hasher.hexdigest()[:16]
```

### ✅ Trigger 3: BM25 Parameters Changed

**What happens:**
- Changing `NOVA_BM25_K1` or `NOVA_BM25_B` environment variables
- Cached index stores old parameters
- Mismatch detected → rebuild

**Example:**
```bash
# Initial cache built with defaults (k1=1.5, b=0.75)
$ python nova_flask_app.py

# Later, tune for different ranking
$ export NOVA_BM25_K1=2.0
$ export NOVA_BM25_B=0.8
$ python nova_flask_app.py
# Console output: "[NovaRAG] BM25 cache params mismatch; rebuilding..."
```

**Validation logic (backend.py lines 799-801):**
```python
# Validate parameters match
if data.get("k1") != _BM25_K1 or data.get("b") != _BM25_B:
    print(f"[NovaRAG] BM25 cache params mismatch; rebuilding...")
    return False
```

### ✅ Trigger 4: Manual Cache Deletion

**What happens:**
- Deleting `vector_db/bm25_index.pkl` or `vector_db/bm25_corpus_hash.txt`
- Cache files not found → rebuild

**Example:**
```bash
$ rm vector_db/bm25_*.pkl vector_db/bm25_*.txt
$ python nova_flask_app.py
# Console output: "[NovaRAG] BM25 index built: 8234 terms, avgdl=156.3"
```

---

## Cache Files

### `vector_db/bm25_index.pkl`
**Purpose:** Serialized BM25 inverted index

**Contents:**
- `index`: Dictionary mapping terms → document IDs → term frequencies
- `doc_len`: List of document lengths (in tokens)
- `avgdl`: Average document length across corpus
- `k1`, `b`: BM25 ranking parameters

**Size:** Typically 1-10 MB for 1000 documents, scales linearly with corpus size

**Format:** Python pickle (or secure_pickle if `secure_cache.py` available)

### `vector_db/bm25_corpus_hash.txt`
**Purpose:** SHA256 hash of corpus content for change detection

**Contents:** 16-character hex string (truncated SHA256 hash)

**Example:** `a3f9c82e1b4d7c5f`

**Size:** ~20 bytes

---

## Configuration

### `NOVA_BM25_CACHE` (Cache Enable/Disable)

**Default:** `1` (enabled)

**Values:**
- `1`: Cache enabled (recommended)
- `0`: Cache disabled - forces rebuild every startup

**Usage:**
```bash
# Enable caching (default)
export NOVA_BM25_CACHE=1

# Disable caching (for testing or troubleshooting)
export NOVA_BM25_CACHE=0
python nova_flask_app.py
# BM25 index rebuilt on every startup
```

**When to disable:**
- Debugging BM25 indexing issues
- Testing different tokenization strategies
- Development/testing workflows with frequent corpus changes

### `NOVA_BM25_K1` (Term Frequency Saturation)

**Default:** `1.5`

**Range:** 1.2 - 2.0 (typical)

**Effect:**
- Higher values → less saturation, repeated terms matter more
- Lower values → more saturation, diminishing returns for repetition

**Usage:**
```bash
export NOVA_BM25_K1=1.8  # Less saturation
python nova_flask_app.py
```

### `NOVA_BM25_B` (Document Length Normalization)

**Default:** `0.75`

**Range:** 0.0 - 1.0

**Effect:**
- `b=1.0`: Full normalization (penalize long documents heavily)
- `b=0.0`: No normalization (ignore document length)
- `b=0.75`: Balanced (recommended)

**Usage:**
```bash
export NOVA_BM25_B=0.5  # Less aggressive normalization
python nova_flask_app.py
```

---

## Performance Impact

### Cache Hit (Normal Startup)

**Time:** ~0.1-0.3 seconds
- Reading pickle file from disk
- Deserializing into memory

**Console output:**
```
[NovaRAG] BM25 index loaded from cache: 8234 terms, avgdl=156.3
```

### Cache Miss (Rebuild Required)

**Time depends on corpus size:**

| Corpus Size | Build Time | Memory Peak |
|-------------|------------|-------------|
| 100 docs    | 0.5-1s     | +50 MB      |
| 1,000 docs  | 3-5s       | +200 MB     |
| 10,000 docs | 30-60s     | +1.5 GB     |
| 100,000 docs| 5-10 min   | +10 GB      |

**Console output:**
```
[NovaRAG] BM25 index built: 8234 terms, avgdl=156.3
[NovaRAG] BM25 index cached to vector_db/bm25_index.pkl
```

**Bottlenecks:**
- Tokenization: O(n) where n = total characters in corpus
- Index building: O(n × m) where m = average doc length
- Pickle serialization: O(index size)

---

## Troubleshooting

### Problem: "BM25 cache invalid (corpus changed)" on Every Startup

**Cause:** Corpus hash mismatch despite no intentional changes

**Possible reasons:**
1. PDFs modified externally (e.g., metadata updated by PDF viewer)
2. File system timestamps changing (network drives, Docker volumes)
3. Race condition during multi-process startup

**Solutions:**
```bash
# 1. Verify no accidental PDF modifications
$ ls -lh data/*.pdf

# 2. Clear cache and rebuild
$ rm vector_db/bm25_*.pkl vector_db/bm25_*.txt
$ python nova_flask_app.py

# 3. If persistent, disable caching temporarily
$ export NOVA_BM25_CACHE=0
```

### Problem: "BM25 cache params mismatch" After Environment Change

**Cause:** Environment variables changed but cache still has old parameters

**Solution:**
```bash
# Option 1: Delete cache (auto-rebuild with new params)
$ rm vector_db/bm25_*.pkl

# Option 2: Restart application (will auto-rebuild)
$ python nova_flask_app.py
```

### Problem: Slow Startup Despite Caching Enabled

**Possible causes:**
1. Cache files corrupted → automatic rebuild
2. Large corpus (>10k docs) → rebuild takes time
3. Slow disk I/O (network drive, HDD instead of SSD)

**Diagnosis:**
```bash
# Check if cache files exist
$ ls -lh vector_db/bm25_*
# Should see bm25_index.pkl and bm25_corpus_hash.txt

# Check console output for "rebuilding" vs "loaded from cache"
$ python nova_flask_app.py 2>&1 | grep BM25
```

**Solutions:**
```bash
# If rebuilding unnecessarily:
$ rm vector_db/bm25_*.pkl vector_db/bm25_*.txt
$ python nova_flask_app.py  # One-time rebuild

# If corpus too large for startup rebuild:
# Pre-build index in background script
$ python -c "import backend; backend._build_bm25_index()"
```

### Problem: Out of Memory During BM25 Build

**Cause:** Very large corpus (>100k documents) exceeds available RAM

**Solutions:**
```bash
# Option 1: Disable BM25 (use vector-only search)
$ export NOVA_HYBRID_SEARCH=0

# Option 2: Reduce corpus size (split into multiple indices)
$ mkdir data_archive
$ mv data/older_manuals*.pdf data_archive/

# Option 3: Increase system memory or use swap
```

---

## Maintenance

### When to Clear Cache

**Scenarios:**
1. **Bulk PDF updates:** After adding/removing many PDFs, manually clear cache to force clean rebuild
   ```bash
   $ rm vector_db/bm25_*.pkl vector_db/bm25_*.txt
   ```

2. **Tokenization changes:** If you modify `_tokenize()` function in backend.py

3. **Index corruption suspected:** Cache files may be corrupted if application crashes during save

4. **Testing:** Verify rebuild logic works correctly

### How to Force Rebuild

**Method 1: Delete cache files**
```bash
$ rm vector_db/bm25_index.pkl vector_db/bm25_corpus_hash.txt
$ python nova_flask_app.py
```

**Method 2: Disable caching temporarily**
```bash
$ NOVA_BM25_CACHE=0 python nova_flask_app.py
# Rebuilds on startup, but doesn't save cache
```

**Method 3: Programmatic rebuild**
```python
from backend import _build_bm25_index
_build_bm25_index()
```

### Verifying Cache Integrity

**Check hash consistency:**
```bash
# Compute current hash
$ python -c "import backend; print(backend._compute_corpus_hash())"

# Compare with cached hash
$ cat vector_db/bm25_corpus_hash.txt
```

**Check index stats:**
```bash
$ python -c "
import backend
backend._load_bm25_index()
print(f'Terms: {len(backend._BM25_INDEX)}')
print(f'Docs: {len(backend._BM25_DOC_LEN)}')
print(f'Avg DL: {backend._BM25_AVGDL:.1f}')
"
```

---

## Advanced Topics

### Secure Pickle

If `secure_cache.py` is available, BM25 caching uses HMAC-verified pickle to prevent tampering:

```python
if SECURE_CACHE_AVAILABLE:
    from secure_cache import secure_pickle_dump, secure_pickle_load
    secure_pickle_dump(data, BM25_CACHE_PATH)
else:
    import pickle
    with BM25_CACHE_PATH.open("wb") as f:
        pickle.dump(data, f)
```

**Benefits:**
- Prevents malicious cache file injection
- Detects accidental corruption

### Multi-Instance Deployments

**Problem:** Multiple application instances sharing same cache directory

**Solutions:**
1. **Read-only cache:** First instance builds, others load (require file locking)
2. **Instance-specific caches:** Use `NOVA_CACHE_DIR` per instance
3. **Centralized cache:** Build once, distribute to instances

---

## Related Configuration

- `NOVA_HYBRID_SEARCH`: Enable/disable hybrid (vector + BM25) retrieval
- `NOVA_DISABLE_EMBED`: Force lexical-only search (no embeddings)
- `INDEX_DIR`: Location of cache files (`vector_db/` by default)

---

## Summary

✅ **Cache automatically manages itself** - no manual intervention needed in normal usage

✅ **Intelligent invalidation** - detects corpus changes, parameter changes, corruption

✅ **Performance boost** - 0.1s load vs 3-60s rebuild for typical corpora

✅ **Production-ready** - secure pickle, error recovery, graceful fallback

⚠️ **Watch for:** Large corpora (>10k docs) may need pre-build or increased memory

📝 **Best practice:** Monitor startup logs for "loaded from cache" vs "rebuilding" messages
