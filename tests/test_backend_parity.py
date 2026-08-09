"""R13 — Both backends must satisfy one interface.

DatabaseService and SupabaseService are independent implementations of
the same contract. This test asserts that every public method on one
exists on the other with a compatible signature.

DOES NOT instantiate SupabaseService (no creds needed). Uses inspect to
compare method signatures at the class level.
"""
import inspect
from typing import Set, Dict, Tuple

import pytest


def _public_methods(cls) -> Dict[str, inspect.Signature]:
    """Return {name: signature} for all public methods (no underscore prefix)."""
    methods = {}
    for name, method in inspect.getmembers(cls, predicate=inspect.isfunction):
        if name.startswith("_"):
            continue
        methods[name] = inspect.signature(method)
    return methods


def _params_compatible(
    sig_a: inspect.Signature,
    sig_b: inspect.Signature,
    method_name: str,
) -> Tuple[bool, str]:
    """Check that sig_b is compatible with sig_a (same required params).

    Compatible means:
      - All required (no-default) params in A also exist in B
      - B may have extra params with defaults (it's a superset)
      - 'self' is excluded from comparison
    """
    params_a = {
        k: v for k, v in sig_a.parameters.items() if k != "self"
    }
    params_b = {
        k: v for k, v in sig_b.parameters.items() if k != "self"
    }

    # Required params in A (no default)
    required_a = {
        k for k, v in params_a.items()
        if v.default is inspect.Parameter.empty
        and v.kind not in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
    }

    # Required params in B
    required_b = {
        k for k, v in params_b.items()
        if v.default is inspect.Parameter.empty
        and v.kind not in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
    }

    # A's required params must all exist in B
    missing_in_b = required_a - set(params_b.keys())
    if missing_in_b:
        return False, f"required params {missing_in_b} from DatabaseService not found in SupabaseService"

    # B's required params must all exist in A (otherwise callers can't satisfy B)
    extra_required_in_b = required_b - set(params_a.keys())
    if extra_required_in_b:
        return False, f"SupabaseService requires extra params {extra_required_in_b} not in DatabaseService"

    return True, ""


class TestBackendParity:
    """Ensure DatabaseService and SupabaseService expose the same public interface."""

    @pytest.fixture(scope="class")
    def classes(self):
        from services.database_service import DatabaseService
        from services.supabase_service import SupabaseService
        return DatabaseService, SupabaseService

    @pytest.fixture(scope="class")
    def method_maps(self, classes):
        db_cls, supa_cls = classes
        return _public_methods(db_cls), _public_methods(supa_cls)

    def test_supabase_has_all_database_methods(self, method_maps):
        """Every public method on DatabaseService must exist on SupabaseService."""
        db_methods, supa_methods = method_maps
        missing = set(db_methods.keys()) - set(supa_methods.keys())
        assert not missing, (
            f"SupabaseService is missing methods present on DatabaseService: {sorted(missing)}"
        )

    def test_database_has_all_supabase_methods(self, method_maps):
        """Every public method on SupabaseService must exist on DatabaseService.

        SupabaseService should not invent methods the in-memory backend doesn't
        have — callers would break when the provider resolves to in-memory.
        """
        db_methods, supa_methods = method_maps
        extra = set(supa_methods.keys()) - set(db_methods.keys())
        # Known gaps: SupabaseService has these that DatabaseService lacks.
        # Each should be backfilled — tracked here so they don't mask NEW gaps.
        allowed_extras = {
            "get_signal",          # diagnostic — Supabase-only
            "get_signals_count",   # diagnostic — Supabase-only
            "check_cache",         # TODO: add to DatabaseService
            "store_cache",         # TODO: add to DatabaseService
            "clear_expired_cache", # TODO: add to DatabaseService
            "downgrade_user",      # TODO: add to DatabaseService
        }
        unexpected = extra - allowed_extras
        assert not unexpected, (
            f"SupabaseService has methods not on DatabaseService: {sorted(unexpected)}"
        )

    def test_signatures_compatible(self, method_maps):
        """Shared methods must have compatible signatures."""
        db_methods, supa_methods = method_maps
        shared = set(db_methods.keys()) & set(supa_methods.keys())

        # Known arity mismatches — tracked here; won't mask new ones.
        # add_venue: SupabaseService requires `embedding` (pgvector needs the
        # vector at insert time; in-memory computes mock embeddings lazily).
        known_mismatches = {"add_venue"}

        mismatches = []
        for name in sorted(shared):
            ok, reason = _params_compatible(db_methods[name], supa_methods[name], name)
            if not ok and name not in known_mismatches:
                mismatches.append(f"  {name}: {reason}")

        assert not mismatches, (
            "NEW signature mismatches between DatabaseService and SupabaseService:\n"
            + "\n".join(mismatches)
            + "\n\n(Known mismatches excluded: " + ", ".join(sorted(known_mismatches)) + ")"
        )

    def test_report_full_interface(self, method_maps, capsys):
        """Informational: print both interfaces for review.

        Always passes — its purpose is to make `pytest -v` output useful
        for spotting arity drift before it hits production.
        """
        db_methods, supa_methods = method_maps
        all_names = sorted(set(db_methods.keys()) | set(supa_methods.keys()))
        print("\n=== Backend Interface Parity Report ===")
        for name in all_names:
            db_sig = str(db_methods.get(name, "(MISSING)"))
            su_sig = str(supa_methods.get(name, "(MISSING)"))
            status = "✓" if name in db_methods and name in supa_methods else "✗"
            print(f"  {status} {name}")
            if name in db_methods:
                print(f"      DB:   {db_sig}")
            if name in supa_methods:
                print(f"      Supa: {su_sig}")
        print(f"\n  Total: DB={len(db_methods)} Supa={len(supa_methods)} Shared={len(set(db_methods) & set(supa_methods))}")
