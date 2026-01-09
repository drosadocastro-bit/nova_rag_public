"""
Shared backend logic for NovaRAG (used by both Gradio and Flask frontends)
Handles RAG, LLM routing, session management, and all core features.
"""

from __future__ import annotations

from pathlib import Path
import json
import os
from datetime import datetime
import re
import requests
from collections import deque

# Import secure pickle if available
try:
    from secure_cache import secure_pickle_dump, secure_pickle_load
    SECURE_CACHE_AVAILABLE = True
except ImportError:
    import pickle
    SECURE_CACHE_AVAILABLE = False

import faiss
import torch
from pypdf import PdfReader
from PIL import Image
from openai import OpenAI
from agents import agent_router
from agents.session_store import save_session, load_session, list_recent_sessions, generate_session_id
from agents.risk_assessment import RiskAssessment, RiskLevel
from response_normalizer import normalize_response

# LLM Engine - Native Python integration (llama-cpp-python)
native_call_llm = None
try:
    from llm_engine import get_engine, call_llm as native_call_llm, LLAMA_CPP_AVAILABLE
    USE_NATIVE_ENGINE = os.environ.get("NOVA_USE_NATIVE_LLM", "1") == "1" and LLAMA_CPP_AVAILABLE
    if USE_NATIVE_ENGINE:
        print("[NovaRAG] Using native llama-cpp-python engine (30k context, optimized)")
    else:
        print("[NovaRAG] Using HTTP client (Ollama API)")
except ImportError:
    USE_NATIVE_ENGINE = False
    print("[NovaRAG] llama-cpp-python not available, using HTTP client")

# Glossary Augmented Retrieval (GAR)
try:
    from glossary_gar import expand_query as gar_expand_query
    GAR_ENABLED = os.environ.get("NOVA_GAR_ENABLED", "1") == "1"
    print(f"[NovaRAG] Glossary Augmented Retrieval (GAR): {'enabled' if GAR_ENABLED else 'disabled'}")
except ImportError:
    gar_expand_query = None
    GAR_ENABLED = False
    print("[NovaRAG] GAR module not found, query expansion disabled")


# =======================
# PATHS
# =======================

BASE_DIR = Path(__file__).parent.resolve()
DOCS_DIR = BASE_DIR / "data"
INDEX_DIR = BASE_DIR / "vector_db"
INDEX_DIR.mkdir(parents=True, exist_ok=True)

INDEX_PATH = INDEX_DIR / "vehicle_index.faiss"
DOCS_PATH = INDEX_DIR / "vehicle_docs.jsonl"
SEARCH_HISTORY_PATH = INDEX_DIR / "search_history.pkl"
FAVORITES_PATH = INDEX_DIR / "favorites.json"

VISION_EMB_PATH = INDEX_DIR / "vehicle_vision_embeddings.pt"
DISABLE_VISION = os.environ.get("NOVA_DISABLE_VISION", "0") == "1"
# Disable text embeddings entirely (forces lexical fallback)
DISABLE_EMBED = os.environ.get("NOVA_DISABLE_EMBED", "0") == "1"

# Force offline mode: disables all network calls (HuggingFace downloads, external APIs)
FORCE_OFFLINE = os.environ.get("NOVA_FORCE_OFFLINE", "0") == "1"
if FORCE_OFFLINE:
    print("[NovaRAG] FORCE OFFLINE MODE: All network operations disabled")
    os.environ["HF_HUB_OFFLINE"] = "1"  # Prevent HuggingFace downloads
    os.environ["TRANSFORMERS_OFFLINE"] = "1"  # Prevent transformer downloads

# Lightweight mode knobs (helpful for low-spec laptops)
# - Disable cross-encoder reranker (heavy) entirely
# - Limit numerical library threads to reduce CPU spikes
DISABLE_CROSS_ENCODER = os.environ.get("NOVA_DISABLE_CROSS_ENCODER", "0") == "1"

# Enable hybrid search (vector + lexical BM25)
HYBRID_SEARCH_ENABLED = os.environ.get("NOVA_HYBRID_SEARCH", "1") == "1"

# Embedding batch size (for index build); tune via env if needed
EMBED_BATCH_SIZE = int(os.environ.get("NOVA_EMBED_BATCH_SIZE", "32"))

# Apply conservative threading defaults unless already set externally
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")


# =======================
# MODELS
# =======================

print("[NovaRAG] Text embedding model will load lazily when needed...")
text_embed_model = None
text_embed_model_error = None

def get_text_embed_model():
    """Load text embedding model, preferring local path to avoid network stalls."""
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
            print(f"[NovaRAG]    Found local model, loading (local_files_only=True)...")
            text_embed_model = SentenceTransformer(str(local_path), local_files_only=True)
            print(f"[NovaRAG]    Local embedding model loaded")
        elif FORCE_OFFLINE:
            print(f"[NovaRAG]    ERROR: Offline mode enabled but local model not found at {local_path}")
            print(f"[NovaRAG]    Cannot download models in offline mode. Please download manually.")
            text_embed_model_error = "Offline mode - no local model available"
            return None
        else:
            print(f"[NovaRAG]    Local model not found at {local_path}")
            print(f"[NovaRAG]   Attempting to download from HuggingFace (this may hang)...")
            text_embed_model = SentenceTransformer("all-MiniLM-L6-v2")
            print(f"[NovaRAG]    Downloaded embedding model")
        return text_embed_model
    except Exception as e:
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
from joblib import load as joblib_load

SKLEARN_MODEL_PATH = BASE_DIR / "models" / "sklearn_reranker.pkl"
sklearn_reranker = None
try:
    if SKLEARN_MODEL_PATH.exists():
        print(f"[NovaRAG] Loading sklearn reranker from {SKLEARN_MODEL_PATH}...")
        # Note: requires importable train-time classes; ensure workspace root in PYTHONPATH
        sklearn_reranker = joblib_load(str(SKLEARN_MODEL_PATH))
        print("[NovaRAG] Sklearn reranker loaded.")
    else:
        print("[NovaRAG] Sklearn reranker not found; using cross-encoder.")
except Exception as e:
    print(f"[NovaRAG] Failed to load sklearn reranker: {e}")

# Env flag to enable sklearn reranker when available (default ON)
USE_SKLEARN_RERANKER = bool(os.environ.get("NOVA_USE_SKLEARN_RERANKER", "1") == "1") and (sklearn_reranker is not None)

# Vision-aware reranker (optional; loaded if available and env flag set)
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
    print(f"[NovaRAG] Vision-aware reranker not available: Using text-only reranker.")

# Env flag to enable vision-aware reranker (default ON if available and vision is enabled)
USE_VISION_AWARE_RERANKER = (
    bool(os.environ.get("NOVA_USE_VISION_AWARE_RERANKER", "1") == "1")
    and (sklearn_vision_reranker is not None)
    and (not DISABLE_VISION)  # Only use if vision is enabled
)


# =======================
# TF-IDF VECTORIZER CACHE (for vision-aware reranker)
# =======================
# Pre-fit TF-IDF vectorizer on all documents at startup
# Pre-fit TF-IDF vectorizer on all documents at startup
# This eliminates the 20-30s bottleneck from vectorizer.fit() on every query
# NOTE: Currently disabled - vision-aware reranker needs retraining without custom class
tfidf_vectorizer = None
tfidf_vectorizer_fitted = False

def init_tfidf_vectorizer():
    """Initialize TF-IDF vectorizer on full document corpus at startup."""
    global tfidf_vectorizer, tfidf_vectorizer_fitted
    
    if tfidf_vectorizer_fitted or not USE_VISION_AWARE_RERANKER:
        return
    
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        import numpy as np
        
        # Load all documents
        if not DOCS_PATH.exists():
            print("[NovaRAG] TF-IDF: Docs file not found, skipping cache init")
            return
        
        all_texts = []
        with DOCS_PATH.open("r", encoding="utf-8") as f:
            for line in f:
                try:
                    doc = json.loads(line)
                    all_texts.append(doc.get("text", ""))
                except:
                    pass
        
        if not all_texts:
            print("[NovaRAG] TF-IDF: No documents found")
            return
        
        # Fit vectorizer on full corpus
        print(f"[NovaRAG] Fitting TF-IDF vectorizer on {len(all_texts)} documents...")
        tfidf_vectorizer = TfidfVectorizer(
            max_features=500, 
            ngram_range=(1, 2), 
            sublinear_tf=True,
            min_df=1,
            max_df=0.95
        )
        tfidf_vectorizer.fit(all_texts)
        tfidf_vectorizer_fitted = True
        print(f"[NovaRAG] TF-IDF cache ready! ({len(tfidf_vectorizer.vocabulary_)} features)")
    except Exception as e:
        print(f"[NovaRAG] TF-IDF cache init failed: {e}")
        tfidf_vectorizer = None
        tfidf_vectorizer_fitted = False


# =======================
# OLLAMA CLIENT
# =======================

# Timeouts: prefer correctness over speed for safety-critical troubleshooting.
# These can be overridden per environment.
OLLAMA_TIMEOUT_S = float(os.environ.get("NOVA_OLLAMA_TIMEOUT_S", "1200"))
OLLAMA_MODEL_LOAD_TIMEOUT_S = float(os.environ.get("NOVA_OLLAMA_MODEL_LOAD_TIMEOUT_S", str(min(OLLAMA_TIMEOUT_S, 1200.0))))


# HTTP client (fallback when native engine not available)
client = None
if not USE_NATIVE_ENGINE:
    try:
        # Use a custom httpx client with SSL verification disabled to avoid
        # Windows SSL context initialization delays for local HTTP endpoints.
        import httpx
        _httpx_client = httpx.Client(verify=False, timeout=httpx.Timeout(OLLAMA_TIMEOUT_S))
        client = OpenAI(
            base_url="http://127.0.0.1:11434/v1",
            api_key="ollama",
            http_client=_httpx_client,
        )
        print("[NovaRAG] HTTP client initialized for Ollama (port 11434)")
    except Exception as e:
        print(f"[NovaRAG] Warning: Ollama client initialization failed ({e}); will retry on first LLM call")
        client = None
# Allow overriding LLAMA model via env to avoid GPU OOM with heavier builds
LLM_LLAMA = os.environ.get(
    "NOVA_LLM_LLAMA",
    "llama3.2:8b",
)
LLM_OSS = os.environ.get(
    "NOVA_LLM_OSS",
    "qwen2.5-coder:14b",
)

# Max output tokens per response (configurable via env)
# Note: This controls generated tokens, not context window size.
# Fireball-llama has 128k context, so we can afford more output tokens
MAX_TOKENS_LLAMA = int(os.environ.get("NOVA_MAX_TOKENS_LLAMA", "4096"))
MAX_TOKENS_OSS   = int(os.environ.get("NOVA_MAX_TOKENS_OSS", "512"))  # Balanced for speed + quality

def get_max_tokens(model_name: str) -> int:
    return MAX_TOKENS_LLAMA if model_name == LLM_LLAMA else MAX_TOKENS_OSS


# =======================
# SESSION STATE
# =======================

session_state = {
    "active": False,
    "topic": None,
    "finding_log": [],
    "turns": 0,
    "session_id": None,
    "model": None,
    "mode": None,
    "feedback": [],
    "turn_history": [],  # List of (question, answer) tuples for multi-turn context
}


# =======================
# SEARCH HISTORY & FAVORITES
# =======================

class SearchHistory:
    def __init__(self, max_size: int = 50):
        self.history = deque(maxlen=max_size)
        self.favorites = []
        self.load()
    
    def add(self, query: str):
        if query in self.history:
            self.history.remove(query)
        self.history.appendleft(query)
        self.save()
    
    def add_favorite(self, query: str, answer: str):
        fav = {"query": query, "answer": answer, "timestamp": datetime.now().isoformat()}
        self.favorites.append(fav)
        self.save_favorites()
    
    def remove_favorite(self, index: int):
        if 0 <= index < len(self.favorites):
            self.favorites.pop(index)
            self.save_favorites()
    
    def get_recent(self, n: int = 10) -> list[str]:
        return list(self.history)[:n]
    
    def save(self):
        """Save search history with HMAC verification for security."""
        try:
            if SECURE_CACHE_AVAILABLE:
                from secure_cache import secure_pickle_dump
                secure_pickle_dump(list(self.history), SEARCH_HISTORY_PATH)
            else:
                import pickle
                with SEARCH_HISTORY_PATH.open("wb") as f:
                    pickle.dump(list(self.history), f)
        except Exception as e:
            print(f"[!] Failed to save search history: {e}")
    
    def save_favorites(self):
        try:
            with FAVORITES_PATH.open("w", encoding="utf-8") as f:
                json.dump(self.favorites, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[!] Failed to save favorites: {e}")
    
    def load(self):
        """Load search history with HMAC verification for security."""
        try:
            if SEARCH_HISTORY_PATH.exists():
                if SECURE_CACHE_AVAILABLE:
                    from secure_cache import secure_pickle_load
                    self.history = deque(secure_pickle_load(SEARCH_HISTORY_PATH), maxlen=50)
                else:
                    import pickle
                    with SEARCH_HISTORY_PATH.open("rb") as f:
                        self.history = deque(pickle.load(f), maxlen=50)
            if FAVORITES_PATH.exists():
                with FAVORITES_PATH.open("r", encoding="utf-8") as f:
                    self.favorites = json.load(f)
        except Exception as e:
            print(f"[!] Failed to load search history: {e}")
            # Clear corrupted cache
            self.history = deque(maxlen=50)
            if SEARCH_HISTORY_PATH.exists():
                try:
                    SEARCH_HISTORY_PATH.unlink()
                except Exception:
                    pass

search_history = SearchHistory()


# =======================
# CONNECTION STATUS
# =======================

def check_ollama_connection() -> tuple[bool, str]:
    """Check if Ollama is reachable."""
    try:
        response = requests.get("http://127.0.0.1:11434/api/tags", timeout=2)
        if response.status_code == 200:
            return True, " Ollama Connected"
        else:
            return False, " Ollama responded but with errors"
    except requests.exceptions.ConnectionError:
        return False, " Ollama Offline - Check if server is running"
    except requests.exceptions.Timeout:
        return False, " Ollama Timeout - Server slow to respond"
    except Exception as e:
        return False, f" Connection Error: {str(e)[:50]}"


# =======================
# SESSION MANAGEMENT
# =======================

def reset_session(save_to_db: bool = True):
    """Reset session and optionally save to database."""
    if save_to_db and session_state["session_id"]:
        save_session(
            session_state["session_id"],
            session_state,
            topic=session_state.get("topic", ""),
            model=session_state.get("model", ""),
            mode=session_state.get("mode", "")
        )
    
    session_state["active"] = False
    session_state["topic"] = None
    session_state["finding_log"] = []
    session_state["turns"] = 0
    session_state["session_id"] = None
    session_state["model"] = None
    session_state["mode"] = None

def start_new_session(topic: str, model: str, mode: str) -> str:
    """Start a new troubleshooting session and return session_id."""
    session_id = generate_session_id()
    session_state["active"] = True
    session_state["topic"] = topic
    session_state["finding_log"] = [f"Initial question: {topic}"]
    session_state["turns"] = 1
    session_state["session_id"] = session_id
    session_state["model"] = model
    session_state["mode"] = mode
    return session_id

def resume_session(session_id: str) -> bool:
    """Load and resume a previous session."""
    saved_state = load_session(session_id)
    if not saved_state:
        return False
    
    session_state.update(saved_state)
    session_state["active"] = True
    session_state["session_id"] = session_id
    return True


TROUBLESHOOT_TRIGGERS = [
    "troubleshoot", "troubleshooting", "intermittent",
    "diagnostic", "fault", "failure", "error", "trouble"
]

END_SESSION_TRIGGERS = [
    "reset session", "end session", "finish session",
    "nuevo caso", "nueva falla", "start over"
]

DEEP_KEYWORDS = [
    "explain", "why", "root cause", "analysis", "analyze",
    "detailed", "theory", "concept", "in depth", "deep",
    "diagnosis", "reasoning"
]

FAST_KEYWORDS = [
    "steps", "procedure", "process", "checklist", "sequence",
    "how do i", "how to", "replace", "remove", "install",
    "test", "verify", "adjust", "reset", "configure", "runbook"
]


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
    text_model = get_text_embed_model()
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
# ERROR CODE TABLE LOOKUP (Lexical Fallback)
# =======================

from collections import defaultdict

# Map error code -> list of doc dicts that appear to contain that code's table entry.
# This is computed once at startup from the PDF-extracted chunks and used to
# augment embedding retrieval for diagnostic queries.
ERROR_CODE_TO_DOCS: dict[str, list[dict]] = defaultdict(list)

_ERROR_CODE_LINE_RE = re.compile(
    r"(?m)^\s*(\d{2,3})\s+[A-Z][A-Z0-9/()\-+\s]{3,120}$"
)

def _init_error_code_index() -> None:
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


_init_error_code_index()

# Optional: Initialize TF-IDF cache for vision-aware reranker (disabled by default).
# The vision-aware model now carries its own vectorizer; skip global init to avoid long startup.
if USE_VISION_AWARE_RERANKER and bool(os.environ.get("NOVA_INIT_TFIDF_CACHE", "0") == "1"):
    init_tfidf_vectorizer()


# =======================
# BM25 LEXICAL INDEX (Hybrid)
# =======================
from math import log
import hashlib

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

def _compute_corpus_hash() -> str:
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
            from secure_cache import secure_pickle_dump
            secure_pickle_dump(data, BM25_CACHE_PATH)
        else:
            import pickle
            with BM25_CACHE_PATH.open("wb") as f:
                pickle.dump(data, f)
        # Save corpus hash
        corpus_hash = _compute_corpus_hash()
        BM25_CORPUS_HASH_PATH.write_text(corpus_hash, encoding="utf-8")
        print(f"[NovaRAG] BM25 index cached to {BM25_CACHE_PATH}")
    except Exception as e:
        print(f"[NovaRAG] Failed to save BM25 cache: {e}")

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

def _bm25_idf(term: str) -> float:
    N = len(_BM25_DOC_LEN)
    df = len(_BM25_INDEX.get(term, {}))
    # Robertson-Sparck Jones IDF
    return log(((N - df + 0.5) / (df + 0.5)) + 1.0) if N and df else 0.0

def bm25_retrieve(query: str, k: int = 12, top_n: int = 6) -> list[dict]:
    """BM25 lexical retrieval over chunked docs."""
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
    # Top by BM25 score
    sorted_idxs = sorted(candidate_docs.items(), key=lambda x: x[1], reverse=True)
    top_idxs = [i for i, _ in sorted_idxs[:max(k, top_n)]]
    results: list[dict] = []
    for idx in top_idxs:
        if 0 <= idx < len(docs):
            d = dict(docs[idx])
            d["bm25_score"] = float(candidate_docs.get(idx, 0.0))
            results.append(d)
    return results

def lexical_retrieve(query: str, k: int = 12, top_n: int = 6) -> list[dict]:
    """Lightweight lexical fallback when embeddings are unavailable.
    Scores by token overlap and returns top_n docs with pseudo-confidence.
    """
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
            doc = dict(doc)
            doc["confidence"] = score
            scored.append((score, doc))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [d for _, d in scored[:max(top_n, k)]]


# =======================
# RETRIEVAL + PROMPTS
# =======================

def retrieve(query: str, k: int = 12, top_n: int = 6, lambda_diversity: float = 0.5, use_reranker: bool = True, use_sklearn_reranker: bool | None = None, use_gar: bool = True) -> list[dict]:
    """
    Retrieve k candidates, optionally rerank with cross-encoder, then apply MMR for diversity.
    Cross-encoder provides much more accurate confidence scores.
    
    Args:
        query: User query
        k: Number of candidates to retrieve
        top_n: Number of results to return after reranking
        lambda_diversity: MMR diversity parameter
        use_reranker: Whether to use cross-encoder reranking
        use_sklearn_reranker: Whether to use sklearn reranker
        use_gar: Whether to apply Glossary Augmented Retrieval expansion
    """
    # Apply GAR query expansion if enabled
    original_query = query
    if use_gar and GAR_ENABLED and gar_expand_query is not None:
        query = gar_expand_query(query)
        if query != original_query:
            print(f"[GAR] Expanded: '{original_query[:50]}...' -> '{query[:80]}...'")
    
    text_model = get_text_embed_model()
    if text_model is None:
        # Lexical fallback when embedding model is unavailable
        bm25_docs = bm25_retrieve(query, k=k, top_n=top_n)
        if bm25_docs:
            # Normalize BM25 scores to confidence (0.0-1.0 range)
            max_score = max((d.get("bm25_score", 0) for d in bm25_docs), default=1.0)
            if max_score > 0:
                for d in bm25_docs:
                    # Map BM25 score to confidence (min 0.5, max 0.95)
                    norm_score = d.get("bm25_score", 0) / max_score
                    d["confidence"] = 0.5 + (norm_score * 0.45)
            return bm25_docs[:top_n]
        # Final fallback to lexical retrieval
        lexical_docs = lexical_retrieve(query, k=k, top_n=top_n)
        return lexical_docs

    q_emb = text_model.encode([query], convert_to_numpy=True)
    distances, indices = index.search(q_emb, k)  # type: ignore[call-arg]

    candidates = []
    for idx in indices[0]:
        if 0 <= idx < len(docs):
            candidates.append(docs[idx])
    # HYBRID: Union with BM25 lexical candidates for broader coverage
    if HYBRID_SEARCH_ENABLED:
        try:
            bm25_candidates = bm25_retrieve(query, k=k, top_n=k)
            # Deduplicate: prefer embedding candidate ordering
            seen = set((c.get("id"), c.get("source"), c.get("page")) for c in candidates)
            for d_bm in bm25_candidates:
                key = (d_bm.get("id"), d_bm.get("source"), d_bm.get("page"))
                if key not in seen:
                    candidates.append(d_bm)
                    seen.add(key)
        except Exception as e:
            print(f"[NovaRAG] Hybrid BM25 union failed: {e}")
    if not candidates:
        return []

    cand_texts = [c.get("text", "") for c in candidates]
    
    # Initialize similarity scores (will be updated by rerankers)
    sim_to_q = [0.5] * len(candidates)
    
    # Detect if query mentions diagrams (for hybrid trigger)
    diagram_keywords = ["diagram", "flow", "block", "schematic", "circuit", "chart", "graph", "visual", "image", "picture"]
    query_mentions_diagrams = any(kw in query.lower() for kw in diagram_keywords)
    
    # Choose reranker: vision-aware sklearn  text sklearn  cross-encoder
    # HYBRID TRIGGER: Only use vision-aware if query mentions diagrams (Option C)
    use_vision_aware = USE_VISION_AWARE_RERANKER and query_mentions_diagrams and (use_sklearn_reranker is None or use_sklearn_reranker == True)
    if use_sklearn_reranker is None:
        use_sklearn = USE_SKLEARN_RERANKER
    else:
        use_sklearn = bool(use_sklearn_reranker) and (sklearn_reranker is not None)

    # Vision-aware sklearn reranking (highest priority if enabled)
    if use_vision_aware and sklearn_vision_reranker is not None:
        try:
            import numpy as np
            from sklearn.feature_extraction.text import TfidfVectorizer
            
            # Prefer vectorizer bundled with the vision-aware model (guaranteed compatible)
            vectorizer = getattr(sklearn_vision_reranker, "vectorizer", None)

            # Otherwise use cached TF-IDF vectorizer (pre-fit on full corpus at startup)
            if vectorizer is None:
                if tfidf_vectorizer is None or not tfidf_vectorizer_fitted:
                    # Fallback: fit on current query + candidates (slower but works)
                    print("[NovaRAG] TF-IDF cache not initialized, using fallback (this is slow)...")
                    vectorizer = TfidfVectorizer(max_features=500, ngram_range=(1, 2), sublinear_tf=True)
                    all_texts = [query] + cand_texts
                    vectorizer.fit(all_texts)
                else:
                    # Use cached vectorizer: instant feature extraction!
                    vectorizer = tfidf_vectorizer
            
            Q = vectorizer.transform([query])
            D = vectorizer.transform(cand_texts)
            
            # TF-IDF cosine sim
            q_norm = np.sqrt((Q.multiply(Q)).sum(axis=1)).A1 + 1e-12  # type: ignore[union-attr]
            d_norm = np.sqrt((D.multiply(D)).sum(axis=1)).A1 + 1e-12  # type: ignore[union-attr]
            dot = (Q.multiply(D)).sum(axis=1).A1  # type: ignore[union-attr]
            tfidf_sim = dot / (q_norm * d_norm)
            
            # Token overlap
            def tokens(text):
                return set(t.lower() for t in text.split())
            query_tokens = tokens(query)
            overlaps = []
            for cand_text in cand_texts:
                cand_tokens = tokens(cand_text)
                inter = len(query_tokens & cand_tokens)
                union = len(query_tokens | cand_tokens) + 1e-12
                overlaps.append(inter / union)
            
            # Diagram flags
            has_diagrams = [1.0 if c.get("diagram_context") else 0.0 for c in candidates]
            diagram_in_query = 1.0 if query_mentions_diagrams else 0.0
            
            # Doc/query lengths (log)
            doc_lengths = np.log1p([len(c.get("text", "").split()) for c in candidates])
            query_length = np.log1p(len(query.split()))
            
            # Build feature matrix: [tfidf, has_diagram, overlap, diagram_in_q, doc_len, query_len]
            features = np.column_stack([
                tfidf_sim,                           # tfidf_cosine
                has_diagrams,                         # has_diagram
                overlaps,                            # token_overlap
                [diagram_in_query] * len(candidates), # diagram_in_query
                doc_lengths,                         # doc_length
                [query_length] * len(candidates),    # query_length
            ])
            
            proba = sklearn_vision_reranker.predict_proba(features)[:, 1]
            proba = np.array(proba)
            # Boost to 6095% range for UI parity
            scores = 0.6 + (proba * 0.35)
            scored_candidates = list(zip(candidates, scores, cand_texts))
            scored_candidates.sort(key=lambda x: x[1], reverse=True)
            candidates = [c[0] for c in scored_candidates[:k]]
            cand_texts = [c[2] for c in scored_candidates[:k]]
            sim_to_q = [float(c[1]) for c in scored_candidates[:k]]
        except Exception as e:
            print(f"[NovaRAG] Vision-aware reranker failed, falling back to text sklearn: {e}")
            use_vision_aware = False

    # Sklearn text-only reranking (fallback)
    if not use_vision_aware and use_sklearn:
        try:
            pairs = [(query, text) for text in cand_texts]
            # Use feature generator to convert pairs to feature vectors
            if hasattr(sklearn_reranker, 'feature_gen'):
                X_features = sklearn_reranker.feature_gen.transform(pairs)  # type: ignore[union-attr]
                proba = sklearn_reranker.predict_proba(X_features)[:, 1]  # type: ignore[union-attr]
            else:
                # Fallback: try direct predict_proba (may fail if model expects features)
                proba = sklearn_reranker.predict_proba(pairs)[:, 1]  # type: ignore[union-attr]
            import numpy as np
            proba = np.array(proba)
            # Boost to 6095% range for UI parity
            scores = 0.6 + (proba * 0.35)
            scored_candidates = list(zip(candidates, scores, cand_texts))
            scored_candidates.sort(key=lambda x: x[1], reverse=True)
            candidates = [c[0] for c in scored_candidates[:k]]
            cand_texts = [c[2] for c in scored_candidates[:k]]
            sim_to_q = [float(c[1]) for c in scored_candidates[:k]]
        except Exception as e:
            print(f"[NovaRAG] Sklearn reranker failed, falling back to cross-encoder: {e}")
            use_sklearn = False

    # Cross-encoder reranking for accurate confidence scores
    ce_scores = None  # Initialize to avoid unbound warning
    if (not use_sklearn) and use_reranker and (not DISABLE_CROSS_ENCODER):
        # Create query-document pairs
        pairs = [[query, text] for text in cand_texts]
        # Get cross-encoder scores (range typically -10 to 10)
        ce_model = get_cross_encoder()
        if ce_model is None:
            # If disabled, fall back to embedding similarity
            use_reranker = False
        else:
            ce_scores = ce_model.predict(pairs)
        
        # Normalize scores to 0-1 range using min-max with boosted range
        import numpy as np
        if ce_scores is not None:
            ce_scores = np.array(ce_scores)
        
            # Clip to reasonable range and normalize
            ce_scores = np.clip(ce_scores, -5, 10)  # Clip extremes
            ce_min, ce_max = ce_scores.min(), ce_scores.max()
            if ce_max > ce_min:
                ce_scores = (ce_scores - ce_min) / (ce_max - ce_min)
            else:
                ce_scores = np.ones_like(ce_scores) * 0.5
            
            # Boost scores to realistic confidence range (60-95%)
            ce_scores = 0.6 + (ce_scores * 0.35)
            
            # Sort candidates by cross-encoder score
            scored_candidates = list(zip(candidates, ce_scores, cand_texts))
            scored_candidates.sort(key=lambda x: x[1], reverse=True)
            
            # Take top candidates after reranking
            candidates = [c[0] for c in scored_candidates[:k]]
            cand_texts = [c[2] for c in scored_candidates[:k]]
            sim_to_q = [float(c[1]) for c in scored_candidates[:k]]
    if (not use_sklearn) and (not use_reranker):
        # Fallback to embedding similarity
        cand_embs = text_model.encode(cand_texts, convert_to_numpy=True)
        q = q_emb[0]
        
        import numpy as np
        def cos(a, b):
            a_n = a / (np.linalg.norm(a) + 1e-12)
            b_n = b / (np.linalg.norm(b) + 1e-12)
            return float(np.dot(a_n, b_n))
        
        sim_to_q = [cos(q, ce) for ce in cand_embs]

    # Now apply MMR for diversity while keeping high confidence scores
    # Small list; still pass small batch size for consistency
    cand_embs = text_model.encode(
        cand_texts,
        convert_to_numpy=True,
        batch_size=min(max(1, EMBED_BATCH_SIZE // 4), max(1, len(cand_texts)))
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
    
    # Add confidence scores to results
    results = []
    for i, idx in enumerate(selected):
        doc = candidates[idx].copy()
        doc["confidence"] = float(selected_scores[i])
        results.append(doc)
    
    return results


def build_standard_prompt(query: str, context_docs: list[dict]) -> str:
    context_text = "\n\n---\n\n".join(
        f"[Source: {d['source']}{f" (pg. {d['page']})" if 'page' in d else ''}]\n{d['text']}" for d in context_docs
    )

    return f"""
You are a precise and helpful vehicle maintenance AI assistant.
You help users troubleshoot and understand vehicle systems.

Always respond in clear professional English.

RULES:
- Use ONLY the manual context below as ground truth.
- If the manual does not contain an answer, say: "The provided manual does not specify this."
- Be structured, practical, and easy to understand.
- When citing sources, include page/paragraph references (e.g., "Para 6-3" or "Table 4-1")

Manuals Context:
-----------------
{context_text}

Question:
---------
{query}

Answer format:
- Short explanation (if needed)
- Then numbered steps (1N)
- Cite sources by filename and page/paragraph number
"""


def build_session_prompt(user_update: str, context_docs: list[dict]) -> str:
    context_text = "\n\n---\n\n".join(
        f"[Source: {d['source']}{f" (pg. {d['page']})" if 'page' in d else ''}]\n{d['text']}" for d in context_docs
    )
    findings = "\n".join(f"- {f}" for f in session_state["finding_log"])

    return f"""
You are a vehicle maintenance troubleshooting assistant.
You are in the MIDDLE of an ongoing diagnostic session.

Session:
- Topic: {session_state['topic']}
- Findings so far:
{findings}

RULES:
- Continue the SAME session (do not restart from zero).
- Provide clear, practical guidance for the user.
- Use ONLY the manuals context below as ground truth.
- If manuals do not cover something, say so.
- Cite sources with page numbers when referencing manuals.

Manuals Context:
----------------
{context_text}

User update:
----------------------------
"{user_update}"

Do:
1) Interpret what the update implies
2) Refine likely root cause (confirm/eliminate)
3) Give the next 13 concrete steps
4) If resolved, how to confirm stability

Respond concise and numbered.
"""


def ensure_model_loaded(model_name: str, max_tokens: int | None = None) -> None:
    """Force Ollama to load the requested model by sending a minimal request.
    This avoids 400 'Model is unloaded' errors on first call.
    """
    try:
        import requests
        payload = {
            "model": model_name,
            "messages": [{"role": "user", "content": "Hi"}],
            "max_tokens": max_tokens or min(64, get_max_tokens(model_name)),
            "temperature": 0.1,
            "stream": False,
        }
        requests.post(
            "http://localhost:11434/v1/chat/completions",
            json=payload,
            timeout=OLLAMA_MODEL_LOAD_TIMEOUT_S,
        )
    except Exception as e:
        print(f"[NovaRAG] Ollama model load check failed: {e}")


def resolve_model_name(requested_model: str) -> str:
    """Ensure the model exists in Ollama; fall back to the first available."""
    try:
        import requests
        resp = requests.get("http://localhost:11434/v1/models", timeout=5)
        if resp.status_code == 200:
            models = resp.json().get("data", [])
            ids = [m.get("id") for m in models if m.get("id")]
            if requested_model in ids:
                print(f"[NovaRAG]  Using requested model: {requested_model}")
                return requested_model
            if ids:
                fallback = ids[0]
                print(f"[NovaRAG]  Model '{requested_model}' not loaded in Ollama")
                print(f"[NovaRAG]  Falling back to: {fallback}")
                print(f"[NovaRAG]  Available models: {', '.join(ids)}")
                print(f"[NovaRAG]  Set NOVA_LLM_LLAMA or NOVA_LLM_OSS env vars to avoid fallback")
                return fallback
            else:
                print(f"[NovaRAG]  No models loaded in Ollama. Load at least one model.")
    except Exception as e:
        print(f"[NovaRAG]  Model resolution check failed: {e}")
        print(f"[NovaRAG]  Ensure Ollama is running on localhost:11434")
    return requested_model


def call_llm(prompt: str, model_name: str, fallback_on_timeout: bool = True) -> str:
    """Call LLM with optional 8B fallback on timeout.
    
    Args:
        prompt: The prompt to send to the model
        model_name: Target model (LLM_LLAMA or LLM_OSS)
        fallback_on_timeout: If True and Qwen times out, retry with 8B model
    """
    system_instructions = (
        "You are an expert vehicle maintenance AI assistant: "
        "precise, helpful, and technically accurate. Use only the provided context; if "
        "something is unknown, say so clearly."
    )
    
    # Map model names to engine keys early (used in both native and HTTP paths)
    model_key = "llama" if "llama" in model_name.lower() or "8b" in model_name.lower() else "qwen"
    
    # === NATIVE ENGINE PATH (llama-cpp-python) ===
    if USE_NATIVE_ENGINE and native_call_llm is not None:
        try:
            # Build full prompt with system instructions
            full_prompt = f"{system_instructions}\n\nUser question:\n{prompt}"
            
            # Call native engine
            print(f"[DEBUG] Calling native engine with model_key={model_key}")
            response = native_call_llm(full_prompt, model=model_key)
            print(f"[DEBUG] Native engine returned successfully, length={len(response)}")
            return response.strip()
            
        except Exception as e:
            print(f"[DEBUG] Native engine exception: {type(e).__name__}: {str(e)[:200]}")
            error_msg = str(e).lower()
            is_timeout = "timeout" in error_msg or "timed out" in error_msg
            
            # Fallback to 8B on Qwen timeout
            if is_timeout and fallback_on_timeout and model_key == "qwen":
                print(f"[NovaRAG] ⚠️  Qwen timeout, falling back to 8B...")
                try:
                    full_prompt = f"{system_instructions}\n\nUser question:\n{prompt}"
                    response = native_call_llm(full_prompt, model="llama")
                    print(f"[NovaRAG] ✅ Fallback to 8B succeeded")
                    return response.strip()
                except Exception as fallback_error:
                    print(f"[NovaRAG] ❌ Fallback failed: {fallback_error}")
                    raise
            raise
    
    # === HTTP CLIENT PATH (Ollama API) ===
    # Ensure client exists (can be None if Ollama was unavailable at import time)
    global client
    if client is None:
        try:
            from openai import OpenAI
            client = OpenAI(
                base_url="http://127.0.0.1:11434/v1",
                api_key="ollama",
                timeout=OLLAMA_TIMEOUT_S,
            )
        except Exception as e:
            raise RuntimeError(f"Ollama client unavailable: {e}")

    # Resolve to an available model and pre-load it
    resolved_model = resolve_model_name(model_name)
    ensure_model_loaded(resolved_model)
    
    try:
        completion = client.chat.completions.create(
            model=resolved_model,
            # Some local prompt templates only allow user/assistant roles;
            # fold the system prompt into the user message to avoid template errors.
            messages=[
                {
                    "role": "user",
                    "content": f"{system_instructions}\n\nUser question:\n{prompt}",
                },
            ],
            temperature=0.15,
            max_tokens=get_max_tokens(resolved_model),
        )
        content = completion.choices[0].message.content
        return content.strip() if content else ""
        
    except Exception as e:
        error_msg = str(e).lower()
        is_timeout = "timeout" in error_msg or "timed out" in error_msg
        
        # If Qwen times out and fallback is enabled, retry with 8B
        if is_timeout and fallback_on_timeout and model_name == LLM_OSS:
            print(f"[NovaRAG] ⚠️  Qwen timeout detected, falling back to 8B model...")
            try:
                fallback_model = resolve_model_name(LLM_LLAMA)
                ensure_model_loaded(fallback_model)
                completion = client.chat.completions.create(
                    model=fallback_model,
                    messages=[
                        {
                            "role": "user",
                            "content": f"{system_instructions}\n\nUser question:\n{prompt}",
                        },
                    ],
                    temperature=0.15,
                    max_tokens=get_max_tokens(fallback_model),
                )
                content = completion.choices[0].message.content
                print(f"[NovaRAG] ✅ Fallback to 8B succeeded")
                return content.strip() if content else ""
            except Exception as fallback_error:
                print(f"[NovaRAG] ❌ Fallback also failed: {fallback_error}")
                raise
        
        # Retry once after an explicit load attempt if first call failed (non-timeout)
        print(f"[NovaRAG] LLM call failed: {e}. Retrying after load...")
        ensure_model_loaded(resolved_model)
        completion = client.chat.completions.create(
            model=resolved_model,
            messages=[
                {
                    "role": "user",
                    "content": f"{system_instructions}\n\nUser question:\n{prompt}",
                },
            ],
            temperature=0.15,
            max_tokens=get_max_tokens(resolved_model),
        )

        content = completion.choices[0].message.content
        return content.strip() if content else ""


# =======================
# SESSION EXPORT
# =======================

def export_session_to_text() -> str:
    """Export current session to formatted text report."""
    if not session_state["session_id"]:
        return "No active session to export."
    
    lines = []
    lines.append("=" * 70)
    lines.append("NOVA RAG - TROUBLESHOOTING SESSION REPORT")
    lines.append("=" * 70)
    lines.append(f"Session ID: {session_state['session_id']}")
    lines.append(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"Model: {session_state.get('model', 'Unknown')}")
    lines.append(f"Mode: {session_state.get('mode', 'Unknown')}")
    lines.append(f"Total Turns: {session_state['turns']}")
    lines.append("")
    lines.append("TOPIC:")
    lines.append(session_state.get('topic', 'N/A'))
    lines.append("")
    lines.append("FINDINGS LOG:")
    lines.append("-" * 70)
    for i, finding in enumerate(session_state.get('finding_log', []), 1):
        lines.append(f"{i}. {finding}")
    lines.append("")
    
    if session_state.get('feedback'):
        lines.append("FEEDBACK:")
        lines.append("-" * 70)
        for fb in session_state['feedback']:
            lines.append(f"- {fb}")
        lines.append("")
    
    lines.append("=" * 70)
    lines.append("End of Report")
    lines.append("=" * 70)
    
    return "\n".join(lines)


def save_session_report() -> str:
    """Save session report to file and return filepath."""
    if not session_state["session_id"]:
        return "No active session to save."
    
    report_text = export_session_to_text()
    
    reports_dir = INDEX_DIR / "session_reports"
    reports_dir.mkdir(exist_ok=True)
    
    filename = f"session_{session_state['session_id']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    filepath = reports_dir / filename
    
    with filepath.open("w", encoding="utf-8") as f:
        f.write(report_text)
    
    return f" Session report saved to:\n{filepath}"


# =======================
# ERROR HANDLING & SUGGESTIONS
# =======================

COMMON_SUBSYSTEMS = [
    "engine", "transmission", "brakes", "steering", "suspension",
    "cooling", "electrical", "fuel", "exhaust", "drivetrain",
    "battery", "alternator", "starter", "ignition", "sensors",
    "HVAC", "power", "diagnostic", "maintenance"
]

def suggest_keywords(query: str) -> str:
    """Suggest related keywords when no results found."""
    query_lower = query.lower()
    
    mentioned = [s for s in COMMON_SUBSYSTEMS if s.lower() in query_lower]
    
    if mentioned:
        return f"Try being more specific about the issue with {', '.join(mentioned)}. Include alarm codes, symptoms, or component names."
    else:
        suggestions = ", ".join(COMMON_SUBSYSTEMS[:12])
        return f"No subsystem keywords detected. Try including: {suggestions}"


# =======================
# MODEL SELECTION
# =======================

def choose_model(query_lower: str, mode: str) -> tuple[str, str]:
    """Returns (model_name, decision_reason)"""
    if mode == "LLAMA (Fast)":
        return LLM_LLAMA, "Manual: LLAMA (Fast)"
    # Back-compat: UI label/value changed over time (GPT-OSS -> Qwen).
    if mode in {"GPT-OSS (Deep)", "Qwen 14B (Deep)", "Qwen 14B (Deep Reasoning)"}:
        return LLM_OSS, f"Manual: {mode}"

    if any(k in query_lower for k in DEEP_KEYWORDS):
        return LLM_OSS, "Auto: deep keywords detected  GPT-OSS"
    if any(k in query_lower for k in FAST_KEYWORDS):
        return LLM_LLAMA, "Auto: procedure keywords detected  LLAMA"
    if any(t in query_lower for t in TROUBLESHOOT_TRIGGERS):
        return LLM_LLAMA, "Auto: troubleshooting keywords detected  LLAMA"

    return LLM_OSS, "Auto: fallback  GPT-OSS"


# =======================
# MULTI-TURN CONTEXT & ALARM DETECTION
# =======================

def build_conversation_context() -> str:
    """Build conversation context from recent turn history."""
    if not session_state.get("turn_history"):
        return ""
    
    context_lines = ["PREVIOUS CONVERSATION HISTORY:"]
    # Include last 3 turns for context window management
    recent_turns = session_state["turn_history"][-3:]
    for i, (q, a) in enumerate(recent_turns, 1):
        context_lines.append(f"\nTurn {i}:")
        context_lines.append(f"Q: {q[:150]}")  # Truncate long questions
        context_lines.append(f"A: {a[:200]}")  # Truncate long answers
    
    return "\n".join(context_lines) + "\n\n"


def detect_error_code(query: str) -> dict:
    """Detect error code queries and return metadata if found."""
    q = query.lower()
    import re
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


# =======================
# TEXT HANDLER
# =======================

def nova_text_handler(question: str, mode: str, npc_name: str | None = None, resume_session_id: str | None = None, fallback_mode: str | None = None) -> tuple[str | dict, str]:
    # Avoid Windows console encoding crashes on emojis by sanitizing preview
    try:
        safe_preview = (question or "")[:80]
        safe_preview = re.sub(r"[^\x20-\x7E]", "?", safe_preview)
    except Exception:
        safe_preview = "(preview unavailable)"
    print(f"[DEBUG] nova_text_handler called with mode={mode}, question={safe_preview}")
    
    if not question or not question.strip():
        return "No question entered.", ""

    q_raw = question.strip()
    q_original = q_raw  # Keep original for logging
    
    # Default warning holder for multi-query mixed cases
    multi_query_warning: str | None = None

    # === HYBRID INJECTION HANDLING (by intent, not syntax) ===
    # Step 1: Detect injection syntax (form only - don't decide safety yet)
    injection_meta = RiskAssessment.detect_injection_syntax(q_raw)
    if injection_meta.get("has_injection"):
        print(f"[INJECTION] Syntax detected: {injection_meta.get('injection_markers', [])[:2]}")
        print(f"[INJECTION] Original: {q_original[:80]}")
        print(f"[INJECTION] Core extracted: {injection_meta['core_question'][:80]}")
    
    # Step 2: Extract core question(s) - strip wrapper BEFORE any decisions
    # This ensures intent classifier never sees injection syntax
    q_clean = injection_meta.get("core_question", q_raw).strip() if injection_meta.get("has_injection") else q_raw
    
    # Step 3: Assess risk on CLEAN segments (multi-query detection + per-segment risk)
    multi_assessment = RiskAssessment.assess_multi_query(q_clean)
    
    # Step 4: Decision rules (conservative - any dangerous segment blocks entire request)
    if multi_assessment.get("is_multi_query"):
        print(f"[MULTI-QUERY] Detected {len(multi_assessment['sub_assessments'])} segments")
        print(f"[MULTI-QUERY] Safe: {len(multi_assessment['safe_queries'])}, Dangerous: {len(multi_assessment['dangerous_queries'])}")
        
        # Rule 1: All segments dangerous → refuse entire request
        if multi_assessment["all_dangerous"]:
            print("[SAFETY] All segments dangerous - refusing entirely")
            refusal_msg = f"I cannot help with any of those requests. {multi_assessment['sub_assessments'][0]['assessment']['reasoning']}"
            return refusal_msg, "multi_query_all_dangerous"
        
        # Rule 2: Mixed safe + dangerous → refuse (never answer part if another part is dangerous)
        if multi_assessment["has_dangerous_parts"] and multi_assessment["has_safe_parts"]:
            print("[SAFETY] Mixed intent detected - refusing entire request (contains dangerous segment)")
            override_msg = multi_assessment["override_response"]
            if override_msg:
                return override_msg, "multi_query_mixed_intent_blocked"
            else:
                return "I cannot process this request because it contains both safe and unsafe queries. Please separate them into individual requests.", "multi_query_mixed_blocked"
        
        # Rule 3: All segments safe → answer using first safe segment
        if multi_assessment["has_safe_parts"] and not multi_assessment["has_dangerous_parts"]:
            q_raw = multi_assessment["safe_queries"][0] if multi_assessment["safe_queries"] else q_clean
            multi_query_warning = None  # No warning needed for all-safe
    else:
        # Single segment - use normal risk assessment
        risk_assessment = multi_assessment["sub_assessments"][0]["assessment"]
        
        print(f"[RISK] {risk_assessment['risk_level'].value} - {risk_assessment['reasoning']}")
        
        # Emergency override: return pre-defined safety response immediately
        if risk_assessment.get("is_emergency") or risk_assessment.get("override_response"):
            override_msg = risk_assessment["override_response"]
            risk_header = RiskAssessment.format_risk_header(risk_assessment)
            full_response = f"{risk_header}\n\n{override_msg}"
            
            if risk_assessment.get("is_emergency"):
                decision_tag = "emergency_override | life_safety"
            elif risk_assessment.get("is_fake_part"):
                decision_tag = "hallucination_prevention | fake_part"
            else:
                decision_tag = f"risk_override | {risk_assessment['risk_level'].value}"
            
            print(f"[SAFETY] Override activated: {decision_tag}")
            return full_response, decision_tag
        
        # For safe single queries, use cleaned version (injection wrapper stripped)
        q_raw = q_clean

    # After all extraction/stripping, recompute lowercase for downstream checks
    q_lower = q_raw.lower()
    
    # Log decision for audit (internal only - never shown to user)
    if injection_meta.get("has_injection"):
        print(f"[INJECTION-DECISION] Original had injection syntax, assessed CONTENT only")
        print(f"[INJECTION-DECISION] Final question for processing: {q_raw[:80]}")

    # Safety fast-path: refuse out-of-scope and unsafe-intent queries BEFORE retrieval.
    # This avoids expensive embedding/model warmup for queries we should not answer anyway.
    try:
        intent_meta = agent_router.classify_intent(q_raw)
        if isinstance(intent_meta, dict) and intent_meta.get("agent") == "refusal":
            intent = (intent_meta.get("intent") or "refusal").strip()
            
            # OPTION 1: Out-of-scope vehicle type detection (motorcycle, boat, aircraft, etc.)
            if intent == "out_of_scope_vehicle":
                message = intent_meta.get("refusal_reason", 
                    "This manual covers automobiles only. Please consult a vehicle-specific manual for your equipment type.")
                reason = "out_of_scope_vehicle"
            elif intent == "unsafe_intent":
                reason = "unsafe_intent"
                message = (
                    "I can't help with that request because it appears to be unsafe or attempts to bypass safety guidance. "
                    "Please ask a safe, manufacturer-recommended maintenance or diagnostic question."
                )
            else:
                reason = "out_of_scope"
                message = "This question is outside the knowledge base (vehicle maintenance topics). Please ask about maintenance procedures, diagnostics, or specifications."
            refusal = {
                "response_type": "refusal",
                "reason": reason,
                "policy": "Scope & Safety",
                "message": message,
                "question": q_raw,
            }
            return refusal, f"refusal | {reason}"
    except Exception:
        # If intent classification fails, continue with normal handling.
        pass
    
    # Fast path for evaluator OR forced fallback: skip heavy processing and return retrieval-only answer
    force_retrieval_only = isinstance(fallback_mode, str) and (fallback_mode.lower() == "retrieval-only")
    if force_retrieval_only or (mode or "").lower() in {"eval", "retrieval", "retrieval-only", "fast eval"} or os.environ.get("NOVA_EVAL_FAST", "0") == "1":
        print(f"[DEBUG] Fast eval mode activated for: {q_raw[:80]}")
        context_docs = retrieve(q_raw, k=12, top_n=6)
        print(f"[DEBUG] Retrieved {len(context_docs)} docs")
        if not context_docs:
            return "[ERROR] No context retrieved.", "retrieval-only | no-context"
        avg_confidence = sum(d.get("confidence", 0) for d in context_docs) / len(context_docs)
        error_meta = detect_error_code(q_raw)
        error_id = error_meta.get("error_id") if error_meta else None
        top = context_docs[0] if context_docs else {}
        snippet = (top.get("snippet") or top.get("text") or "").strip().replace("\n", " ")
        src = f"{top.get('source','')} p{top.get('page','')}".strip()
        pieces = []
        if error_id:
            pieces.append(f"Alarm {error_id} summary:")
        if snippet:
            pieces.append(snippet[:280])
        if src:
            pieces.append(f"Source: {src}")
        answer = "\n".join(pieces) if pieces else "No context available."
        print(f"[DEBUG] Fast eval returning answer (len={len(answer)})")
        suffix = "forced" if force_retrieval_only else "retrieval-only"
        return answer, f"{suffix} | Confidence: {avg_confidence:.2%}"
    
    search_history.add(q_raw)

    if resume_session_id:
        if resume_session(resume_session_id):
            return f" Resumed session: {session_state['topic'][:80]}...\nTurns so far: {session_state['turns']}", "session-resumed"
        else:
            return "[ERROR] Could not load that session.", "session-load-failed"

    if any(trigger in q_lower for trigger in END_SESSION_TRIGGERS):
        reset_session(save_to_db=True)
        return " Troubleshooting session saved & reset. New case whenever you're ready.", "session-reset"

    if mode and "NPC" in mode.upper():
        model_name = f"npc:{(npc_name or 'sibiji')}"
        decision = f"NPC: {(npc_name or 'sibiji')}"
    else:
        model_name, decision = choose_model(q_lower, mode)
        # Safety warning: mode override bypasses intent-based routing
        if mode and ("LLAMA" in mode.upper() or "GPT" in mode.upper()):
            print(f"[NIC-SAFETY] Mode override '{mode}' bypasses safety routing for query: {q_raw[:50]}...")

    # Track the actual model used after Ollama availability/fallback resolution.
    last_resolved_model: str | None = None

    # Provide an LLM callable that supports both 1-arg and 2-arg (prompt, model) styles.
    # Model aliases supported: "llama" and "gpt-oss".
    def llm_dispatch(prompt_text: str, requested_model: str | None = None, **kwargs) -> str:
        nonlocal last_resolved_model
        target_model = model_name
        if isinstance(requested_model, str) and requested_model:
            alias = requested_model.strip().lower()
            if alias in {"llama", "fast"}:
                target_model = LLM_LLAMA
            elif alias in {"gpt-oss", "gpt_oss", "oss", "deep"}:
                target_model = LLM_OSS
            else:
                # Allow passing an explicit Ollama model id (e.g., "qwen2.5-coder:14b")
                target_model = requested_model

        # Resolve to what Ollama will actually run (may fall back).
        try:
            last_resolved_model = resolve_model_name(target_model)
        except Exception:
            last_resolved_model = target_model

        # call_llm will resolve again internally; keep this call simple.
        return call_llm(prompt_text, last_resolved_model)

    if (not session_state["active"]) and any(t in q_lower for t in TROUBLESHOOT_TRIGGERS):
        session_id = start_new_session(q_raw, model_name, mode)

        context_docs = retrieve(q_raw, k=12, top_n=6)
        context_docs = _boost_error_docs(q_raw, context_docs)
        if not context_docs:
            reset_session(save_to_db=False)
            suggestion = suggest_keywords(q_raw)
            return (
                f"[ERROR] I couldn't retrieve relevant manual context for that question.\n\nSuggestion: {suggestion}",
                f"{model_name} | {decision}"
            )

        avg_confidence = sum(d.get("confidence", 0) for d in context_docs) / len(context_docs)
        
        # =============================================================================
        # OPTION 3: CONFIDENCE-GATED VEHICLE SCOPE CHECK
        # =============================================================================
        # If confidence is low AND query mentions ambiguous vehicle terms, ask for clarification
        # This catches edge cases where vehicle type wasn't explicitly detected in pre-filter
        AMBIGUOUS_VEHICLE_TERMS = ["my vehicle", "my car", "the engine", "my engine", "this vehicle"]
        LOW_CONFIDENCE_THRESHOLD = 0.65
        
        if avg_confidence < LOW_CONFIDENCE_THRESHOLD:
            # Check if query could be about a non-automobile but wasn't caught by pre-filter
            ambiguous_context_words = ["generic", "universal", "any vehicle", "all vehicles"]
            has_ambiguous_term = any(term in q_lower for term in AMBIGUOUS_VEHICLE_TERMS + ambiguous_context_words)
            
            if has_ambiguous_term:
                print(f"[CONFIDENCE-GATE] Low confidence ({avg_confidence:.2%}) + ambiguous vehicle term detected")
                # Don't refuse, but add a disclaimer to the response
                pass  # Let it continue but flag for disclaimer in response

        # **HALLUCINATION BLOCKER**: If retrieval confidence is too low, skip LLM and return snippet instead
        CONFIDENCE_THRESHOLD = 0.60  # Require 60%+ confidence to use LLM
        if avg_confidence < CONFIDENCE_THRESHOLD:
            print(f"[BLOCKER] Retrieval confidence {avg_confidence:.2%} < {CONFIDENCE_THRESHOLD:.0%}  skipping LLM, returning Fast Eval")
            top = context_docs[0] if context_docs else {}
            snippet = (top.get("snippet") or top.get("text") or "").strip().replace("\n", " ")
            src = f"{top.get('source','')} p{top.get('page','')}".strip()
            pieces = [snippet[:280]] if snippet else []
            if src:
                pieces.append(f"Source: {src}")
            answer = "\n".join(pieces) if pieces else " Retrieved context too weak for confident answer."
            reset_session(save_to_db=False)
            return answer, f"eval-blocked | Confidence: {avg_confidence:.2%} (blocker: {CONFIDENCE_THRESHOLD:.0%})"

        prompt = build_standard_prompt(q_raw, context_docs)
        answer = agent_router.handle(
            prompt=prompt,
            model=model_name,
            mode=mode,
            session_state=session_state,
            context_docs=context_docs,
            llm_call_fn=llm_dispatch,
        )
        # Return answer with confidence as separate value
        used = last_resolved_model or model_name
        return answer, f"{used} | {decision} | Session: {session_id} | Confidence: {avg_confidence:.2%}"

    if session_state["active"]:
        session_state["finding_log"].append(q_raw)
        session_state["turns"] += 1

        retrieval_query = session_state["topic"] or q_raw
        context_docs = retrieve(retrieval_query, k=12, top_n=6)

        # Error code boosting: reorder results if query contains a diagnostic code
        error_meta = detect_error_code(q_raw)
        if error_meta and context_docs:
            eid = error_meta.get("error_id")
            key_terms = [f"code {eid}", f"error {eid}", eid]
            def score(doc):
                t = (doc.get("text") or "").lower()
                return int(any(term in t for term in key_terms)) + doc.get("confidence", 0)
            context_docs = sorted(context_docs, key=score, reverse=True)

        # Build context including turn history
        conv_context = build_conversation_context()

        if not context_docs:
            prompt = f"""
You are a vehicle maintenance assistant in an ongoing diagnostic session.
Manuals retrieval returned no context. Continue logically using only the user's updates.

{conv_context}
User update:
"{q_raw}"

Give the next 13 steps and keep it practical.
"""
        else:
            base_prompt = build_session_prompt(q_raw, context_docs)
            # Prepend conversation context if there's previous history
            prompt = conv_context + base_prompt if conv_context else base_prompt

        answer = agent_router.handle(
            prompt=prompt,
            model=model_name,
            mode=mode,
            session_state=session_state,
            context_docs=context_docs,
            llm_call_fn=llm_dispatch,
        )
        used = last_resolved_model or model_name
        return answer, f"{used} | {decision}"

    # Normal path: non-eval, non-session queries
    context_docs = retrieve(q_raw, k=12, top_n=6)
    context_docs = _boost_error_docs(q_raw, context_docs)
    if not context_docs:
        suggestion = suggest_keywords(q_raw)
        return (
            f"[ERROR] No relevant technical documentation was found.\n\nSuggestion: {suggestion}",
            f"{model_name} | {decision}"
        )

    avg_confidence = sum(d.get("confidence", 0) for d in context_docs) / len(context_docs)
    
    # DEBUG: Print context_docs confidence values
    print(f"[DEBUG-BACKEND] Passing {len(context_docs)} docs to agent with avg confidence {avg_confidence:.2%}")
    print(f"[DEBUG-BACKEND] Individual confidences: {[d.get('confidence', 0.0) for d in context_docs]}")
    
    answer = agent_router.handle(
        # IMPORTANT: pass the raw user question into the NIL router.
        # The router already receives `context_docs` and will build its own prompt.
        # Passing a composed prompt here can contaminate intent classification (e.g., keywords from context).
        prompt=q_raw,
        model=model_name,
        mode=mode,
        session_state=session_state,
        context_docs=context_docs,
        llm_call_fn=llm_dispatch,
    )
    
    # Normalize response to consistent WARNINGS/STEPS/VERIFY format
    # This prevents mixed JSON/prose outputs that confuse RAGAS evaluators
    answer_normalized = normalize_response(answer)
    
    used = last_resolved_model or model_name
    return answer_normalized, f"{used} | {decision} | Confidence: {avg_confidence:.2%}"


# =======================
# VISION: DIAGRAM SEARCH
# =======================

def vision_search(user_image: Image.Image, top_k: int = 5):
    if user_image is None:
        return []

    if vision_embeddings is None or vision_paths is None or vision_model is None:
        return []

    img_emb = vision_model.encode(user_image, convert_to_tensor=True)  # type: ignore[arg-type]
    img_emb = torch.nn.functional.normalize(img_emb, p=2, dim=-1)

    scores = (vision_embeddings @ img_emb.unsqueeze(1)).squeeze(1)
    top_k = max(1, min(int(top_k), len(scores)))
    vals, idxs = torch.topk(scores, k=top_k)

    results = []
    for score, idx in zip(vals, idxs):
        path = vision_paths[int(idx)]
        if os.path.exists(path):
            caption = f"{Path(path).name} | sim={float(score):.3f}"
            results.append((path, caption))
    return results
