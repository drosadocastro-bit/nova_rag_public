"""Offline utility to inspect domain overlap via clustering.

Usage:
    python scripts/domain_cluster_analysis.py --k 8 --sample 400

- Loads chunks_with_metadata.pkl
- Encodes samples per domain with the same embedding model
- Performs KMeans clustering to spot cross-domain overlaps
- Prints top terms per cluster and domain distribution
"""

from __future__ import annotations

import argparse
import random
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List

import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.cluster import KMeans

BASE_DIR = Path(__file__).resolve().parents[1]
VECTOR_DB_DIR = BASE_DIR / "vector_db"
CHUNKS_FILE = VECTOR_DB_DIR / "chunks_with_metadata.pkl"
MODEL_DIR = BASE_DIR / "models" / "all-MiniLM-L6-v2"


def load_chunks() -> List[dict]:
    import pickle

    if not CHUNKS_FILE.exists():
        raise FileNotFoundError(f"Chunks file not found at {CHUNKS_FILE}")
    with CHUNKS_FILE.open("rb") as f:
        return pickle.load(f)


def sample_chunks(chunks: List[dict], sample_per_domain: int) -> List[dict]:
    by_domain: Dict[str, List[dict]] = defaultdict(list)
    for c in chunks:
        by_domain[c.get("domain", "unknown")].append(c)

    sampled: List[dict] = []
    for domain, items in by_domain.items():
        if sample_per_domain <= 0:
            sampled.extend(items)
            continue
        sampled.extend(random.sample(items, min(len(items), sample_per_domain)))
    return sampled


def top_terms(texts: List[str], top_n: int = 8) -> List[str]:
    terms = Counter()
    for t in texts:
        for token in t.lower().split():
            if len(token) < 3:
                continue
            terms[token] += 1
    return [t for t, _ in terms.most_common(top_n)]


def cluster_embeddings(embeddings: np.ndarray, k: int) -> np.ndarray:
    km = KMeans(n_clusters=k, n_init="auto", random_state=42)
    return km.fit_predict(embeddings)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--k", type=int, default=8, help="Number of clusters")
    parser.add_argument("--sample", type=int, default=400, help="Samples per domain (0 = all)")
    args = parser.parse_args()

    chunks = load_chunks()
    sampled = sample_chunks(chunks, args.sample)

    if not sampled:
        print("No chunks available")
        return 1

    model = SentenceTransformer(str(MODEL_DIR))
    texts = [c.get("text", "") for c in sampled]
    embeddings = model.encode(texts, convert_to_numpy=True, show_progress_bar=True)

    labels = cluster_embeddings(embeddings, args.k)

    clusters: Dict[int, List[int]] = defaultdict(list)
    for idx, label in enumerate(labels):
        clusters[int(label)].append(idx)

    print(f"\nCluster summary (k={args.k}):")
    for cid, idxs in sorted(clusters.items()):
        domains = [sampled[i].get("domain", "unknown") for i in idxs]
        domain_counts = Counter(domains)
        cluster_texts = [sampled[i].get("text", "") for i in idxs]
        print(f"- Cluster {cid}: {len(idxs)} items | Domains: {dict(domain_counts)}")
        print(f"  Top terms: {top_terms(cluster_texts)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
