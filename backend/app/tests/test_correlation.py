"""
test_correlation.py — Unit tests for multi-camera spatial/temporal event correlation.

    python tests/test_correlation.py
    pytest  tests/test_correlation.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ibvap.correlation import IncidentCorrelator  # noqa: E402

CASES = []


def case(name):
    def deco(fn):
        CASES.append((name, fn))
        return fn
    return deco


@case("single event creates a new active incident")
def _():
    corr = IncidentCorrelator(correlation_window_s=60.0)
    ev = {"event_id": "e1", "cam_id": 0, "cam_name": "Gate", "category": "plate", "severity": "Info", "ts": 100.0}
    inc = corr.ingest_event(ev)
    assert len(corr.get_active()) == 1
    assert inc.cameras == [0]
    assert inc.highest_severity == "Info"


@case("sequential events across multiple cameras merge into one incident chain")
def _():
    corr = IncidentCorrelator(correlation_window_s=60.0)
    e1 = {"event_id": "e1", "cam_id": 0, "cam_name": "Gate", "category": "plate", "severity": "Info", "ts": 100.0, "details": {"plate": "DL-01-AB"}}
    e2 = {"event_id": "e2", "cam_id": 1, "cam_name": "Fence", "category": "intrusion", "severity": "High", "ts": 120.0, "details": {"breach": True, "fence_name": "North Fence"}}
    e3 = {"event_id": "e3", "cam_id": 2, "cam_name": "Post", "category": "weapon", "severity": "Critical", "ts": 135.0, "details": {"armed": True}}

    corr.ingest_event(e1)
    corr.ingest_event(e2)
    inc = corr.ingest_event(e3)

    assert len(corr.get_active()) == 1
    assert inc.cameras == [0, 1, 2]
    assert inc.highest_severity == "Critical"
    assert len(inc.event_ids) == 3

    narrative = inc.synthesize_narrative()
    assert "MULTI-CAMERA INCIDENT [CRITICAL]" in narrative
    assert "Vehicle plate [DL-01-AB]" in narrative
    assert "Breach across 'North Fence'" in narrative
    assert "Armed individual" in narrative


@case("event outside correlation window starts a new separate incident")
def _():
    corr = IncidentCorrelator(correlation_window_s=30.0)
    e1 = {"event_id": "e1", "cam_id": 0, "category": "risk", "severity": "Low", "ts": 100.0}
    e2 = {"event_id": "e2", "cam_id": 1, "category": "risk", "severity": "High", "ts": 200.0}

    inc1 = corr.ingest_event(e1)
    inc2 = corr.ingest_event(e2)

    assert inc1.incident_id != inc2.incident_id
    assert len(corr.get_active()) == 1
    assert corr.get_active()[0].incident_id == inc2.incident_id


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
