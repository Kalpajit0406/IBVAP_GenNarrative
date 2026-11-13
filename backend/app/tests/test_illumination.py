"""
test_illumination.py — Unit tests for IlluminationEstimator and Day/Night/IR perception.

    python tests/test_illumination.py
    pytest  tests/test_illumination.py
"""
from __future__ import annotations

import sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ibvap.illumination import IlluminationEstimator, IlluminationMetrics  # noqa: E402

CASES = []


def case(name):
    def deco(fn):
        CASES.append((name, fn))
        return fn
    return deco


@case("bright colorful frame is classified as DAY")
def _():
    est = IlluminationEstimator(hysteresis_frames=3)
    # 720x1280 bright colorful frame
    frame = np.zeros((120, 160, 3), dtype=np.uint8)
    frame[:, :, 0] = 180  # Blue
    frame[:, :, 1] = 120  # Green
    frame[:, :, 2] = 220  # Red
    for _ in range(3):
        m = est.assess_frame(0, frame)
    assert m.state == "day"
    assert not m.is_night
    assert not m.is_ir
    assert m.mean_luma > 100.0
    assert m.saturation > 20.0


@case("dark monochrome frame is classified as NIGHT_IR")
def _():
    est = IlluminationEstimator(hysteresis_frames=3)
    # Low luma grayscale frame
    frame = np.full((120, 160, 3), 30, dtype=np.uint8)
    for _ in range(3):
        m = est.assess_frame(1, frame)
    assert m.is_night
    assert m.is_ir
    assert m.state == "night_ir"
    assert m.mean_luma < 55.0
    assert m.saturation < 1.0


@case("low light colorful frame is classified as LOW_LIGHT")
def _():
    est = IlluminationEstimator(hysteresis_frames=3)
    # Dusk: moderate luma with color difference
    frame = np.zeros((120, 160, 3), dtype=np.uint8)
    frame[:, :, 0] = 80
    frame[:, :, 1] = 60
    frame[:, :, 2] = 75
    for _ in range(3):
        m = est.assess_frame(2, frame)
    assert m.state == "low_light"
    assert not m.is_night


@case("hysteresis prevents single-frame transient flicker")
def _():
    est = IlluminationEstimator(hysteresis_frames=5)
    dark_ir = np.full((100, 100, 3), 20, dtype=np.uint8)
    bright = np.full((100, 100, 3), 200, dtype=np.uint8)

    # Establish dark night
    for _ in range(5):
        m = est.assess_frame(0, dark_ir)
    assert m.is_night

    # Single transient headlight flash
    flash = est.assess_frame(0, bright)
    # Due to hysteresis, state should still remain night
    assert flash.is_night


@case("none or empty frame returns safe nominal day metrics")
def _():
    est = IlluminationEstimator()
    m = est.assess_frame(0, None)
    assert m.state == "day"
    assert not m.is_night


def run():
    failed = 0
    for name, fn in CASES:
        try:
            fn()
            print(f"  PASS  {name}")
        except Exception as e:
            print(f"  FAIL  {name}: {e}")
            failed += 1
    print(f"\n{len(CASES) - failed}/{len(CASES)} passed")
    if failed:
        sys.exit(1)


def test_all():
    for _, fn in CASES:
        fn()


if __name__ == "__main__":
    run()
