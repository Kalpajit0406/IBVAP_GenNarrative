"""
acoustic.py — Acoustic sensor and gunshot/explosion event classifier.

Analyzes acoustic sensor telemetry from border outpost microphone arrays:
  * Gunshot: High peak-to-average power, ultra-fast rise time (<10ms), high SPL (>85 dB).
  * Explosion / IED: Heavy low-frequency energy (<600 Hz), long decay (>400ms), extreme SPL (>95 dB).
  * Drone / UAV Rotor: Sustained narrow harmonic band (200-800 Hz) with moderate SPL.
  * Wire Fence Cut / Metal Strike: High spectral centroid (>4000 Hz), sharp transient.
  * Vehicle Engine: Low-frequency broadband drone (<500 Hz), sustained duration.

Fuses acoustic Direction of Arrival (DoA / bearing in degrees) with camera Azimuth FOVs
to automatically slew or highlight the corresponding camera sector.
Pure Python/math, zero heavy audio DSP or GPU dependencies.
"""
from __future__ import annotations

import logging
import math
import time
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("ibvap.acoustic")

ACOUSTIC_PRIORITIES = {
    "gunshot": 1,
    "explosion": 1,
    "wire_cut": 2,
    "drone_rotor": 2,
    "engine_rev": 3,
    "ambient": 5,
}

ACOUSTIC_SEVERITIES = {
    "gunshot": "Critical",
    "explosion": "Critical",
    "wire_cut": "High",
    "drone_rotor": "High",
    "engine_rev": "Elevated",
    "ambient": "Info",
}


@dataclass
class AcousticEvent:
    event_id: str
    event_type: str
    confidence: float
    spl_db: float
    bearing_deg: Optional[float]
    timestamp: float
    associated_cam_id: Optional[int]
    tactical_priority: int
    severity: str
    advisory: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "confidence": round(self.confidence, 3),
            "spl_db": round(self.spl_db, 1),
            "bearing_deg": round(self.bearing_deg, 1) if self.bearing_deg is not None else None,
            "timestamp": self.timestamp,
            "associated_cam_id": self.associated_cam_id,
            "tactical_priority": self.tactical_priority,
            "severity": self.severity,
            "advisory": self.advisory,
        }


class AcousticClassifier:
    """Classifies acoustic feature vectors and correlates events to camera azimuths."""

    def __init__(self, camera_azimuths: Optional[Dict[int, Tuple[float, float]]] = None):
        """camera_azimuths: dict mapping cam_id -> (start_azimuth_deg, end_azimuth_deg)"""
        self.camera_azimuths = camera_azimuths or {
            1: (0.0, 90.0),      # Sector-1 North-East
            2: (90.0, 180.0),    # Sector-2 South-East
            3: (180.0, 270.0),   # Sector-3 South-West
            4: (270.0, 360.0),   # Sector-4 North-West
        }

    def correlate_camera(self, bearing_deg: Optional[float]) -> Optional[int]:
        """Finds camera whose field of view encompasses the acoustic bearing."""
        if bearing_deg is None:
            return None
        bearing = (bearing_deg + 360.0) % 360.0
        for cam_id, (start_az, end_az) in self.camera_azimuths.items():
            if start_az <= end_az:
                if start_az <= bearing <= end_az:
                    return cam_id
            else:  # spans 0 deg (e.g. 315 to 45)
                if bearing >= start_az or bearing <= end_az:
                    return cam_id
        return None

    def classify(
        self,
        peak_amplitude: float,
        rise_time_ms: float,
        decay_time_ms: float,
        spectral_centroid_hz: float,
        spl_db: float,
        bearing_deg: Optional[float] = None,
        timestamp: Optional[float] = None,
    ) -> AcousticEvent:
        """Classifies acoustic transient features into tactical alert types."""
        now = timestamp if timestamp is not None else time.time()
        ev_id = f"ACOUS-{uuid.uuid4().hex[:8]}"

        # Classification decision tree based on transient physical parameters
        if spl_db >= 85.0 and rise_time_ms <= 12.0 and decay_time_ms <= 300.0:
            ev_type = "gunshot"
            conf = min(0.98, 0.70 + (spl_db - 85.0) * 0.01 + max(0.0, (12.0 - rise_time_ms) * 0.02))
            advisory = "Gunshot transient detected. Immediate armed cover; alert Quick Reaction Team."
        elif spl_db >= 92.0 and spectral_centroid_hz <= 700.0 and decay_time_ms >= 350.0:
            ev_type = "explosion"
            conf = min(0.99, 0.75 + (spl_db - 92.0) * 0.015)
            advisory = "High-energy blast / detonation signature. Initiate outpost defense lockdown."
        elif 200.0 <= spectral_centroid_hz <= 900.0 and rise_time_ms >= 80.0 and spl_db >= 48.0:
            ev_type = "drone_rotor"
            conf = min(0.92, 0.65 + (spl_db - 48.0) * 0.01)
            advisory = "Low-altitude UAV rotor harmonic detected. Slew anti-drone jammer to bearing."
        elif spectral_centroid_hz >= 3500.0 and rise_time_ms <= 25.0 and spl_db >= 55.0:
            ev_type = "wire_cut"
            conf = min(0.90, 0.60 + (spectral_centroid_hz - 3500.0) / 5000.0)
            advisory = "High-frequency metallic transient (fence cutting). Verify perimeter sensor wire."
        elif spectral_centroid_hz < 600.0 and decay_time_ms > 500.0 and spl_db >= 60.0:
            ev_type = "engine_rev"
            conf = 0.80
            advisory = "Heavy vehicular engine signature approaching border track."
        else:
            ev_type = "ambient"
            conf = 0.50
            advisory = "Acoustic background levels nominal."

        priority = ACOUSTIC_PRIORITIES[ev_type]
        severity = ACOUSTIC_SEVERITIES[ev_type]
        cam_id = self.correlate_camera(bearing_deg)

        if bearing_deg is not None and cam_id is not None and ev_type != "ambient":
            advisory += f" (DoA {bearing_deg:.1f}° correlates to CAM-{cam_id:02d})."

        return AcousticEvent(
            event_id=ev_id,
            event_type=ev_type,
            confidence=conf,
            spl_db=spl_db,
            bearing_deg=bearing_deg,
            timestamp=now,
            associated_cam_id=cam_id,
            tactical_priority=priority,
            severity=severity,
            advisory=advisory,
        )
