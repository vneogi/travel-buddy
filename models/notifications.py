"""SPEC-35 Phase A: typed notification response models.

Read-only candidates returned by GET /api/v1/trip/{trip_id}/notifications.
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class RouteEvidence(BaseModel):
    """Provider-backed route observation."""

    source: str
    observed_at: datetime
    normal_duration_minutes: Optional[int] = None
    traffic_duration_minutes: int
    mode: str
    origin_basis: str


class WeatherEvidence(BaseModel):
    """Weather observation used for the rain buffer decision."""

    source: str
    observed_at: datetime
    rain_probability: float


class PolicyBuffers(BaseModel):
    """Separately disclosed policy buffers (not folded into provider data)."""

    arrival_buffer_minutes: int
    weather_buffer_minutes: int


class DepartureEvidence(BaseModel):
    """Evidence envelope for a departure reminder."""

    route: Optional[RouteEvidence] = None
    weather: Optional[WeatherEvidence] = None
    policy: PolicyBuffers


class NotificationCandidate(BaseModel):
    """A single notification candidate in the response."""

    notification_id: str
    type: str
    priority: str
    node_id: str
    title: str
    message: str
    eligible_at: datetime
    expires_at: datetime
    recommended_departure_at: Optional[datetime] = None
    time_zone: Optional[str] = None
    deep_link: str
    evidence: DepartureEvidence


class TripNotificationsResponse(BaseModel):
    """Top-level response for the notifications endpoint."""

    trip_id: str
    refreshed_at: datetime
    status: str  # "available" | "partial" | "unconfigured"
    notifications: List[NotificationCandidate]
