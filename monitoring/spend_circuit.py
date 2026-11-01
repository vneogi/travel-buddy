"""SPEC-43 Gap 11: in-process provider-spend circuit.

Counts estimated/actual provider USD in process memory before LiteLLM is
invoked. Two independent sliding-window buckets: one for the whole process
(so rotating identities cannot bypass it) and one per identity. Either over
cap is a reject. No prompts, keys, or USD figures are put on the reject.
"""

from __future__ import annotations

import math
import threading
import time
from typing import Callable, Dict, List, Optional, Tuple

SPEND_WINDOW_S = 86400
MAX_PROCESS_USD = 5.0
MAX_IDENTITY_USD = 1.0

SPEND_CAPPED = "spend_capped"
ANONYMOUS_IDENTITY = "anonymous"
_PROCESS_KEY = "__process__"

# Embedding reservation: text-embedding-3-small list price per 1K tokens.
EMBEDDING_COST_PER_1K_TOKENS = 0.00002
# Rough token estimate without a tokenizer dependency (~4 chars per token).
CHARS_PER_TOKEN = 4


class SpendCapped(Exception):
    """Raised instead of calling a provider when the spend cap is reached.

    The message is the stable code only: no USD, model, or prompt text.
    """

    detail = SPEND_CAPPED

    def __init__(self) -> None:
        super().__init__(SPEND_CAPPED)


def normalize_identity(user_id: object) -> str:
    """Stripped, lowercased identity; empty or missing -> 'anonymous'."""
    value = str(user_id).strip().lower() if user_id is not None else ""
    return value or ANONYMOUS_IDENTITY


def estimate_tokens(text: str) -> int:
    return max(1, math.ceil(len(text or "") / CHARS_PER_TOKEN))


def estimate_messages_tokens(messages: List[Dict]) -> int:
    return sum(estimate_tokens(str(m.get("content") or "")) for m in messages or [])


def estimate_embedding_usd(texts: List[str]) -> float:
    tokens = sum(estimate_tokens(t) for t in texts or [])
    return round((tokens / 1000) * EMBEDDING_COST_PER_1K_TOKENS, 8)


class SpendCircuit:
    """Sliding-window USD caps per process and per identity."""

    def __init__(
        self,
        max_process_usd: float = MAX_PROCESS_USD,
        max_identity_usd: float = MAX_IDENTITY_USD,
        window_s: float = SPEND_WINDOW_S,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.max_process_usd = max_process_usd
        self.max_identity_usd = max_identity_usd
        self.window_s = window_s
        self._clock = clock
        self._entries: Dict[str, List[Tuple[float, float]]] = {}
        self._lock = threading.Lock()

    def _sum(self, key: str, now: float) -> float:
        cutoff = now - self.window_s
        return sum(usd for t, usd in self._entries.get(key, ()) if t > cutoff)

    def _prune(self, key: str, now: float) -> None:
        cutoff = now - self.window_s
        kept = [(t, usd) for t, usd in self._entries.get(key, ()) if t > cutoff]
        if kept:
            self._entries[key] = kept
        else:
            self._entries.pop(key, None)

    def process_over_cap(self, reserved_usd: float, now: float) -> bool:
        return self._sum(_PROCESS_KEY, now) + reserved_usd >= self.max_process_usd

    def identity_over_cap(self, identity: str, reserved_usd: float, now: float) -> bool:
        return self._sum(identity, now) + reserved_usd >= self.max_identity_usd

    def allow(self, identity: object, reserved_usd: float = 0.0) -> bool:
        """True if a call reserving *reserved_usd* fits both buckets. Read-only."""
        key = normalize_identity(identity)
        reserved = max(0.0, float(reserved_usd or 0.0))
        with self._lock:
            now = self._clock()
            if self.process_over_cap(reserved, now):
                return False
            if self.identity_over_cap(key, reserved, now):
                return False
            return True

    def check(self, identity: object, reserved_usd: float = 0.0) -> None:
        """Raise SpendCapped unless allow(); never calls a provider."""
        if not self.allow(identity, reserved_usd):
            raise SpendCapped()

    def record(self, identity: object, usd: float) -> None:
        """Append the ACTUAL cost of a successful provider call to both buckets."""
        cost = float(usd or 0.0)
        if cost <= 0:
            return
        key = normalize_identity(identity)
        with self._lock:
            now = self._clock()
            for bucket in (_PROCESS_KEY, key):
                self._prune(bucket, now)
                self._entries.setdefault(bucket, []).append((now, cost))

    def spent(self, identity: Optional[object] = None) -> float:
        """USD in the current window for *identity*, or the process if None."""
        key = _PROCESS_KEY if identity is None else normalize_identity(identity)
        with self._lock:
            return self._sum(key, self._clock())

    def reset(self) -> None:
        with self._lock:
            self._entries.clear()


# Module-level default used by llm_service and embedding_service.
default_spend_circuit = SpendCircuit()
