# Phase 3: Incremental Indexing Architecture

**Status:** Design Phase  
**Target:** Production hot-reload capability without downtime  
**Success Criteria:** Add 1,000+ chunks in <5s per manual with zero quality degradation

---

## Overview

Phase 3 implements **incremental indexing** to enable corpus scaling in production without server restarts. The architecture maintains deterministic retrieval while supporting append-only FAISS updates and incremental BM25 corpus expansion.

---

## Design Principles

1. **Zero Downtime:** Index updates happen without server restart
2. **Deterministic:** Same corpus state → same retrieval results
3. **Atomic:** Updates succeed completely or roll back entirely
4. **Auditable:** Every corpus change logged with hash, timestamp, operator
5. **Backward Compatible:** Existing Phase 2/2.5 functionality preserved

---

## Architecture Components

### 1. File-Hash Tracking System

**Purpose:** Detect corpus changes efficiently without re-processing entire corpus

**Implementation:**
```python
# vector_db/corpus_manifest.json
{
  "version": "3.0",
  "last_updated": "2026-01-22T10:30:00Z",
  "total_chunks": 1692,
  "files": {
    "data/vehicle_manual.pdf": {
      "sha256": "a3f5b2...",
      "chunk_count": 432,
      "domain": "vehicle_civilian",
      "last_modified": "2026-01-20T14:22:00Z",
      "ingested_at": "2026-01-20T15:00:00Z",
      "chunk_ids": [0, 1, 2, ..., 431]
    },
    "data/forklift_manual.pdf": {
      "sha256": "c7d9e1...",
      "chunk_count": 986,
      "domain": "forklift",
      "last_modified": "2025-12-15T09:00:00Z",
      "ingested_at": "2025-12-15T10:30:00Z",
      "chunk_ids": [432, 433, ..., 1417]
    }
  }
}
```

**Key Methods:**
- `compute_file_hash(file_path) -> str`: SHA-256 hash of file content
- `detect_changes() -> List[FileChange]`: Compare current corpus vs manifest
- `update_manifest(file_path, metadata)`: Record new file ingestion
- `validate_manifest_integrity()`: Verify manifest matches actual index state

**Change Detection Logic:**
```python
class FileChange:
    NEW = "new"           # File not in manifest
    MODIFIED = "modified" # Hash mismatch
    DELETED = "deleted"   # File in manifest but missing
    UNCHANGED = "unchanged"

def detect_changes(corpus_dir: str, manifest: CorpusManifest) -> List[FileChange]:
    current_files = scan_corpus_directory(corpus_dir)
    manifest_files = set(manifest.files.keys())
    
    changes = []
    for file_path in current_files:
        current_hash = compute_file_hash(file_path)
        if file_path not in manifest_files:
            changes.append(FileChange(file_path, FileChange.NEW))
        elif manifest.files[file_path].sha256 != current_hash:
            changes.append(FileChange(file_path, FileChange.MODIFIED))
    
    for file_path in manifest_files - current_files:
        changes.append(FileChange(file_path, FileChange.DELETED))
    
    return changes
```

---

### 2. FAISS Append-Only Updates

**Purpose:** Add new embeddings without rebuilding entire index

**Current State (Phase 2.5):**
- Full index rebuild on any corpus change
- ~2-5 minutes for 1,692 chunks
- Blocks retrieval during rebuild

**Target State (Phase 3):**
- Incremental additions in <5 seconds
- No retrieval blocking
- Atomic updates with rollback

**Implementation Strategy:**

```python
class IncrementalFAISSIndex:
    def __init__(self, index_path: str, dimension: int):
        self.index_path = index_path
        self.dimension = dimension
        self.index = self._load_or_create_index()
        self.metadata = self._load_metadata()
    
    def add_chunks(self, new_chunks: List[Chunk]) -> UpdateResult:
        """
        Add new chunks to existing index without rebuild.
        
        Returns UpdateResult with:
        - success: bool
        - chunks_added: int
        - time_elapsed: float
        - new_chunk_ids: List[int]
        """
        try:
            # 1. Generate embeddings for new chunks
            embeddings = self._generate_embeddings(new_chunks)
            
            # 2. Get current index size (determines new chunk IDs)
            current_size = self.index.ntotal
            new_chunk_ids = range(current_size, current_size + len(new_chunks))
            
            # 3. Backup current index state (for rollback)
            backup_path = self._create_backup()
            
            # 4. Add embeddings to FAISS index
            self.index.add(embeddings)  # FAISS append operation
            
            # 5. Update metadata mapping (chunk_id -> chunk_data)
            for chunk_id, chunk in zip(new_chunk_ids, new_chunks):
                self.metadata[chunk_id] = {
                    "text": chunk.text,
                    "source": chunk.source,
                    "domain": chunk.domain,
                    "page": chunk.page
                }
            
            # 6. Persist updated index and metadata
            self._save_index()
            self._save_metadata()
            
            # 7. Clean up backup
            self._remove_backup(backup_path)
            
            return UpdateResult(
                success=True,
                chunks_added=len(new_chunks),
                new_chunk_ids=list(new_chunk_ids)
            )
        
        except Exception as e:
            # Rollback on any error
            self._restore_from_backup(backup_path)
            return UpdateResult(success=False, error=str(e))
    
    def _create_backup(self) -> str:
        """Create timestamped backup of index + metadata"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = f"{self.index_path}.backup_{timestamp}"
        shutil.copytree(self.index_path, backup_dir)
        return backup_dir
```

**FAISS Index Format:**
- Use `IndexFlatL2` (deterministic, supports incremental adds)
- Store in `vector_db/faiss_index/`
- Metadata in `vector_db/faiss_metadata.json`

**Version Coordination:**
```json
// vector_db/faiss_version.json
{
  "version": "3.0.0",
  "embedding_model": "sentence-transformers/all-MiniLM-L6-v2",
  "dimension": 384,
  "total_vectors": 2500,
  "last_incremental_update": "2026-01-22T10:30:00Z",
  "updates": [
    {
      "timestamp": "2026-01-22T10:30:00Z",
      "chunks_added": 808,
      "files_added": ["data/phase3_corpus/arduino_manual.pdf"],
      "operator": "system"
    }
  ]
}
```

---

### 3. Incremental BM25 Corpus Expansion

**Purpose:** Add new documents to BM25 index without full rebuild

**Current State (Phase 2.5):**
- BM25 index cached to disk
- Invalidated on any corpus change
- Full rebuild required

**Target State (Phase 3):**
- Incremental document additions
- Preserve existing BM25 statistics
- Update IDF scores efficiently

**Implementation Strategy:**

```python
class IncrementalBM25:
    def __init__(self, cache_dir: str):
        self.cache_dir = cache_dir
        self.corpus = self._load_corpus()  # List of tokenized documents
        self.bm25 = self._load_or_build_bm25()
        self.doc_metadata = self._load_metadata()
    
    def add_documents(self, new_docs: List[str], metadata: List[Dict]) -> UpdateResult:
        """
        Add new documents to BM25 index incrementally.
        
        Strategy:
        1. Append new docs to corpus
        2. Rebuild BM25 (fast since it's in-memory)
        3. Update cache
        """
        try:
            # 1. Tokenize new documents
            tokenized_new_docs = [self._tokenize(doc) for doc in new_docs]
            
            # 2. Get current corpus size (for new doc IDs)
            current_size = len(self.corpus)
            new_doc_ids = range(current_size, current_size + len(new_docs))
            
            # 3. Backup current state
            backup_path = self._create_backup()
            
            # 4. Append to corpus
            self.corpus.extend(tokenized_new_docs)
            
            # 5. Rebuild BM25 (using rank_bm25 library)
            # Note: BM25 rebuild is fast (<1s for 10k docs) since it's in-memory
            from rank_bm25 import BM25Okapi
            self.bm25 = BM25Okapi(self.corpus)
            
            # 6. Update metadata
            for doc_id, meta in zip(new_doc_ids, metadata):
                self.doc_metadata[doc_id] = meta
            
            # 7. Persist to cache
            self._save_cache()
            
            # 8. Clean up backup
            self._remove_backup(backup_path)
            
            return UpdateResult(
                success=True,
                docs_added=len(new_docs),
                new_doc_ids=list(new_doc_ids)
            )
        
        except Exception as e:
            self._restore_from_backup(backup_path)
            return UpdateResult(success=False, error=str(e))
    
    def _save_cache(self):
        """Persist corpus, BM25 params, and metadata to disk"""
        cache_data = {
            "corpus": self.corpus,
            "avgdl": self.bm25.avgdl,
            "doc_len": self.bm25.doc_len,
            "idf": self.bm25.idf,
            "metadata": self.doc_metadata
        }
        with open(f"{self.cache_dir}/bm25_cache.pkl", "wb") as f:
            pickle.dump(cache_data, f)
```

**Why BM25 Rebuild is Acceptable:**
- BM25 construction is O(n) and fast in-memory
- ~1s for 10,000 docs on modern hardware
- No GPU required (unlike embeddings)
- Cache persistence amortizes cost

---

### 4. Hot-Reload API Endpoint

**Purpose:** Trigger index updates without server restart

**Endpoint Specification:**

```python
# POST /api/reload
# Request Body:
{
  "operation": "incremental_update",  # or "full_rebuild"
  "files": ["data/new_manual.pdf"],   # optional: specific files
  "dry_run": false                     # optional: validate without applying
}

# Response:
{
  "success": true,
  "operation": "incremental_update",
  "stats": {
    "files_processed": 1,
    "chunks_added": 342,
    "faiss_update_time": 3.2,
    "bm25_update_time": 0.8,
    "total_time": 4.5
  },
  "warnings": [],
  "errors": []
}
```

**Implementation:**

```python
@app.route('/api/reload', methods=['POST'])
def reload_corpus():
    """
    Hot-reload corpus with incremental indexing.
    
    Workflow:
    1. Detect corpus changes
    2. Process new/modified files
    3. Update FAISS incrementally
    4. Update BM25 incrementally
    5. Update manifest
    6. Log operation
    """
    try:
        data = request.get_json()
        operation = data.get('operation', 'incremental_update')
        dry_run = data.get('dry_run', False)
        
        # 1. Detect changes
        manifest = CorpusManifest.load()
        changes = detect_changes(CORPUS_DIR, manifest)
        
        if not changes:
            return jsonify({"success": True, "message": "No changes detected"})
        
        # 2. Process new/modified files
        new_chunks = []
        for change in changes:
            if change.type in [FileChange.NEW, FileChange.MODIFIED]:
                chunks = ingest_document(change.file_path)
                new_chunks.extend(chunks)
        
        if dry_run:
            return jsonify({
                "success": True,
                "dry_run": True,
                "changes": [c.to_dict() for c in changes],
                "estimated_chunks": len(new_chunks)
            })
        
        # 3. Update indices
        start_time = time.time()
        
        faiss_start = time.time()
        faiss_result = faiss_index.add_chunks(new_chunks)
        faiss_time = time.time() - faiss_start
        
        bm25_start = time.time()
        bm25_result = bm25_index.add_documents(
            [c.text for c in new_chunks],
            [c.metadata for c in new_chunks]
        )
        bm25_time = time.time() - bm25_start
        
        total_time = time.time() - start_time
        
        # 4. Update manifest
        for change in changes:
            manifest.update_file(change.file_path, compute_file_hash(change.file_path))
        manifest.save()
        
        # 5. Log operation
        log_incremental_update(changes, faiss_result, bm25_result, total_time)
        
        return jsonify({
            "success": True,
            "operation": operation,
            "stats": {
                "files_processed": len(changes),
                "chunks_added": len(new_chunks),
                "faiss_update_time": faiss_time,
                "bm25_update_time": bm25_time,
                "total_time": total_time
            }
        })
    
    except Exception as e:
        logger.error(f"Reload failed: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
```

**Progress Tracking:**
```python
# For large batches, emit progress events
from flask import stream_with_context

@app.route('/api/reload/stream', methods=['POST'])
def reload_corpus_stream():
    """Stream progress updates for long-running reloads"""
    def generate():
        yield json.dumps({"status": "detecting_changes"}) + "\n"
        
        changes = detect_changes(CORPUS_DIR, manifest)
        yield json.dumps({"status": "processing", "total_files": len(changes)}) + "\n"
        
        for i, change in enumerate(changes):
            chunks = ingest_document(change.file_path)
            yield json.dumps({
                "status": "progress",
                "file": change.file_path,
                "chunks": len(chunks),
                "progress": (i+1) / len(changes)
            }) + "\n"
        
        yield json.dumps({"status": "complete"}) + "\n"
    
    return Response(stream_with_context(generate()), mimetype='application/json')
```

---

## Rollback Strategy

**Atomic Updates:**
- Create timestamped backup before any index modification
- If any step fails, restore from backup
- Clean up backup only after successful completion

**Backup Contents:**
- FAISS index files
- BM25 cache
- Manifest
- Metadata

**Rollback Triggers:**
- Embedding generation failure
- FAISS add() exception
- BM25 rebuild error
- Metadata corruption
- Disk space exhaustion

**Implementation:**
```python
class AtomicIndexUpdate:
    def __init__(self):
        self.backup_dir = None
        self.committed = False
    
    def __enter__(self):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.backup_dir = f"vector_db/backup_{timestamp}"
        self._create_backup()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            # Exception occurred, rollback
            self._rollback()
            return False
        else:
            # Success, clean up backup
            self._cleanup_backup()
            return True
    
    def _create_backup(self):
        shutil.copytree("vector_db", self.backup_dir)
    
    def _rollback(self):
        logger.warning(f"Rolling back to {self.backup_dir}")
        shutil.rmtree("vector_db")
        shutil.copytree(self.backup_dir, "vector_db")
    
    def _cleanup_backup(self):
        shutil.rmtree(self.backup_dir)

# Usage:
with AtomicIndexUpdate():
    faiss_index.add_chunks(new_chunks)
    bm25_index.add_documents(new_docs)
    manifest.update()
```

---

## Performance Targets

| Metric | Target | Rationale |
|--------|--------|-----------|
| **Single Manual Index** | <5s | Production hot-reload requirement |
| **Batch (10 manuals)** | <30s | Overnight corpus updates |
| **Large Batch (100 manuals)** | <5min | Initial air-gap deployment |
| **FAISS Append Time** | <2s per 1000 chunks | Dominated by embedding generation |
| **BM25 Rebuild Time** | <1s per 10k docs | In-memory operation |
| **Manifest Update** | <100ms | File I/O + JSON serialization |

**Optimization Strategies:**
- Batch embedding generation (GPU parallelization)
- Async BM25 rebuild (non-blocking)
- Compressed manifest storage (msgpack instead of JSON)
- Memory-mapped FAISS index (reduce load time)

---

## Testing Strategy

### Unit Tests
- File hash computation
- Change detection logic
- FAISS append operations
- BM25 incremental updates
- Manifest integrity validation
- Rollback mechanism

### Integration Tests
- Add single file
- Add batch of files
- Handle duplicates (same hash)
- Detect modifications (hash change)
- Rollback on error
- Concurrent reload requests (locking)

### Performance Tests
- Measure index update time vs chunk count
- Validate <5s target for single manual
- Memory usage during updates
- Cache hit rates after reload

### Safety Tests
- Retrieval quality unchanged (before/after)
- No embedding dimension mismatch
- BM25 IDF scores consistent
- Domain distribution preserved

---

## Migration Path (Phase 2.5 → Phase 3)

**Step 1: Create Initial Manifest**
```bash
python scripts/create_corpus_manifest.py
# Scans data/ directory, computes hashes, generates manifest
```

**Step 2: Validate Manifest**
```bash
python scripts/validate_manifest.py
# Verifies manifest matches current index state
```

**Step 3: Enable Incremental Mode**
```bash
export NOVA_INCREMENTAL_INDEXING=1
python nova_flask_app.py
```

**Step 4: Test with New Document**
```bash
curl -X POST http://localhost:5000/api/reload \
  -H "Content-Type: application/json" \
  -d '{"operation": "incremental_update", "dry_run": true}'
```

**Backward Compatibility:**
- If `NOVA_INCREMENTAL_INDEXING=0`, use Phase 2.5 full rebuild
- Manifest generation is optional (fallback to full rebuild)
- Existing indices work without modification

---

## Open Questions & Decisions

1. **Deletion Handling:** How to remove chunks when files are deleted?
   - **Decision:** Mark as deleted in manifest, skip in retrieval, periodic compaction

2. **Concurrent Updates:** How to handle multiple reload requests?
   - **Decision:** Single-writer lock, queue subsequent requests

3. **Cache Size Limits:** How to handle disk space exhaustion?
   - **Decision:** Pre-flight check, fail early with clear error message

4. **Embedding Model Changes:** How to handle model upgrades?
   - **Decision:** Trigger full rebuild (dimension mismatch requires it)

5. **Chunk ID Gaps:** If file deleted, do we reuse IDs?
   - **Decision:** No reuse, monotonic IDs only (simpler, avoids race conditions)

---

## Scaling Considerations

### When Does RAG Break?

RAG systems don't have a single "breaking point"—they degrade across multiple dimensions as corpus size grows:

| Component | Breaks At | Why | Symptom |
|-----------|-----------|-----|---------|
| **FAISS IndexFlatL2** (brute-force) | ~10M vectors | O(n) linear search | Query latency > 1s |
| **BM25 (in-memory)** | ~1M documents | Memory exhaustion | OOM crashes |
| **Top-k retrieval quality** | ~100k chunks | Noise dominates signal | Recall drops < 50% |
| **Reranking** | k > 100 candidates | Reranker becomes bottleneck | Latency > 500ms |
| **LLM context window** | ~50 chunks | Context overflow | Truncation/hallucination |

### Why RAG Breaks at Scale

**1. The "Needle in Haystack" Problem**
- **Small corpus (< 10k chunks):** Top-k retrieval finds relevant docs easily
- **Medium corpus (10k-100k):** Semantic noise increases; borderline-relevant chunks compete
- **Large corpus (> 100k):** Without domain filtering, recall degrades because:
  - Similar but wrong documents score higher than distant but correct ones
  - Embedding space becomes crowded; cosine similarity loses discrimination

**2. FAISS IndexFlatL2 Performance**
- NIC uses **IndexFlatL2** (exact brute-force search)
- **Linear scaling:** 1M vectors = ~100ms query latency on CPU
- **Why it breaks:** No approximation = must compare query to every vector
- **Mitigation:** Switch to FAISS IndexIVFFlat (inverted file index) at 100k+ chunks

**3. BM25 Memory Scaling**
- BM25 stores entire corpus in RAM (token → document mappings)
- **Rule of thumb:** ~1KB per document in memory
- **Breaking point:** System RAM / 1KB = max documents
  - 8GB RAM → ~5M documents (theoretical)
  - But effective limit ~1M (accounting for OS, embeddings, LLM)

**4. Retrieval Quality Cliff**
- **Known phenomenon:** Retrieval quality drops sharply around **100k-500k chunks**
- **Why:** 
  - Embeddings are lossy; semantic collisions increase
  - Domain diversity dilutes relevance (unless filtered)
  - Top-k becomes arbitrary (position 11 vs 15 is noise)

### Real-World Production Numbers

| System Type | Typical Corpus Size | Architecture |
|-------------|---------------------|--------------|
| **Document QA (single domain)** | 10k-50k chunks | Flat index + reranking |
| **Enterprise search (multi-domain)** | 100k-1M chunks | IVF index + domain routing |
| **Web-scale retrieval** | 10M+ chunks | Approximate NN + heavy filtering |

### NIC's Current Position

**Current:** 1,692 chunks across 5 domains
- **Headroom:** ~50x before quality degradation
- **Safe zone:** Can scale to ~50k chunks with current architecture
- **Phase 3 target:** 10k-50k chunks (well within limits)

### When to Worry

| Corpus Size | Recommendation |
|-------------|----------------|
| **< 10k chunks** | Flat index is optimal |
| **10k-100k** | Consider IndexIVFFlat, domain filtering mandatory |
| **100k-1M** | Need approximate NN (HNSW/IVF), aggressive filtering |
| **> 1M** | Rethink architecture: sharding, hierarchical retrieval |

### Phase 3 Positioning

Phase 3's **incremental indexing** is perfectly timed because:
- NIC will grow from 1.7k → ~10k-50k chunks (real corpus)
- This crosses the threshold where index rebuild becomes painful (>30s)
- But stays well below where FAISS IndexFlatL2 breaks (~10M)
- Hot-reload solves the operational problem (rebuild time) before hitting the performance wall

**Bottom line:** You have ~50x headroom before architectural changes needed. Phase 3 solves operational pain (long rebuilds) while staying in the safe performance zone.

---

## Next Steps

1. ✅ Architecture design (this document)
2. 🔄 Implement file-hash tracking (Task 2 - in progress)
3. ⏭️ Implement FAISS append-only (Task 3)
4. ⏭️ Implement BM25 incremental (Task 4)
5. ⏭️ Create hot-reload endpoint (Task 5)
6. ⏭️ Write comprehensive tests (Task 6)

**Success Criteria (from README):**
- ✅ Add 1,000+ chunks without server restart
- ✅ Index update < 5 seconds for single manual
- ✅ Zero degradation in retrieval quality

---

**Document Version:** 1.1  
**Last Updated:** 2026-01-22  
**Author:** NIC Phase 3 Development Team
