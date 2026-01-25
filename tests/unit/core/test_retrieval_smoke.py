import importlib
from typing import Any

import pytest
import core.retrieval.retrieval_engine as retrieval_module

# Skip this smoke test if FAISS isn't available in the environment
faiss = pytest.importorskip("faiss")


@pytest.mark.smoke
@pytest.mark.parametrize("query", ["How do I check the battery cables?", "What should I inspect when the starter clicks?"])
def test_retrieve_emits_anomaly_metadata(monkeypatch, query):
    monkeypatch.setenv("NOVA_FORCE_OFFLINE", "1")
    monkeypatch.setenv("NOVA_DISABLE_CROSS_ENCODER", "1")
    monkeypatch.setenv("NOVA_DISABLE_VISION", "1")
    monkeypatch.setenv("NOVA_BM25_CACHE", "0")
    monkeypatch.setenv("NOVA_HYBRID_SEARCH", "0")
    monkeypatch.setenv("NOVA_EMBEDDING_MODEL", "models/nic-embeddings-v1.0")
    monkeypatch.setenv("NOVA_ANOMALY_DETECTOR", "1")
    monkeypatch.setenv("NOVA_ANOMALY_MODEL", "models/anomaly_detector_v1.0.pth")
    monkeypatch.setenv("NOVA_ANOMALY_CONFIG", "models/anomaly_detector_v1.0_config.json")

    importlib.reload(retrieval_module)
    engine: Any = retrieval_module.RetrievalEngine()  # type: ignore[attr-defined]

    text_model = engine.get_text_embed_model()
    if text_model is None:
        pytest.skip("Text embedding model unavailable; ensure finetuned model is present locally.")

    detector = engine.get_anomaly_detector()
    if detector is None:
        pytest.skip("Anomaly detector unavailable; ensure model and config files exist.")

    docs = [
        {
            "id": "battery",
            "source": "vehicle_manual.txt",
            "page": 1,
            "text": "If the engine will not start, clean and tighten the battery terminals and inspect the cables.",
            "snippet": "clean and tighten the battery terminals",
        },
        {
            "id": "starter",
            "source": "vehicle_manual.txt",
            "page": 2,
            "text": "A repeated clicking sound often indicates low voltage at the starter motor.",
            "snippet": "clicking sound indicates low voltage at the starter",
        },
    ]

    embeddings = text_model.encode([d["text"] for d in docs], convert_to_numpy=True)
    engine.index = faiss.IndexFlatL2(embeddings.shape[1])
    engine.index.add(embeddings)  # type: ignore[arg-type]
    engine.docs = docs
    engine._BM25_INDEX = {}
    engine._BM25_DOC_LEN = []
    engine._BM25_AVGDL = 0.0
    engine._BM25_READY = False

    results = engine.retrieve(
        query,
        k=2,
        top_n=2,
        lambda_diversity=0.5,
        use_reranker=False,
        use_sklearn_reranker=False,
        use_gar=False,
    )

    assert results, "Expected retrieval to return at least one document"
    top = results[0]
    assert "anomaly_score" in top, "Anomaly score should be attached to retrieval results"
    assert "anomaly_threshold" in top, "Anomaly threshold should be attached to retrieval results"
    assert "anomaly_flag" in top, "Anomaly flag should be attached to retrieval results"
