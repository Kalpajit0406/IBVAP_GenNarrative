"""
test_stream_negotiator.py — Unit tests for camera substream auto-negotiator.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ibvap.stream_negotiator import PROFILES, SubstreamNegotiator


def run_tests():
    passed = 0

    # 1. Default profile
    neg = SubstreamNegotiator(default_profile="nominal", hysteresis_steps=2)
    p = neg.get_profile("cam1")
    assert p.name == "nominal"
    assert p.target_fps == 15
    print("  PASS  camera feed initializes with nominal operational substream profile")
    passed += 1

    # 2. Stress / latency downgrade
    # 1st high load tick: hysteresis not met
    p1 = neg.update_telemetry("cam1", inference_latency_ms=180.0, queue_depth=4)
    assert p1.name == "nominal"

    # 2nd high load tick: hysteresis met, downgrades to eco
    p2 = neg.update_telemetry("cam1", inference_latency_ms=190.0, queue_depth=4)
    assert p2.name == "eco"
    assert p2.target_fps == 10
    print("  PASS  inference latency and queue stress step down profile to eco mode")
    passed += 1

    # 3. Recovery / idle upgrade
    # 2 ticks of low load to step up from eco to nominal
    neg.update_telemetry("cam1", inference_latency_ms=25.0, queue_depth=0)
    p_rec1 = neg.update_telemetry("cam1", inference_latency_ms=25.0, queue_depth=0)
    assert p_rec1.name == "nominal"

    # 2 more ticks of low load to step up from nominal to hd
    neg.update_telemetry("cam1", inference_latency_ms=20.0, queue_depth=0)
    p_rec2 = neg.update_telemetry("cam1", inference_latency_ms=20.0, queue_depth=0)
    assert p_rec2.name == "hd"
    assert p_rec2.target_fps == 25
    print("  PASS  low pipeline latency recovers and upgrades feed profile to HD")
    passed += 1

    # 4. Tactical burst escalation
    p_burst = neg.trigger_burst("cam1", duration_s=0.2)
    assert p_burst.name == "tactical_burst"
    assert p_burst.target_fps == 30
    assert p_burst.jpeg_quality == 95

    # High load during active burst should not downgrade
    p_still_burst = neg.update_telemetry("cam1", inference_latency_ms=300.0, queue_depth=10)
    assert p_still_burst.name == "tactical_burst"
    print("  PASS  critical tactical burst locks high resolution and suppresses downgrades")
    passed += 1

    # 5. Burst expiration
    time.sleep(0.25)
    p_post_burst = neg.update_telemetry("cam1", inference_latency_ms=50.0, queue_depth=0)
    assert p_post_burst.name == "nominal"
    print("  PASS  tactical burst expires cleanly and restores nominal baseline")
    passed += 1

    print(f"\n{passed}/{passed} passed")


if __name__ == "__main__":
    run_tests()
