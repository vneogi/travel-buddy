"""Travel Buddy MVP - Embedding Service

Generates vector embeddings. Uses OpenAI's text-embedding-3-small when an API
key is configured (TB_LITELLM_API_KEY); otherwise falls back to deterministic
synthetic embeddings so the app runs key-free in dev.
"""

import hashlib
import math
from typing import List, Optional

from config.settings import settings, configure_provider_keys


class EmbeddingService:
    """Generates and manages text embeddings."""

    def __init__(self, use_synthetic: Optional[bool] = None):
        # Auto-detect: real embeddings when an OpenAI key exists, else synthetic.
        if use_synthetic is None:
            use_synthetic = not bool(settings.litellm_api_key)
        self.use_synthetic = use_synthetic
        self.dimensions = settings.embedding_dimensions
        if not use_synthetic:
            configure_provider_keys()

    def generate_embedding(self, text: str) -> List[float]:
        if self.use_synthetic:
            return self._synthetic_embedding(text)
        return self._api_embedding(text)

    def _synthetic_embedding(self, text: str) -> List[float]:
        """Deterministic SHA-256-based pseudo-embedding, unit-normalized.

        NOTE: same text -> same vector, but this is NOT semantic -- paraphrases
        are ~orthogonal. Only used when no API key is configured.
        """
        embedding: List[float] = []
        for i in range(0, self.dimensions, 32):
            hash_bytes = hashlib.sha256(f"{text}_{i}".encode()).digest()
            for byte in hash_bytes:
                if len(embedding) < self.dimensions:
                    embedding.append((byte / 127.5) - 1.0)
        magnitude = math.sqrt(sum(x * x for x in embedding))
        if magnitude > 0:
            embedding = [x / magnitude for x in embedding]
        return embedding[: self.dimensions]

    def _api_embedding(self, text: str) -> List[float]:
        """Real embedding via OpenAI (through litellm)."""
        try:
            import litellm

            response = litellm.embedding(model=settings.embedding_model, input=[text])
            return response.data[0]["embedding"]
        except Exception as e:
            # Safety net: never crash a request. (Mixing synthetic + real
            # vectors degrades similarity, so treat repeated failures as a
            # config problem to investigate, not a steady state.)
            print(f"API embedding failed, falling back to synthetic: {e}")
            return self._synthetic_embedding(text)

    def cosine_similarity(self, vec_a: List[float], vec_b: List[float]) -> float:
        dot_product = sum(a * b for a, b in zip(vec_a, vec_b))
        magnitude_a = math.sqrt(sum(a * a for a in vec_a))
        magnitude_b = math.sqrt(sum(b * b for b in vec_b))
        if magnitude_a == 0 or magnitude_b == 0:
            return 0.0
        return dot_product / (magnitude_a * magnitude_b)

    def batch_generate(self, texts: List[str]) -> List[List[float]]:
        return [self.generate_embedding(t) for t in texts]


# Singleton instance (auto-detects real vs synthetic)
embedding_service = EmbeddingService()
