"""
ibvap/models.py — Pydantic API Data Models & Command and Control (C2) Contract.

Directly addresses Roadmap Item H (C2 Integration Contract):
Defines typed response and request schemas so that FastAPI's generated /openapi.json
and /docs serve as an immutable, formal integration contract for third-party C2,
SOC SIEMs, and border force dispatch networks.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class SiteInfo(BaseModel):
    site_id: Optional[str] = Field(None, description="Global border outpost identifier")
    post_name: Optional[str] = Field(None, description="Human readable border post name")


class CameraInfo(BaseModel):
    cam_id: int = Field(..., description="Camera index")
    name: Optional[str] = Field(None, description="Camera display label")
    lat: Optional[float] = Field(None, description="Latitude coordinate")
    lon: Optional[float] = Field(None, description="Longitude coordinate")


class EntityCounts(BaseModel):
    persons: int = Field(0, description="Tracked human subjects in frame")
    vehicles: int = Field(0, description="Tracked vehicles in frame")


class EvidenceHash(BaseModel):
    sha256: Optional[str] = Field(None, description="Cryptographic SHA-256 hash of event evidence")


class IncidentEvent(BaseModel):
    schema_version: str = Field("ibvap.event/2", alias="schema")
    event_id: str = Field(..., description="Monotonic Crockford-base32 ULID")
    ts_utc: str = Field(..., description="ISO 8601 UTC timestamp")
    severity: str = Field(..., description="Incident severity (Info, Low, Medium, High, Critical)")
    category: str = Field(..., description="Incident classification category")
    score: float = Field(..., ge=0.0, le=100.0, description="Dynamic threat score")
    site: SiteInfo
    camera: CameraInfo
    counts: EntityCounts
    evidence: EvidenceHash
    details: Dict[str, Any] = Field(default_factory=dict, description="Anomaly metadata")
    producer: Optional[str] = Field(None, description="Source subsystem")


class EventAckRequest(BaseModel):
    operator: str = Field(..., description="Operator badge or callsign accepting responsibility")
    note: Optional[str] = Field("", description="Operational disposition note")


class EventAckResponse(BaseModel):
    ok: bool
    event: Dict[str, Any]


class NarrativeResponse(BaseModel):
    ok: bool
    event_id: str
    narrative: Dict[str, Any]
