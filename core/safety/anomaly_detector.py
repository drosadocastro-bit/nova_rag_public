"""
Anomaly detection utilities for Phase 3.5.

Loads a lightweight autoencoder and scores query embeddings for
reconstruction error-based anomaly detection. Advisory only.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import json
import numpy as np
import torch
import torch.nn as nn


@dataclass
class AnomalyResult:
    score: float
    threshold: float
    category: str
    flagged: bool


class QueryAutoencoder(nn.Module):
    """Lightweight autoencoder used for anomaly scoring."""

    def __init__(self, embedding_dim: int = 384, latent_dim: int = 64):
        super().__init__()
        self.encoder = nn.Sequential(
            nn.Linear(embedding_dim, 128),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(128, latent_dim),
            nn.ReLU(),
        )
        self.decoder = nn.Sequential(
            nn.Linear(latent_dim, 128),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(128, embedding_dim),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        latent = self.encoder(x)
        return self.decoder(latent)

    @torch.no_grad()
    def reconstruction_error(self, x: torch.Tensor) -> torch.Tensor:
        reconstructed = self.forward(x)
        mse = torch.mean((x - reconstructed) ** 2, dim=1)
        return mse


class AnomalyDetector:
    """Loads a trained autoencoder and scores embeddings."""

    def __init__(self, model_path: Path, config_path: Path, device: str | None = None):
        self.model_path = Path(model_path)
        self.config_path = Path(config_path)
        self.config: dict[str, Any] = self._load_config(self.config_path)

        embedding_dim = int(self.config.get("embedding_dim", 384))
        latent_dim = int(self.config.get("latent_dim", 64))

        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.model = QueryAutoencoder(embedding_dim=embedding_dim, latent_dim=latent_dim).to(self.device)
        self.model.load_state_dict(torch.load(self.model_path, map_location=self.device))
        self.model.eval()

    @staticmethod
    def _load_config(path: Path) -> dict[str, Any]:
        if not path.exists():
            raise FileNotFoundError(f"Anomaly config not found: {path}")
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)

    def score_embedding(self, embedding: np.ndarray) -> AnomalyResult:
        if embedding.ndim == 1:
            embedding = embedding.reshape(1, -1)

        tensor = torch.tensor(embedding, dtype=torch.float32, device=self.device)
        error = float(self.model.reconstruction_error(tensor).mean().item())

        threshold = float(self.config.get("threshold", 0.0))
        std_error = float(self.config.get("std_error", 0.0))

        if std_error > 0:
            medium_cutoff = threshold + std_error
            high_cutoff = threshold + (2.0 * std_error)
        else:
            medium_cutoff = threshold * 1.5 if threshold > 0 else 0.0
            high_cutoff = threshold * 2.0 if threshold > 0 else 0.0

        if error <= threshold:
            category = "low"
        elif error <= medium_cutoff:
            category = "medium"
        elif error <= high_cutoff:
            category = "high"
        else:
            category = "critical"

        return AnomalyResult(
            score=error,
            threshold=threshold,
            category=category,
            flagged=category in {"medium", "high", "critical"},
        )
