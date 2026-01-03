"""
Glossary Augmented Retrieval (GAR) Module

Expands user queries with domain-specific synonyms before retrieval
to improve recall on technical vocabulary.

Usage:
    from glossary_gar import expand_query
    
    expanded = expand_query("my car won't turn over")
    # Returns: "my car won't turn over crank cranks cranking starter engage engine rotation"
"""

import json
import os
from pathlib import Path
from typing import Optional
import logging

logger = logging.getLogger(__name__)

# Path to glossary file
GLOSSARY_PATH = Path(__file__).parent / "data" / "automotive_glossary.json"

# Cached glossary (loaded once)
_glossary: Optional[dict] = None
_flat_glossary: Optional[dict] = None


def load_glossary() -> dict:
    """Load glossary from JSON file."""
    global _glossary
    
    if _glossary is not None:
        return _glossary
    
    if not GLOSSARY_PATH.exists():
        logger.warning(f"Glossary file not found: {GLOSSARY_PATH}")
        _glossary = {}
        return _glossary
    
    try:
        with open(GLOSSARY_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Remove metadata keys
        _glossary = {k: v for k, v in data.items() if not k.startswith('_')}
        logger.info(f"Loaded glossary with {sum(len(v) for v in _glossary.values())} term categories")
        return _glossary
    
    except Exception as e:
        logger.error(f"Failed to load glossary: {e}")
        _glossary = {}
        return _glossary


def get_flat_glossary() -> dict:
    """Get flattened glossary (term -> synonyms list)."""
    global _flat_glossary
    
    if _flat_glossary is not None:
        return _flat_glossary
    
    glossary = load_glossary()
    _flat_glossary = {}
    
    for category, terms in glossary.items():
        if isinstance(terms, dict):
            for term, synonyms in terms.items():
                if isinstance(synonyms, list):
                    _flat_glossary[term.lower()] = synonyms
    
    logger.info(f"Flattened glossary: {len(_flat_glossary)} terms")
    return _flat_glossary


def expand_query(query: str, max_expansions: int = 3) -> str:
    """
    Expand query with glossary synonyms.
    
    Args:
        query: Original user query
        max_expansions: Maximum number of synonym terms to add per match
        
    Returns:
        Expanded query with appended synonyms
    """
    flat_glossary = get_flat_glossary()
    q_lower = query.lower()
    
    expansions = []
    matched_terms = set()
    
    for term, synonyms in flat_glossary.items():
        if term in q_lower and term not in matched_terms:
            matched_terms.add(term)
            # Add up to max_expansions synonyms
            for syn in synonyms[:max_expansions]:
                if syn.lower() not in q_lower and syn.lower() not in expansions:
                    expansions.append(syn)
    
    if expansions:
        expanded = query + " " + " ".join(expansions)
        logger.debug(f"GAR expanded: '{query}' -> '{expanded}'")
        return expanded
    
    return query


def expand_query_weighted(query: str) -> tuple[str, list[tuple[str, float]]]:
    """
    Expand query and return weighted expansion terms.
    
    Returns:
        Tuple of (expanded_query, [(expansion_term, weight), ...])
        Weights are 1.0 for original terms, 0.7 for expansions
    """
    flat_glossary = get_flat_glossary()
    q_lower = query.lower()
    
    expansions = []
    
    for term, synonyms in flat_glossary.items():
        if term in q_lower:
            for syn in synonyms[:3]:
                if syn.lower() not in q_lower:
                    expansions.append((syn, 0.7))  # Lower weight for expansions
    
    expanded = query
    if expansions:
        expanded = query + " " + " ".join(e[0] for e in expansions)
    
    return expanded, expansions


def get_glossary_stats() -> dict:
    """Get statistics about the loaded glossary."""
    glossary = load_glossary()
    flat = get_flat_glossary()
    
    return {
        "categories": len(glossary),
        "total_terms": len(flat),
        "total_synonyms": sum(len(syns) for syns in flat.values()),
        "categories_detail": {cat: len(terms) for cat, terms in glossary.items()}
    }


# Pre-load glossary on import
if os.environ.get("NOVA_PRELOAD_GLOSSARY", "1") == "1":
    load_glossary()


if __name__ == "__main__":
    # Test the glossary
    print("=== Glossary Augmented Retrieval (GAR) Test ===\n")
    
    stats = get_glossary_stats()
    print(f"Glossary Stats:")
    print(f"  Categories: {stats['categories']}")
    print(f"  Terms: {stats['total_terms']}")
    print(f"  Total Synonyms: {stats['total_synonyms']}")
    print()
    
    test_queries = [
        "my car won't turn over",
        "what does p0420 mean",
        "temperature gauge high",
        "torque spec for lug nuts",
        "engine hesitates on acceleration",
        "how to bleed brakes",
        "maf sensor cleaning",
        "check engine light is on",
    ]
    
    print("Query Expansions:")
    print("-" * 60)
    for q in test_queries:
        expanded = expand_query(q)
        if expanded != q:
            print(f"  IN:  {q}")
            print(f"  OUT: {expanded}")
            print()
        else:
            print(f"  IN:  {q}")
            print(f"  OUT: (no expansion)")
            print()
