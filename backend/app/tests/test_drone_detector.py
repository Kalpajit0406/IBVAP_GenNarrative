"""
test_drone_detector.py — Unit tests for rogue UAV drone and payload drop tracker.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ibvap.drone_detector import DroneAlert, DroneTrackAnalyzer


def run_tests():
    passed = 0
    analyzer = DroneTrackAnalyzer(hover_duration_s=1.0)

    # 1. Ground target (walking person) should not trigger drone alerts
    analyzer.clear()
    analyzer.update_track("ground_1", (0.4, 0.80, 0.45, 0.95), timestamp=10.0)
    analyzer.update_track("ground_1", (0.41, 0.81, 0.46, 0.96), timestamp=10.5)
    alert_g = analyzer.update_track("ground_1", (0.42, 0.82, 0.47, 0.97), timestamp=11.0)
    assert alert_g is None, "Ground targets must not trigger drone alerts"
    print("  PASS  ground targets correctly ignored by drone kinematics analyzer")
    passed += 1

    # 2. High-speed aerial incursion
    analyzer.clear()
    # Moves horizontally across sky (y=0.20) from x=0.1 to x=0.6 in 1.5s -> speed = 0.5 / 1.5 = 0.33 units/s
    analyzer.update_track("uav_fast", (0.10, 0.18, 0.14, 0.22), timestamp=10.0)
    analyzer.update_track("uav_fast", (0.35, 0.18, 0.39, 0.22), timestamp=10.8)
    alert_inc = analyzer.update_track("uav_fast", (0.60, 0.18, 0.64, 0.22), timestamp=11.5)
    assert alert_inc is not None
    assert alert_inc.alert_type == "UAV_INCURSION"
    assert alert_inc.tactical_priority == 2
    assert alert_inc.severity == "High"
    print("  PASS  high-speed aerial target triggers UAV_INCURSION alert")
    passed += 1

    # 3. UAV Hovering
    analyzer.clear()
    # Airborne at (0.5, 0.25), nearly stationary over 1.2 seconds
    analyzer.update_track("uav_hov", (0.48, 0.23, 0.52, 0.27), timestamp=20.0)
    analyzer.update_track("uav_hov", (0.481, 0.231, 0.521, 0.271), timestamp=20.6)
    alert_hov = analyzer.update_track("uav_hov", (0.482, 0.232, 0.522, 0.272), timestamp=21.3)
    assert alert_hov is not None
    assert alert_hov.alert_type == "UAV_HOVERING"
    assert "hovering" in alert_hov.advisory.lower()
    print("  PASS  airborne stationary target triggers UAV_HOVERING reconnaissance alert")
    passed += 1

    # 4. Contraband Payload Drop
    analyzer.clear()
    # Target starts high at y=0.15, drops rapidly to y=0.75 within 1.0s
    analyzer.update_track("uav_drop", (0.50, 0.15, 0.54, 0.19), timestamp=30.0)
    analyzer.update_track("uav_drop", (0.50, 0.45, 0.54, 0.49), timestamp=30.5)
    alert_drop = analyzer.update_track("uav_drop", (0.50, 0.75, 0.54, 0.79), timestamp=31.0)
    assert alert_drop is not None
    assert alert_drop.alert_type == "PAYLOAD_DROP_DETECTED"
    assert alert_drop.tactical_priority == 1
    assert alert_drop.severity == "Critical"
    assert alert_drop.drop_point is not None
    assert abs(alert_drop.drop_point[0] - 0.52) < 0.05
    assert abs(alert_drop.drop_point[1] - 0.77) < 0.05
    print("  PASS  vertical decoupling triggers PAYLOAD_DROP_DETECTED with drop coordinates")
    passed += 1

    # 5. Serialization to dict
    d = alert_drop.to_dict()
    assert d["alert_type"] == "PAYLOAD_DROP_DETECTED"
    assert d["tactical_priority"] == 1
    assert d["drop_point"] is not None
    print("  PASS  drone alert cleanly serializes to operational telemetry dict")
    passed += 1

    print(f"\n{passed}/{passed} passed")


if __name__ == "__main__":
    run_tests()
