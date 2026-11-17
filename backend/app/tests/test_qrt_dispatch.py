"""
test_qrt_dispatch.py — Unit tests for QRT mission brief and vector dispatch generator.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ibvap.qrt_dispatch import QRTDispatchCard, QRTDispatchEngine


def run_tests():
    passed = 0
    engine = QRTDispatchEngine()

    # 1. Armed threat incident
    armed_incident = {
        "cam_id": 2,
        "cam_name": "Sector-2 Main Perimeter Fence",
        "category": "weapon_ready",
        "severity": "Critical",
        "details": {
            "weapon_class": "assault_rifle",
            "intruders": 2,
            "zone": "primary_wire",
        },
    }
    card_armed = engine.generate_mission_card(armed_incident, call_sign="QRT-ALPHA")
    assert card_armed.is_armed is True
    assert card_armed.threat_level == "CRITICAL"
    assert card_armed.recommended_approach == "CONCEALED_FLANKING_APPROACH"
    assert any("Ballistic" in eq for eq in card_armed.equipment_loadout)
    assert "SUSPECT CONFIRMED ARMED" in card_armed.radio_script_en
    assert "संदिग्ध हथियारबंद है" in card_armed.radio_script_hi
    print("  PASS  armed incident generates concealed approach and ballistic shield loadout")
    passed += 1

    # 2. Night crawling stealth incursion
    crawl_incident = {
        "cam_id": 3,
        "cam_name": "Sector-3 Riverine Zero-Line",
        "category": "crawling_prone",
        "severity": "Critical",
        "details": {"intruders": 1, "zone": "riverine_flank"},
    }
    card_crawl = engine.generate_mission_card(crawl_incident, call_sign="QRT-BRAVO")
    assert card_crawl.is_armed is False
    assert card_crawl.recommended_approach == "COORDINATED_CORDON_SEARCH"
    assert any("Canine" in eq for eq in card_crawl.equipment_loadout)
    assert any("Thermal" in eq for eq in card_crawl.equipment_loadout)
    print("  PASS  night crawling incursion assigns cordon search and canine/thermal equipment")
    passed += 1

    # 3. Vehicle / Roadway incident
    veh_incident = {
        "cam_id": 1,
        "cam_name": "Sector-1 Checkpost North",
        "category": "anpr_alert",
        "severity": "High",
        "details": {"persons_detected": 3},
    }
    card_veh = engine.generate_mission_card(veh_incident, call_sign="QRT-CHARLIE")
    assert card_veh.recommended_approach == "RAPID_INTERCEPTION_LIGHTS"
    assert any("Spike Belt" in eq for eq in card_veh.equipment_loadout)
    print("  PASS  vehicle alert generates rapid interception with spike belt roadblock")
    passed += 1

    # 4. Serialization
    d = card_armed.to_dict()
    assert d["call_sign"] == "QRT-ALPHA"
    assert d["is_armed"] is True
    assert "radio_script_en" in d
    assert "radio_script_hi" in d
    print("  PASS  QRT mission card serializes cleanly to operational dict")
    passed += 1

    print(f"\n{passed}/{passed} passed")


if __name__ == "__main__":
    run_tests()
