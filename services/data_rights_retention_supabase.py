"""SPEC-43 Gap 4 slice R2: retention backend over a supabase-py style client.

Not wired to any route, scheduler or CLI; any hosted run is an owner decision before production.

Implements the R1 ``RetentionBackend`` protocol (``count_expired`` and
``delete_expired``) for exactly the two approved policies in ``POLICIES``:
expired ``cached_responses`` rows (expires_at <= cutoff) and ``signal`` rows
older than the window (captured_at < cutoff). It must answer exactly like
``InMemoryRetentionBackend`` for the same rows.

- The client is injected (the service-key client, as for the erase and
  tombstone backends); this module never builds one.
- Every check runs before any client call. A failed check makes no call.
- A delete always carries both a non-empty primary-key ``in_`` filter and the
  policy time filter, so a row whose time moved after the select is kept.
- At most ``limit`` rows are deleted per call, oldest first, then by primary
  key, sent in chunks of at most ``DELETE_CHUNK`` keys.
- Nothing is logged. Failures raise ``RetentionBackendError`` whose message is
  a closed code only: no row, id, URL or response body.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from services.data_rights_retention import (
    MAX_BATCH_LIMIT,
    MIN_BATCH_LIMIT,
    POLICIES,
    RetentionCount,
    RetentionPolicy,
    validate_policy,
)

PRIMARY_KEYS: Dict[str, str] = {"cached_responses": "cache_id", "signal": "signal_id"}

# Most primary keys sent in one delete; a 5000-id in_ list is too long a URL.
DELETE_CHUNK = 200

COUNT_FAILED = "retention_count_failed"
DELETE_FAILED = "retention_delete_failed"
BACKEND_ERROR_CODES = frozenset({COUNT_FAILED, DELETE_FAILED})


class RetentionBackendError(Exception):
    """Retention backend failure. The message is the closed code only."""

    def __init__(self, code: str) -> None:
        if code not in BACKEND_ERROR_CODES:
            raise ValueError("unknown retention backend error code")
        super().__init__(code)
        self.code = code


def _approved(policy: RetentionPolicy) -> RetentionPolicy:
    validate_policy(policy)
    if policy not in POLICIES:
        raise ValueError("policy is not one of the approved retention policies")
    return policy


def _cutoff_text(cutoff: Any) -> str:
    """UTC with a Z suffix and microseconds; never a +00:00 offset."""
    if not isinstance(cutoff, datetime) or cutoff.tzinfo is None or cutoff.utcoffset() is None:
        raise ValueError("cutoff must be a timezone-aware datetime")
    return cutoff.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _checked_limit(limit: Any) -> int:
    if (
        isinstance(limit, bool)
        or not isinstance(limit, int)
        or not MIN_BATCH_LIMIT <= limit <= MAX_BATCH_LIMIT
    ):
        raise ValueError(f"limit must be an int in {MIN_BATCH_LIMIT}..{MAX_BATCH_LIMIT}")
    return limit


def _time_filter(query: Any, policy: RetentionPolicy, cutoff_text: str) -> Any:
    """The one boundary rule, matching R1 is_candidate.

    Expiry policy: time <= cutoff. Window policy: time < cutoff.
    """
    if policy.expiry_column:
        return query.lte(policy.time_column, cutoff_text)
    return query.lt(policy.time_column, cutoff_text)


def _exact_count(result: Any) -> int:
    count = getattr(result, "count", None)
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise RetentionBackendError(COUNT_FAILED)
    return count


class SupabaseRetentionBackend:
    """RetentionBackend over an injected supabase-py style client."""

    def __init__(self, client: Any) -> None:
        self._client = client

    def count_expired(self, policy: RetentionPolicy, cutoff: datetime) -> RetentionCount:
        approved = _approved(policy)
        cutoff_text = _cutoff_text(cutoff)
        table, pk = approved.table, PRIMARY_KEYS[approved.table]
        try:
            candidates = (
                _time_filter(
                    self._client.table(table).select(pk, count="exact"), approved, cutoff_text
                )
                .limit(1)
                .execute()
            )
            skipped = (
                self._client.table(table)
                .select(pk, count="exact")
                .is_(approved.time_column, "null")
                .limit(1)
                .execute()
            )
        except Exception:
            raise RetentionBackendError(COUNT_FAILED) from None
        return RetentionCount(
            candidates=_exact_count(candidates), skipped_invalid=_exact_count(skipped)
        )

    def delete_expired(self, policy: RetentionPolicy, cutoff: datetime, limit: int) -> int:
        approved = _approved(policy)
        cutoff_text = _cutoff_text(cutoff)
        batch = _checked_limit(limit)
        table, pk, column = approved.table, PRIMARY_KEYS[approved.table], approved.time_column
        try:
            selected = (
                _time_filter(
                    self._client.table(table).select(f"{pk},{column}"), approved, cutoff_text
                )
                .order(column)
                .order(pk)
                .limit(batch)
                .execute()
            )
        except Exception:
            raise RetentionBackendError(DELETE_FAILED) from None
        rows = getattr(selected, "data", None)
        if rows is None:
            rows = []
        if not isinstance(rows, list):
            raise RetentionBackendError(DELETE_FAILED)
        keys: List[Any] = [
            row[pk] for row in rows if isinstance(row, dict) and row.get(pk) is not None
        ][:batch]
        if not keys:
            return 0

        deleted = 0
        for start in range(0, len(keys), DELETE_CHUNK):
            chunk = keys[start : start + DELETE_CHUNK]
            try:
                result = _time_filter(
                    self._client.table(table).delete().in_(pk, chunk), approved, cutoff_text
                ).execute()
            except Exception:
                raise RetentionBackendError(DELETE_FAILED) from None
            data = getattr(result, "data", None)
            deleted += len(data) if isinstance(data, list) else 0
        return deleted
