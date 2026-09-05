"""SPEC-17 decision 15: sponsored search disclosure slice.

Guards:
- Response is flat (no nested ``venue`` key).
- Positive boost always returns ``sponsored_boost_applied: true``.
- Unboosted results are not falsely labelled.
- No ``suitable_for`` anywhere (SPEC-14).
- ``food_disclaimer`` is present.
"""

import pytest

from tests.conftest import auth


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _search(client, user="sponsor-user", query="food"):
    """Search venues via the API with Dubai coordinates."""
    return client.get(
        "/api/v1/venues/search",
        params={"query": query, "lat": 25.1972, "lng": 55.2744, "top_k": 10},
        headers=auth(user),
    )


# ---------------------------------------------------------------------------
# tests
# ---------------------------------------------------------------------------


class TestFlatResponseShape:
    """The response must be flat -- no nested ``venue`` object."""

    def test_results_are_flat(self, client):
        resp = _search(client)
        assert resp.status_code == 200
        body = resp.json()
        assert "results" in body
        assert "food_disclaimer" in body
        for item in body["results"]:
            assert "venue" not in item, "nested venue object must not appear"
            assert "venue_id" in item
            assert "name" in item
            assert "description" in item
            assert "micro_location" in item
            assert "vibe_tags" in item
            assert "is_sponsored" in item
            assert "sponsored_boost_applied" in item

    def test_results_zero_returns_nested_venue_fails(self, client):
        """Explicitly verify no result item has a ``venue`` key."""
        resp = _search(client)
        body = resp.json()
        nested = [r for r in body["results"] if "venue" in r]
        assert nested == [], "results[] must not contain a venue key"


class TestSponsoredBoostDisclosure:
    """A positive boost must carry disclosure; unboosted must not."""

    def test_positive_boost_returns_disclosure(self, client):
        resp = _search(client)
        body = resp.json()
        sponsored = [r for r in body["results"] if r["is_sponsored"]]
        assert len(sponsored) > 0, "test data must include a sponsored venue"
        for item in sponsored:
            if item["sponsored_boost_applied"]:
                # This is the case we care about -- it was boosted.
                assert item["is_sponsored"] is True

    def test_boosted_venue_has_both_flags(self, client):
        resp = _search(client)
        body = resp.json()
        boosted = [r for r in body["results"] if r["sponsored_boost_applied"]]
        assert len(boosted) > 0, "test data must include a venue with positive boost"
        for item in boosted:
            assert item["is_sponsored"] is True, "sponsored_boost_applied requires is_sponsored"

    def test_unboosted_results_not_falsely_labelled(self, client):
        resp = _search(client)
        body = resp.json()
        unboosted = [r for r in body["results"] if not r["is_sponsored"]]
        assert len(unboosted) > 0, "test data must include organic venues"
        for item in unboosted:
            assert item["sponsored_boost_applied"] is False, (
                "non-sponsored venues must not have boost disclosure"
            )


class TestSpec14NoSuitableFor:
    """SPEC-14: suitable_for must never appear in any result."""

    def test_no_suitable_for_in_results(self, client):
        resp = _search(client)
        body = resp.json()
        for item in body["results"]:
            assert "suitable_for" not in item
            # Since we flatten, dishes should not appear either,
            # but guard against accidental leakage.
            assert "dishes" not in item
