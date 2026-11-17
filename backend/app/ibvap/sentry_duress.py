"""
sentry_duress.py — Tactical sentry duress, man-down, and post abandonment monitor.

Monitors border watchtowers, morchas, and sentry gates to safeguard security personnel:
  * Man-Down Detection: Sentry collapsed or prone/supine with prolonged immobility (>15s).
  * Duress / Hostage Posture: Sentry held with hands raised above head under coercion.
  * Sentry Post Desertion: Sentry post vacant during scheduled armed watch window (>30s).
"""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("ibvap.sentry_duress")


@dataclass
class SentryPostConfig:
    post_id: str
    name: str
    cam_id: int
    man_down_timeout_s: float = 15.0
    abandon_timeout_s: float = 30.0


@dataclass
class SentryAlert:
    alert_id: str
    post_id: str
    post_name: str
    cam_id: int
    status: str                # "MAN_DOWN", "DURESS_HANDS_UP", "POST_ABANDONED"
    severity: str              # "Critical"
    tactical_priority: int     # 1 (Immediate)
    duration_s: float
    advisory: str
    timestamp: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "alert_id": self.alert_id,
            "post_id": self.post_id,
            "post_name": self.post_name,
            "cam_id": self.cam_id,
            "status": self.status,
            "severity": self.severity,
            "tactical_priority": self.tactical_priority,
            "duration_s": round(self.duration_s, 1),
            "advisory": self.advisory,
            "timestamp": self.timestamp,
        }


class SentryDuressMonitor:
    """Tracks sentry posture states and generates tactical distress alarms."""

    def __init__(self, posts: Optional[List[SentryPostConfig]] = None):
        self._posts: Dict[str, SentryPostConfig] = {}
        self._post_vacant_since: Dict[str, Optional[float]] = {}
        self._man_down_since: Dict[str, Optional[float]] = {}
        self._last_alert_status: Dict[str, Optional[str]] = {}

        if posts:
            for p in posts:
                self.register_post(p)

    def register_post(self, post: SentryPostConfig) -> None:
        self._posts[post.post_id] = post
        self._post_vacant_since[post.post_id] = None
        self._man_down_since[post.post_id] = None
        self._last_alert_status[post.post_id] = None

    def update(
        self,
        post_id: str,
        persons: List[Dict[str, Any]],
        timestamp: Optional[float] = None,
    ) -> Optional[SentryAlert]:
        """Evaluates detected persons in the sentry post sector.
        
        persons: list of dicts with keys: 'track_id', 'posture' (e.g. 'standing', 'lying_down', 'hands_up')
        """
        post = self._posts.get(post_id)
        if not post:
            return None

        now = timestamp if timestamp is not None else time.time()

        # 1. Check for Empty / Vacant Post
        if not persons:
            self._man_down_since[post_id] = None
            if self._post_vacant_since[post_id] is None:
                self._post_vacant_since[post_id] = now
                return None

            vacant_dur = now - self._post_vacant_since[post_id]
            if vacant_dur >= post.abandon_timeout_s:
                if self._last_alert_status.get(post_id) != "POST_ABANDONED":
                    self._last_alert_status[post_id] = "POST_ABANDONED"
                    return SentryAlert(
                        alert_id=f"SENTRY-ABAN-{uuid.uuid4().hex[:6]}",
                        post_id=post.post_id,
                        post_name=post.name,
                        cam_id=post.cam_id,
                        status="POST_ABANDONED",
                        severity="Critical",
                        tactical_priority=1,
                        duration_s=vacant_dur,
                        advisory=f"CRITICAL: Sentry post '{post.name}' vacant for {vacant_dur:.0f}s. Dispatch relief squad immediately.",
                        timestamp=now,
                    )
            return None

        # Post is occupied
        self._post_vacant_since[post_id] = None

        # 2. Check for Duress / Hostage posture (hands up)
        for p in persons:
            posture = str(p.get("posture") or "").lower()
            if "hands_up" in posture or "surrender" in posture:
                self._last_alert_status[post_id] = "DURESS_HANDS_UP"
                return SentryAlert(
                    alert_id=f"SENTRY-DUR-{uuid.uuid4().hex[:6]}",
                    post_id=post.post_id,
                    post_name=post.name,
                    cam_id=post.cam_id,
                    status="DURESS_HANDS_UP",
                    severity="Critical",
                    tactical_priority=1,
                    duration_s=0.0,
                    advisory=f"EMERGENCY: Sentry at '{post.name}' observed with hands raised (duress posture). Armed standoff protocol.",
                    timestamp=now,
                )

        # 3. Check for Man-Down / Prolonged immobility in prone or lying down state
        any_prone = any(
            p.get("posture") in ("lying_down", "prone", "crawling_prone", "fallen")
            for p in persons
        )
        if any_prone:
            if self._man_down_since[post_id] is None:
                self._man_down_since[post_id] = now
                return None

            down_dur = now - self._man_down_since[post_id]
            if down_dur >= post.man_down_timeout_s:
                if self._last_alert_status.get(post_id) != "MAN_DOWN":
                    self._last_alert_status[post_id] = "MAN_DOWN"
                    return SentryAlert(
                        alert_id=f"SENTRY-DOWN-{uuid.uuid4().hex[:6]}",
                        post_id=post.post_id,
                        post_name=post.name,
                        cam_id=post.cam_id,
                        status="MAN_DOWN",
                        severity="Critical",
                        tactical_priority=1,
                        duration_s=down_dur,
                        advisory=f"EMERGENCY: Man-down detected at sentry post '{post.name}'. Sentry immobile for {down_dur:.0f}s. Dispatch medical QRT.",
                        timestamp=now,
                    )
            return None
        else:
            # Person standing or normal: reset man-down
            self._man_down_since[post_id] = None
            self._last_alert_status[post_id] = None
            return None
