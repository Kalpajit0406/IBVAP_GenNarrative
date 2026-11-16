"""
test_zones.py — Unit tests for tactical border zone escalation matrix.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ibvap.zones import (
    TacticalZone,
    ZoneEscalationEngine,
    _point_in_polygon,
)


def run_tests():
    passed = 0

    # 1. Point in polygon test
    square = [(0.2, 0.2), (0.8, 0.2), (0.8, 0.8), (0.2, 0.8)]
    assert _point_in_polygon(0.5, 0.5, square) is True, "Center point must be inside square"
    assert _point_in_polygon(0.1, 0.5, square) is False, "Left point must be outside square"
    assert _point_in_polygon(0.9, 0.9, square) is False, "Corner point must be outside square"
    print("  PASS  point-in-polygon ray casting identifies interior and exterior points")
    passed += 1

    # 2. TacticalZone post_init multiplier defaults
    z_pw = TacticalZone("z1", "Zero Line Alpha", "primary_wire", square)
    assert z_pw.risk_multiplier == 2.5, f"Expected 2.5, got {z_pw.risk_multiplier}"
    z_bop = TacticalZone("z2", "Post HQ", "bop_perimeter", square)
    assert z_bop.risk_multiplier == 3.0, f"Expected 3.0, got {z_bop.risk_multiplier}"
    print("  PASS  zone type assigns correct default tactical risk multipliers")
    passed += 1

    # 3. Schedule arming across midnight and daytime
    z_night = TacticalZone(
        "z_night", "Night Ambush Zone", "buffer_corridor", square,
        schedule_start_hour=21, schedule_end_hour=5
    )
    assert z_night.is_armed_at(22) is True, "22:00 must be armed"
    assert z_night.is_armed_at(2) is True, "02:00 must be armed"
    assert z_night.is_armed_at(12) is False, "12:00 must be disarmed"

    z_day = TacticalZone(
        "z_day", "Day Patrol Route", "patrol_road", square,
        schedule_start_hour=8, schedule_end_hour=18
    )
    assert z_day.is_armed_at(10) is True, "10:00 must be armed"
    assert z_day.is_armed_at(20) is False, "20:00 must be disarmed"
    print("  PASS  time-of-day zone arming handles daytime and midnight-crossing schedules")
    passed += 1

    # 4. Engine evaluation outside zones
    engine = ZoneEscalationEngine()
    outside_res = engine.evaluate_point("cam1", (0.05, 0.05), base_risk=0.4)
    assert outside_res.primary_zone is None
    assert outside_res.matched_zones == []
    assert outside_res.tactical_action == "MONITOR"
    print("  PASS  unmatched target outside zones returns nominal monitoring result")
    passed += 1

    # 5. Engine evaluation with single zone escalation
    engine.add_zone("cam1", z_pw)
    eval_res = engine.evaluate_point("cam1", (0.5, 0.5), base_risk=0.4)
    assert eval_res.primary_zone.name == "Zero Line Alpha"
    assert eval_res.effective_risk == 1.0  # 0.4 * 2.5 = 1.0 clamped
    assert eval_res.escalation_level == "CRITICAL"
    assert eval_res.tactical_action == "DEPLOY_QRT"
    assert "Zero Line Alpha" in eval_res.advisory
    print("  PASS  target in primary wire zone triggers high multiplier and QRT dispatch advisory")
    passed += 1

    # 6. Overlapping zones select highest risk multiplier
    buffer_zone = TacticalZone("z_buf", "Outer Buffer", "buffer_corridor", square, risk_multiplier=1.8)
    engine.add_zone("cam1", buffer_zone)
    overlap_res = engine.evaluate_point("cam1", (0.5, 0.5), base_risk=0.3)
    assert len(overlap_res.matched_zones) == 2
    assert overlap_res.primary_zone.name == "Zero Line Alpha"  # 2.5 > 1.8
    assert overlap_res.effective_risk == round(0.3 * 2.5, 3)
    print("  PASS  overlapping tactical zones select highest severity zone for primary advisory")
    passed += 1

    # 7. Disarmed zone bypass
    disarmed_pw = TacticalZone(
        "z_pw_disarm", "Disarmed Wire", "primary_wire", square,
        schedule_start_hour=22, schedule_end_hour=4
    )
    engine2 = ZoneEscalationEngine()
    engine2.add_zone("cam2", disarmed_pw)
    day_res = engine2.evaluate_point("cam2", (0.5, 0.5), base_risk=0.4, hour=12)
    assert day_res.primary_zone is None, "Should not match scheduled-off zone"
    night_res = engine2.evaluate_point("cam2", (0.5, 0.5), base_risk=0.4, hour=23)
    assert night_res.primary_zone is not None
    print("  PASS  schedule correctly suppresses inactive tactical zones during off-hours")
    passed += 1

    # 8. Serialization and persistence roundtrip
    with tempfile.TemporaryDirectory() as td:
        persist_file = Path(td) / "zones.json"
        engine_p = ZoneEscalationEngine(persistence_path=persist_file)
        engine_p.add_zone("cam_east", z_pw)
        engine_p.add_zone("cam_east", buffer_zone)
        
        # Reload in fresh engine instance
        engine_loaded = ZoneEscalationEngine(persistence_path=persist_file)
        loaded_zones = engine_loaded.get_zones("cam_east")
        assert len(loaded_zones) == 2
        z_names = {z.name for z in loaded_zones}
        assert "Zero Line Alpha" in z_names
        assert "Outer Buffer" in z_names
        
        # Test removal
        assert engine_loaded.remove_zone("cam_east", "z1") is True
        assert len(engine_loaded.get_zones("cam_east")) == 1
    print("  PASS  zone definitions successfully persist and reload via JSON configuration")
    passed += 1

    print(f"\n{passed}/{passed} passed")


if __name__ == "__main__":
    run_tests()
