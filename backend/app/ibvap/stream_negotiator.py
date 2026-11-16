"""
stream_negotiator.py — Dynamic camera substream and bandwidth auto-negotiator.

Dynamically adapts video ingest resolution, target FPS, and compression quality
based on inference worker pipeline latency, queue depth, and network backpressure.
Provides automatic burst escalation during high-threat tactical alarms to capture
maximum evidentiary resolution, with hysteresis to avoid oscillation.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger("ibvap.stream_negotiator")


@dataclass(frozen=True)
class StreamProfile:
    name: str
    resolution: Tuple[int, int]
    target_fps: int
    jpeg_quality: int
    bitrate_kbps: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "width": self.resolution[0],
            "height": self.resolution[1],
            "target_fps": self.target_fps,
            "jpeg_quality": self.jpeg_quality,
            "bitrate_kbps": self.bitrate_kbps,
        }


PROFILES: Dict[str, StreamProfile] = {
    "eco": StreamProfile("eco", (640, 360), 10, 55, 500),
    "nominal": StreamProfile("nominal", (1280, 720), 15, 75, 1800),
    "hd": StreamProfile("hd", (1920, 1080), 25, 85, 4500),
    "tactical_burst": StreamProfile("tactical_burst", (1920, 1080), 30, 95, 8000),
}

_PROFILE_ORDER = ["eco", "nominal", "hd"]


@dataclass
class _CamStreamState:
    profile: StreamProfile
    burst_until: float = 0.0
    consecutive_high_load: int = 0
    consecutive_low_load: int = 0


class SubstreamNegotiator:
    """Manages adaptive stream profiles per camera feed with burst support."""

    def __init__(
        self,
        default_profile: str = "nominal",
        burst_duration_s: float = 15.0,
        latency_downgrade_ms: float = 120.0,
        latency_upgrade_ms: float = 45.0,
        hysteresis_steps: int = 3,
    ):
        self.default_profile = PROFILES.get(default_profile, PROFILES["nominal"])
        self.burst_duration_s = burst_duration_s
        self.latency_downgrade_ms = latency_downgrade_ms
        self.latency_upgrade_ms = latency_upgrade_ms
        self.hysteresis_steps = max(1, hysteresis_steps)
        self._camera_states: Dict[str, _CamStreamState] = {}

    def _get_state(self, cam_id: str) -> _CamStreamState:
        if cam_id not in self._camera_states:
            self._camera_states[cam_id] = _CamStreamState(profile=self.default_profile)
        return self._camera_states[cam_id]

    def trigger_burst(self, cam_id: str, duration_s: Optional[float] = None) -> StreamProfile:
        """Escalate feed to tactical burst mode for high-fidelity incident capture."""
        dur = duration_s if duration_s is not None else self.burst_duration_s
        state = self._get_state(cam_id)
        state.burst_until = time.monotonic() + max(0.01, dur)
        state.profile = PROFILES["tactical_burst"]
        state.consecutive_high_load = 0
        state.consecutive_low_load = 0
        logger.info("Camera %s escalated to tactical_burst for %.1fs", cam_id, dur)
        return state.profile

    def update_telemetry(
        self,
        cam_id: str,
        inference_latency_ms: float,
        queue_depth: int = 0,
        dropped_frames: int = 0,
    ) -> StreamProfile:
        """Updates pipeline load metrics and adjusts profile if needed."""
        state = self._get_state(cam_id)
        now = time.monotonic()

        # In burst mode: retain high profile until window expires
        if now < state.burst_until:
            return state.profile
        elif state.profile.name == "tactical_burst":
            # Burst expired, return to nominal
            state.profile = self.default_profile
            state.consecutive_high_load = 0
            state.consecutive_low_load = 0

        # Assess load
        is_stressed = (inference_latency_ms > self.latency_downgrade_ms) or (queue_depth >= 3) or (dropped_frames > 2)
        is_idle = (inference_latency_ms < self.latency_upgrade_ms) and (queue_depth == 0) and (dropped_frames == 0)

        if is_stressed:
            state.consecutive_high_load += 1
            state.consecutive_low_load = 0
            if state.consecutive_high_load >= self.hysteresis_steps:
                state.consecutive_high_load = 0
                state.profile = self._step_profile_down(state.profile)
        elif is_idle:
            state.consecutive_low_load += 1
            state.consecutive_high_load = 0
            if state.consecutive_low_load >= self.hysteresis_steps:
                state.consecutive_low_load = 0
                state.profile = self._step_profile_up(state.profile)
        else:
            state.consecutive_high_load = 0
            state.consecutive_low_load = 0

        return state.profile

    def _step_profile_down(self, current: StreamProfile) -> StreamProfile:
        curr_name = current.name
        if curr_name not in _PROFILE_ORDER:
            return PROFILES["nominal"]
        idx = _PROFILE_ORDER.index(curr_name)
        new_idx = max(0, idx - 1)
        return PROFILES[_PROFILE_ORDER[new_idx]]

    def _step_profile_up(self, current: StreamProfile) -> StreamProfile:
        curr_name = current.name
        if curr_name not in _PROFILE_ORDER:
            return PROFILES["nominal"]
        idx = _PROFILE_ORDER.index(curr_name)
        new_idx = min(len(_PROFILE_ORDER) - 1, idx + 1)
        return PROFILES[_PROFILE_ORDER[new_idx]]

    def get_profile(self, cam_id: str) -> StreamProfile:
        return self._get_state(cam_id).profile

    def status(self) -> Dict[str, Any]:
        return {
            cam_id: {
                "profile": state.profile.name,
                "is_bursting": time.monotonic() < state.burst_until,
                "resolution": state.profile.resolution,
                "fps": state.profile.target_fps,
                "bitrate_kbps": state.profile.bitrate_kbps,
            }
            for cam_id, state in self._camera_states.items()
        }
