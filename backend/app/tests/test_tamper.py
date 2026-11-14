"""
test_tamper.py — Camera tamper, feed health and replay detection tests.

    python tests/test_tamper.py
    pytest  tests/test_tamper.py
"""
from __future__ import annotations

import sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ibvap.tamper import TamperDetector  # noqa: E402

CASES = []


def case(name):
    def deco(fn):
        CASES.append((name, fn))
        return fn
    return deco


@case("normal textured frame reports operational state ok")
def _():
    det = TamperDetector()
    frame = np.random.randint(0, 255, (120, 160, 3), dtype=np.uint8)
    health = det.assess_frame(0, frame, ts=100.0)
    assert health.state == "ok"
    assert not health.tampered


@case("covered lens held past threshold triggers occlusion alert")
def _():
    det = TamperDetector(occlusion_hold_s=2.0)
    # Solid black/gray frame (variance = 0)
    covered = np.full((120, 160, 3), 40, dtype=np.uint8)

    h1 = det.assess_frame(1, covered, ts=100.0)
    assert not h1.tampered  # hold time not elapsed

    h2 = det.assess_frame(1, covered, ts=101.0)
    assert not h2.tampered

    h3 = det.assess_frame(1, covered, ts=102.5)
    assert h3.tampered
    assert h3.state == "occlusion"
    assert "obstructed or covered" in h3.description


@case("feed frozen with exact identical frames triggers replay/freeze alert")
def _():
    det = TamperDetector(frozen_hold_s=4.0)
    frame = np.arange(100, dtype=np.uint8).reshape((10, 10))

    det.assess_frame(2, frame, ts=10.0)
    det.assess_frame(2, frame, ts=12.0)
    h_frozen = det.assess_frame(2, frame, ts=16.5)

    assert h_frozen.tampered
    assert h_frozen.state == "frozen"
    assert "frozen or replay" in h_frozen.description


@case("signal loss detected when camera stops transmitting frames")
def _():
    det = TamperDetector(signal_timeout_s=5.0)
    frame = np.random.randint(0, 255, (60, 60, 3), dtype=np.uint8)
    det.assess_frame(3, frame, ts=10.0)

    h_ok = det.check_signal(3, now=12.0)
    assert h_ok.state == "ok"

    h_lost = det.check_signal(3, now=16.0)
    assert h_lost.tampered
    assert h_lost.state == "signal_loss"


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
