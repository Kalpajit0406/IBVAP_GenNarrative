"""
test_trajectory.py — Unit tests for trajectory kinematics and border approach vector analyzer.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ibvap.trajectory import BorderBoundarySegment, TrajectoryAnalyzer


def run_tests():
    passed = 0

    # 1. Stationary target
    analyzer = TrajectoryAnalyzer()
    analyzer.add_point("trk_1", 0.5, 0.5, 10.0)
    analyzer.add_point("trk_1", 0.5001, 0.5001, 11.0)
    v_stat = analyzer.analyze("trk_1")
    assert v_stat is not None
    assert v_stat.pattern == "STATIONARY"
    assert v_stat.speed < 0.005
    print("  PASS  stationary targets accurately classified without false motion triggers")
    passed += 1

    # 2. Sprint towards boundary fence
    # Fence line horizontally at y = 0.2 (from (0.0, 0.2) to (1.0, 0.2))
    fence = BorderBoundarySegment((0.0, 0.2), (1.0, 0.2))
    analyzer.clear()
    
    # Target moves northwards (-Y) from y=0.8 to y=0.4 in 2 seconds
    analyzer.add_point("trk_sprint", 0.5, 0.8, 0.0)
    analyzer.add_point("trk_sprint", 0.5, 0.6, 1.0)
    analyzer.add_point("trk_sprint", 0.5, 0.4, 2.0)
    
    v_sprint = analyzer.analyze("trk_sprint", boundary=fence)
    assert v_sprint is not None
    assert v_sprint.is_approaching is True
    assert v_sprint.pattern == "SPRINT_TO_BOUNDARY"
    assert v_sprint.speed == 0.2  # (0.8 - 0.4) / 2.0 = 0.2 units/sec
    assert abs(v_sprint.heading_deg - 0.0) < 1.0  # North is 0 deg
    # Current distance to fence (at y=0.4) is 0.2 units. At rate 0.2 units/s, TTB ~ 1.0 sec
    assert v_sprint.time_to_boundary_s is not None
    assert abs(v_sprint.time_to_boundary_s - 1.0) < 0.1
    print("  PASS  rapid sprint toward perimeter triggers SPRINT_TO_BOUNDARY and computes TTB")
    passed += 1

    # 3. Receding target moving away from fence
    analyzer.clear()
    analyzer.add_point("trk_away", 0.5, 0.3, 0.0)
    analyzer.add_point("trk_away", 0.5, 0.6, 2.0)
    v_away = analyzer.analyze("trk_away", boundary=fence)
    assert v_away is not None
    assert v_away.is_approaching is False
    assert v_away.pattern == "RECEDING"
    print("  PASS  receding target correctly identified with non-approaching status")
    passed += 1

    # 4. Zigzag evasive maneuvers
    analyzer.clear()
    # Rapid back and forth zigzag while moving forward
    analyzer.add_point("trk_evasive", 0.50, 0.8, 0.0)
    analyzer.add_point("trk_evasive", 0.58, 0.7, 0.5)
    analyzer.add_point("trk_evasive", 0.42, 0.6, 1.0)
    analyzer.add_point("trk_evasive", 0.59, 0.5, 1.5)
    analyzer.add_point("trk_evasive", 0.41, 0.4, 2.0)
    
    v_evasive = analyzer.analyze("trk_evasive", boundary=fence)
    assert v_evasive is not None
    assert v_evasive.is_evasive is True
    assert v_evasive.pattern == "ZIGZAG_EVASION"
    print("  PASS  evasive zigzag motion detected across multiple heading oscillations")
    passed += 1

    # 5. Boundary segment distance and normal angle
    seg = BorderBoundarySegment((0.1, 0.5), (0.9, 0.5))
    d = seg.distance_to_point(0.5, 0.8)
    assert abs(d - 0.3) < 1e-4
    assert seg.normal_angle_deg() is not None
    print("  PASS  boundary segment geometry accurately computes perpendicular offset and normal")
    passed += 1

    print(f"\n{passed}/{passed} passed")


if __name__ == "__main__":
    run_tests()
