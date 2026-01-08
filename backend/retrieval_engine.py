"""
Retrieval engine for NovaRAG - handles all document retrieval logic.
Includes FAISS vector search, BM25 lexical search, and hybrid retrieval.
"""

from __future__ import annotations

from pathlib import Path
import json
import os
import re
from collections import defaultdict
from math import log
import hashlib

import faiss

# Import secure pickle if available
try:
    from secure_cache import secure_pickle_dump, secure_pickle_load
    SECURE_CACHE_AVAILABLE = True
except ImportError:
    import pickle
    SECURE_CACHE_AVAILABLE = False

# Glossary Augmented Retrieval (GAR)
try:
    from glossary_gar import expand_query as gar_expand_query
    GAR_ENABLED = os.environ.get("NOVA_GAR_ENABLED", "1") == "1"
except ImportError:
    gar_expand_query = None
    GAR_ENABLED = False


# =======================
# PATHS & CONFIG
# =======================

BASE_DIR = Path(__file__).parent.parent.resolve()
DOCS_DIR = BASE_DIR / "data"
INDEX_DIR = BASE_DIR / "vector_db"
INDEX_DIR.mkdir(parents=True, exist_ok=True)

INDEX_PATH = INDEX_DIR / "vehicle_index.faiss"
DOCS_PATH = INDEX_DIR / "vehicle_docs.jsonl"

# Disable text embeddings entirely (forces lexical fallback)
DISABLE_EMBED = os.environ.get("NOVA_DISABLE_EMBED", "0") == "1"

# Enable hybrid search (vector + lexical BM25)
HYBRID_SEARCH_ENABLED = os.environ.get("NOVA_HYBRID_SEARCH", "1") == "1"

# Embedding batch size (for index build); tune via env if needed
EMBED_BATCH_SIZE = int(os.environ.get("NOVA_EMBED_BATCH_SIZE", "32"))

# Disable cross-encoder reranker (heavy) entirely
DISABLE_CROSS_ENCODER = os.environ.get("NOVA_DISABLE_CROSS_ENCODER", "0") == "1"


# =======================
# TEXT UTILS
# =======================

def split_text_semantic(text: str, chunk_size: int = 800, overlap: int = 200) -> list[str]:
    """Split text with semantic awareness - respecting paragraphs and sentences."""
    paragraphs = re.split(r'\n\s*\n', text)
    
    chunks = []
    current_chunk = ""
    
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        
        if len(current_chunk) + len(para) + 2 <= chunk_size:
            current_chunk += ("\n\n" if current_chunk else "") + para
        else:
            if current_chunk:
                chunks.append(current_chunk)
            
            if len(para) > chunk_size:
                sentences = re.split(r'(?<=[.!?])\s+', para)
                temp_chunk = ""
                for sent in sentences:
                    if len(temp_chunk) + len(sent) + 1 <= chunk_size:
                        temp_chunk += (" " if temp_chunk else "") + sent
                    else:
                        if temp_chunk:
                            chunks.append(temp_chunk)
                        temp_chunk = sent
                current_chunk = temp_chunk
            else:
                current_chunk = para
    
    if current_chunk:
        chunks.append(current_chunk)
    
    if overlap > 0 and len(chunks) > 1:
        overlapped_chunks = [chunks[0]]
        for i in range(1, len(chunks)):
            prev_chunk = chunks[i-1]
            curr_chunk = chunks[i]
            overlap_text = prev_chunk[-overlap:] if len(prev_chunk) > overlap else prev_chunk
            overlapped_chunks.append(overlap_text + "\n" + curr_chunk)
        return overlapped_chunks
    
    return chunks


def split_text(text: str, chunk_size: int = 800, overlap: int = 200) -> list[str]:
    """Fallback to semantic chunking."""
    return split_text_semantic(text, chunk_size, overlap)


def load_pdf_text_with_pages(pdf_path: Path) -> list[tuple[str, int]]:
    """Load PDF and return list of (text, page_number) tuples."""
    from pypdf import PdfReader
    reader = PdfReader(str(pdf_path))
    pages_data = []

    for i, page in enumerate(reader.pages):
        try:
            txt = page.extract_text() or ""
        except Exception as e:
            print(f"[!] Error reading page {i} from {pdf_path.name}: {e}")
            txt = ""
        pages_data.append((txt, i + 1))

    return pages_data


def load_pdf_text(pdf_path: Path) -> str:
    """Legacy function for compatibility."""
    pages_data = load_pdf_text_with_pages(pdf_path)
    return "\n".join(text for text, _ in pages_data)


# =======================
# FAISS INDEX
# =======================

def build_index():
    """Build FAISS index from PDFs in DOCS_DIR."""
    pdfs = sorted(DOCS_DIR.glob("*.pdf"))
    if not pdfs:
        raise RuntimeError(f"No PDFs found in {DOCS_DIR}")

    print(f"[NovaRAG] Building index from {len(pdfs)} PDFs...")

    all_chunks = []
    texts = []

    for pdf_path in pdfs:
        print(f" - Reading {pdf_path.name}")
        pages_data = load_pdf_text_with_pages(pdf_path)

        if not pages_data:
            print(f"   [!] {pdf_path.name} returned empty text.")
            continue

        for page_text, page_num in pages_data:
            if not page_text.strip():
                continue
            
            chunks = split_text(page_text)
            
            for i, chunk in enumerate(chunks):
                doc = {
                    "id": f"{pdf_path.name}_p{page_num}_chunk_{i}",
                    "source": pdf_path.name,
                    "page": page_num,
                    "text": chunk,
                    "snippet": chunk[:200]
                }
                all_chunks.append(doc)
                texts.append(chunk)

    print(f"[NovaRAG] Generating embeddings for {len(all_chunks)} chunks...")
    # Import lazily to avoid circular dependency at module load time
    import backend as backend_module
    text_model = backend_module.get_text_embed_model()
    if text_model is None:
        raise RuntimeError("Text embedding model not available. Cannot build index.")
    embeddings = text_model.encode(
        texts,
        convert_to_numpy=True,
        show_progress_bar=True,
        batch_size=max(1, EMBED_BATCH_SIZE)
    )

    dim = embeddings.shape[1]
    index = faiss.IndexFlatL2(dim)
    index.add(embeddings)  # type: ignore[call-arg]

    faiss.write_index(index, str(INDEX_PATH))

    with DOCS_PATH.open("w", encoding="utf-8") as f:
        for doc in all_chunks:
            f.write(json.dumps(doc, ensure_ascii=False) + "\n")

    print("[NovaRAG] Index built successfully.\n")
    return index, all_chunks


def load_index():
    """Load or build FAISS index."""
    if INDEX_PATH.exists() and DOCS_PATH.exists():
        print("[NovaRAG] Loading existing index...")
        index = faiss.read_index(str(INDEX_PATH))

        docs = []
        with DOCS_PATH.open("r", encoding="utf-8") as f:
            for line in f:
                docs.append(json.loads(line))
        print(f"[NovaRAG] Loaded {index.ntotal} vectors.\n")
        return index, docs

    print("[NovaRAG] No index found, building a new one...\n")
    return build_index()


# =======================
# ERROR CODE TABLE LOOKUP (Lexical Fallback)
# =======================

# Map error code -> list of doc dicts that appear to contain that code's table entry.
# This is computed once at startup from the PDF-extracted chunks and used to
# augment embedding retrieval for diagnostic queries.
ERROR_CODE_TO_DOCS: dict[str, list[dict]] = defaultdict(list)

_ERROR_CODE_LINE_RE = re.compile(
    r"(?m)^\s*(\d{2,3})\s+[A-Z][A-Z0-9/()\-+\s]{3,120}$"
)

def _init_error_code_index(docs: list[dict]) -> None:
    """Initialize error code index from document chunks."""
    try:
        for d in docs:
            t = d.get("text") or ""
            if not t:
                continue
            tl = t.lower()
            # Heuristic: only scan chunks that look like error code tables / diagnostic codes.
            if ("error" not in tl) and ("code" not in tl) and ("diagnostic" not in tl):
                continue
            for m in _ERROR_CODE_LINE_RE.finditer(t):
                code = m.group(1)
                # Avoid flooding the map with random section numbers by requiring the
                # chunk to mention diagnostic terminology somewhere.
                if "error" not in tl and "code" not in tl:
                    continue
                ERROR_CODE_TO_DOCS[code].append(d)
        if ERROR_CODE_TO_DOCS:
            print(f"[NovaRAG] Error-code index ready: {len(ERROR_CODE_TO_DOCS)} codes")
        else:
            print("[NovaRAG] Error-code index ready: 0 codes (no diagnostic tables detected)")
    except Exception as e:
        print(f"[NovaRAG] Error-code index init failed: {e}")


# =======================
# BM25 LEXICAL INDEX (Hybrid)
# =======================

_BM25_INDEX: dict[str, dict[int, int]] = {}
_BM25_DOC_LEN: list[int] = []
_BM25_AVGDL: float = 0.0
_BM25_READY: bool = False
_BM25_K1: float = float(os.environ.get("NOVA_BM25_K1", "1.5"))
_BM25_B: float = float(os.environ.get("NOVA_BM25_B", "0.75"))

# BM25 disk cache (enabled by default; set NOVA_BM25_CACHE=0 to disable)
BM25_CACHE_ENABLED = os.environ.get("NOVA_BM25_CACHE", "1") == "1"
BM25_CACHE_PATH = INDEX_DIR / "bm25_index.pkl"
BM25_CORPUS_HASH_PATH = INDEX_DIR / "bm25_corpus_hash.txt"

def _tokenize(text: str) -> list[str]:
    return [t for t in re.split(r"\W+", (text or "").lower()) if t]

def _compute_corpus_hash(docs: list[dict]) -> str:
    """Compute a hash of the corpus to detect changes."""
    hasher = hashlib.sha256()
    for d in docs:
        hasher.update(d.get("text", "").encode("utf-8"))
    return hasher.hexdigest()[:16]

def _save_bm25_index():
    """Save BM25 index and corpus hash to disk."""
    if not BM25_CACHE_ENABLED:
        return
    try:
        data = {
            "index": _BM25_INDEX,
            "doc_len": _BM25_DOC_LEN,
            "avgdl": _BM25_AVGDL,
            "k1": _BM25_K1,
            "b": _BM25_B,
        }
        if SECURE_CACHE_AVAILABLE:
            secure_pickle_dump(data, BM25_CACHE_PATH)
        else:
            import pickle
            with BM25_CACHE_PATH.open("wb") as f:
                pickle.dump(data, f)
        # Save corpus hash (will be set by caller)
        print(f"[NovaRAG] BM25 index cached to {BM25_CACHE_PATH}")
    except Exception as e:
        print(f"[NovaRAG] Failed to save BM25 cache: {e}")

def _load_bm25_index(docs: list[dict]) -> bool:
    """Load BM25 index from disk if valid; return True if loaded."""
    global _BM25_INDEX, _BM25_DOC_LEN, _BM25_AVGDL, _BM25_READY
    if not BM25_CACHE_ENABLED or not BM25_CACHE_PATH.exists() or not BM25_CORPUS_HASH_PATH.exists():
        return False
    try:
        # Check corpus hash
        saved_hash = BM25_CORPUS_HASH_PATH.read_text(encoding="utf-8").strip()
        current_hash = _compute_corpus_hash(docs)
        if saved_hash != current_hash:
            print(f"[NovaRAG] BM25 cache invalid (corpus changed); rebuilding...")
            return False
        # Load index
        if SECURE_CACHE_AVAILABLE:
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

def _build_bm25_index(docs: list[dict]):
    """Build BM25 index from document chunks."""
    global _BM25_INDEX, _BM25_DOC_LEN, _BM25_AVGDL, _BM25_READY
    # Try loading from cache first
    if _load_bm25_index(docs):
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
        # Save corpus hash
        corpus_hash = _compute_corpus_hash(docs)
        BM25_CORPUS_HASH_PATH.write_text(corpus_hash, encoding="utf-8")
    except Exception as e:
        _BM25_READY = False
        print(f"[NovaRAG] BM25 index build failed: {e}")

def _bm25_idf(term: str) -> float:
    N = len(_BM25_DOC_LEN)
    df = len(_BM25_INDEX.get(term, {}))
    # Robertson-Sparck Jones IDF
    return log(((N - df + 0.5) / (df + 0.5)) + 1.0) if N and df else 0.0

def bm25_retrieve(query: str, k: int = 12, top_n: int = 6, docs: list[dict] | None = None) -> list[dict]:
    """BM25 lexical retrieval over chunked docs."""
    if docs is None:
        # Import lazily to avoid circular dependency
        import backend as backend_module
        docs = backend_module.docs
    
    if not _BM25_READY:
        _build_bm25_index(docs)
    if not _BM25_READY:
        return []
    q_terms = _tokenize(query)
    scores: dict[int, float] = {}
    for qt in q_terms:
        idf = _bm25_idf(qt)
        for doc_id, tf in _BM25_INDEX.get(qt, {}).items():
            doc_len = _BM25_DOC_LEN[doc_id]
            numerator = tf * (_BM25_K1 + 1.0)
            denominator = tf + _BM25_K1 * (1.0 - _BM25_B + _BM25_B * (doc_len / max(_BM25_AVGDL, 1.0)))
            scores[doc_id] = scores.get(doc_id, 0.0) + idf * (numerator / denominator)
    
    top = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:k]
    results = []
    for doc_id, score in top[:top_n]:
        d = dict(docs[doc_id])
        d["confidence"] = min(0.99, score / max(1.0, max(scores.values()) if scores else 1.0))
        results.append(d)
    return results


def lexical_retrieve(query: str, k: int = 12, top_n: int = 6, docs: list[dict] | None = None) -> list[dict]:
    """Simple term-matching fallback when embedding model unavailable."""
    if docs is None:
        # Import lazily to avoid circular dependency
        import backend as backend_module
        docs = backend_module.docs
    
    q_terms = set(_tokenize(query))
    if not q_terms:
        return []
    
    doc_scores = []
    for i, d in enumerate(docs):
        d_tokens = set(_tokenize(d.get("text", "")))
        overlap = len(q_terms & d_tokens)
        if overlap > 0:
            doc_scores.append((i, overlap))
    
    doc_scores.sort(key=lambda x: x[1], reverse=True)
    top = doc_scores[:top_n]
    
    results = []
    max_score = max((score for _, score in top), default=1)
    for doc_id, score in top:
        d = dict(docs[doc_id])
        d["confidence"] = min(0.99, score / max_score)
        results.append(d)
    return results


def retrieve(
    query: str, 
    k: int = 12, 
    top_n: int = 6, 
    lambda_diversity: float = 0.5, 
    use_reranker: bool = True, 
    use_sklearn_reranker: bool | None = None,
    use_gar: bool = True,
    index=None,
    docs: list[dict] | None = None,
    text_embed_model=None,
    cross_encoder=None,
    sklearn_reranker=None
) -> list[dict]:
    """
    Main retrieval function supporting hybrid search (vector + BM25).
    
    Args:
        query: Search query
        k: Number of candidates to retrieve
        top_n: Number of results to return after reranking
        lambda_diversity: Diversity parameter (0 = pure relevance, 1 = pure diversity)
        use_reranker: Whether to use cross-encoder reranking
        use_sklearn_reranker: Whether to use sklearn reranker (None = auto-detect)
        use_gar: Whether to use Glossary Augmented Retrieval
        index: FAISS index (will use global if not provided)
        docs: Document chunks (will use global if not provided)
        text_embed_model: Embedding model (will use global if not provided)
        cross_encoder: Cross-encoder model (will use global if not provided)
        sklearn_reranker: Sklearn reranker model (will use global if not provided)
    """
    # Import lazily to avoid circular dependency
    import backend as backend_module
    
    if docs is None:
        docs = backend_module.docs
    if index is None:
        index = backend_module.index
    if text_embed_model is None:
        text_embed_model = backend_module.get_text_embed_model()
    if cross_encoder is None and use_reranker:
        cross_encoder = backend_module.get_cross_encoder()
    if sklearn_reranker is None and use_sklearn_reranker:
        sklearn_reranker = backend_module.sklearn_reranker
    
    # GAR query expansion
    expanded_query = query
    if use_gar and GAR_ENABLED and gar_expand_query:
        try:
            expanded_query = gar_expand_query(query)
            if expanded_query != query:
                print(f"[GAR] Expanded query: {query[:50]}... → {expanded_query[:50]}...")
        except Exception as e:
            print(f"[GAR] Query expansion failed: {e}")
            expanded_query = query
    
    # === VECTOR RETRIEVAL ===
    vector_results = []
    if text_embed_model is not None and not DISABLE_EMBED:
        try:
            q_emb = text_embed_model.encode([expanded_query], convert_to_numpy=True)
            distances, indices = index.search(q_emb, k)  # type: ignore[call-arg]
            
            for i, dist in zip(indices[0], distances[0]):
                if i == -1:
                    continue
                d = dict(docs[i])
                # L2 distance -> confidence heuristic
                d["confidence"] = max(0.0, min(0.99, 1.0 - (dist / 10.0)))
                vector_results.append(d)
        except Exception as e:
            print(f"[NovaRAG] Vector retrieval failed: {e}")
            vector_results = []
    
    # === LEXICAL RETRIEVAL (BM25 or fallback) ===
    lexical_results = []
    if HYBRID_SEARCH_ENABLED:
        try:
            lexical_results = bm25_retrieve(query, k=k, top_n=top_n, docs=docs)
        except Exception as e:
            print(f"[NovaRAG] BM25 retrieval failed: {e}")
            lexical_results = []
    
    # === FALLBACK: If vector failed, use lexical-only ===
    if not vector_results and not lexical_results:
        print("[NovaRAG] Both vector and BM25 failed; using simple lexical fallback")
        return lexical_retrieve(query, k=k, top_n=top_n, docs=docs)
    
    # === MERGE VECTOR + LEXICAL (Hybrid) ===
    if vector_results and lexical_results:
        # Deduplicate by (source, page, text snippet)
        seen = set()
        merged = []
        for d in vector_results + lexical_results:
            key = (d.get("source"), d.get("page"), (d.get("text") or "")[:100])
            if key not in seen:
                seen.add(key)
                merged.append(d)
        candidates = merged[:k]
    else:
        candidates = vector_results or lexical_results
    
    # === RERANKING ===
    if use_reranker and len(candidates) > 1:
        # Auto-detect sklearn reranker if not explicitly set
        if use_sklearn_reranker is None:
            import backend as backend_module
            use_sklearn_reranker = backend_module.USE_SKLEARN_RERANKER
        
        if use_sklearn_reranker and sklearn_reranker is not None:
            # Sklearn reranker path
            try:
                pairs = [[query, d.get("text", "")] for d in candidates]
                sklearn_scores = sklearn_reranker.predict_proba(pairs)[:, 1]
                for d, score in zip(candidates, sklearn_scores):
                    d["rerank_score"] = float(score)
                candidates.sort(key=lambda x: x.get("rerank_score", 0.0), reverse=True)
            except Exception as e:
                print(f"[NovaRAG] Sklearn reranking failed: {e}")
        elif cross_encoder is not None:
            # Cross-encoder reranker path
            try:
                pairs = [[query, d.get("text", "")] for d in candidates]
                scores = cross_encoder.predict(pairs)
                for d, score in zip(candidates, scores):
                    d["rerank_score"] = float(score)
                candidates.sort(key=lambda x: x.get("rerank_score", 0.0), reverse=True)
            except Exception as e:
                print(f"[NovaRAG] Cross-encoder reranking failed: {e}")
    
    return candidates[:top_n]


def detect_error_code(query: str) -> dict:
    """Detect error code queries and return metadata if found."""
    q = query.lower()
    # Match patterns like "code P0171" or "error P0171"
    m = re.search(r"\b(code|error|dtc)\s*[:#-]?\s*([A-Z]?\d{2,5})\b", q, re.IGNORECASE)
    if m:
        return {"error_id": m.group(2).upper(), "term": m.group(0)}
    # Match reversed pattern like "P0171 code"
    m_rev = re.search(r"\b([A-Z]?\d{2,5})\s*(code|error|dtc)\b", q, re.IGNORECASE)
    if m_rev:
        return {"error_id": m_rev.group(1).upper(), "term": m_rev.group(0)}
    return {}


def _boost_error_docs(query: str, context_docs: list[dict]) -> list[dict]:
    """Augment + re-rank retrieved docs to prefer exact error code mentions.

    1) Inject likely error code table chunks for the detected code (lexical fallback).
    2) Re-rank results so diagnostic code pages outrank generic summaries.
    """
    error_meta = detect_error_code(query)
    if not error_meta or not context_docs:
        return context_docs
    eid = error_meta.get("error_id")
    if not eid:
        return context_docs

    # 1) Inject alarm-table matches (if available) so strict citation can succeed even
    # when embedding search returns generic pages.
    injected: list[dict] = []

    # Include adjacent error code table entries when available.
    neighbor_ids: list[str] = [str(eid)]
    try:
        eid_int = int(str(eid).lstrip('P'))  # Handle codes like P0171
        neighbor_ids = [str(eid_int - 1), str(eid_int), str(eid_int + 1)]
    except Exception:
        pass

    for nid in neighbor_ids:
        for d in ERROR_CODE_TO_DOCS.get(nid, []):
            dd = dict(d)
            # Treat an exact error code table hit as high-confidence context.
            dd.setdefault("confidence", 0.95)
            injected.append(dd)

    if injected:
        # Prefer entries that also mention key query terms.
        ql = query.lower()
        def inj_score(doc: dict) -> float:
            t = (doc.get("text") or "").lower()
            s = 0.0
            s += 2.0 if re.search(rf"(?m)^\s*{re.escape(str(eid))}\s+", doc.get("text") or "") else 0.0
            # Add relevance scoring based on common diagnostic terms
            if "diagnostic" in ql:
                s += 2.0 if "diagnostic" in t else 0.0
            if "symptom" in ql:
                s += 1.0 if "symptom" in t else 0.0
            return s

        injected.sort(key=inj_score, reverse=True)

        # Merge (dedupe by id/source/page/text tuple) and keep injected first.
        seen: set[tuple] = set()
        merged: list[dict] = []
        for d in injected + context_docs:
            key = (
                d.get("id"),
                d.get("source"),
                d.get("page"),
                (d.get("text") or d.get("snippet") or "")[:200],
            )
            if key in seen:
                continue
            seen.add(key)
            merged.append(d)
        context_docs = merged

    key_terms = [f"code {eid}", f"error {eid}", str(eid)]

    def score(doc: dict) -> float:
        t = ((doc.get("text") or doc.get("snippet") or "") + " " + (doc.get("source") or "")).lower()
        hit = 1.0 if any(term in t for term in key_terms) else 0.0
        return hit + float(doc.get("confidence", 0.0))

    return sorted(context_docs, key=score, reverse=True)
