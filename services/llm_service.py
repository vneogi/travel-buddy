"""Travel Buddy MVP - LLM Integration Service

Production LLM layer using LiteLLM for unified model access.
Implements:
  - Asymmetric routing (light vs heavy models)
  - Token counting and cost estimation
  - Streaming support for chat responses
  - Automatic fallback on model failure
  - Structured output for itinerary changes

Models:
  Heavy (structural): GPT-4o, Claude 3.5 Sonnet
  Light (info/translate): Gemini 1.5 Flash, GPT-4o-mini
  Embedding: text-embedding-3-small (1536 dims)

Requires:
  pip install litellm tiktoken
  Environment vars: TB_LITELLM_API_KEY (or per-provider keys)
"""

import json
import time
from typing import AsyncGenerator, Dict, List, Optional, Tuple

from config.settings import settings


class LLMService:
    """Unified LLM gateway with cost tracking and routing."""

    # Cost per 1K tokens (input/output) for supported models
    MODEL_COSTS = {
        "gpt-4o": {"input": 0.0025, "output": 0.010},
        "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
        "claude-3-5-sonnet-20241022": {"input": 0.003, "output": 0.015},
        "gemini/gemini-1.5-flash": {"input": 0.000075, "output": 0.0003},
        "gemini/gemini-1.5-pro": {"input": 0.00125, "output": 0.005},
    }

    # Fallback chains
    HEAVY_FALLBACK = ["gpt-4o", "claude-3-5-sonnet-20241022", "gemini/gemini-1.5-pro"]
    LIGHT_FALLBACK = ["gpt-4o-mini"]

    def __init__(self):
        self.heavy_model = settings.heavy_model
        self.light_model = settings.light_model
        self.embedding_model = settings.embedding_model
        self._total_tokens_used = 0
        self._total_cost = 0.0
        self._call_log: List[Dict] = []

    # =========================================================================
    # Core Completion
    # =========================================================================

    async def complete(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        routing_tier: str = "light",
        temperature: float = 0.7,
        max_tokens: int = 1024,
        response_format: Optional[Dict] = None,
    ) -> Dict:
        """Generate a completion with automatic fallback.

        Returns:
            {
                "content": str,
                "model_used": str,
                "tokens": {"input": int, "output": int, "total": int},
                "cost_usd": float,
                "latency_ms": int,
            }
        """
        import litellm

        # Determine model from tier if not explicitly set
        if model is None:
            model = self.heavy_model if routing_tier == "heavy" else self.light_model

        # Get fallback chain
        fallback_chain = (
            self.HEAVY_FALLBACK if routing_tier == "heavy" else self.LIGHT_FALLBACK
        )

        # Ensure primary model is first in chain
        if model not in fallback_chain:
            fallback_chain = [model] + fallback_chain

        last_error = None
        for attempt_model in fallback_chain:
            try:
                start_time = time.time()

                kwargs = {
                    "model": attempt_model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                }
                if response_format:
                    kwargs["response_format"] = response_format

                response = await litellm.acompletion(**kwargs)

                latency_ms = int((time.time() - start_time) * 1000)

                # Extract usage
                usage = response.usage
                tokens = {
                    "input": usage.prompt_tokens,
                    "output": usage.completion_tokens,
                    "total": usage.total_tokens,
                }

                # Calculate cost
                cost = self._calculate_cost(attempt_model, tokens)

                # Track
                self._total_tokens_used += tokens["total"]
                self._total_cost += cost
                self._log_call(attempt_model, routing_tier, tokens, cost, latency_ms)

                return {
                    "content": response.choices[0].message.content,
                    "model_used": attempt_model,
                    "tokens": tokens,
                    "cost_usd": cost,
                    "latency_ms": latency_ms,
                }

            except Exception as e:
                last_error = e
                continue

        raise RuntimeError(
            f"All models failed for {routing_tier} tier. Last error: {last_error}"
        )

    # =========================================================================
    # Specialized Methods
    # =========================================================================

    async def classify_intent(
        self, user_message: str, event_type: str
    ) -> Tuple[str, float]:
        """Use LLM to classify intent when keyword matching is ambiguous.

        Returns: (routing_tier, confidence)
        """
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a travel app intent classifier. Given a user message, "
                    "classify whether it requires STRUCTURAL changes to their itinerary "
                    "(heavy: rescheduling, swapping, rerouting) or is a SIMPLE information "
                    "request (light: translations, dress codes, prices, directions).\n\n"
                    "Respond with JSON: {\"tier\": \"heavy\" or \"light\", \"confidence\": 0.0-1.0}"
                ),
            },
            {
                "role": "user",
                "content": f"Event type: {event_type}\nUser message: {user_message}",
            },
        ]

        result = await self.complete(
            messages=messages,
            routing_tier="light",  # Classification itself is cheap
            temperature=0.1,
            max_tokens=50,
            response_format={"type": "json_object"},
        )

        try:
            parsed = json.loads(result["content"])
            return (parsed.get("tier", "light"), parsed.get("confidence", 0.5))
        except (json.JSONDecodeError, KeyError):
            return ("light", 0.5)

    async def generate_itinerary_response(
        self,
        user_message: str,
        trip_state: Dict,
        venues_found: List[Dict],
        routing_tier: str = "heavy",
    ) -> str:
        """Generate a natural language response for itinerary changes."""
        system_prompt = (
            "You are Travel Buddy AI, a concise and helpful Dubai travel companion. "
            "You help travelers modify their itineraries in real-time.\n\n"
            "Rules:\n"
            "- Never modify LOCKED activities\n"
            "- Suggest specific venues from the provided options\n"
            "- Include transit time estimates when swapping\n"
            "- Be warm but concise (2-3 sentences max)\n"
            "- Mention the vibe/atmosphere of suggested venues"
        )

        user_context = (
            f"User request: {user_message}\n\n"
            f"Current itinerary nodes: {json.dumps(trip_state.get('nodes', [])[:5], default=str)}\n\n"
            f"Available replacement venues: {json.dumps(venues_found[:3], default=str)}"
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_context},
        ]

        result = await self.complete(
            messages=messages,
            routing_tier=routing_tier,
            temperature=0.8,
            max_tokens=256,
        )
        return result["content"]

    async def generate_info_response(
        self, user_message: str, context: Dict = None
    ) -> str:
        """Generate a light response for info queries."""
        system_prompt = (
            "You are Travel Buddy AI, a Dubai travel expert. "
            "Answer the user's question concisely (1-2 sentences). "
            "Focus on practical, actionable information for tourists."
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]

        result = await self.complete(
            messages=messages,
            routing_tier="light",
            temperature=0.5,
            max_tokens=150,
        )
        return result["content"]

    # =========================================================================
    # Embeddings
    # =========================================================================

    async def generate_embedding(self, text: str) -> List[float]:
        """Generate a real embedding vector using the configured model."""
        import litellm

        response = await litellm.aembedding(
            model=self.embedding_model,
            input=[text],
        )
        return response.data[0]["embedding"]

    async def batch_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for multiple texts in one call."""
        import litellm

        response = await litellm.aembedding(
            model=self.embedding_model,
            input=texts,
        )
        return [item["embedding"] for item in response.data]

    # =========================================================================
    # Streaming (for real-time chat UI)
    # =========================================================================

    async def stream_response(
        self,
        messages: List[Dict[str, str]],
        routing_tier: str = "light",
    ) -> AsyncGenerator[str, None]:
        """Stream a response token-by-token for the chat UI."""
        import litellm

        model = self.heavy_model if routing_tier == "heavy" else self.light_model

        response = await litellm.acompletion(
            model=model,
            messages=messages,
            stream=True,
            temperature=0.7,
        )

        async for chunk in response:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    # =========================================================================
    # Cost Tracking
    # =========================================================================

    def _calculate_cost(
        self, model: str, tokens: Dict[str, int]
    ) -> float:
        """Calculate USD cost for a completion."""
        costs = self.MODEL_COSTS.get(model, {"input": 0.001, "output": 0.002})
        input_cost = (tokens["input"] / 1000) * costs["input"]
        output_cost = (tokens["output"] / 1000) * costs["output"]
        return round(input_cost + output_cost, 6)

    def _log_call(
        self,
        model: str,
        tier: str,
        tokens: Dict,
        cost: float,
        latency_ms: int,
    ) -> None:
        """Log a call for internal tracking."""
        self._call_log.append({
            "model": model,
            "tier": tier,
            "tokens": tokens,
            "cost_usd": cost,
            "latency_ms": latency_ms,
            "timestamp": time.time(),
        })

    def get_usage_stats(self) -> Dict:
        """Get accumulated usage statistics."""
        return {
            "total_calls": len(self._call_log),
            "total_tokens": self._total_tokens_used,
            "total_cost_usd": round(self._total_cost, 4),
            "calls_by_tier": {
                "heavy": sum(1 for c in self._call_log if c["tier"] == "heavy"),
                "light": sum(1 for c in self._call_log if c["tier"] == "light"),
            },
            "avg_latency_ms": (
                int(sum(c["latency_ms"] for c in self._call_log) / len(self._call_log))
                if self._call_log else 0
            ),
        }


# Singleton instance
llm_service = LLMService()
