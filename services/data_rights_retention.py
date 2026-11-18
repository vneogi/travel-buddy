"""SPEC-43 Gap 4 slice R1: retention planner and bounded, dry-run-first delete.

Windows are proposals subject to counsel review; hosted enablement is owner-only.

Two windows only (SPEC-43 proposed defaults):

- cached_responses: a row is expired when expires_at <= now.
- signal: a row is a candidate when captured_at is older than 365 days.

The planner is pure. The executor only calls ``count_expired`` and
``delete_expired`` on a backend; it builds no SQL and runs nothing against a
hosted database. ``InMemoryRetentionBackend`` is the reference shape for a
later database backend. Reports carry counts and times only: no user ids, no
row ids, no text. The suppression record table is never a valid policy.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, NamedTuple, Optional, Protocol, Tuple

from config.data_rights import ERASE_EXEMPT_TABLES

SIGNAL_WINDOW = timedelta(days=365)
MIN_BATCH_LIMIT = 1
MAX_BATCH_LIMIT = 5000
DEFAULT_BATCH_LIMIT = 500
_FORBIDDEN_TABLES = frozenset({"data_rights_tombstone"}) | ERASE_EXEMPT_TABLES


@dataclass(frozen=True)
class RetentionPolicy:
    table: str  # "cached_responses" or "signal"
    time_column: str  # "expires_at" or "captured_at"
    window: Optional[timedelta]  # None means "delete when time_column <= now"
    expiry_column: bool  # True for expires_at semantics

    def __post_init__(self) -> None:
        validate_policy(self)


def validate_policy(policy: RetentionPolicy) -> None:
    """Reject policies that could delete protected rows or are malformed."""
    if policy.table in _FORBIDDEN_TABLES:
        raise ValueError("retention policy may not target an erase-exempt table")
    if not policy.table or not policy.time_column:
        raise ValueError("retention policy needs a table and a time column")
    if policy.expiry_column:
        if policy.window is not None:
            raise ValueError("expiry policy must not set a window")
    else:
        if policy.window is None or policy.window <= timedelta(0):
            raise ValueError("window policy needs a positive window")


POLICIES: Tuple[RetentionPolicy, ...] = (
    RetentionPolicy(
        table="cached_responses",
        time_column="expires_at",
        window=None,
        expiry_column=True,
    ),
    RetentionPolicy(
        table="signal",
        time_column="captured_at",
        window=SIGNAL_WINDOW,
        expiry_column=False,
    ),
)


def _require_aware_utc(now: Any) -> datetime:
    if not isinstance(now, datetime):
        raise ValueError("now must be a datetime")
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware UTC")
    return now.astimezone(timezone.utc)


def cutoff_for(policy: RetentionPolicy, now: datetime) -> datetime:
    """Expiry policy: now. Window policy: now minus the window."""
    aware = _require_aware_utc(now)
    if policy.expiry_column:
        return aware
    return aware - policy.window


def is_candidate(policy: RetentionPolicy, row_time: datetime, cutoff: datetime) -> bool:
    """Boundary rule. Expiry: row_time <= cutoff. Window: row_time < cutoff."""
    if policy.expiry_column:
        return row_time <= cutoff
    return row_time < cutoff


def _valid_time(value: Any) -> Optional[datetime]:
    """An aware datetime, else None (missing, wrong type, or naive)."""
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        return None
    return value


class RetentionCount(NamedTuple):
    candidates: int
    skipped_invalid: int


class RetentionBackend(Protocol):
    def count_expired(self, policy: RetentionPolicy, cutoff: datetime) -> RetentionCount: ...

    def delete_expired(self, policy: RetentionPolicy, cutoff: datetime, limit: int) -> int: ...


@dataclass(frozen=True)
class TableRetention:
    table: str
    cutoff: str  # ISO UTC
    candidates: int
    deleted: int
    skipped_invalid: int
    remaining: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "table": self.table,
            "cutoff": self.cutoff,
            "candidates": self.candidates,
            "deleted": self.deleted,
            "skipped_invalid": self.skipped_invalid,
            "remaining": self.remaining,
        }


@dataclass(frozen=True)
class RetentionReport:
    now: str  # ISO UTC
    dry_run: bool
    tables: Tuple[TableRetention, ...]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "now": self.now,
            "dry_run": self.dry_run,
            "tables": [t.to_dict() for t in self.tables],
        }


def _check_batch_limit(batch_limit: Any) -> int:
    if (
        isinstance(batch_limit, bool)
        or not isinstance(batch_limit, int)
        or not MIN_BATCH_LIMIT <= batch_limit <= MAX_BATCH_LIMIT
    ):
        raise ValueError(f"batch_limit must be an int in {MIN_BATCH_LIMIT}..{MAX_BATCH_LIMIT}")
    return batch_limit


def run_retention(
    backend: RetentionBackend,
    *,
    now: datetime,
    dry_run: bool = True,
    batch_limit: int = DEFAULT_BATCH_LIMIT,
    policies: Iterable[RetentionPolicy] = POLICIES,
) -> RetentionReport:
    """Count, and unless dry_run delete, at most batch_limit rows per policy."""
    aware_now = _require_aware_utc(now)
    limit = _check_batch_limit(batch_limit)
    chosen = tuple(policies)
    for policy in chosen:
        validate_policy(policy)

    tables: List[TableRetention] = []
    for policy in chosen:
        cutoff = cutoff_for(policy, aware_now)
        counted = backend.count_expired(policy, cutoff)
        candidates = int(counted.candidates)
        deleted = 0 if dry_run else int(backend.delete_expired(policy, cutoff, limit))
        tables.append(
            TableRetention(
                table=policy.table,
                cutoff=cutoff.isoformat(),
                candidates=candidates,
                deleted=deleted,
                skipped_invalid=int(counted.skipped_invalid),
                remaining=candidates > deleted,
            )
        )
    return RetentionReport(now=aware_now.isoformat(), dry_run=dry_run, tables=tuple(tables))


class InMemoryRetentionBackend:
    """Reference backend: rows are dicts keyed by table, each with an id and a
    time column. Test and design use only; no persistence.
    """

    PRIMARY_KEYS: Dict[str, str] = {"cached_responses": "cache_id", "signal": "signal_id"}

    def __init__(self, tables: Optional[Dict[str, List[Dict[str, Any]]]] = None) -> None:
        self.tables: Dict[str, List[Dict[str, Any]]] = {
            name: [dict(row) for row in rows] for name, rows in (tables or {}).items()
        }
        # Primary keys in delete order, for tests of ordering only.
        self.deleted_keys: List[Tuple[str, Any]] = []

    def _pk(self, table: str) -> str:
        return self.PRIMARY_KEYS.get(table, "id")

    def _scan(self, policy: RetentionPolicy, cutoff: datetime):
        pk = self._pk(policy.table)
        candidates = []
        skipped = 0
        for index, row in enumerate(self.tables.get(policy.table, [])):
            row_time = _valid_time(row.get(policy.time_column))
            if row_time is None:
                skipped += 1
                continue
            if is_candidate(policy, row_time, cutoff):
                candidates.append((row_time, str(row.get(pk)), index))
        candidates.sort(key=lambda c: (c[0], c[1]))
        return candidates, skipped

    def count_expired(self, policy: RetentionPolicy, cutoff: datetime) -> RetentionCount:
        candidates, skipped = self._scan(policy, cutoff)
        return RetentionCount(candidates=len(candidates), skipped_invalid=skipped)

    def delete_expired(self, policy: RetentionPolicy, cutoff: datetime, limit: int) -> int:
        limit = _check_batch_limit(limit)
        candidates, _ = self._scan(policy, cutoff)
        chosen = candidates[:limit]
        rows = self.tables.get(policy.table, [])
        drop = {index for _, _, index in chosen}
        pk = self._pk(policy.table)
        for _, _, index in chosen:
            self.deleted_keys.append((policy.table, rows[index].get(pk)))
        self.tables[policy.table] = [row for i, row in enumerate(rows) if i not in drop]
        return len(chosen)
