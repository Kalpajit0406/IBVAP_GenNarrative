"""
test_gis.py — RFC 7946 GeoJSON spatial feature converter tests.

    python tests/test_gis.py
    pytest  tests/test_gis.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ibvap.gis import to_geojson_feature, to_geojson_feature_collection  # noqa: E402

CASES = []


def case(name):
    def deco(fn):
        CASES.append((name, fn))
        return fn
    return deco


@case("event with GPS coordinates converts to GeoJSON Point with lon-lat order")
def _():
    event = {
        "event_id": "01HX1",
        "lat": 26.85,
        "lon": 88.35,
        "cam_id": 1,
        "cam_name": "Gate-01",
        "severity": "Critical",
        "category": "weapon",
        "score": 95.0,
    }
    feat = to_geojson_feature(event)
    assert feat["type"] == "Feature"
    assert feat["geometry"]["type"] == "Point"
    # RFC 7946: [longitude, latitude]
    assert feat["geometry"]["coordinates"] == [88.35, 26.85]
    assert feat["properties"]["marker_color"] == "#EF4444"
    assert feat["properties"]["severity"] == "Critical"


@case("event without coordinates produces None geometry without error")
def _():
    event = {
        "event_id": "01HX2",
        "severity": "High",
        "category": "intrusion",
    }
    feat = to_geojson_feature(event)
    assert feat["geometry"] is None
    assert feat["properties"]["marker_color"] == "#F97316"


@case("feature collection calculates metadata and spatial counts correctly")
def _():
    events = [
        {"event_id": "e1", "lat": 27.1, "lon": 88.2, "severity": "Critical"},
        {"event_id": "e2", "severity": "Info"},
    ]
    fc = to_geojson_feature_collection(events, site_name="BOP North")
    assert fc["type"] == "FeatureCollection"
    assert fc["metadata"]["site_name"] == "BOP North"
    assert fc["metadata"]["total_features"] == 2
    assert fc["metadata"]["spatial_features"] == 1
    assert len(fc["features"]) == 2


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
