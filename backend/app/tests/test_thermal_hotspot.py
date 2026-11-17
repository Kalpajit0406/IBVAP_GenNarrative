"""
test_thermal_hotspot.py — Unit tests for thermal hotspot and concealed engine heat profiler.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ibvap.thermal_hotspot import ThermalHotspot, ThermalHotspotAnalyzer


def run_tests():
    passed = 0
    analyzer = ThermalHotspotAnalyzer()

    # 1. Clean background matrix (all 20.0 C, ambient 20.0 C)
    grid_clean = [[20.0 for _ in range(8)] for _ in range(8)]
    res_clean = analyzer.analyze_grid(grid_clean, ambient_temp_c=20.0)
    assert len(res_clean) == 0
    print("  PASS  uniform ambient temperature grid yields zero false hotspot anomalies")
    passed += 1

    # 2. Running vehicle engine (+38 C delta)
    grid_engine = [[20.0 for _ in range(8)] for _ in range(8)]
    # Place hot cluster at (2, 2)
    grid_engine[2][2] = 58.0
    grid_engine[2][3] = 56.0
    grid_engine[3][2] = 57.0

    res_engine = analyzer.analyze_grid(grid_engine, ambient_temp_c=20.0)
    assert len(res_engine) == 1
    h_eng = res_engine[0]
    assert h_eng.estimated_source == "VEHICLE_ENGINE"
    assert h_eng.severity == "Critical"
    assert h_eng.tactical_priority == 1
    assert h_eng.relative_temp_delta_c == 38.0
    print("  PASS  high-delta engine exhaust cluster triggers VEHICLE_ENGINE Critical alert")
    passed += 1

    # 3. Concealed human in foliage mask
    grid_human = [[18.0 for _ in range(8)] for _ in range(8)]
    # Human cluster at (5, 5) with temp 34.0 C (+16 C delta)
    grid_human[5][5] = 34.0
    grid_human[5][6] = 33.5

    # Foliage mask covers row 5
    foliage = [[False for _ in range(8)] for _ in range(8)]
    foliage[5][5] = True
    foliage[5][6] = True

    res_human = analyzer.analyze_grid(grid_human, ambient_temp_c=18.0, foliage_mask=foliage)
    assert len(res_human) == 1
    h_hum = res_human[0]
    assert h_hum.estimated_source == "HUMAN_CORE"
    assert h_hum.is_concealed is True
    assert "concealed" in h_hum.advisory.lower()
    print("  PASS  thermal signature in foliage mask correctly identifies concealed human")
    passed += 1

    # 4. Serialization
    d = h_eng.to_dict()
    assert d["estimated_source"] == "VEHICLE_ENGINE"
    assert d["relative_temp_delta_c"] == 38.0
    assert d["tactical_priority"] == 1
    print("  PASS  thermal hotspot serializes cleanly to operational telemetry dict")
    passed += 1

    print(f"\n{passed}/{passed} passed")


if __name__ == "__main__":
    run_tests()
