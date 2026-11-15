"""
ibvap/weather.py — Atmospheric Visibility & Adverse Weather Estimator.

Directly addresses Weather Robustness (IBVAP Project Context §8):
Analyzes optical transmission and atmospheric contrast degradation (fog, haze, rain)
using a lightweight edge-optimized Dark Channel Prior (DCP) heuristic to calculate:
  - Atmospheric Visibility Index (0.0 = zero visibility / whiteout, 1.0 = clear line of sight)
  - Weather condition category ("clear", "haze", "fog", "rain")
  - Adaptive detection confidence threshold adjustment to recover obscured silhouettes.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Dict, List, Optional
import numpy as np


@dataclass
class WeatherCondition:
    cam_id: int
    state: str                 # "clear" | "haze" | "fog" | "rain"
    visibility_index: float    # 0.0 to 1.0
    contrast: float            # Weber/Michelson standard deviation
    dark_channel_mean: float   # 0 to 255 (higher = thicker haze/airlight)
    conf_offset: float         # Suggested confidence delta (e.g. -0.05 in fog)

    def to_dict(self) -> dict:
        return {
            "cam_id": self.cam_id,
            "state": self.state,
            "visibility_index": round(self.visibility_index, 2),
            "contrast": round(self.contrast, 2),
            "dark_channel_mean": round(self.dark_channel_mean, 2),
            "conf_offset": round(self.conf_offset, 2),
        }


class WeatherEstimator:
    """
    Per-camera atmospheric degradation estimator with temporal smoothing.
    """

    def __init__(
        self,
        fog_dark_threshold: float = 145.0,
        haze_dark_threshold: float = 95.0,
        min_contrast_clear: float = 38.0,
        smoothing_frames: int = 5,
    ) -> None:
        self.fog_thresh = fog_dark_threshold
        self.haze_thresh = haze_dark_threshold
        self.min_contrast = min_contrast_clear
        self.smoothing_frames = max(1, smoothing_frames)

        self._history: Dict[int, List[float]] = {}
        self._states: Dict[int, str] = {}

    def assess_frame(self, cam_id: int, frame: np.ndarray) -> WeatherCondition:
        if frame is None or frame.size == 0:
            return WeatherCondition(cam_id, "clear", 1.0, 50.0, 30.0, 0.0)

        # Fast subsampling for multi-stream throughput
        sub = frame[::8, ::8]

        if sub.ndim == 3 and sub.shape[2] == 3:
            # Dark Channel Prior: min across color channels
            dark_channel = np.min(sub, axis=2)
            gray = 0.299 * sub[:, :, 2] + 0.587 * sub[:, :, 1] + 0.114 * sub[:, :, 0]
        else:
            dark_channel = sub
            gray = sub.astype(np.float32)

        dcp_mean = float(np.mean(dark_channel))
        contrast = float(np.std(gray))

        # Smooth DCP mean across history
        hist = self._history.setdefault(cam_id, [])
        hist.append(dcp_mean)
        if len(hist) > self.smoothing_frames:
            hist.pop(0)
        smoothed_dcp = float(np.mean(hist))

        # Classify state
        if smoothed_dcp >= self.fog_thresh:
            state = "fog"
            vis = max(0.1, 1.0 - (smoothed_dcp / 255.0))
            offset = -0.08    # lower threshold to pick up faint targets in fog
        elif smoothed_dcp >= self.haze_thresh:
            state = "haze"
            vis = max(0.3, 1.0 - (smoothed_dcp / 255.0))
            offset = -0.04
        else:
            state = "clear"
            vis = min(1.0, max(0.7, 1.0 - (smoothed_dcp / 255.0)))
            offset = 0.0

        self._states[cam_id] = state

        return WeatherCondition(
            cam_id=cam_id,
            state=state,
            visibility_index=vis,
            contrast=contrast,
            dark_channel_mean=smoothed_dcp,
            conf_offset=offset,
        )

    def reset(self, cam_id: int) -> None:
        self._history.pop(cam_id, None)
        self._states.pop(cam_id, None)
