"""Guards: VALID_DISH_CONTAINS lives in config.dietary only (R5, R17).

1. Identity: the loader re-exports the exact object from config.dietary.
2. Set equality: the constant equals the expected union so shrinking either
   side silently cannot stay green.
3. Rejection: an unknown contains term is caught by the loader's validation.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config.dietary
import scripts.load_dish_glossary


class TestValidDishContainsIdentity:
    """The loader must use the canonical constant, not a local copy."""

    def test_loader_uses_same_object_as_config(self):
        """scripts.load_dish_glossary.VALID_DISH_CONTAINS IS config.dietary.VALID_DISH_CONTAINS."""
        assert (
            scripts.load_dish_glossary.VALID_DISH_CONTAINS is config.dietary.VALID_DISH_CONTAINS
        ), (
            "VALID_DISH_CONTAINS in the loader is not the same object as in "
            "config.dietary -- a local redefinition has crept back in"
        )


class TestValidDishContainsSetEquality:
    """The constant equals the expected explicit union."""

    def test_equals_expected_union(self):
        """VALID_DISH_CONTAINS == VALID_ALLERGENS | extension set."""
        expected_extension = frozenset(
            {
                "pork",
                "beef",
                "chilli",
                "alcohol",
                "fish_sauce",
                "egg",
                "peanut",
                "soy",
                "tree_nut",
            }
        )
        expected = config.dietary.VALID_ALLERGENS | expected_extension
        assert config.dietary.VALID_DISH_CONTAINS == expected, (
            f"VALID_DISH_CONTAINS has diverged from expected union.\n"
            f"  Missing: {expected - config.dietary.VALID_DISH_CONTAINS}\n"
            f"  Extra: {config.dietary.VALID_DISH_CONTAINS - expected}"
        )


class TestDishContainsRejection:
    """The loader validation rejects unknown contains terms."""

    def test_unknown_term_rejected(self):
        """A dish with an invalid contains term produces a validation error."""
        from scripts.load_dish_glossary import validate_glossary

        dishes = [
            {
                "dish_key": "test_bad_dish",
                "name_en": "Test Bad Dish",
                "contains": ["unicorn_tears"],
                "may_contain": [],
                "suitable_for": [],
            }
        ]
        errors = validate_glossary(dishes)
        assert any("unicorn_tears" in e for e in errors), (
            f"Expected rejection of unknown term 'unicorn_tears', got: {errors}"
        )
