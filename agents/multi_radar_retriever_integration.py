#!/usr/bin/env python3
"""
Integration layer for MultiRadarRetriever with agent_router.

Provides domain-filtered retrieval with automatic domain detection from queries.
"""

import logging
import re
import sys
import os
from typing import Optional, List, Dict

# Add parent directory to path to import multi_radar_retriever
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from multi_radar_retriever import MultiRadarRetriever

logger = logging.getLogger(__name__)


class MultiRadarRetrieverAdapter:
    """
    Adapter that integrates MultiRadarRetriever with agent_router's retriever interface.
    
    Provides:
    - Automatic domain detection from queries
    - Domain-filtered retrieval
    - Backward compatibility with existing retriever interface
    """
    
    def __init__(
        self,
        index_path="vector_db/multi_radar_index.faiss",
        chunks_path="vector_db/multi_radar_chunks.pkl",
        metadata_path="vector_db/multi_radar_metadata.pkl",
        model_name="all-MiniLM-L6-v2"
    ):
        """Initialize adapter with MultiRadarRetriever."""
        self.retriever = MultiRadarRetriever(
            index_path=index_path,
            chunks_path=chunks_path,
            metadata_path=metadata_path,
            model_name=model_name
        )
        self._build_domain_keywords()
    
    def _build_domain_keywords(self):
        """Build keyword mappings for automatic domain detection."""
        self.domain_keywords = {
            "nexrad": {
                "primary": ["nexrad", "wsr-88d", "wsr88d", "weather radar", "weather surveillance", "reflectivity", "velocity", "doppler"],
                "secondary": ["precipitation", "echo", "radar scan", "beam", "antenna rotation", "weather product"]
            },
            "asr8": {
                "primary": ["asr-8", "asr8", "air surveillance", "atc radar", "airport radar", "l-band", "1200-1350 mhz"],
                "secondary": ["primary radar", "target detection", "surveillance range", "blip", "scan rate", "antenna"]
            },
            "beacon": {
                "primary": ["beacon", "atcrb", "secondary radar", "transponder", "mode c", "shf", "1030/1090", "interrogation"],
                "secondary": ["altitude encoding", "aircraft identification", "reply pulse", "mode s", "target identification"]
            }
        }
    
    def _detect_domain(self, query: str) -> Optional[str]:
        """
        Detect domain from query keywords.
        
        Returns:
            Domain name (nexrad, asr8, beacon) or None
        """
        q_lower = query.lower()
        
        # Check each domain
        for domain, keywords in self.domain_keywords.items():
            # Primary keywords match strongly
            for kw in keywords["primary"]:
                if kw in q_lower:
                    logger.debug(f"[DOMAIN-DETECT] Query matched {domain} (primary: '{kw}')")
                    return domain
        
        # Secondary keyword match (weaker)
        for domain, keywords in self.domain_keywords.items():
            for kw in keywords["secondary"]:
                if kw in q_lower:
                    logger.debug(f"[DOMAIN-DETECT] Query matched {domain} (secondary: '{kw}')")
                    return domain
        
        # No domain detected - return None for unfiltered search
        logger.debug(f"[DOMAIN-DETECT] No domain detected in query")
        return None
    
    def retrieve(
        self,
        query: str,
        k: int = 5,
        top_n: int = 3,
        domain: Optional[str] = None,
        auto_detect: bool = True
    ) -> List[Dict]:
        """
        Retrieve documents with optional domain filtering.
        
        Args:
            query: User query
            k: Number of results to retrieve (overridden by domain filtering)
            top_n: Number of results to return (legacy parameter, use k)
            domain: Explicit domain filter (nexrad, asr8, beacon), or None
            auto_detect: If True and domain is None, auto-detect from query
        
        Returns:
            List of chunk dictionaries with confidence scores
        """
        effective_k = top_n if top_n > 0 else k
        
        # Auto-detect domain if not specified
        if domain is None and auto_detect:
            domain = self._detect_domain(query)
        
        # Retrieve with domain filtering
        if domain:
            logger.info(f"[RETRIEVAL] Query: '{query[:60]}...' | Domain: {domain} | k={effective_k}")
            results = self.retriever.retrieve(query, domain=domain, top_k=effective_k)
        else:
            logger.info(f"[RETRIEVAL] Query: '{query[:60]}...' | No domain filter | k={effective_k}")
            results = self.retriever.retrieve(query, domain=None, top_k=effective_k)
        
        # Add metadata for agent_router compatibility
        for result in results:
            result["confidence"] = result.get("score", 0.5)
            result["source"] = result.get("source", "unknown")
            result["snippet"] = result.get("text", "")[:200]
        
        logger.info(f"[RETRIEVAL] Returned {len(results)} results")
        return results
    
    def retrieve_batch(
        self,
        queries: List[str],
        k: int = 5,
        domain: Optional[str] = None
    ) -> Dict[str, List[Dict]]:
        """
        Retrieve results for multiple queries.
        
        Args:
            queries: List of query strings
            k: Number of results per query
            domain: Optional domain filter for all queries
        
        Returns:
            Dict mapping query to results list
        """
        results = {}
        for query in queries:
            results[query] = self.retrieve(query, k=k, domain=domain)
        return results


# Global retriever instance (lazy-loaded)
_retriever_instance: Optional[MultiRadarRetrieverAdapter] = None


def get_retriever() -> MultiRadarRetrieverAdapter:
    """Get or create global retriever instance."""
    global _retriever_instance
    if _retriever_instance is None:
        logger.info("[INIT] Initializing MultiRadarRetrieverAdapter...")
        _retriever_instance = MultiRadarRetrieverAdapter()
    return _retriever_instance


def retrieve_for_agent(
    query: str,
    k: int = 12,
    top_n: int = 6,
    auto_detect_domain: bool = True
) -> List[Dict]:
    """
    Retrieve documents for agent_router compatibility.
    
    This is the main retrieval function to pass to NICAgent.
    
    Args:
        query: User query
        k: Number of results (default 12)
        top_n: Legacy parameter (overrides k if > 0)
        auto_detect_domain: Auto-detect domain from query
    
    Returns:
        List of chunk dictionaries for agent processing
    """
    retriever = get_retriever()
    return retriever.retrieve(
        query,
        k=k,
        top_n=top_n,
        auto_detect=auto_detect_domain
    )


if __name__ == "__main__":
    """Test the adapter."""
    import sys
    
    print("Testing MultiRadarRetrieverAdapter...")
    adapter = MultiRadarRetrieverAdapter()
    
    test_queries = [
        ("What is the NEXRAD WSR-88D operating frequency?", "nexrad"),
        ("How does ASR-8 perform primary radar surveillance?", "asr8"),
        ("What is the BEACON transponder interrogation frequency?", "beacon"),
    ]
    
    for query, expected_domain in test_queries:
        print(f"\nQuery: {query}")
        detected = adapter._detect_domain(query)
        print(f"  Detected domain: {detected} (expected: {expected_domain})")
        
        results = adapter.retrieve(query, k=3)
        print(f"  Retrieved {len(results)} results:")
        for i, result in enumerate(results, 1):
            domain = result.get("domain", "?")
            conf = result.get("confidence", 0)
            print(f"    {i}. [{domain}] {result['text'][:80]}... (conf: {conf:.2f})")
