"""
ibvap/illumination.py — Camera illumination and Day/Night/IR environment estimator.

Addresses P0 Item B (Night-time surveillance perception):
Extracts frame luma and chrominance saturation to classify each camera stream into:
  - DAY: Normal ambient daylight or full illumination.
  - LOW_LIGHT: Dusk, poorly lit perimeter, or twilight.
  - NIGHT_IR: Infrared illuminator active / near-monochrome night mode.

Applies temporal hysteresis smoothing to prevent state flicker from brief transients
(e.g. passing vehicle headlights or momentary shadows).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional
import numpy as np


@dataclass
class IlluminationMetrics:
    cam_id: int
    mean_luma: float          # 0.0 to 255.0
    saturation: float         # 0.0 to 255.0 (colorfulness)
    state: str                # "day" | "low_light" | "night_ir"
    is_night: bool
    is_ir: bool

    def to_dict(self) -> dict:
        return {
            "cam_id": self.cam_id,
            "mean_luma": round(self.mean_luma, 2),
            "saturation": round(self.saturation, 2),
            "state": self.state,
            "is_night": self.is_night,
            "is_ir": self.is_ir,
        }


class IlluminationEstimator:
    """
    Per-camera day/night and IR-illuminator estimator with hysteresis filtering.
    """

    def __init__(
        self,
        luma_night_threshold: float = 55.0,
        luma_low_light_threshold: float = 90.0,
        saturation_ir_threshold: float = 12.0,
        hysteresis_frames: int = 5,
    ) -> None:
        self.luma_night = luma_night_threshold
        self.luma_low = luma_low_light_threshold
        self.sat_ir = saturation_ir_threshold
        self.hysteresis_frames = max(1, hysteresis_frames)

        # per-camera history for temporal smoothing
        self._camera_states: Dict[int, str] = {}
        self._history: Dict[int, List[str]] = {}

    def assess_frame(self, cam_id: int, frame: np.ndarray) -> IlluminationMetrics:
        """
        Analyze a BGR or grayscale numpy frame to determine lighting state.
        Uses fast sub-sampling for efficiency in multi-stream pipelines.
        """
        if frame is None or frame.size == 0:
            return IlluminationMetrics(cam_id, 128.0, 100.0, "day", False, False)

        # Subsample frame (e.g. 1 in 8 pixels) for near-instant statistics
        sub = frame[::8, ::8]

        if sub.ndim == 2:
            # Grayscale / monochrome
            luma = float(np.mean(sub))
            saturation = 0.0
        elif sub.ndim == 3 and sub.shape[2] == 3:
            # BGR format: B=sub[:,:,0], G=sub[:,:,1], R=sub[:,:,2]
            b = sub[:, :, 0].astype(np.float32)
            g = sub[:, :, 1].astype(np.float32)
            r = sub[:, :, 2].astype(np.float32)

            # Rec. 601 luma
            luma_map = 0.299 * r + 0.587 * g + 0.114 * b
            luma = float(np.mean(luma_map))

            # Mean absolute channel differences as color saturation proxy
            # Near zero indicates black & white / infrared illumination
            diff = np.abs(r - g) + np.abs(g - b) + np.abs(b - r)
            saturation = float(np.mean(diff) / 2.0)
        else:
            luma = float(np.mean(sub))
            saturation = 50.0

        # Classify instantaneous candidate state
        if luma < self.luma_night:
            candidate = "night_ir" if saturation < self.sat_ir else "night"
        elif luma < self.luma_low:
            candidate = "low_light"
        else:
            candidate = "day"

        # Apply hysteresis queue
        hist = self._history.setdefault(cam_id, [])
        hist.append(candidate)
        if len(hist) > self.hysteresis_frames:
            hist.pop(0)

        # Transition only if candidate dominates history window
        current = self._camera_states.get(cam_id, candidate)
        if hist.count(candidate) >= (self.hysteresis_frames // 2 + 1):
            current = candidate
            self._camera_states[cam_id] = current

        is_night = current in ("night", "night_ir")
        is_ir = current == "night_ir" or (is_night and saturation < self.sat_ir)
        state_label = "night_ir" if is_ir else ("low_light" if current == "low_light" else ("night" if is_night else "day"))

        return IlluminationMetrics(
            cam_id=cam_id,
            mean_luma=luma,
            saturation=saturation,
            state=state_label,
            is_night=is_night,
            is_ir=is_ir,
        )

    def reset_camera(self, cam_id: int) -> None:
        self._camera_states.pop(cam_id, None)
        self._history.pop(cam_id, None)
