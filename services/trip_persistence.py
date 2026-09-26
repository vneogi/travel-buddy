"""Typed persistence contract for atomic trip commands (SPEC-44 A1-A3)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Callable, Optional, Protocol

from models.schemas import TripParty, TripPartyIn, TripState


class TripPersistenceError(RuntimeError):
    """Base class for named trip command failures."""

    code = "trip_persistence_error"


class TripVersionConflict(TripPersistenceError):
    """The stored trip changed after the caller loaded it."""

    code = "trip_version_conflict"


class CommandPayloadMismatch(TripPersistenceError):
    """A command ID was reused with a different type or payload."""

    code = "command_payload_mismatch"


class RerouteLimitReached(TripPersistenceError):
    """A structural command could not reserve quota in its transaction."""

    code = "daily_reroute_limit_reached"


@dataclass(frozen=True)
class TripCommandResult:
    trip_state: TripState
    party: Optional[TripParty] = None
    response_data: Optional[dict[str, Any]] = None
    replayed: bool = False


def command_payload_hash(payload: dict[str, Any]) -> str:
    """Return a stable hash without retaining the command's raw payload."""
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class TripPersistence(Protocol):
    def get_trip_command(
        self,
        user_id: str,
        command_id: str,
        command_type: str,
        command_payload: dict[str, Any],
    ) -> Optional[TripCommandResult]:
        """Return a matching prior command or reject command ID reuse."""
        ...

    def commit_trip_command(
        self,
        trip_state: TripState,
        command_id: str,
        command_type: str,
        command_payload: dict[str, Any],
        expected_version: Optional[int] = None,
        party: Optional[TripPartyIn] = None,
        response_data: Optional[dict[str, Any]] = None,
        consume_reroute: bool = False,
        failure_injector: Optional[Callable[[str], None]] = None,
    ) -> TripCommandResult:
        """Atomically persist a create or mutation and its command outcome."""
        ...
