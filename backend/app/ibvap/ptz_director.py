"""
ptz_director.py — Multi-camera cross-sensor slew-to-cue PTZ tracking director.

Translates intrusion detections and coordinates from wide-angle fixed or thermal cameras
into automated Pan-Tilt-Zoom (PTZ) steering vectors for high-magnification optical cameras.
Calculates target azimuth, elevation, and adaptive optical zoom based on target bounding height.
"""
from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("ibvap.ptz_director")


@dataclass
class CameraMountGeometry:
    cam_id: int
    azimuth_center_deg: float   # Center pointing compass azimuth (0-360)
    tilt_center_deg: float      # Elevation tilt (-45 down to +45 up)
    hfov_deg: float             # Horizontal Field of View in degrees
    vfov_deg: float             # Vertical Field of View in degrees


@dataclass
class PTZCommand:
    ptz_cam_id: int
    pan_deg: float              # 0.0 to 360.0
    tilt_deg: float             # -90.0 (straight down) to +90.0 (up)
    zoom_factor: float          # 1.0x to 30.0x
    source_cam_id: int
    target_track_id: str
    target_priority: int        # 1 (Highest)
    timestamp: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ptz_cam_id": self.ptz_cam_id,
            "pan_deg": round(self.pan_deg, 2),
            "tilt_deg": round(self.tilt_deg, 2),
            "zoom_factor": round(self.zoom_factor, 1),
            "source_cam_id": self.source_cam_id,
            "target_track_id": self.target_track_id,
            "target_priority": self.target_priority,
            "timestamp": self.timestamp,
        }


class SlewToCueDirector:
    """Computes PTZ steering angles and locks onto high-threat perimeter targets."""

    def __init__(
        self,
        ptz_cam_id: int = 4,
        max_optical_zoom: float = 30.0,
        lock_hold_duration_s: float = 4.0,
    ):
        self.ptz_cam_id = ptz_cam_id
        self.max_optical_zoom = max_optical_zoom
        self.lock_hold_duration_s = lock_hold_duration_s

        self._mounts: Dict[int, CameraMountGeometry] = {}
        self._current_lock_target: Optional[str] = None
        self._lock_priority: int = 99
        self._lock_expires_at: float = 0.0

    def register_mount(self, mount: CameraMountGeometry) -> None:
        self._mounts[mount.cam_id] = mount

    def compute_slew(
        self,
        source_cam_id: int,
        target_point: Tuple[float, float],
        target_bbox_height: float,
        target_track_id: str,
        priority: int = 2,
        now: Optional[float] = None,
    ) -> Optional[PTZCommand]:
        """Calculates PTZ pan/tilt/zoom from a normalized (x, y) target point on a source camera."""
        ts = now if now is not None else time.time()
        mount = self._mounts.get(source_cam_id)
        if not mount:
            return None

        # Lock-on arbitration: higher priority (lower number) overrides lower priority
        if ts < self._lock_expires_at and self._current_lock_target != target_track_id:
            if priority >= self._lock_priority:
                # Retain current lock
                return None

        # Acquire or renew lock
        self._current_lock_target = target_track_id
        self._lock_priority = priority
        self._lock_expires_at = ts + self.lock_hold_duration_s

        px, py = target_point
        # Pan: compass azimuth = center_azimuth + (px - 0.5) * hfov
        pan = (mount.azimuth_center_deg + (px - 0.5) * mount.hfov_deg + 360.0) % 360.0
        # Tilt: tilt = center_tilt - (py - 0.5) * vfov (py=0 is top, py=1 is bottom)
        tilt = mount.tilt_center_deg - (py - 0.5) * mount.vfov_deg
        tilt = max(-90.0, min(90.0, tilt))

        # Adaptive zoom: if target height is very small in wide FOV, zoom in heavily
        # Target fills ~0.4 of PTZ frame: zoom ~ 0.4 / max(0.01, target_bbox_height)
        ideal_zoom = 0.40 / max(0.01, target_bbox_height)
        zoom = max(1.0, min(self.max_optical_zoom, ideal_zoom))

        return PTZCommand(
            ptz_cam_id=self.ptz_cam_id,
            pan_deg=pan,
            tilt_deg=tilt,
            zoom_factor=zoom,
            source_cam_id=source_cam_id,
            target_track_id=target_track_id,
            target_priority=priority,
            timestamp=ts,
        )
