"""
Function Gemma fast query pre-filter/classifier.

Stage 4: Optional acceleration layer that runs BEFORE safety checks.
Provides confidence hints and routing suggestions, but does NOT override safety gates.

Design Principles:
- Fast (<500ms): Lightweight 300MB model for instant classification
- Graceful timeout: If Gemma slow, skip it and use normal routing
- Safety-first: All safety checks remain authoritative
- Informational: Used only for acceleration hints, not decisions
"""

from __future__ import annotations
from typing import Optional, Dict, Any, Tuple
import os
import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

logger = logging.getLogger(__name__)

# Singleton thread pool for Gemma calls (max 1 worker to avoid saturation)
_gemma_executor: Optional[ThreadPoolExecutor] = None


def get_gemma_executor() -> ThreadPoolExecutor:
    """Get or create Gemma executor (single-threaded for lightweight model)."""
    global _gemma_executor
    if _gemma_executor is None:
        _gemma_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="gemma")
    return _gemma_executor


def gemma_quick_classify(
    query: str,
    timeout_sec: float = 2.0,
) -> Dict[str, Any]:
    """
    Fast query classification using Function Gemma (300MB, ~100ms).
    
    Returns confidence hints for routing acceleration, NOT authoritative decisions.
    All actual safety checks happen in query_handler (kept authoritative).
    
    Args:
        query: User's question text
        timeout_sec: Max time to wait for Gemma response (2s default)
    
    Returns:
        Dict with keys:
            - success: bool (Gemma call succeeded)
            - query_confidence: float 0-1 (how confident Gemma is about this query)
            - estimated_type: str (troubleshooting|faq|general|unclear)
            - retrieval_likely_needed: bool (Gemma thinks retrieval might help)
            - gemma_time_ms: float (how long Gemma took)
            - error: Optional[str] (if failed)
    """
    import time
    start_time = time.time()
    
    try:
        from core.generation.llm_gateway import client, LLM_LLAMA
        
        if client is None:
            return {
                "success": False,
                "error": "Ollama client not available",
                "query_confidence": 0.5,
                "estimated_type": "unclear",
                "retrieval_likely_needed": True,
                "gemma_time_ms": 0.0,
            }
        
        # Fast prompt for Gemma classification
        classification_prompt = f"""Classify this vehicle maintenance query in ONE word:
Query: "{query[:100]}"

Classification (choose ONE):
- troubleshooting (diagnosing a problem)
- faq (general info question)
- general (other maintenance topic)
- unclear (can't tell)

Answer with ONLY the word:"""
        
        # Run Gemma in thread pool with timeout
        executor = get_gemma_executor()
        future = executor.submit(
            _call_gemma_blocking,
            classification_prompt,
            client,
            LLM_LLAMA,
        )
        
        try:
            response_text = future.result(timeout=timeout_sec)
            elapsed_ms = (time.time() - start_time) * 1000
            
            # Parse response
            classification = response_text.strip().lower()
            valid_types = {"troubleshooting", "faq", "general", "unclear"}
            estimated_type = classification if classification in valid_types else "unclear"
            
            # Confidence heuristics
            query_confidence = 0.8 if estimated_type != "unclear" else 0.4
            retrieval_likely = estimated_type in {"troubleshooting", "general"}
            
            logger.info(
                f"[GEMMA] Classification: {estimated_type} (confidence={query_confidence:.0%}, time={elapsed_ms:.0f}ms)"
            )
            
            return {
                "success": True,
                "query_confidence": query_confidence,
                "estimated_type": estimated_type,
                "retrieval_likely_needed": retrieval_likely,
                "gemma_time_ms": elapsed_ms,
                "error": None,
            }
        
        except FuturesTimeoutError:
            logger.warning(f"[GEMMA] Classification timeout (>{timeout_sec}s), skipping")
            return {
                "success": False,
                "error": f"Timeout after {timeout_sec}s",
                "query_confidence": 0.5,
                "estimated_type": "unclear",
                "retrieval_likely_needed": True,
                "gemma_time_ms": (time.time() - start_time) * 1000,
            }
    
    except Exception as e:
        logger.warning(f"[GEMMA] Classification error: {e}")
        return {
            "success": False,
            "error": str(e)[:100],
            "query_confidence": 0.5,
            "estimated_type": "unclear",
            "retrieval_likely_needed": True,
            "gemma_time_ms": (time.time() - start_time) * 1000,
        }


def _call_gemma_blocking(prompt: str, client, model_name: str) -> str:
    """Blocking call to Gemma via Ollama HTTP API."""
    try:
        response = client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=10,
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.debug(f"[GEMMA] HTTP call failed: {e}")
        raise


def shutdown_gemma() -> None:
    """Gracefully shutdown Gemma executor."""
    global _gemma_executor
    if _gemma_executor is not None:
        _gemma_executor.shutdown(wait=True)
        _gemma_executor = None


__all__ = [
    "gemma_quick_classify",
    "shutdown_gemma",
    "get_gemma_executor",
]
