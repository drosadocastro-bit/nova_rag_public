"""
Search history and favorites management with optional secure persistence.
"""

from __future__ import annotations

from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Optional
import json

# Import secure pickle if available
try:
    from secure_cache import secure_pickle_dump, secure_pickle_load

    SECURE_CACHE_AVAILABLE = True
except ImportError:  # pragma: no cover - fallback path
    import pickle  # type: ignore

    SECURE_CACHE_AVAILABLE = False
    secure_pickle_dump = None  # type: ignore
    secure_pickle_load = None  # type: ignore


class SearchHistory:
    """Manages search history and favorites with persistence."""

    def __init__(
        self,
        max_size: int = 50,
        history_path: Optional[Path] = None,
        favorites_path: Optional[Path] = None,
    ) -> None:
        self.history = deque(maxlen=max_size)
        self.favorites: list[dict] = []
        self.history_path = history_path
        self.favorites_path = favorites_path
        if self.history_path and self.favorites_path:
            self.load()

    def add(self, query: str) -> None:
        if query in self.history:
            self.history.remove(query)
        self.history.appendleft(query)
        self.save()

    def add_favorite(self, query: str, answer: str) -> None:
        fav = {"query": query, "answer": answer, "timestamp": datetime.now().isoformat()}
        self.favorites.append(fav)
        self.save_favorites()

    def remove_favorite(self, index: int) -> None:
        if 0 <= index < len(self.favorites):
            self.favorites.pop(index)
            self.save_favorites()

    def get_recent(self, n: int = 10) -> list[str]:
        return list(self.history)[:n]

    def save(self) -> None:
        """Save search history with HMAC verification when available."""
        if not self.history_path:
            return
        try:
            if SECURE_CACHE_AVAILABLE:
                secure_pickle_dump(list(self.history), self.history_path)  # type: ignore[arg-type]
            else:  # pragma: no cover - fallback path
                import pickle

                with self.history_path.open("wb") as file:
                    pickle.dump(list(self.history), file)
        except Exception as exc:  # noqa: BLE001 - resilience over strictness
            print(f"[!] Failed to save search history: {exc}")

    def save_favorites(self) -> None:
        if not self.favorites_path:
            return
        try:
            with self.favorites_path.open("w", encoding="utf-8") as file:
                json.dump(self.favorites, file, indent=2, ensure_ascii=False)
        except Exception as exc:  # noqa: BLE001
            print(f"[!] Failed to save favorites: {exc}")

    def load(self) -> None:
        """Load search history with HMAC verification when available."""
        if not self.history_path or not self.favorites_path:
            return
        try:
            if self.history_path.exists():
                if SECURE_CACHE_AVAILABLE:
                    self.history = deque(secure_pickle_load(self.history_path), maxlen=self.history.maxlen)  # type: ignore[arg-type]
                else:  # pragma: no cover - fallback path
                    import pickle

                    with self.history_path.open("rb") as file:
                        self.history = deque(pickle.load(file), maxlen=self.history.maxlen)
            if self.favorites_path.exists():
                with self.favorites_path.open("r", encoding="utf-8") as file:
                    self.favorites = json.load(file)
        except Exception as exc:  # noqa: BLE001
            print(f"[!] Failed to load search history: {exc}")
            self.history = deque(maxlen=self.history.maxlen)
            if self.history_path.exists():
                try:
                    self.history_path.unlink()
                except Exception:
                    pass