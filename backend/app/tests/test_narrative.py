"""
test_narrative.py -- Explainable AI Generative Incident Narrative Engine tests.

    python tests/test_narrative.py
    pytest  tests/test_narrative.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ibvap.narrative import generate_event_narrative, generate_shift_narrative  # noqa: E402

CASES = []


def case(name):
    def deco(fn):
        CASES.append((name, fn))
        return fn
    return deco


@case("armed threat event triggers priority 1 Critical narrative")
def _():
    event = {
        "event_id": "01HX98Z123456789ABCDEF001",
        "cam_id": 1,
        "cam_name": "Sector North Fence",
        "severity": "Critical",
        "category": "weapon",
        "score": 95.5,
        "persons": 1,
        "vehicles": 0,
        "details": {"armed": True, "weapon": True, "posture": "AIM"},
    }
    narrative = generate_event_narrative(event)
    assert narrative["tactical_priority"] == 1
    assert narrative["severity"] == "Critical"
    assert "ARMED THREAT" in narrative["headline"]
    assert "AIM posture" in narrative["summary"]
    assert "Quick Reaction Team" in narrative["recommended_action"]


@case("weapon detected without aim stance raises Critical priority 1")
def _():
    event = {
        "event_id": "01HX98Z123456789ABCDEF002",
        "cam_id": 2,
        "severity": "Critical",
        "category": "weapon",
        "score": 88.0,
        "persons": 1,
        "vehicles": 0,
        "details": {"weapon": True, "posture": "UPRIGHT"},
    }
    narrative = generate_event_narrative(event)
    assert narrative["tactical_priority"] == 1
    assert "Weapon Confirmed" in narrative["headline"]
    assert "firearm/weapon carried" in narrative["summary"]


@case("geofence breach event includes boundary name and escalation")
def _():
    event = {
        "event_id": "01HX98Z123456789ABCDEF003",
        "cam_id": 3,
        "severity": "Critical",
        "category": "intrusion",
        "score": 85.0,
        "persons": 2,
        "vehicles": 0,
        "details": {"breach": True, "fence_name": "Zone Bravo Exclusion Line"},
    }
    narrative = generate_event_narrative(event)
    assert "Perimeter Intrusion" in narrative["headline"]
    assert "Zone Bravo Exclusion Line" in narrative["summary"]
    assert "response patrol" in narrative["recommended_action"]


@case("watchlist face match cites target identity and CrPI guidance")
def _():
    event = {
        "event_id": "01HX98Z123456789ABCDEF004",
        "cam_id": 0,
        "severity": "High",
        "category": "face_match",
        "score": 75.0,
        "persons": 1,
        "vehicles": 0,
        "details": {"criminal_match": True, "criminal_name": "Target-Alpha"},
    }
    narrative = generate_event_narrative(event)
    assert "Watchlist Match" in narrative["headline"]
    assert "Target-Alpha" in narrative["summary"]
    assert "CrPI" in narrative["recommended_action"]


@case("ANPR vehicle detection logs plate and registration check action")
def _():
    event = {
        "event_id": "01HX98Z123456789ABCDEF005",
        "cam_id": 4,
        "severity": "Info",
        "category": "plate",
        "score": 10.0,
        "persons": 0,
        "vehicles": 1,
        "details": {"plate": "DL-01-AB-1234", "vehicle_type": "truck"},
    }
    narrative = generate_event_narrative(event)
    assert "DL-01-AB-1234" in narrative["headline"]
    assert "truck" in narrative["summary"]
    assert "VAHAN" in narrative["recommended_action"]


@case("loitering and rapid running categories are recognized")
def _():
    loiter_ev = {
        "event_id": "01HX98Z123456789ABCDEF006",
        "cam_id": 1,
        "severity": "Medium",
        "category": "loiter",
        "score": 45.0,
        "persons": 1,
        "vehicles": 0,
        "details": {"duration": 42.5},
    }
    run_ev = {
        "event_id": "01HX98Z123456789ABCDEF007",
        "cam_id": 2,
        "severity": "Medium",
        "category": "running",
        "score": 50.0,
        "persons": 1,
        "vehicles": 0,
        "details": {},
    }
    n_loiter = generate_event_narrative(loiter_ev)
    n_run = generate_event_narrative(run_ev)
    assert "Loitering Detected" in n_loiter["headline"]
    assert "42s" in n_loiter["summary"]
    assert "High-Velocity Transit" in n_run["headline"]


@case("empty event list generates clean nominal shift report")
def _():
    report = generate_shift_narrative([], site_name="BOP Beta")
    assert "BOP Beta" in report
    assert "Zero security anomalies" in report
    assert "nominal status" in report


@case("shift narrative report formats markdown table and alerts banner")
def _():
    events = [
        {
            "event_id": "01HX98Z123456789ABCDEF001",
            "cam_id": 1,
            "cam_name": "Gate-01",
            "severity": "Critical",
            "category": "weapon",
            "score": 96.0,
            "persons": 1,
            "vehicles": 0,
            "details": {"armed": True, "weapon": True, "posture": "AIM"},
            "ts_utc": "2026-11-13T21:00:00Z",
        },
        {
            "event_id": "01HX98Z123456789ABCDEF005",
            "cam_id": 2,
            "cam_name": "Checkpost-South",
            "severity": "Info",
            "category": "plate",
            "score": 15.0,
            "persons": 0,
            "vehicles": 1,
            "details": {"plate": "HR-26-DK-8899", "vehicle_type": "car"},
            "ts_utc": "2026-11-13T21:05:00Z",
        },
    ]
    report = generate_shift_narrative(events, site_name="BOP Charlie")
    assert "BOP Charlie" in report
    assert "CRITICAL ALERTS DETECTED" in report
    assert "HR-26-DK-8899" in report
    assert "SHA-256" in report


@case("hindi narrative generation formats incident in hindi")
def _():
    event = {
        "event_id": "01HX98Z123456789ABCDEF001",
        "cam_id": 1,
        "cam_name": "उत्तर सीमा बाड़",
        "severity": "Critical",
        "category": "weapon",
        "score": 96.0,
        "persons": 1,
        "vehicles": 0,
        "details": {"armed": True, "weapon": True, "posture": "AIM"},
        "ts_utc": "2026-11-13T21:00:00Z",
    }
    n = generate_event_narrative(event, lang="hi")
    assert "सशस्त्र खतरा" in n["headline"]
    assert "त्वरित प्रतिक्रिया दल" in n["recommended_action"]
    assert n["tactical_priority"] == 1


@case("hindi shift report formats hindi summary and nominal message")
def _():
    nominal = generate_shift_narrative([], site_name="बीओपी अल्फा", lang="hi")
    assert "आईबीवीएपी (IBVAP) शिफ्ट घटना एवं परिचालन रिपोर्ट" in nominal
    assert "कोई सुरक्षा विसंगति" in nominal


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
