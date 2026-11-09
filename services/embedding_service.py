"""Travel Buddy MVP - Embedding Service

Generates vector embeddings. Uses OpenAI's text-embedding-3-small when an API
key is configured (TB_LITELLM_API_KEY); otherwise falls back to deterministic
synthetic embeddings so the app runs key-free in dev.
"""

import hashlib
import logging
import math
from typing import List, Optional

from config.settings import settings, configure_provider_keys
from monitoring import spend_circuit as _spend
from monitoring.redact import redact_outbound_llm_text
from monitoring.spend_circuit import SpendCapped, SpendCircuit, normalize_identity

logger = logging.getLogger("travelbuddy")


class EmbeddingService:
    """Generates and manages text embeddings."""

    def __init__(
        self, use_synthetic: Optional[bool] = None, circuit: Optional[SpendCircuit] = None
    ):
        # SPEC-43 Gap 11: provider-spend circuit; tests inject a private one.
        self._circuit = circuit if circuit is not None else _spend.default_spend_circuit
        # Auto-detect: real embeddings when an OpenAI key exists, else synthetic.
        if use_synthetic is None:
            use_synthetic = not bool(settings.litellm_api_key)
        self.use_synthetic = use_synthetic
        self.dimensions = settings.embedding_dimensions
        if not use_synthetic:
            configure_provider_keys()

    def generate_embedding(
        self, text: str, user_id: Optional[str] = None, restricted_needles=()
    ) -> List[float]:
        if self.use_synthetic:
            # Synthetic vectors are not provider spend: no circuit, no LiteLLM.
            # Hashes the original text (SPEC-43 Gap 3: not a provider payload).
            return self._synthetic_embedding(text)
        return self._api_embedding(text, user_id=user_id, restricted_needles=restricted_needles)

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

    def _api_embedding(
        self, text: str, user_id: Optional[str] = None, restricted_needles=()
    ) -> List[float]:
        """Real embedding via OpenAI (through litellm).

        SPEC-43 Gap 11: the spend circuit runs before litellm.embedding. A
        spend reject raises SpendCapped; it never falls back to synthetic
        (that would mix embedding spaces while a live key is configured).
        """
        identity = normalize_identity(user_id)
        estimate = _spend.estimate_embedding_usd([text])
        self._circuit.check(identity, estimate)
        try:
            import litellm

            # SPEC-43 Gap 3: only the provider payload is redacted; the
            # synthetic fallback below still hashes the original text.
            outbound = redact_outbound_llm_text(text, restricted_needles)
            response = litellm.embedding(model=settings.embedding_model, input=[outbound])
            self._circuit.record(identity, estimate)
            return response.data[0]["embedding"]
        except SpendCapped:
            raise
        except Exception as e:
            # Safety net: never crash a request. (Mixing synthetic + real
            # vectors degrades similarity, so treat repeated failures as a
            # config problem to investigate, not a steady state.)
            # SPEC-43 Gap 3: provider text can echo the input, so only the
            # exception class name is logged.
            logger.warning(
                "embedding provider failed; using synthetic fallback (%s)", type(e).__name__
            )
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
