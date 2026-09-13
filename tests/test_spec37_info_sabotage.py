"""SPEC-37 sabotage: Laos ask_info must never fall back to Dubai.

The LLM system prompt for informational queries used to hardcode
"Dubai travel expert".  After the fix, generate_info_response receives
the traveller's geo_region and grounds its answer there.

The mock LLM echoes the system prompt, so we can assert the prompt
itself contains no Dubai reference when the context is Laos.
"""

import pytest

from services.llm_service import LLMService


class _CaptureLLM(LLMService):
    """Subclass that captures the last messages list instead of calling LiteLLM."""

    def __init__(self):
        super().__init__()
        self.last_messages = None

    async def complete(self, messages, **kwargs):
        self.last_messages = messages
        # Return a dummy response so the caller doesn't crash.
        return {
            "content": "I don't have specific food data for this area.",
            "model_used": "test",
            "tokens": {"input": 0, "output": 0, "total": 0},
            "cost_usd": 0.0,
            "latency_ms": 0,
        }


@pytest.mark.asyncio
async def test_vientiane_ask_does_not_mention_dubai():
    """A Vientiane night-market question must not produce a Dubai-grounded prompt."""
    llm = _CaptureLLM()
    await llm.generate_info_response(
        "What street food should I try at the Vientiane night market?",
        context={
            "geo_region": "vientiane_laos",
            "venue_name": "Ban Anou Night Market",
        },
    )
    system_msg = llm.last_messages[0]["content"].lower()
    user_msg = llm.last_messages[1]["content"].lower()
    full = system_msg + " " + user_msg

    # The prompt must reference the traveller's actual region
    assert "vientiane" in full, "Prompt should ground in the Vientiane region"

    # Sabotage check: Dubai must NOT appear in the prompt
    for forbidden in ("dubai", "emirati", "uae"):
        assert forbidden not in full, (
            f"Prompt must not mention {forbidden!r} for a Laos query. System: {system_msg}"
        )


@pytest.mark.asyncio
async def test_info_response_admits_missing_data():
    """When grounded food data is absent, the LLM should not invent dishes."""
    llm = _CaptureLLM()
    await llm.generate_info_response(
        "Best dishes at this night market?",
        context={"geo_region": "vientiane_laos"},
    )
    # The _CaptureLLM returns a honest fallback; real LLM should too
    # because the system prompt says "say so honestly".
    system_msg = llm.last_messages[0]["content"].lower()
    assert "honestly" in system_msg or "say so" in system_msg, (
        "System prompt must instruct the LLM to admit missing data"
    )


@pytest.mark.asyncio
async def test_no_context_does_not_crash():
    """generate_info_response with context=None must not raise."""
    llm = _CaptureLLM()
    result = await llm.generate_info_response("Hello")
    assert result is not None
    # System prompt should NOT mention any specific city
    system_msg = llm.last_messages[0]["content"].lower()
    assert "dubai" not in system_msg
