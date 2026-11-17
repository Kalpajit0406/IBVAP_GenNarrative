"""
test_heatmap.py — Unit tests for spatial threat density and infiltration heatmap.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ibvap.heatmap import SpatialThreatHeatmap


def run_tests():
    passed = 0
    hm = SpatialThreatHeatmap(cols=10, rows=6)

    # 1. Empty heatmap
    empty_hotspots = hm.get_top_hotspots()
    assert len(empty_hotspots) == 0
    print("  PASS  empty heatmap returns zero active hotspot clusters")
    passed += 1

    # 2. Add single Critical weapon event at (0.35, 0.45)
    # col = int(0.35 * 10) = 3; row = int(0.45 * 6) = 2
    hm.add_event(0.35, 0.45, severity="Critical", category="weapon_ready")
    hotspots1 = hm.get_top_hotspots(top_k=1)
    assert len(hotspots1) == 1
    h1 = hotspots1[0]
    assert h1.col == 3
    assert h1.row == 2
    assert h1.primary_category == "weapon_ready"
    assert h1.intensity > 1.0
    print("  PASS  single high-threat event registers at correct spatial cell")
    passed += 1

    # 3. Kernel smoothing diffusion
    # Grid cell (2, 3) is center; adjacent neighbor (2, 4) should have diffused intensity
    grid = hm.compute_smoothed_grid(kernel_radius=1)
    assert grid[2][3] > 0.0, "Center cell must have positive intensity"
    assert grid[2][4] > 0.0, "Adjacent cell must have non-zero diffused intensity"
    assert grid[2][4] < grid[2][3], "Adjacent cell must have less intensity than center"
    print("  PASS  kernel smoothing correctly diffuses spatial threat radius")
    passed += 1

    # 4. Multi-event accumulation and hotspot ranking
    # Add multiple breaches at (0.85, 0.15) -> col 8, row 0
    for _ in range(3):
        hm.add_event(0.85, 0.15, severity="Critical", category="geofence_breach")

    top_hotspots = hm.get_top_hotspots(top_k=2)
    assert len(top_hotspots) == 2
    # The cluster with 3 breaches should be rank 1
    assert top_hotspots[0].col == 8
    assert top_hotspots[0].row == 0
    assert top_hotspots[0].primary_category == "geofence_breach"
    print("  PASS  multiple incidents accumulate density and rank highest threat corridor first")
    passed += 1

    # 5. ASCII rendering
    ascii_out = hm.render_ascii()
    assert "TACTICAL BORDER THREAT HEATMAP" in ascii_out
    assert "Events: 4" in ascii_out
    assert len(ascii_out.splitlines()) >= 8
    print("  PASS  ASCII tactical heatmap renders clean multi-line visual matrix")
    passed += 1

    # 6. GeoJSON export
    geo = hm.to_geojson(base_lat=26.6852, base_lon=88.1425)
    assert geo["type"] == "FeatureCollection"
    assert geo["total_events"] == 4
    assert len(geo["features"]) >= 1
    feat0 = geo["features"][0]
    assert feat0["geometry"]["type"] == "Point"
    assert len(feat0["geometry"]["coordinates"]) == 2
    assert feat0["properties"]["primary_category"] == "geofence_breach"
    print("  PASS  GeoJSON spatial export produces compliant RFC 7946 point features")
    passed += 1

    print(f"\n{passed}/{passed} passed")


if __name__ == "__main__":
    run_tests()
