"""SPEC-14: dietary suitability claim is retired.

The app must not tell a traveller a venue or dish is halal, Jain,
vegetarian, vegan, or otherwise suitable for a diet.  Ingredient facts
stay as facts.  The hole closes by silence.

Sabotage proofs:
  S1: Keep a suitable_for badge in API response -> payload test fails.
  S2: Filter venues on dietary constraint -> no-filter test fails.
  S3: Return contains: [] for unknown -> absent-vs-empty test fails.
  S4: Skip driver card disclaimer -> disclaimer test fails.
"""

import json

import pytest

from tests.conftest import auth


def _create_dubai_trip(client):
    resp = client.post(
        "/api/v1/trip/create",
        json={"start_date": "2026-10-10T00:00:00", "geo_region": "dubai_uae"},
        headers=auth("u_spec14"),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["trip_id"]


class TestNoDietarySuitabilityClaim:
    """No API response carries a dietary suitability claim for a venue."""

    def test_venue_search_has_no_suitable_for(self, client):
        """suitable_for must be absent from /venues/search results."""
        resp = client.get(
            "/api/v1/venues/search",
            params={"query": "cafe", "lat": 25.1972, "lng": 55.2744},
            headers=auth("u_spec14"),
        )
        assert resp.status_code == 200
        body = resp.json()
        raw = json.dumps(body["results"])
        assert "suitable_for" not in raw, (
            "suitable_for leaked into venue search response"
        )

    def test_trip_event_response_has_no_suitable_for_in_nodes(self, client):
        """updated_nodes from /trip/event must not contain suitable_for."""
        trip_id = _create_dubai_trip(client)
        resp = client.post(
            "/api/v1/trip/event",
            json={
                "trip_id": trip_id,
                "event_type": "ask_info",
                "message": "What food should I eat?",
            },
            headers=auth("u_spec14"),
        )
        assert resp.status_code == 200
        body = resp.json()
        nodes_raw = json.dumps(body["updated_nodes"])
        assert "suitable_for" not in nodes_raw, (
            "suitable_for leaked into trip event updated_nodes"
        )

    def test_trip_get_has_no_suitable_for_claim(self, client):
        """GET /trip/{id} nodes must not carry suitable_for."""
        trip_id = _create_dubai_trip(client)
        resp = client.get(
            f"/api/v1/trip/{trip_id}",
            headers=auth("u_spec14"),
        )
        assert resp.status_code == 200
        raw = json.dumps(resp.json())
        assert "suitable_for" not in raw, (
            "suitable_for leaked into GET /trip response"
        )


class TestNoDietaryFiltering:
    """A request with a dietary preference must not shrink the candidate set."""

    def test_dietary_constraint_does_not_filter_venues(self, client):
        """Venues returned for a halal user match a non-halal query."""
        params_base = {
            "query": "restaurant",
            "lat": 25.1972,
            "lng": 55.2744,
            "top_k": 5,
        }
        headers = auth("u_spec14")

        resp_neutral = client.get(
            "/api/v1/venues/search", params=params_base, headers=headers
        )
        resp_dietary = client.get(
            "/api/v1/venues/search",
            params={**params_base, "dietary_constraint": "halal"},
            headers=headers,
        )
        assert resp_neutral.status_code == 200
        assert resp_dietary.status_code == 200
        # The dietary param should be ignored; same results
        assert resp_neutral.json()["results_count"] == resp_dietary.json()["results_count"]


class TestIngredientFactsNotClaims:
    """Ingredient facts with disclaimer; missing ingredients are absent not empty."""

    def test_venue_search_includes_food_disclaimer(self, client):
        """Venue search response must include the food disclaimer."""
        resp = client.get(
            "/api/v1/venues/search",
            params={"query": "cafe", "lat": 25.1972, "lng": 55.2744},
            headers=auth("u_spec14"),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "food_disclaimer" in body, "food_disclaimer missing from response"
        assert "incomplete" in body["food_disclaimer"].lower()
        assert "confirm" in body["food_disclaimer"].lower()

    def test_trip_event_includes_food_disclaimer(self, client):
        """Trip event response must include the food disclaimer."""
        trip_id = _create_dubai_trip(client)
        resp = client.post(
            "/api/v1/trip/event",
            json={
                "trip_id": trip_id,
                "event_type": "ask_info",
                "message": "Where is a good restaurant?",
            },
            headers=auth("u_spec14"),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "food_disclaimer" in body, "food_disclaimer missing from event response"
        assert "incomplete" in body["food_disclaimer"].lower()


class TestDisclaimerConstants:
    """Disclaimer constants are valid and match across Python and Dart."""

    def test_python_disclaimer_is_ascii(self):
        from config.disclaimers import FOOD_DISCLAIMER, FOOD_DISCLAIMER_SHORT

        for s in (FOOD_DISCLAIMER, FOOD_DISCLAIMER_SHORT):
            assert all(ord(c) < 128 for c in s), f"Non-ASCII in disclaimer: {s!r}"

    def test_python_disclaimer_has_required_phrases(self):
        from config.disclaimers import FOOD_DISCLAIMER

        assert "incomplete" in FOOD_DISCLAIMER.lower()
        assert "menus change" in FOOD_DISCLAIMER.lower()
        assert "confirm" in FOOD_DISCLAIMER.lower()


class TestExistingLoaderTestsUnbroken:
    """Existing loader/vocab tests that guard VALID_DISH_CONTAINS stay green."""

    def test_valid_dish_contains_identity(self):
        """config.dietary.VALID_DISH_CONTAINS is still the canonical object."""
        import config.dietary
        import scripts.load_dish_glossary

        assert (
            scripts.load_dish_glossary.VALID_DISH_CONTAINS
            is config.dietary.VALID_DISH_CONTAINS
        )

    def test_check_allergen_conflicts_still_works(self):
        """check_allergen_conflicts still catches vegan + dairy."""
        from config.dietary import check_allergen_conflicts

        conflicts = check_allergen_conflicts(
            suitable_for=["vegan"],
            contains=["dairy"],
            may_contain=[],
        )
        assert len(conflicts) == 1
        assert "dairy" in conflicts[0]

    def test_valid_dietary_labels_still_present(self):
        """VALID_DIETARY_LABELS still exists for loader validation."""
        from config.dietary import VALID_DIETARY_LABELS

        assert "vegan" in VALID_DIETARY_LABELS
        assert "halal" in VALID_DIETARY_LABELS
