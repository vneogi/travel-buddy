"""Travel Buddy MVP - Embedding Service

Handles vector embedding generation. In production, uses OpenAI's
text-embedding-3-small. For MVP testing, generates deterministic
synthetic embeddings based on text hashing.
"""

import hashlib
import math
from typing import List

from config.settings import settings


class EmbeddingService:
    """Generates and manages text embeddings."""

    def __init__(self, use_synthetic: bool = True):
        self.use_synthetic = use_synthetic
        self.dimensions = settings.embedding_dimensions

    def generate_embedding(self, text: str) -> List[float]:
        """Generate an embedding vector for the given text.

        In synthetic mode, creates a deterministic pseudo-embedding
        based on text hashing. Same text always produces same vector.
        """
        if self.use_synthetic:
            return self._synthetic_embedding(text)
        else:
            return self._api_embedding(text)

    def _synthetic_embedding(self, text: str) -> List[float]:
        """Generate a deterministic synthetic embedding.

        Uses SHA-256 hash expanded to fill 1536 dimensions.
        Normalized to unit length for valid cosine similarity.
        """
        # Create a series of hashes to fill all dimensions
        embedding = []
        for i in range(0, self.dimensions, 32):
            seed = f"{text}_{i}"
            hash_bytes = hashlib.sha256(seed.encode()).digest()
            # Convert each byte to a float in [-1, 1]
            for byte in hash_bytes:
                if len(embedding) < self.dimensions:
                    embedding.append((byte / 127.5) - 1.0)

        # Normalize to unit vector
        magnitude = math.sqrt(sum(x * x for x in embedding))
        if magnitude > 0:
            embedding = [x / magnitude for x in embedding]

        return embedding[:self.dimensions]

    def _api_embedding(self, text: str) -> List[float]:
        """Generate embedding via OpenAI API (production mode)."""
        try:
            import litellm
            response = litellm.embedding(
                model=settings.embedding_model,
                input=[text]
            )
            return response.data[0]["embedding"]
        except Exception as e:
            print(f"API embedding failed, falling back to synthetic: {e}")
            return self._synthetic_embedding(text)

    def cosine_similarity(self, vec_a: List[float], vec_b: List[float]) -> float:
        """Compute cosine similarity between two vectors."""
        dot_product = sum(a * b for a, b in zip(vec_a, vec_b))
        magnitude_a = math.sqrt(sum(a * a for a in vec_a))
        magnitude_b = math.sqrt(sum(b * b for b in vec_b))

        if magnitude_a == 0 or magnitude_b == 0:
            return 0.0

        return dot_product / (magnitude_a * magnitude_b)

    def batch_generate(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for multiple texts."""
        return [self.generate_embedding(text) for text in texts]


# Singleton instance
embedding_service = EmbeddingService(use_synthetic=True)
