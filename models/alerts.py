"""SPEC-29: Context Alert models."""

import hashlib
from datetime import datetime, timezone
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class AlertEvidence(BaseModel):
    """Typed evidence containing only observed provider values."""

    rain_probability: Optional[float] = None
    temp_c: Optional[float] = None
    feels_like_c: Optional[float] = None
    humidity: Optional[int] = None
    condition_code: Optional[int] = None


class ContextAlert(BaseModel):
    """A single structured context alert."""

    alert_id: str
    alert_type: str  # rain | storm | high_heat | extreme_heat | high_humidity
    severity: str  # info | advisory | warning
    message: str
    affected_node_ids: List[str]
    affected_node_names: List[str]
    source: str = "openweather"
    source_updated_at: datetime
    valid_from: datetime
    valid_until: datetime
    expires_at: datetime
    location_basis: str  # "trip_region" | "node_coordinates"
    geo_region: Optional[str] = None
    evidence: AlertEvidence
    suggested_action: Optional[str] = None
    auto_applied: bool = False


class TripAlertsResponse(BaseModel):
    """Response model for GET /api/v1/trip/{trip_id}/alerts."""

    trip_id: str
    status: str = "available"  # available | unconfigured
    alerts: List[ContextAlert] = Field(default_factory=list)
    refreshed_at: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))


def make_alert_id(
    trip_id: str, alert_type: str, window_start: datetime, node_ids: List[str]
) -> str:
    """Generate a stable, deterministic alert_id."""
    key = f"{trip_id}:{alert_type}:{window_start.isoformat()}:{','.join(sorted(node_ids))}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]
