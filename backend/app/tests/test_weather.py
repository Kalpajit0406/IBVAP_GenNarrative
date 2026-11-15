"""
test_weather.py — Atmospheric visibility and adverse weather estimator tests.

    python tests/test_weather.py
    pytest  tests/test_weather.py
"""
from __future__ import annotations

import sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ibvap.weather import WeatherEstimator  # noqa: E402

CASES = []


def case(name):
    def deco(fn):
        CASES.append((name, fn))
        return fn
    return deco


@case("clear high-contrast scene classifies as clear with zero conf offset")
def _():
    est = WeatherEstimator()
    # High contrast natural scene with color variance (foliage + ground + sky)
    frame = np.zeros((120, 160, 3), dtype=np.uint8)
    frame[:60, :] = [180, 80, 30]    # Blue/orange horizon
    frame[60:, :] = [20, 140, 15]    # Green terrain

    for _ in range(5):
        w = est.assess_frame(0, frame)
    assert w.state == "clear"
    assert w.visibility_index >= 0.7
    assert w.conf_offset == 0.0


@case("dense fog/washed-out frame classifies as fog with negative conf offset")
def _():
    est = WeatherEstimator()
    # Fog: high airlight, all channels near uniform high value, low contrast
    fog_frame = np.full((120, 160, 3), 195, dtype=np.uint8)

    for _ in range(5):
        w = est.assess_frame(1, fog_frame)
    assert w.state == "fog"
    assert w.visibility_index < 0.5
    assert w.conf_offset < 0.0  # relaxes detection floor in fog


@case("haze condition detected when contrast degrades moderately")
def _():
    est = WeatherEstimator(haze_dark_threshold=80.0)
    # Haze: moderate airlight
    haze_frame = np.full((120, 160, 3), 110, dtype=np.uint8)

    for _ in range(5):
        w = est.assess_frame(2, haze_frame)
    assert w.state in ("haze", "fog")


@case("temporal smoothing averages noisy fluctuations across frames")
def _():
    est = WeatherEstimator(smoothing_frames=4)
    clear = np.zeros((100, 100, 3), dtype=np.uint8)
    clear[:50] = [180, 80, 30]
    clear[50:] = [20, 140, 15]
    fog = np.full((100, 100, 3), 200, dtype=np.uint8)

    # 3 clear frames then 1 fog frame
    for _ in range(3):
        est.assess_frame(3, clear)
    spike = est.assess_frame(3, fog)
    # History of 3 clear + 1 fog should remain clear/haze, not instant fog
    assert spike.state != "fog"


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
