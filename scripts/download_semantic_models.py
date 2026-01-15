"""Download semantic models for offline use."""

from pathlib import Path

from sentence_transformers import SentenceTransformer


def download_models() -> bool:
    """Download sentence-transformers model for offline semantic safety."""
    print("\n=== SEMANTIC SAFETY MODEL DOWNLOAD ===")
    models_dir = Path(__file__).parent.parent / "models"
    models_dir.mkdir(parents=True, exist_ok=True)

    print("Preparing to download model: all-MiniLM-L6-v2 (~80MB)")
    model_path = models_dir / "semantic-safety"

    try:
        model = SentenceTransformer("all-MiniLM-L6-v2")
        model.save(str(model_path))
        print(f"Model downloaded and saved to: {model_path}")

        embedding = model.encode("test query")
        print(f"Test embedding created (dim={len(embedding)})")
    except Exception as exc:  # pragma: no cover - network errors allowed
        print(f"Error downloading model: {exc}")
        return False

    print("Download complete. Next steps:")
    print(f"- Set SEMANTIC_MODEL_PATH={model_path}")
    print("- Run tests to verify semantic safety")
    print("- Optionally zip the models/semantic-safety directory for air-gapped transfer")
    return True


if __name__ == "__main__":
    success = download_models()
    print("✅ Done" if success else "❌ Failed")
