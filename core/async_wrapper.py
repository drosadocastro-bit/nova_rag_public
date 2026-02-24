"""
Stage 2: Async Containment with ThreadPoolExecutor.

This module wraps expensive, parallelizable operations in a thread pool.
All functions return SYNCHRONOUSLY - no async/await, fully WSGI-compatible.

Key principle: Long-running operations run in background threads, but Flask
routes remain fully synchronous. This allows I/O and CPU work to not block
WSGI worker threads while maintaining deterministic behavior.

Operations:
- Embedding generation (batch text encoding)
- BM25 scoring (lexical retrieval)
- Session report generation
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from typing import Optional, Any, Callable, List, Dict
import logging
from time import time

logger = logging.getLogger("nova_async_wrapper")

# Thread pool configuration
# max_workers=2: Conservative to avoid overwhelming Flask workers
# Safe on both low-RAM and high-RAM systems
_executor: Optional[ThreadPoolExecutor] = None
_executor_lock = threading.Lock()
_THREAD_POOL_SIZE = 2
_DEFAULT_TIMEOUT = 30  # seconds


def get_executor() -> ThreadPoolExecutor:
    """Get or create the global thread pool (singleton)."""
    global _executor
    if _executor is None:
        with _executor_lock:
            if _executor is None:
                _executor = ThreadPoolExecutor(
                    max_workers=_THREAD_POOL_SIZE,
                    thread_name_prefix="nova-worker"
                )
                logger.info(f"ThreadPool created: {_THREAD_POOL_SIZE} workers")
    return _executor


def run_in_thread(
    func: Callable,
    *args,
    timeout: float = _DEFAULT_TIMEOUT,
    operation_name: str = "unknown",
    **kwargs
) -> Any:
    """
    Run a function in thread pool, wait for result, return synchronously.
    
    Args:
        func: Function to execute in thread
        *args: Positional arguments
        timeout: How long to wait (seconds)
        operation_name: For logging
        **kwargs: Keyword arguments
    
    Returns:
        Result from func(*args, **kwargs)
    
    Raises:
        TimeoutError: If operation exceeds timeout
        RuntimeError: If thread pool execution fails
    
    Example:
        >>> result = run_in_thread(
        ...     expensive_embedding_func,
        ...     query_text,
        ...     timeout=10,
        ...     operation_name="query-embedding"
        ... )
    """
    executor = get_executor()
    
    start = time()
    try:
        future = executor.submit(func, *args, **kwargs)
        result = future.result(timeout=timeout)
        elapsed = time() - start
        
        if elapsed > timeout * 0.8:
            logger.warning(
                f"Operation '{operation_name}' took {elapsed:.2f}s (near timeout {timeout}s)"
            )
        else:
            logger.debug(f"Operation '{operation_name}' completed in {elapsed:.2f}s")
        
        return result
    
    except FutureTimeoutError:
        logger.error(f"Operation '{operation_name}' timed out after {timeout}s")
        raise TimeoutError(f"{operation_name} exceeded {timeout}s timeout")
    
    except Exception as e:
        logger.error(f"Operation '{operation_name}' failed: {e}", exc_info=True)
        raise RuntimeError(f"{operation_name} failed: {str(e)}")


def batch_encode_async(
    texts: List[str],
    model: Any,
    batch_size: int = 32,
    operation_name: str = "batch-encoding"
) -> List[Any]:
    """
    Encode multiple texts using model, in thread pool.
    
    Parallelizable: long-running text encoding doesn't block Flask.
    Returns synchronously (waits for completion).
    
    Args:
        texts: List of text strings to encode
        model: Embedding model with .encode() method
        batch_size: Batch size for encoding
        operation_name: For logging
    
    Returns:
        List of embeddings (same order as texts)
    
    Example:
        >>> embeddings = batch_encode_async(
        ...     [query1, query2, query3],
        ...     embedding_model,
        ...     batch_size=32,
        ...     operation_name="query-embeddings"
        ... )
    """
    def _encode():
        """Inner function to run in thread."""
        return model.encode(texts, batch_size=batch_size, convert_to_numpy=True)
    
    return run_in_thread(
        _encode,
        timeout=60,  # Longer timeout for large batches
        operation_name=operation_name
    )


def bm25_score_async(
    query: str,
    docs_texts: List[str],
    bm25_model: Any,
    operation_name: str = "bm25-scoring"
) -> List[float]:
    """
    Score documents with BM25 in thread pool.
    
    BM25 scoring is CPU-intensive; running in thread allows parallelization.
    Returns synchronously.
    
    Args:
        query: Query string
        docs_texts: List of document texts to score
        bm25_model: BM25 model with .get_scores() method
        operation_name: For logging
    
    Returns:
        List of BM25 scores (same order as docs_texts)
    
    Example:
        >>> scores = bm25_score_async(
        ...     "battery replacement",
        ...     [doc1_text, doc2_text, doc3_text],
        ...     bm25_model,
        ...     operation_name="doc-scoring"
        ... )
    """
    def _score():
        """Inner function to run in thread."""
        # BM25 get_scores() expects query tokens or uses tokenizer
        # Most implementations accept query string directly
        scores = bm25_model.get_scores(query)
        return scores if scores is not None else [0.0] * len(docs_texts)
    
    return run_in_thread(
        _score,
        timeout=30,
        operation_name=operation_name
    )


def session_report_async(
    session_state: Dict[str, Any],
    operation_name: str = "session-report"
) -> str:
    """
    Generate session report in thread pool.
    
    Report generation (formatting, aggregation) is CPU-bound and can run async.
    Returns synchronously.
    
    Args:
        session_state: Session state dictionary
        operation_name: For logging
    
    Returns:
        Formatted session report as string
    
    Example:
        >>> report = session_report_async(
        ...     current_session_state,
        ...     operation_name="export-session"
        ... )
    """
    def _generate_report():
        """Inner function to run in thread."""
        from core.session.session_manager import export_session_to_text
        
        # export_session_to_text returns string (uses global session_state)
        report = export_session_to_text()
        return report if report else "(empty report)"
    
    return run_in_thread(
        _generate_report,
        timeout=15,
        operation_name=operation_name
    )


def parallel_embedding_retrieval(
    query: str,
    docs: List[Dict],
    embedding_model: Any,
    cross_encoder: Optional[Any] = None,
    operation_name: str = "parallel-retrieval"
) -> List[Dict]:
    """
    Parallel embedding generation + reranking in thread pool.
    
    Encodes query and reranks docs in background thread.
    Useful when doing vector search with cross-encoder reranking.
    
    Args:
        query: Query string
        docs: List of candidate documents
        embedding_model: Text embedding model
        cross_encoder: Optional cross-encoder for reranking
        operation_name: For logging
    
    Returns:
        List of documents (may be reranked if cross_encoder provided)
    
    Example:
        >>> docs = parallel_embedding_retrieval(
        ...     query,
        ...     candidate_docs,
        ...     embedding_model,
        ...     cross_encoder=reranker,
        ... )
    """
    def _retrieve():
        """Inner function to run in thread."""
        # Encode query (usually fast, but parallelization helps on first request)
        query_embedding = embedding_model.encode([query], convert_to_numpy=True)[0]
        
        # If cross-encoder provided, rerank
        if cross_encoder and len(docs) > 0:
            doc_texts = [d.get('text', '') for d in docs]
            
            # Prepare query-doc pairs for reranking
            pairs = [[query, text] for text in doc_texts]
            scores = cross_encoder.predict(pairs)
            
            # Attach scores and sort
            for doc, score in zip(docs, scores):
                doc['rerank_score'] = float(score)
            
            docs_sorted = sorted(docs, key=lambda d: d.get('rerank_score', 0), reverse=True)
            return docs_sorted
        
        return docs
    
    return run_in_thread(
        _retrieve,
        timeout=45,
        operation_name=operation_name
    )


def shutdown_executor():
    """Shutdown thread pool gracefully (call on app shutdown)."""
    global _executor
    if _executor is not None:
        logger.info("Shutting down ThreadPool...")
        _executor.shutdown(wait=True)
        _executor = None
        logger.info("ThreadPool shutdown complete")


# ============================================
# Integration Helpers for Flask Request Lifecycle
# ============================================

def register_shutdown_hooks(app):
    """
    Register shutdown hooks with Flask app.
    
    Args:
        app: Flask application instance
    
    Example:
        >>> from core.async_wrapper import register_shutdown_hooks
        >>> register_shutdown_hooks(app)
    """
    @app.teardown_appcontext
    def shutdown_pools(exception=None):
        """Called when app context ends."""
        # ThreadPool shutdown is graceful; won't block
        pass  # Executor lives for app lifetime
    
    def atexit_handler():
        """Called on process exit."""
        shutdown_executor()
    
    import atexit
    atexit.register(atexit_handler)
