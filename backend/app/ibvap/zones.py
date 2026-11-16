"""
zones.py — Tactical border zone classification and spatial escalation matrix.

Provides high-resolution spatial threat weighting for border installations:
  * Primary Wire: Zero-line international perimeter fence.
  * Buffer Corridor: High-sensitivity buffer zone between zero-line and depth fences.
  * Patrol Road: Border Security Force vehicular/foot patrol routes.
  * BOP Perimeter: Base Outpost core compound & ammunition storage.
  * Riverine Flank: Nullah, river, or watercourse entry corridors.
  * Neutral Zone: Demarcated treaty strip with non-escalation monitoring.

Applies spatial risk multipliers, arming schedules (e.g. night-only zones),
and automatic tactical escalation advisories (e.g. QRT dispatch, perimeter illumination).
Pure Python geometry, zero GPU/OpenCV requirement.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("ibvap.zones")

ZONE_TYPES = {
    "primary_wire": {"multiplier": 2.5, "default_action": "DEPLOY_QRT", "level": "CRITICAL"},
    "buffer_corridor": {"multiplier": 1.8, "default_action": "SECTOR_SEARCH", "level": "HIGH"},
    "patrol_road": {"multiplier": 1.3, "default_action": "TRACK_MOVEMENT", "level": "ELEVATED"},
    "bop_perimeter": {"multiplier": 3.0, "default_action": "LOCKDOWN_ALARM", "level": "CRITICAL"},
    "riverine_flank": {"multiplier": 2.0, "default_action": "ILLUMINATE_SECTOR", "level": "HIGH"},
    "neutral_zone": {"multiplier": 1.0, "default_action": "LOG_TRANSIT", "level": "NOMINAL"},
}


def _point_in_polygon(px: float, py: float, polygon: List[Tuple[float, float]]) -> bool:
    """Ray casting algorithm for point-in-polygon containment test.
    
    Coordinates are normalized (0.0 to 1.0).
    """
    if len(polygon) < 3:
        return False
    inside = False
    n = len(polygon)
    p1x, p1y = polygon[0]
    for i in range(n + 1):
        p2x, p2y = polygon[i % n]
        if py > min(p1y, p2y):
            if py <= max(p1y, p2y):
                if px <= max(p1x, p2x):
                    if p1y != p2y:
                        xinters = (py - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                    else:
                        xinters = p1x
                    if p1x == p2x or px <= xinters:
                        inside = not inside
        p1x, p1y = p2x, p2y
    return inside


@dataclass
class TacticalZone:
    zone_id: str
    name: str
    zone_type: str
    polygon: List[Tuple[float, float]]
    risk_multiplier: float = 1.0
    armed: bool = True
    schedule_start_hour: Optional[int] = None  # 0..23 (e.g. 19 for 19:00 night-arm)
    schedule_end_hour: Optional[int] = None    # 0..23 (e.g. 6 for 06:00 dawn-disarm)
    advisory_override: str = ""

    def __post_init__(self):
        if self.zone_type in ZONE_TYPES and self.risk_multiplier == 1.0:
            self.risk_multiplier = ZONE_TYPES[self.zone_type]["multiplier"]

    def contains(self, px: float, py: float) -> bool:
        return _point_in_polygon(px, py, self.polygon)

    def is_armed_at(self, hour: Optional[int] = None) -> bool:
        if not self.armed:
            return False
        if hour is None or self.schedule_start_hour is None or self.schedule_end_hour is None:
            return True
        start, end = self.schedule_start_hour, self.schedule_end_hour
        if start <= end:
            return start <= hour <= end
        else:  # crosses midnight, e.g. 20:00 to 06:00
            return hour >= start or hour <= end

    def to_dict(self) -> Dict[str, Any]:
        return {
            "zone_id": self.zone_id,
            "name": self.name,
            "zone_type": self.zone_type,
            "polygon": self.polygon,
            "risk_multiplier": self.risk_multiplier,
            "armed": self.armed,
            "schedule_start_hour": self.schedule_start_hour,
            "schedule_end_hour": self.schedule_end_hour,
            "advisory_override": self.advisory_override,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> TacticalZone:
        poly_raw = data.get("polygon", [])
        poly = [(float(pt[0]), float(pt[1])) for pt in poly_raw]
        return cls(
            zone_id=data.get("zone_id", ""),
            name=data.get("name", "Unnamed Zone"),
            zone_type=data.get("zone_type", "buffer_corridor"),
            polygon=poly,
            risk_multiplier=float(data.get("risk_multiplier", 1.0)),
            armed=bool(data.get("armed", True)),
            schedule_start_hour=data.get("schedule_start_hour"),
            schedule_end_hour=data.get("schedule_end_hour"),
            advisory_override=data.get("advisory_override", ""),
        )


@dataclass
class ZoneEvaluationResult:
    matched_zones: List[str]
    primary_zone: Optional[TacticalZone]
    effective_risk: float
    escalation_level: str
    advisory: str
    tactical_action: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "matched_zones": self.matched_zones,
            "primary_zone_name": self.primary_zone.name if self.primary_zone else None,
            "primary_zone_type": self.primary_zone.zone_type if self.primary_zone else None,
            "effective_risk": round(self.effective_risk, 3),
            "escalation_level": self.escalation_level,
            "advisory": self.advisory,
            "tactical_action": self.tactical_action,
        }


class ZoneEscalationEngine:
    """Manages tactical border zones per camera feed and computes escalation threat multipliers."""

    def __init__(self, persistence_path: Optional[Path | str] = None):
        self._zones_by_camera: Dict[str, Dict[str, TacticalZone]] = {}
        self._path = Path(persistence_path) if persistence_path else None
        if self._path and self._path.is_file():
            self.load()

    def add_zone(self, cam_id: str, zone: TacticalZone) -> None:
        if cam_id not in self._zones_by_camera:
            self._zones_by_camera[cam_id] = {}
        self._zones_by_camera[cam_id][zone.zone_id] = zone
        if self._path:
            self.save()

    def remove_zone(self, cam_id: str, zone_id: str) -> bool:
        if cam_id in self._zones_by_camera and zone_id in self._zones_by_camera[cam_id]:
            del self._zones_by_camera[cam_id][zone_id]
            if self._path:
                self.save()
            return True
        return False

    def get_zones(self, cam_id: str) -> List[TacticalZone]:
        return list(self._zones_by_camera.get(cam_id, {}).values())

    def evaluate_point(
        self,
        cam_id: str,
        point: Tuple[float, float],
        base_risk: float = 0.5,
        hour: Optional[int] = None,
    ) -> ZoneEvaluationResult:
        """Evaluates a normalized coordinate (x, y) against configured tactical zones."""
        px, py = point
        cam_zones = self.get_zones(cam_id)
        
        matching_active_zones: List[TacticalZone] = []
        for zone in cam_zones:
            if zone.is_armed_at(hour) and zone.contains(px, py):
                matching_active_zones.append(zone)

        if not matching_active_zones:
            level = "CRITICAL" if base_risk >= 0.8 else "HIGH" if base_risk >= 0.6 else "ELEVATED" if base_risk >= 0.4 else "NOMINAL"
            return ZoneEvaluationResult(
                matched_zones=[],
                primary_zone=None,
                effective_risk=min(1.0, max(0.0, base_risk)),
                escalation_level=level,
                advisory="Target outside designated tactical zones; nominal tracking active.",
                tactical_action="MONITOR",
            )

        # Pick zone with highest risk multiplier
        primary = max(matching_active_zones, key=lambda z: z.risk_multiplier)
        effective_risk = min(1.0, base_risk * primary.risk_multiplier)

        type_meta = ZONE_TYPES.get(primary.zone_type, {"default_action": "INTERCEPT", "level": "HIGH"})
        tactical_action = type_meta["default_action"]

        if effective_risk >= 0.85:
            escalation_level = "CRITICAL"
        elif effective_risk >= 0.65:
            escalation_level = "HIGH"
        elif effective_risk >= 0.45:
            escalation_level = "ELEVATED"
        else:
            escalation_level = "NOMINAL"

        if primary.advisory_override:
            advisory = primary.advisory_override
        else:
            advisory = f"Active intrusion in {primary.name} ({primary.zone_type.replace('_', ' ').title()}). Recommended action: {tactical_action}."

        return ZoneEvaluationResult(
            matched_zones=[z.name for z in matching_active_zones],
            primary_zone=primary,
            effective_risk=effective_risk,
            escalation_level=escalation_level,
            advisory=advisory,
            tactical_action=tactical_action,
        )

    def to_dict(self) -> Dict[str, Any]:
        out = {}
        for cam_id, zones in self._zones_by_camera.items():
            out[cam_id] = [z.to_dict() for z in zones.values()]
        return out

    def save(self) -> None:
        if not self._path:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")

    def load(self) -> None:
        if not self._path or not self._path.is_file():
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            self._zones_by_camera = {}
            for cam_id, zone_list in data.items():
                self._zones_by_camera[cam_id] = {
                    item["zone_id"]: TacticalZone.from_dict(item) for item in zone_list
                }
        except Exception as e:
            logger.warning("Failed to load tactical zones from %s: %s", self._path, e)
