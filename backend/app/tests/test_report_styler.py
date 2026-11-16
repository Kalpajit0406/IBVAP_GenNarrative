"""
test_report_styler.py — Unit tests for HTML shift handover report generator.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ibvap.report_styler import generate_html_shift_report


def run_tests():
    passed = 0

    # 1. Empty events nominal fallback
    html_empty = generate_html_shift_report([], shift_info={"bop_name": "BOP Raxaul"})
    assert "<!DOCTYPE html>" in html_empty
    assert "BOP Raxaul" in html_empty
    assert "NO CRITICAL OR THREAT INCIDENTS RECORDED" in html_empty
    assert "Total Events</div>" in html_empty
    print("  PASS  empty event list renders nominal shift dossier with operational status")
    passed += 1

    # 2. Multi-event severity and category breakdown
    sample_events = [
        {
            "event_id": "EV-001",
            "timestamp_utc": "2026-11-16 02:14:00 UTC",
            "cam_id": 3,
            "cam_name": "Zero-Line North",
            "severity": "Critical",
            "tactical_priority": 1,
            "category": "weapon_ready",
            "summary": "Unholstered assault rifle identified in Sector 3.",
            "recommended_action": "Deploy QRT Alpha immediately.",
        },
        {
            "event_id": "EV-002",
            "timestamp_utc": "2026-11-16 03:45:10 UTC",
            "cam_id": 1,
            "severity": "Critical",
            "tactical_priority": 1,
            "category": "geofence_breach",
            "summary": "Target crossed primary wire perimeter line.",
            "recommended_action": "Sound sector siren.",
        },
        {
            "event_id": "EV-003",
            "timestamp_utc": "2026-11-16 05:10:00 UTC",
            "cam_id": 2,
            "severity": "High",
            "tactical_priority": 2,
            "category": "anpr_alert",
            "summary": "Blacklisted vehicle plate WB-74-E-1234 identified.",
            "recommended_action": "Halt vehicle at checkpoint.",
        },
    ]

    html_events = generate_html_shift_report(
        sample_events,
        shift_info={
            "bop_name": "BOP Panitanki",
            "outgoing_officer": "SI A. Kumar",
            "incoming_officer": "Insp. M. Sen",
        },
        merkle_root="0x1234567890abcdef",
    )

    assert "BOP Panitanki" in html_events
    assert "SI A. Kumar" in html_events
    assert "Insp. M. Sen" in html_events
    assert "0x1234567890abcdef" in html_events
    assert "CRITICAL (P1)" in html_events
    assert "HIGH (P2)" in html_events
    assert "WB-74-E-1234" in html_events
    assert "Zero-Line North (CAM-03)" in html_events
    print("  PASS  multi-incident report accurately renders severity badges, cameras, and metadata")
    passed += 1

    # 3. HTML escaping test
    xss_events = [
        {
            "event_id": "EV-<script>alert(1)</script>",
            "summary": "Target <b>escaped</b> across <fence>",
            "category": "suspicious",
            "severity": "Medium",
        }
    ]
    html_safe = generate_html_shift_report(xss_events)
    assert "<script>" not in html_safe
    assert "&lt;script&gt;" in html_safe
    assert "&lt;b&gt;escaped&lt;/b&gt;" in html_safe
    print("  PASS  html escaping prevents malicious script or raw tag injection")
    passed += 1

    print(f"\n{passed}/{passed} passed")


if __name__ == "__main__":
    run_tests()
