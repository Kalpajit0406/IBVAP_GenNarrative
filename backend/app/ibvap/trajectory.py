"""
trajectory.py — Target trajectory vector analyzer and boundary approach estimation.

Calculates heading, velocity, perimeter approach angles, Time-To-Boundary (TTB),
and anomalous kinematics (sprints toward zero-line, parallel pacing, zigzag evasion).
Operates on normalized coordinates (0.0 to 1.0) with zero external C/GPU dependencies.
"""
from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass
from typing import Deque, Dict, List, Optional, Tuple


@dataclass(frozen=True)
class TrajectoryPoint:
    x: float
    y: float
    timestamp: float


@dataclass
class TrajectoryVector:
    track_id: str
    speed: float                  # normalized units per second
    heading_deg: float            # 0° = North (-Y), 90° = East (+X), 180° = South (+Y), 270° = West (-X)
    is_approaching: bool          # moving closer to boundary
    approach_angle_deg: Optional[float] = None  # angle relative to boundary line normal (0° = straight-in)
    time_to_boundary_s: Optional[float] = None  # estimated seconds until crossing line
    is_evasive: bool = False      # true if zigzagging or erratic heading changes
    pattern: str = "STATIONARY"   # "SPRINT_TO_BOUNDARY", "PARALLEL_PROBING", "RECEDING", "STATIONARY", "ZIGZAG_EVASION"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "track_id": self.track_id,
            "speed": round(self.speed, 4),
            "heading_deg": round(self.heading_deg, 1),
            "is_approaching": self.is_approaching,
            "approach_angle_deg": round(self.approach_angle_deg, 1) if self.approach_angle_deg is not None else None,
            "time_to_boundary_s": round(self.time_to_boundary_s, 2) if self.time_to_boundary_s is not None else None,
            "is_evasive": self.is_evasive,
            "pattern": self.pattern,
        }


class BorderBoundarySegment:
    """Represents a border perimeter or tripwire line segment in normalized space."""

    def __init__(self, p1: Tuple[float, float], p2: Tuple[float, float]):
        self.p1 = (float(p1[0]), float(p1[1]))
        self.p2 = (float(p2[0]), float(p2[1]))
        self.dx = self.p2[0] - self.p1[0]
        self.dy = self.p2[1] - self.p1[1]
        self.length = math.hypot(self.dx, self.dy)

    def distance_to_point(self, px: float, py: float) -> float:
        """Computes shortest perpendicular distance from point to segment."""
        if self.length == 0:
            return math.hypot(px - self.p1[0], py - self.p1[1])
        t = max(0.0, min(1.0, ((px - self.p1[0]) * self.dx + (py - self.p1[1]) * self.dy) / (self.length ** 2)))
        proj_x = self.p1[0] + t * self.dx
        proj_y = self.p1[1] + t * self.dy
        return math.hypot(px - proj_x, py - proj_y)

    def normal_angle_deg(self) -> float:
        """Returns the normal angle (0..360°) perpendicular to the line segment."""
        angle = math.degrees(math.atan2(-self.dx, self.dy))
        return (angle + 360.0) % 360.0


class TrajectoryAnalyzer:
    """Tracks historical target positions and computes kinematics and threat vectors."""

    def __init__(self, history_len: int = 20, min_speed_threshold: float = 0.01):
        self.history_len = max(3, history_len)
        self.min_speed_threshold = min_speed_threshold
        self._tracks: Dict[str, Deque[TrajectoryPoint]] = {}

    def add_point(self, track_id: str, x: float, y: float, timestamp: float) -> None:
        if track_id not in self._tracks:
            self._tracks[track_id] = deque(maxlen=self.history_len)
        self._tracks[track_id].append(TrajectoryPoint(float(x), float(y), float(timestamp)))

    def clear(self, track_id: Optional[str] = None) -> None:
        if track_id is None:
            self._tracks.clear()
        elif track_id in self._tracks:
            del self._tracks[track_id]

    def analyze(
        self,
        track_id: str,
        boundary: Optional[BorderBoundarySegment] = None,
    ) -> Optional[TrajectoryVector]:
        pts = self._tracks.get(track_id)
        if not pts or len(pts) < 2:
            return None

        p_start = pts[0]
        p_end = pts[-1]
        dt = p_end.timestamp - p_start.timestamp
        if dt <= 0.001:
            return None

        dx = p_end.x - p_start.x
        dy = p_end.y - p_start.y
        dist = math.hypot(dx, dy)
        speed = dist / dt

        # Compass heading: 0° is North (-Y), 90° East (+X), 180° South (+Y), 270° West (-X)
        raw_heading = math.degrees(math.atan2(dx, -dy))
        heading_deg = (raw_heading + 360.0) % 360.0

        if speed < self.min_speed_threshold:
            return TrajectoryVector(
                track_id=track_id,
                speed=speed,
                heading_deg=heading_deg,
                is_approaching=False,
                pattern="STATIONARY",
            )

        # Evasion detection: check angular variance across step-by-step headings
        step_headings = []
        for i in range(len(pts) - 1):
            s_dx = pts[i + 1].x - pts[i].x
            s_dy = pts[i + 1].y - pts[i].y
            if math.hypot(s_dx, s_dy) > 0.005:
                ang = (math.degrees(math.atan2(s_dx, -s_dy)) + 360.0) % 360.0
                step_headings.append(ang)

        is_evasive = False
        if len(step_headings) >= 3:
            # Check consecutive turn changes
            sign_changes = 0
            for i in range(len(step_headings) - 2):
                diff1 = (step_headings[i + 1] - step_headings[i] + 180.0) % 360.0 - 180.0
                diff2 = (step_headings[i + 2] - step_headings[i + 1] + 180.0) % 360.0 - 180.0
                if (diff1 * diff2) < -100.0:  # sharp back-and-forth switch > 10 degrees
                    sign_changes += 1
            if sign_changes >= 2:
                is_evasive = True

        # Boundary interaction analysis
        approach_angle: Optional[float] = None
        ttb: Optional[float] = None
        is_approaching = False

        if boundary:
            d_start = boundary.distance_to_point(p_start.x, p_start.y)
            d_end = boundary.distance_to_point(p_end.x, p_end.y)
            delta_d = d_start - d_end
            approach_rate = delta_d / dt  # rate of closing distance

            if approach_rate > 0.005:
                is_approaching = True
                ttb = max(0.0, d_end / approach_rate)
            else:
                is_approaching = False

            # Calculate relative approach angle to boundary normal
            boundary_normal = boundary.normal_angle_deg()
            diff_angle = abs((heading_deg - boundary_normal + 180.0) % 360.0 - 180.0)
            approach_angle = min(diff_angle, 180.0 - diff_angle)

        # Determine tactical pattern
        if is_evasive:
            pattern = "ZIGZAG_EVASION"
        elif is_approaching:
            if speed > 0.08:
                pattern = "SPRINT_TO_BOUNDARY"
            elif approach_angle is not None and approach_angle > 60.0:
                pattern = "PARALLEL_PROBING"
            else:
                pattern = "APPROACHING_PERIMETER"
        elif speed > 0.05:
            pattern = "RECEDING"
        else:
            pattern = "LOITERING"

        return TrajectoryVector(
            track_id=track_id,
            speed=speed,
            heading_deg=heading_deg,
            is_approaching=is_approaching,
            approach_angle_deg=approach_angle,
            time_to_boundary_s=ttb,
            is_evasive=is_evasive,
            pattern=pattern,
        )
