"""
Retrieval engine for NovaRAG.
Handles index management, embeddings, lexical/BM25 hybrid retrieval,
reranking, and vision search utilities.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Tuple

import faiss
import torch
from joblib import load as joblib_load

from core.utils.text_processing import (
    load_pdf_text_with_pages,
    split_text,
)

# Import secure pickle if available (used for BM25 cache)
try:
    from secure_cache import secure_pickle_dump, secure_pickle_load

    SECURE_CACHE_AVAILABLE = True
except ImportError:  # pragma: no cover - fallback when secure_cache is missing
    import pickle  # type: ignore

    SECURE_CACHE_AVAILABLE = False
    
    # Provide stub functions for type checker
    def secure_pickle_dump(obj, filepath):
        with open(filepath, 'wb') as f:
            pickle.dump(obj, f)
    
    def secure_pickle_load(filepath):
        with open(filepath, 'rb') as f:
            return pickle.load(f)

# Optional GAR expansion
try:
    from glossary_gar import expand_query as gar_expand_query

    GAR_ENABLED = os.environ.get("NOVA_GAR_ENABLED", "1") == "1"
    print(f"[NovaRAG] Glossary Augmented Retrieval (GAR): {'enabled' if GAR_ENABLED else 'disabled'}")
except ImportError:
    gar_expand_query = None
    GAR_ENABLED = False
    print("[NovaRAG] GAR module not found, query expansion disabled")

# =======================
# PATHS / ENV
# =======================

BASE_DIR = Path(__file__).resolve().parents[2]
DOCS_DIR = BASE_DIR / "data"
INDEX_DIR = BASE_DIR / "vector_db"
INDEX_DIR.mkdir(parents=True, exist_ok=True)

INDEX_PATH = INDEX_DIR / "vehicle_index.faiss"
DOCS_PATH = INDEX_DIR / "vehicle_docs.jsonl"
SEARCH_HISTORY_PATH = INDEX_DIR / "search_history.pkl"
FAVORITES_PATH = INDEX_DIR / "favorites.json"

VISION_EMB_PATH = INDEX_DIR / "vehicle_vision_embeddings.pt"
DISABLE_VISION = os.environ.get("NOVA_DISABLE_VISION", "0") == "1"
DISABLE_EMBED = os.environ.get("NOVA_DISABLE_EMBED", "0") == "1"

FORCE_OFFLINE = os.environ.get("NOVA_FORCE_OFFLINE", "0") == "1"
if FORCE_OFFLINE:
    print("[NovaRAG] FORCE OFFLINE MODE: All network operations disabled")
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"

DISABLE_CROSS_ENCODER = os.environ.get("NOVA_DISABLE_CROSS_ENCODER", "0") == "1"
HYBRID_SEARCH_ENABLED = os.environ.get("NOVA_HYBRID_SEARCH", "1") == "1"
EMBED_BATCH_SIZE = int(os.environ.get("NOVA_EMBED_BATCH_SIZE", "32"))

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

# =======================
# MODELS / EMBEDDINGS
# =======================

print("[NovaRAG] Text embedding model will load lazily when needed...")
text_embed_model = None
text_embed_model_error: str | None = None


def get_text_embed_model():
    """Load text embedding model, preferring local path to avoid downloads."""
    global text_embed_model, text_embed_model_error
    if DISABLE_EMBED:
        print("[NovaRAG] Embeddings disabled via NOVA_DISABLE_EMBED=1; using lexical fallback.")
        return None
    if text_embed_model is not None:
        return text_embed_model
    try:
        from sentence_transformers import SentenceTransformer

        local_path = BASE_DIR / "models" / "all-MiniLM-L6-v2"
        print(f"[NovaRAG] Loading text embedding model from {local_path}...")

        if local_path.exists():
            print("[NovaRAG]    Found local model, loading (local_files_only=True)...")
            text_embed_model = SentenceTransformer(str(local_path), local_files_only=True)
            print("[NovaRAG]    Local embedding model loaded")
        elif FORCE_OFFLINE:
            print(f"[NovaRAG]    ERROR: Offline mode enabled but local model not found at {local_path}")
            print("[NovaRAG]    Cannot download models in offline mode. Please download manually.")
            text_embed_model_error = "Offline mode - no local model available"
            return None
        else:
            print(f"[NovaRAG]    Local model not found at {local_path}")
            print("[NovaRAG]   Attempting to download from HuggingFace (this may hang)...")
            text_embed_model = SentenceTransformer("all-MiniLM-L6-v2")
            print("[NovaRAG]    Downloaded embedding model")
        return text_embed_model
    except Exception as e:  # pragma: no cover - handled at runtime
        text_embed_model_error = str(e)
        print(f"[NovaRAG] ERROR: Failed to load text embedding model: {e}")
        return None


print("[NovaRAG] Cross-encoder reranker will load lazily when needed...")
cross_encoder = None


def get_cross_encoder():
    global cross_encoder
    if DISABLE_CROSS_ENCODER:
        print("[NovaRAG] Cross-encoder disabled via NOVA_DISABLE_CROSS_ENCODER=1")
        return None
    if cross_encoder is None:
        from sentence_transformers import CrossEncoder

        print("[NovaRAG] Loading cross-encoder for reranking...")
        cross_encoder = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
    return cross_encoder


if not DISABLE_VISION:
    print("[NovaRAG Vision] Vision model will load lazily when needed...")
else:
    print("[NovaRAG Vision] Disabled via NOVA_DISABLE_VISION=1")
vision_model = None
vision_embeddings = None
vision_paths = None


def ensure_vision_loaded():
    """Lazy-load CLIP vision model and embeddings when first needed."""
    global vision_model, vision_embeddings, vision_paths
    if DISABLE_VISION:
        return None, None, None
    if vision_model is None:
        from sentence_transformers import SentenceTransformer

        device = "cuda" if torch.cuda.is_available() else "cpu"
        print("[NovaRAG Vision] Loading CLIP model...")
        vision_model = SentenceTransformer("clip-ViT-B-32").to(device)
        if VISION_EMB_PATH.exists():
            print(f"[NovaRAG Vision] Loading vision embeddings from {VISION_EMB_PATH}...")
            v_data = torch.load(VISION_EMB_PATH, map_location=device)
            vision_embeddings = torch.nn.functional.normalize(v_data["embeddings"], p=2, dim=1)
            vision_paths = v_data["paths"]
        else:
            print("[NovaRAG Vision] WARNING: Vision embeddings file not found.")
            vision_embeddings = None
            vision_paths = None
    return vision_model, vision_embeddings, vision_paths


# =======================
# SKLEARN RERANKER (Optional)
# =======================

SKLEARN_MODEL_PATH = BASE_DIR / "models" / "sklearn_reranker.pkl"
sklearn_reranker = None
try:
    if SKLEARN_MODEL_PATH.exists():
        print(f"[NovaRAG] Loading sklearn reranker from {SKLEARN_MODEL_PATH}...")
        sklearn_reranker = joblib_load(str(SKLEARN_MODEL_PATH))
        print("[NovaRAG] Sklearn reranker loaded.")
    else:
        print("[NovaRAG] Sklearn reranker not found; using cross-encoder.")
except Exception as e:  # pragma: no cover - runtime logging
    print(f"[NovaRAG] Failed to load sklearn reranker: {e}")

USE_SKLEARN_RERANKER = bool(os.environ.get("NOVA_USE_SKLEARN_RERANKER", "1") == "1") and (
    sklearn_reranker is not None
)

SKLEARN_VISION_MODEL_PATH = BASE_DIR / "models" / "sklearn_reranker_vision_aware.pkl"
sklearn_vision_reranker = None
try:
    if SKLEARN_VISION_MODEL_PATH.exists():
        print(f"[NovaRAG] Loading vision-aware sklearn reranker from {SKLEARN_VISION_MODEL_PATH}...")
        sklearn_vision_reranker = joblib_load(str(SKLEARN_VISION_MODEL_PATH))
        print("[NovaRAG] Vision-aware reranker loaded.")
    else:
        print("[NovaRAG] Vision-aware reranker not found; text-only reranker active.")
except Exception:
    print("[NovaRAG] Vision-aware reranker not available: Using text-only reranker.")

USE_VISION_AWARE_RERANKER = (
    bool(os.environ.get("NOVA_USE_VISION_AWARE_RERANKER", "1") == "1")
    and (sklearn_vision_reranker is not None)
    and (not DISABLE_VISION)
)

# =======================
# TF-IDF CACHE (vision reranker)
# =======================

from sklearn.feature_extraction.text import TfidfVectorizer


tfidf_vectorizer = None
tfidf_vectorizer_fitted = False


def init_tfidf_vectorizer():
    """Initialize TF-IDF vectorizer on full document corpus at startup."""
    global tfidf_vectorizer, tfidf_vectorizer_fitted

    if tfidf_vectorizer_fitted or not USE_VISION_AWARE_RERANKER:
        return

    try:
        import numpy as np

        if not DOCS_PATH.exists():
            print("[NovaRAG] TF-IDF: Docs file not found, skipping cache init")
            return

        all_texts: list[str] = []
        with DOCS_PATH.open("r", encoding="utf-8") as f:
            for line in f:
                try:
                    doc = json.loads(line)
                    all_texts.append(doc.get("text", ""))
                except Exception:
                    pass

        if not all_texts:
            print("[NovaRAG] TF-IDF: No documents found")
            return

        print(f"[NovaRAG] Fitting TF-IDF vectorizer on {len(all_texts)} documents...")
        tfidf_vectorizer = TfidfVectorizer(
            max_features=500,
            ngram_range=(1, 2),
            sublinear_tf=True,
            min_df=1,
            max_df=0.95,
        )
        tfidf_vectorizer.fit(all_texts)
        tfidf_vectorizer_fitted = True
        print(f"[NovaRAG] TF-IDF cache ready! ({len(tfidf_vectorizer.vocabulary_)} features)")
    except Exception as e:  # pragma: no cover
        print(f"[NovaRAG] TF-IDF cache init failed: {e}")
        tfidf_vectorizer = None
        tfidf_vectorizer_fitted = False


# =======================
# INDEX MANAGEMENT
# =======================


def _fallback_docs() -> list[dict]:
    """Provide lightweight docs so tests and offline runs don't crash.

    Prefer the plain-text vehicle manual if available; otherwise emit a small
    generic maintenance stub covering common queries used in tests.
    """
    docs: list[dict] = []

    manual_path = DOCS_DIR / "vehicle_manual.txt"
    if manual_path.exists():
        try:
            text = manual_path.read_text(encoding="utf-8", errors="ignore")
            for i, chunk in enumerate(split_text(text)):
                docs.append(
                    {
                        "id": f"{manual_path.name}_chunk_{i}",
                        "source": manual_path.name,
                        "page": None,
                        "text": chunk,
                        "snippet": chunk[:200],
                    }
                )
        except Exception as e:
            print(f"[NovaRAG] Fallback manual load failed: {e}")

    if not docs:
        stub = (
            "General vehicle maintenance guidance: oil change every 5000 miles or 6 months, "
            "check tire pressure monthly (32-35 psi typical), address diagnostic codes promptly, "
            "and follow manufacturer safety procedures."
        )
        docs.append(
            {
                "id": "fallback_stub_0",
                "source": "fallback_manual.txt",
                "page": 1,
                "text": stub,
                "snippet": stub[:200],
            }
        )

    return docs


def build_index():
    pdfs = sorted(DOCS_DIR.glob("*.pdf"))
    if not pdfs:
        print(f"[NovaRAG] No PDFs found in {DOCS_DIR}; using fallback docs and lexical/BM25 only.")
        fallback = _fallback_docs()
        with DOCS_PATH.open("w", encoding="utf-8") as f:
            for doc in fallback:
                f.write(json.dumps(doc, ensure_ascii=False) + "\n")
        # No FAISS index in fallback mode; retrieval will use lexical/BM25 paths.
        return None, fallback

    print(f"[NovaRAG] Building index from {len(pdfs)} PDFs...")

    all_chunks = []
    texts: list[str] = []

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
                    "snippet": chunk[:200],
                }
                all_chunks.append(doc)
                texts.append(chunk)

    print(f"[NovaRAG] Generating embeddings for {len(all_chunks)} chunks...")
    text_model = get_text_embed_model()
    if text_model is None:
        raise RuntimeError("Text embedding model not available. Cannot build index.")
    embeddings = text_model.encode(
        texts,
        convert_to_numpy=True,
        show_progress_bar=True,
        batch_size=max(1, EMBED_BATCH_SIZE),
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


index, docs = load_index()

# =======================
# ERROR CODE TABLE LOOKUP
# =======================

ERROR_CODE_TO_DOCS: dict[str, list[dict]] = defaultdict(list)

_ERROR_CODE_LINE_RE = re.compile(r"(?m)^\s*(\d{2,3})\s+[A-Z][A-Z0-9/()\-+\s]{3,120}$")


def _init_error_code_index() -> None:
    try:
        for d in docs:
            t = d.get("text") or ""
            if not t:
                continue
            tl = t.lower()
            if ("error" not in tl) and ("code" not in tl) and ("diagnostic" not in tl):
                continue
            for m in _ERROR_CODE_LINE_RE.finditer(t):
                code = m.group(1)
                if "error" not in tl and "code" not in tl:
                    continue
                ERROR_CODE_TO_DOCS[code].append(d)
        if ERROR_CODE_TO_DOCS:
            print(f"[NovaRAG] Error-code index ready: {len(ERROR_CODE_TO_DOCS)} codes")
        else:
            print("[NovaRAG] Error-code index ready: 0 codes (no diagnostic tables detected)")
    except Exception as e:  # pragma: no cover
        print(f"[NovaRAG] Error-code index init failed: {e}")


_init_error_code_index()

if USE_VISION_AWARE_RERANKER and bool(os.environ.get("NOVA_INIT_TFIDF_CACHE", "0") == "1"):
    init_tfidf_vectorizer()

# =======================
# BM25 INDEX
# =======================

from math import log

_BM25_INDEX: dict[str, dict[int, int]] = {}
_BM25_DOC_LEN: list[int] = []
_BM25_AVGDL: float = 0.0
_BM25_READY: bool = False
_BM25_K1: float = float(os.environ.get("NOVA_BM25_K1", "1.5"))
_BM25_B: float = float(os.environ.get("NOVA_BM25_B", "0.75"))

BM25_CACHE_ENABLED = os.environ.get("NOVA_BM25_CACHE", "1") == "1"
BM25_CACHE_PATH = INDEX_DIR / "bm25_index.pkl"
BM25_CORPUS_HASH_PATH = INDEX_DIR / "bm25_corpus_hash.txt"


def _tokenize(text: str) -> list[str]:
    return [t for t in re.split(r"\W+", (text or "").lower()) if t]


def _compute_corpus_hash() -> str:
    hasher = hashlib.sha256()
    for d in docs:
        hasher.update(d.get("text", "").encode("utf-8"))
    return hasher.hexdigest()[:16]


def _save_bm25_index():
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
        corpus_hash = _compute_corpus_hash()
        BM25_CORPUS_HASH_PATH.write_text(corpus_hash, encoding="utf-8")
        print(f"[NovaRAG] BM25 index cached to {BM25_CACHE_PATH}")
    except Exception as e:  # pragma: no cover
        print(f"[NovaRAG] Failed to save BM25 cache: {e}")


def _load_bm25_index() -> bool:
    global _BM25_INDEX, _BM25_DOC_LEN, _BM25_AVGDL, _BM25_READY
    if not BM25_CACHE_ENABLED or not BM25_CACHE_PATH.exists() or not BM25_CORPUS_HASH_PATH.exists():
        return False
    try:
        saved_hash = BM25_CORPUS_HASH_PATH.read_text(encoding="utf-8").strip()
        current_hash = _compute_corpus_hash()
        if saved_hash != current_hash:
            print("[NovaRAG] BM25 cache invalid (corpus changed); rebuilding...")
            return False
        if SECURE_CACHE_AVAILABLE:
            data = secure_pickle_load(BM25_CACHE_PATH)
        else:
            import pickle

            with BM25_CACHE_PATH.open("rb") as f:
                data = pickle.load(f)
        if data.get("k1") != _BM25_K1 or data.get("b") != _BM25_B:
            print("[NovaRAG] BM25 cache params mismatch; rebuilding...")
            return False
        _BM25_INDEX = data["index"]
        _BM25_DOC_LEN = data["doc_len"]
        _BM25_AVGDL = data["avgdl"]
        _BM25_READY = True
        print(f"[NovaRAG] BM25 index loaded from cache: {len(_BM25_INDEX)} terms, avgdl={_BM25_AVGDL:.1f}")
        return True
    except Exception as e:  # pragma: no cover
        print(f"[NovaRAG] Failed to load BM25 cache: {e}; rebuilding...")
        return False


def _build_bm25_index():
    global _BM25_INDEX, _BM25_DOC_LEN, _BM25_AVGDL, _BM25_READY
    if _load_bm25_index():
        return
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
    except Exception as e:  # pragma: no cover
        _BM25_READY = False
        print(f"[NovaRAG] BM25 index build failed: {e}")


def _bm25_idf(term: str) -> float:
    N = len(_BM25_DOC_LEN)
    df = len(_BM25_INDEX.get(term, {}))
    return log(((N - df + 0.5) / (df + 0.5)) + 1.0) if N and df else 0.0


def bm25_retrieve(query: str, k: int = 12, top_n: int = 6) -> list[dict]:
    if not _BM25_READY:
        _build_bm25_index()
    if not _BM25_READY:
        return []
    q_terms = _tokenize(query)
    candidate_docs: dict[int, float] = {}
    for qt in set(q_terms):
        posting = _BM25_INDEX.get(qt)
        if not posting:
            continue
        idf = _bm25_idf(qt)
        for doc_idx, tf in posting.items():
            dl = _BM25_DOC_LEN[doc_idx]
            denom = tf + _BM25_K1 * (1.0 - _BM25_B + _BM25_B * (dl / max(1.0, _BM25_AVGDL)))
            score = idf * ((tf * (_BM25_K1 + 1.0)) / max(1e-12, denom))
            candidate_docs[doc_idx] = candidate_docs.get(doc_idx, 0.0) + score
    if not candidate_docs:
        return []
    sorted_idxs = sorted(candidate_docs.items(), key=lambda x: x[1], reverse=True)
    top_idxs = [i for i, _ in sorted_idxs[: max(k, top_n)]]
    results: list[dict] = []
    for idx in top_idxs:
        if 0 <= idx < len(docs):
            d = dict(docs[idx])
            d["bm25_score"] = float(candidate_docs.get(idx, 0))
            results.append(d)
    return results


def lexical_retrieve(query: str, k: int = 12, top_n: int = 6) -> list[dict]:
    if not docs:
        return []
    q_tokens = set(query.lower().split())
    scored = []
    for doc in docs:
        text = doc.get("text", "").lower()
        d_tokens = set(text.split())
        inter = len(q_tokens & d_tokens)
        union = max(1, len(q_tokens | d_tokens))
        score = inter / union
        if score > 0:
            doc_copy = dict(doc)
            doc_copy["confidence"] = score
            scored.append((score, doc_copy))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [d for _, d in scored[: max(top_n, k)]]


# =======================
# RETRIEVAL
# =======================


def retrieve(
    query: str,
    k: int = 12,
    top_n: int = 6,
    lambda_diversity: float = 0.5,
    use_reranker: bool = True,
    use_sklearn_reranker: bool | None = None,
    use_gar: bool = True,
) -> list[dict]:
    original_query = query
    if use_gar and GAR_ENABLED and gar_expand_query is not None:
        query = gar_expand_query(query)
        if query != original_query:
            print(f"[GAR] Expanded: '{original_query[:50]}...' -> '{query[:80]}...'")

    text_model = get_text_embed_model()
    # If embeddings or FAISS index are unavailable, rely on lexical/BM25 only.
    if text_model is None or index is None:
        bm25_docs = bm25_retrieve(query, k=k, top_n=top_n)
        if bm25_docs:
            max_score = max((d.get("bm25_score", 0) for d in bm25_docs), default=1.0)
            if max_score > 0:
                for d in bm25_docs:
                    norm_score = d.get("bm25_score", 0) / max_score
                    d["confidence"] = 0.5 + (norm_score * 0.45)
            return bm25_docs[:top_n]
        return lexical_retrieve(query, k=k, top_n=top_n)

    q_emb = text_model.encode([query], convert_to_numpy=True)
    distances, indices = index.search(q_emb, k)  # type: ignore[call-arg]

    candidates = []
    for idx in indices[0]:
        if 0 <= idx < len(docs):
            candidates.append(docs[idx])

    if HYBRID_SEARCH_ENABLED:
        try:
            bm25_candidates = bm25_retrieve(query, k=k, top_n=k)
            seen = set((c.get("id"), c.get("source"), c.get("page")) for c in candidates)
            for d_bm in bm25_candidates:
                key = (d_bm.get("id"), d_bm.get("source"), d_bm.get("page"))
                if key not in seen:
                    candidates.append(d_bm)
                    seen.add(key)
        except Exception as e:  # pragma: no cover
            print(f"[NovaRAG] Hybrid BM25 union failed: {e}")
    if not candidates:
        return []

    cand_texts = [c.get("text", "") for c in candidates]
    sim_to_q = [0.5] * len(candidates)

    diagram_keywords = [
        "diagram",
        "flow",
        "block",
        "schematic",
        "circuit",
        "chart",
        "graph",
        "visual",
        "image",
        "picture",
    ]
    query_mentions_diagrams = any(kw in query.lower() for kw in diagram_keywords)

    use_vision_aware = (
        USE_VISION_AWARE_RERANKER
        and query_mentions_diagrams
        and (use_sklearn_reranker is None or use_sklearn_reranker is True)
    )
    if use_sklearn_reranker is None:
        use_sklearn = USE_SKLEARN_RERANKER
    else:
        use_sklearn = bool(use_sklearn_reranker) and (sklearn_reranker is not None)

    if use_vision_aware and sklearn_vision_reranker is not None:
        try:
            import numpy as np

            vectorizer = getattr(sklearn_vision_reranker, "vectorizer", None)
            if vectorizer is None:
                if tfidf_vectorizer is None or not tfidf_vectorizer_fitted:
                    print("[NovaRAG] TF-IDF cache not initialized, using fallback (this is slow)...")
                    vectorizer = TfidfVectorizer(max_features=500, ngram_range=(1, 2), sublinear_tf=True)
                    all_texts = [query] + cand_texts
                    vectorizer.fit(all_texts)
                else:
                    vectorizer = tfidf_vectorizer

            Q = vectorizer.transform([query])
            D = vectorizer.transform(cand_texts)

            q_norm = np.sqrt((Q.multiply(Q)).sum(axis=1)).A1 + 1e-12  # type: ignore[union-attr]
            d_norm = np.sqrt((D.multiply(D)).sum(axis=1)).A1 + 1e-12  # type: ignore[union-attr]
            dot = (Q.multiply(D)).sum(axis=1).A1  # type: ignore[union-attr]
            tfidf_sim = dot / (q_norm * d_norm)

            def tokens(text):
                return set(t.lower() for t in text.split())

            query_tokens = tokens(query)
            overlaps = []
            for cand_text in cand_texts:
                cand_tokens = tokens(cand_text)
                inter = len(query_tokens & cand_tokens)
                union = len(query_tokens | cand_tokens) + 1e-12
                overlaps.append(inter / union)

            has_diagrams = [1.0 if c.get("diagram_context") else 0.0 for c in candidates]
            diagram_in_query = 1.0 if query_mentions_diagrams else 0.0

            doc_lengths = np.log1p([len(c.get("text", "").split()) for c in candidates])
            query_length = np.log1p(len(query.split()))

            features = np.column_stack(
                [
                    tfidf_sim,
                    has_diagrams,
                    overlaps,
                    [diagram_in_query] * len(candidates),
                    doc_lengths,
                    [query_length] * len(candidates),
                ]
            )

            proba = sklearn_vision_reranker.predict_proba(features)[:, 1]
            proba = np.array(proba)
            scores = 0.6 + (proba * 0.35)
            scored_candidates = list(zip(candidates, scores, cand_texts))
            scored_candidates.sort(key=lambda x: x[1], reverse=True)
            candidates = [c[0] for c in scored_candidates[:k]]
            cand_texts = [c[2] for c in scored_candidates[:k]]
            sim_to_q = [float(c[1]) for c in scored_candidates[:k]]
        except Exception as e:  # pragma: no cover
            print(f"[NovaRAG] Vision-aware reranker failed, falling back to text sklearn: {e}")
            use_vision_aware = False

    if not use_vision_aware and use_sklearn:
        try:
            pairs = [(query, text) for text in cand_texts]
            if hasattr(sklearn_reranker, "feature_gen"):
                X_features = sklearn_reranker.feature_gen.transform(pairs)  # type: ignore[union-attr]
                proba = sklearn_reranker.predict_proba(X_features)[:, 1]  # type: ignore[union-attr]
            else:
                proba = sklearn_reranker.predict_proba(pairs)[:, 1]  # type: ignore[union-attr]
            import numpy as np

            proba = np.array(proba)
            scores = 0.6 + (proba * 0.35)
            scored_candidates = list(zip(candidates, scores, cand_texts))
            scored_candidates.sort(key=lambda x: x[1], reverse=True)
            candidates = [c[0] for c in scored_candidates[:k]]
            cand_texts = [c[2] for c in scored_candidates[:k]]
            sim_to_q = [float(c[1]) for c in scored_candidates[:k]]
        except Exception as e:  # pragma: no cover
            print(f"[NovaRAG] Sklearn reranker failed, falling back to cross-encoder: {e}")
            use_sklearn = False

    if (not use_sklearn) and use_reranker and (not DISABLE_CROSS_ENCODER):
        pairs = [[query, text] for text in cand_texts]
        ce_model = get_cross_encoder()
        if ce_model is None:
            use_reranker = False
        else:
            ce_scores = ce_model.predict(pairs)
            import numpy as np

            ce_scores = np.array(ce_scores)
            ce_scores = np.clip(ce_scores, -5, 10)
            ce_min, ce_max = ce_scores.min(), ce_scores.max()
            if ce_max > ce_min:
                ce_scores = (ce_scores - ce_min) / (ce_max - ce_min)
            else:
                ce_scores = np.ones_like(ce_scores) * 0.5
            ce_scores = 0.6 + (ce_scores * 0.35)
            scored_candidates = list(zip(candidates, ce_scores, cand_texts))
            scored_candidates.sort(key=lambda x: x[1], reverse=True)
            candidates = [c[0] for c in scored_candidates[:k]]
            cand_texts = [c[2] for c in scored_candidates[:k]]
            sim_to_q = [float(c[1]) for c in scored_candidates[:k]]

    if (not use_sklearn) and (not use_reranker):
        cand_embs = text_model.encode(cand_texts, convert_to_numpy=True)
        q = q_emb[0]

        import numpy as np

        def cos(a, b):
            a_n = a / (np.linalg.norm(a) + 1e-12)
            b_n = b / (np.linalg.norm(b) + 1e-12)
            return float(np.dot(a_n, b_n))

        sim_to_q = [cos(q, ce) for ce in cand_embs]

    cand_embs = text_model.encode(
        cand_texts,
        convert_to_numpy=True,
        batch_size=min(max(1, EMBED_BATCH_SIZE // 4), max(1, len(cand_texts))),
    )

    import numpy as np

    def cos(a, b):
        a_n = a / (np.linalg.norm(a) + 1e-12)
        b_n = b / (np.linalg.norm(b) + 1e-12)
        return float(np.dot(a_n, b_n))

    selected = []
    selected_embs = []
    selected_scores = []
    remaining = list(range(len(candidates)))

    while remaining and len(selected) < top_n:
        best_idx = None
        best_score = -1.0
        for ri in remaining:
            if selected_embs:
                div = max(cos(cand_embs[ri], se) for se in selected_embs)
            else:
                div = 0.0
            mmr_score = lambda_diversity * sim_to_q[ri] - (1 - lambda_diversity) * div
            if mmr_score > best_score:
                best_score = mmr_score
                best_idx = ri

        if best_idx is not None:
            selected.append(best_idx)
            selected_embs.append(cand_embs[best_idx])
            selected_scores.append(sim_to_q[best_idx])
            remaining.remove(best_idx)

    results = []
    for i, idx in enumerate(selected):
        doc = candidates[idx].copy()
        doc["confidence"] = float(selected_scores[i])
        results.append(doc)

    return results


# =======================
# ERROR CODE BOOSTING
# =======================


def detect_error_code(query: str) -> dict:
    q = query.lower()
    m = re.search(r"\b(code|error|dtc)\s*[:#-]?\s*([A-Z]?\d{2,5})\b", q, re.IGNORECASE)
    if m:
        return {"error_id": m.group(2).upper(), "term": m.group(0)}
    m_rev = re.search(r"\b([A-Z]?\d{2,5})\s*(code|error|dtc)\b", q, re.IGNORECASE)
    if m_rev:
        return {"error_id": m_rev.group(1).upper(), "term": m_rev.group(0)}
    return {}


def boost_error_docs(query: str, context_docs: list[dict]) -> list[dict]:
    error_meta = detect_error_code(query)
    if not error_meta or not context_docs:
        return context_docs
    eid = error_meta.get("error_id")
    if not eid:
        return context_docs

    injected: list[dict] = []
    neighbor_ids: list[str] = [str(eid)]
    try:
        eid_int = int(str(eid).lstrip("P"))
        neighbor_ids = [str(eid_int - 1), str(eid_int), str(eid_int + 1)]
    except Exception:
        pass

    for nid in neighbor_ids:
        for d in ERROR_CODE_TO_DOCS.get(nid, []):
            dd = dict(d)
            dd.setdefault("confidence", 0.95)
            injected.append(dd)

    if injected:
        ql = query.lower()

        def inj_score(doc: dict) -> float:
            t = (doc.get("text") or "").lower()
            s = 0.0
            s += 2.0 if re.search(rf"(?m)^\s*{re.escape(str(eid))}\s+", doc.get("text") or "") else 0.0
            if "diagnostic" in ql:
                s += 2.0 if "diagnostic" in t else 0.0
            if "symptom" in ql:
                s += 1.0 if "symptom" in t else 0.0
            return s

        injected.sort(key=inj_score, reverse=True)

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


# Back-compat alias used by older tests
_boost_error_docs = boost_error_docs


# =======================
# VISION SEARCH
# =======================


def vision_search(user_image, top_k: int = 5):
    if user_image is None:
        return []

    model, v_emb, v_paths = ensure_vision_loaded()
    if v_emb is None or v_paths is None or model is None:
        return []

    img_emb = model.encode(user_image, convert_to_tensor=True)  # type: ignore[arg-type]
    img_emb = torch.nn.functional.normalize(img_emb, p=2, dim=-1)

    scores = (v_emb @ img_emb.unsqueeze(1)).squeeze(1)
    top_k = max(1, min(int(top_k), len(scores)))
    vals, idxs = torch.topk(scores, k=top_k)

    results = []
    for score, idx in zip(vals, idxs):
        path = v_paths[int(idx)]
        if os.path.exists(path):
            caption = f"{Path(path).name} | sim={float(score):.3f}"
            results.append((path, caption))
    return results


__all__ = [
    "BASE_DIR",
    "DOCS_DIR",
    "INDEX_DIR",
    "INDEX_PATH",
    "DOCS_PATH",
    "SEARCH_HISTORY_PATH",
    "FAVORITES_PATH",
    "DISABLE_EMBED",
    "DISABLE_CROSS_ENCODER",
    "HYBRID_SEARCH_ENABLED",
    "EMBED_BATCH_SIZE",
    "text_embed_model_error",
    "get_text_embed_model",
    "get_cross_encoder",
    "ensure_vision_loaded",
    "build_index",
    "load_index",
    "index",
    "docs",
    "bm25_retrieve",
    "lexical_retrieve",
    "retrieve",
    "detect_error_code",
    "boost_error_docs",
    "_boost_error_docs",
    "vision_search",
    "ERROR_CODE_TO_DOCS",
    "GAR_ENABLED",
]
