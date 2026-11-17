"""
drone_detector.py — Rogue UAV drone detection and contraband payload drop tracker.

Tracks aerial targets traversing border airspace:
  * Drone Incursion: High-speed aerial target in upper frame FOV.
  * Drone Hovering: Stationary airborne loitering characteristic of drop-zone reconnaissance.
  * Contraband Payload Drop: Rapid vertical descent of object or target decoupling
    from airborne altitude to ground level, followed by fast egress.
  * Estimates ground drop coordinates for rapid Quick Reaction Team (QRT) recovery.
"""
from __future__ import annotations

import logging
import math
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, List, Optional, Tuple

logger = logging.getLogger("ibvap.drone_detector")


@dataclass
class DroneAlert:
    alert_id: str
    track_id: str
    alert_type: str            # "UAV_INCURSION", "UAV_HOVERING", "PAYLOAD_DROP_DETECTED", "UAV_EGRESS"
    severity: str              # "Critical", "High", "Medium"
    tactical_priority: int     # 1 (Highest) or 2
    threat_score: float        # 0.0 to 1.0
    altitude_relative: float   # normalized (0.0=top of sky, 1.0=ground)
    speed_normalized: float    # units per second
    drop_point: Optional[Tuple[float, float]]
    advisory: str
    timestamp: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "alert_id": self.alert_id,
            "track_id": self.track_id,
            "alert_type": self.alert_type,
            "severity": self.severity,
            "tactical_priority": self.tactical_priority,
            "threat_score": round(self.threat_score, 3),
            "altitude_relative": round(self.altitude_relative, 3),
            "speed_normalized": round(self.speed_normalized, 4),
            "drop_point": (round(self.drop_point[0], 3), round(self.drop_point[1], 3)) if self.drop_point else None,
            "advisory": self.advisory,
            "timestamp": self.timestamp,
        }


@dataclass
class _DroneObservation:
    cx: float
    cy: float
    w: float
    h: float
    timestamp: float


class DroneTrackAnalyzer:
    """Analyzes visual kinematic tracks for drone dynamics and contraband drops."""

    def __init__(
        self,
        sky_threshold_y: float = 0.65,
        hover_duration_s: float = 1.5,
        history_len: int = 25,
    ):
        self.sky_threshold_y = sky_threshold_y
        self.hover_duration_s = hover_duration_s
        self.history_len = max(5, history_len)
        self._tracks: Dict[str, Deque[_DroneObservation]] = {}
        self._dropped_tracks: set[str] = set()

    def clear(self, track_id: Optional[str] = None) -> None:
        if track_id is None:
            self._tracks.clear()
            self._dropped_tracks.clear()
        else:
            self._tracks.pop(track_id, None)
            self._dropped_tracks.discard(track_id)

    def update_track(
        self,
        track_id: str,
        bbox: Tuple[float, float, float, float],
        timestamp: Optional[float] = None,
    ) -> Optional[DroneAlert]:
        """Updates track with normalized bbox (x1, y1, x2, y2) and evaluates drone kinematics."""
        now = timestamp if timestamp is not None else time.time()
        x1, y1, x2, y2 = bbox
        cx = (x1 + x2) / 2.0
        cy = (y1 + y2) / 2.0
        w = max(0.001, x2 - x1)
        h = max(0.001, y2 - y1)

        if track_id not in self._tracks:
            self._tracks[track_id] = deque(maxlen=self.history_len)

        self._tracks[track_id].append(_DroneObservation(cx, cy, w, h, now))
        history = self._tracks[track_id]

        if len(history) < 3:
            return None

        p_start = history[0]
        p_latest = history[-1]
        dt = p_latest.timestamp - p_start.timestamp
        if dt <= 0.01:
            return None

        dx = p_latest.cx - p_start.cx
        dy = p_latest.cy - p_start.cy
        dist = math.hypot(dx, dy)
        speed = dist / dt

        # Target must be operating in upper airspace or descending from it
        is_airborne = p_start.cy <= self.sky_threshold_y or p_latest.cy <= self.sky_threshold_y
        if not is_airborne:
            return None

        # 1. Payload Drop Detection: Target was in sky, now rapid downward velocity (positive dy)
        # and has reached lower region or dropped significantly (dy > 0.25 within short time)
        if track_id not in self._dropped_tracks and p_start.cy < 0.4 and p_latest.cy > 0.65 and (dy / dt) > 0.12:
            self._dropped_tracks.add(track_id)
            drop_x = p_latest.cx
            drop_y = p_latest.cy
            return DroneAlert(
                alert_id=f"DRONE-DROP-{uuid.uuid4().hex[:6]}",
                track_id=track_id,
                alert_type="PAYLOAD_DROP_DETECTED",
                severity="Critical",
                tactical_priority=1,
                threat_score=0.98,
                altitude_relative=p_latest.cy,
                speed_normalized=speed,
                drop_point=(drop_x, drop_y),
                advisory=f"CRITICAL: Contraband payload drop detected at ({drop_x:.2f}, {drop_y:.2f}). Dispatch QRT search team.",
                timestamp=now,
            )

        # 2. Hovering Detection: Airborne, small displacement, held for >= hover_duration_s
        if is_airborne and dist < 0.04 and dt >= self.hover_duration_s:
            return DroneAlert(
                alert_id=f"DRONE-HOV-{uuid.uuid4().hex[:6]}",
                track_id=track_id,
                alert_type="UAV_HOVERING",
                severity="High",
                tactical_priority=2,
                threat_score=0.88,
                altitude_relative=p_latest.cy,
                speed_normalized=speed,
                drop_point=None,
                advisory="Rogue UAV hovering in border airspace. Possible pre-drop reconnaissance; activate RF scanner.",
                timestamp=now,
            )

        # 3. High-Speed Aerial Incursion: Fast motion in sky
        if is_airborne and speed > 0.08:
            return DroneAlert(
                alert_id=f"DRONE-INC-{uuid.uuid4().hex[:6]}",
                track_id=track_id,
                alert_type="UAV_INCURSION",
                severity="High",
                tactical_priority=2,
                threat_score=0.85,
                altitude_relative=p_latest.cy,
                speed_normalized=speed,
                drop_point=None,
                advisory=f"High-speed aerial incursion across border line (speed: {speed:.3f} units/s). Track with PTZ.",
                timestamp=now,
            )

        return None
