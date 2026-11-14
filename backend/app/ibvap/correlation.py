"""
ibvap/correlation.py — Multi-Camera Spatial & Temporal Incident Correlation.

Correlates related security events across multiple camera feeds occurring within
a rolling operational time window (e.g. vehicle approach at gate -> perimeter breach -> weapon detected),
synthesizing cross-stream tactical intelligence into a single coherent incident narrative.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


_SEVERITY_WEIGHT = {"Info": 0, "Low": 1, "Medium": 2, "High": 3, "Critical": 4}


@dataclass
class CorrelatedIncident:
    incident_id: str
    start_time: float
    last_update: float
    cameras: List[int]
    camera_names: List[str]
    highest_severity: str
    event_ids: List[str]
    event_sequence: List[str]
    events: List[Dict[str, Any]] = field(default_factory=list)

    def synthesize_narrative(self) -> str:
        """Generate a unified multi-camera tactical narrative."""
        cams_str = ", ".join(f"CAM-{c:02d}" for c in sorted(set(self.cameras)))
        duration = max(1.0, self.last_update - self.start_time)

        lines = [
            f"MULTI-CAMERA INCIDENT [{self.highest_severity.upper()}]: Coordinated activity across {cams_str} over {duration:.0f} seconds.",
        ]

        # Sequence description
        steps = []
        for ev in self.events:
            cam = ev.get("cam_name") or f"CAM-{ev.get('cam_id', 0):02d}"
            cat = str(ev.get("category", "activity")).upper()
            details = ev.get("details") or {}
            if isinstance(details, dict) and details.get("plate"):
                steps.append(f"{cam}: Vehicle plate [{details['plate']}]")
            elif isinstance(details, dict) and details.get("armed"):
                steps.append(f"{cam}: Armed individual identified in tactical posture")
            elif isinstance(details, dict) and details.get("breach"):
                fence = details.get("fence_name", "Perimeter")
                steps.append(f"{cam}: Breach across '{fence}'")
            else:
                steps.append(f"{cam}: {cat}")

        lines.append("Progression sequence: " + " ➔ ".join(steps))
        return " ".join(lines)


class IncidentCorrelator:
    """
    Correlates incident events across camera streams within a rolling window.
    """

    def __init__(self, correlation_window_s: float = 120.0) -> None:
        self.window_s = correlation_window_s
        self.active_incidents: List[CorrelatedIncident] = []
        self._incident_seq = 0

    def ingest_event(self, event: Dict[str, Any]) -> CorrelatedIncident:
        """
        Ingest a new event. Adds to an existing active incident if within time window,
        or creates a new correlated incident chain.
        """
        now = float(event.get("ts") or time.time())
        cam_id = int(event.get("cam_id") or 0)
        cam_name = str(event.get("cam_name") or f"CAM-{cam_id:02d}")
        ev_id = str(event.get("event_id") or f"ev-{int(now*1000)}")
        cat = str(event.get("category") or "risk")
        sev = str(event.get("severity") or "Info").capitalize()

        # Prune expired incidents
        self.active_incidents = [
            inc for inc in self.active_incidents
            if (now - inc.last_update) <= self.window_s
        ]

        # Find matching incident to attach to (within window)
        target: Optional[CorrelatedIncident] = None
        for inc in self.active_incidents:
            if (now - inc.last_update) <= self.window_s:
                target = inc
                break

        if target is None:
            self._incident_seq += 1
            target = CorrelatedIncident(
                incident_id=f"INC-{int(now)}-{self._incident_seq:03d}",
                start_time=now,
                last_update=now,
                cameras=[cam_id],
                camera_names=[cam_name],
                highest_severity=sev,
                event_ids=[ev_id],
                event_sequence=[cat],
                events=[event],
            )
            self.active_incidents.append(target)
        else:
            target.last_update = now
            if cam_id not in target.cameras:
                target.cameras.append(cam_id)
            if cam_name not in target.camera_names:
                target.camera_names.append(cam_name)
            target.event_ids.append(ev_id)
            target.event_sequence.append(cat)
            target.events.append(event)

            # Update highest severity
            if _SEVERITY_WEIGHT.get(sev, 0) > _SEVERITY_WEIGHT.get(target.highest_severity, 0):
                target.highest_severity = sev

        return target

    def get_active(self) -> List[CorrelatedIncident]:
        return list(self.active_incidents)
