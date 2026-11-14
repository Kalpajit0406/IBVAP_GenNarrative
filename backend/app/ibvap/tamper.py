"""
ibvap/tamper.py — Camera Tamper, Signal Loss & Video Feed Health Monitor.

Directly addresses SIH Theme: Cybersecurity (Item 2 in CLAUDE.md & Backlog):
Detects hostile physical and cyber attacks against surveillance camera feeds:
  1. Lens Occlusion / Covered Camera: Spray paint, bag, or physical obstruction (abnormally low spatial variance).
  2. Frozen Frame / Replay Spoofing: Stream socket remains open but image content is completely static across time.
  3. Video Signal Loss: Camera disconnected, RTSP stall, or power loss exceeding heartbeat timeout.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Dict, Optional, Tuple
import numpy as np


@dataclass
class CameraHealth:
    cam_id: int
    state: str                 # "ok" | "occlusion" | "frozen" | "signal_loss"
    tampered: bool
    description: str
    variance: float
    last_seen_ts: float


class TamperDetector:
    """
    Evaluates frame variance and temporal dynamics to detect feed tampering.
    """

    def __init__(
        self,
        min_variance: float = 12.0,
        occlusion_hold_s: float = 3.0,
        frozen_hold_s: float = 8.0,
        signal_timeout_s: float = 10.0,
    ) -> None:
        self.min_variance = min_variance
        self.occlusion_hold_s = occlusion_hold_s
        self.frozen_hold_s = frozen_hold_s
        self.signal_timeout_s = signal_timeout_s

        # Per-camera tracking
        self._last_frames: Dict[int, np.ndarray] = {}
        self._last_ts: Dict[int, float] = {}
        self._occlusion_since: Dict[int, Optional[float]] = {}
        self._frozen_since: Dict[int, Optional[float]] = {}

    def assess_frame(self, cam_id: int, frame: np.ndarray, ts: Optional[float] = None) -> CameraHealth:
        now = ts if ts is not None else time.time()
        self._last_ts[cam_id] = now

        if frame is None or frame.size == 0:
            return CameraHealth(cam_id, "signal_loss", True, "Null or empty frame received", 0.0, now)

        # Fast subsampling for variance check
        sub = frame[::8, ::8]
        if sub.ndim == 3:
            # Grayscale luma approximation
            gray = 0.299 * sub[:, :, 2] + 0.587 * sub[:, :, 1] + 0.114 * sub[:, :, 0]
        else:
            gray = sub.astype(np.float32)

        # Spatial variance (texture check): completely covered lens has near-zero variance
        variance = float(np.var(gray))

        # Check 1: Lens Occlusion / Bagged / Spray-painted
        if variance < self.min_variance:
            if self._occlusion_since.get(cam_id) is None:
                self._occlusion_since[cam_id] = now
            elif (now - self._occlusion_since[cam_id]) >= self.occlusion_hold_s:
                return CameraHealth(
                    cam_id=cam_id,
                    state="occlusion",
                    tampered=True,
                    description=f"Camera lens obstructed or covered (variance {variance:.1f} < {self.min_variance})",
                    variance=variance,
                    last_seen_ts=now,
                )
        else:
            self._occlusion_since[cam_id] = None

        # Check 2: Frozen Feed / Frame Replay Spoofing
        prev = self._last_frames.get(cam_id)
        if prev is not None and prev.shape == sub.shape:
            # Absolute difference
            diff = float(np.mean(np.abs(sub.astype(np.float32) - prev.astype(np.float32))))
            # Exactly identical down to pixel noise indicates frozen decode buffer
            if diff < 0.01:
                if self._frozen_since.get(cam_id) is None:
                    self._frozen_since[cam_id] = now
                elif (now - self._frozen_since[cam_id]) >= self.frozen_hold_s:
                    return CameraHealth(
                        cam_id=cam_id,
                        state="frozen",
                        tampered=True,
                        description=f"Video feed frozen or replay detected (zero temporal delta for {self.frozen_hold_s}s)",
                        variance=variance,
                        last_seen_ts=now,
                    )
            else:
                self._frozen_since[cam_id] = None
        else:
            self._frozen_since[cam_id] = None

        self._last_frames[cam_id] = sub.copy()

        return CameraHealth(
            cam_id=cam_id,
            state="ok",
            tampered=False,
            description="Camera operational",
            variance=variance,
            last_seen_ts=now,
        )

    def check_signal(self, cam_id: int, now: Optional[float] = None) -> CameraHealth:
        curr = now if now is not None else time.time()
        last = self._last_ts.get(cam_id)
        if last is None or (curr - last) > self.signal_timeout_s:
            return CameraHealth(
                cam_id=cam_id,
                state="signal_loss",
                tampered=True,
                description=f"Camera signal lost: no frames for >{self.signal_timeout_s}s",
                variance=0.0,
                last_seen_ts=last or 0.0,
            )
        return CameraHealth(cam_id, "ok", False, "Signal active", 100.0, last)

    def reset(self, cam_id: int) -> None:
        self._last_frames.pop(cam_id, None)
        self._last_ts.pop(cam_id, None)
        self._occlusion_since.pop(cam_id, None)
        self._frozen_since.pop(cam_id, None)
