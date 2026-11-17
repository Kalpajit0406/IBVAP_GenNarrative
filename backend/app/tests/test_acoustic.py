"""
test_acoustic.py — Unit tests for acoustic gunshot and transient event classifier.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ibvap.acoustic import AcousticClassifier, AcousticEvent


def run_tests():
    passed = 0
    classifier = AcousticClassifier()

    # 1. Gunshot classification
    # High SPL 95 dB, fast rise 4 ms, decay 120 ms, centroid 2200 Hz
    ev_shot = classifier.classify(
        peak_amplitude=0.92,
        rise_time_ms=4.0,
        decay_time_ms=120.0,
        spectral_centroid_hz=2200.0,
        spl_db=95.0,
        bearing_deg=45.0,
    )
    assert ev_shot.event_type == "gunshot"
    assert ev_shot.severity == "Critical"
    assert ev_shot.tactical_priority == 1
    assert ev_shot.associated_cam_id == 1
    assert "CAM-01" in ev_shot.advisory
    print("  PASS  gunshot transient triggers Critical Priority 1 alert and correlates CAM-01")
    passed += 1

    # 2. Explosion classification
    # High SPL 105 dB, slow decay 550 ms, low centroid 320 Hz
    ev_blast = classifier.classify(
        peak_amplitude=0.98,
        rise_time_ms=8.0,
        decay_time_ms=550.0,
        spectral_centroid_hz=320.0,
        spl_db=105.0,
        bearing_deg=135.0,
    )
    assert ev_blast.event_type == "explosion"
    assert ev_blast.severity == "Critical"
    assert ev_blast.associated_cam_id == 2
    assert "detonation" in ev_blast.advisory.lower()
    print("  PASS  blast acoustic profile triggers explosion lockdown and correlates CAM-02")
    passed += 1

    # 3. Drone / UAV rotor harmonic
    ev_drone = classifier.classify(
        peak_amplitude=0.45,
        rise_time_ms=120.0,
        decay_time_ms=600.0,
        spectral_centroid_hz=420.0,
        spl_db=58.0,
        bearing_deg=220.0,
    )
    assert ev_drone.event_type == "drone_rotor"
    assert ev_drone.severity == "High"
    assert ev_drone.associated_cam_id == 3
    assert "uav" in ev_drone.advisory.lower()
    print("  PASS  drone acoustic harmonic identifies low-altitude UAV signature")
    passed += 1

    # 4. Wire fence cut / metal transient
    ev_wire = classifier.classify(
        peak_amplitude=0.60,
        rise_time_ms=15.0,
        decay_time_ms=80.0,
        spectral_centroid_hz=4500.0,
        spl_db=62.0,
        bearing_deg=310.0,
    )
    assert ev_wire.event_type == "wire_cut"
    assert ev_wire.severity == "High"
    assert ev_wire.associated_cam_id == 4
    assert "fence" in ev_wire.advisory.lower()
    print("  PASS  high-frequency metal transient identifies perimeter wire cutting")
    passed += 1

    # 5. Ambient nominal fallback
    ev_ambient = classifier.classify(
        peak_amplitude=0.1,
        rise_time_ms=200.0,
        decay_time_ms=200.0,
        spectral_centroid_hz=1500.0,
        spl_db=40.0,
    )
    assert ev_ambient.event_type == "ambient"
    assert ev_ambient.tactical_priority == 5
    assert ev_ambient.severity == "Info"
    print("  PASS  ambient background acoustic levels return nominal informational status")
    passed += 1

    # 6. Serialization to dictionary
    d = ev_shot.to_dict()
    assert d["event_type"] == "gunshot"
    assert d["bearing_deg"] == 45.0
    assert d["tactical_priority"] == 1
    print("  PASS  acoustic event serializes cleanly to operational telemetry dictionary")
    passed += 1

    print(f"\n{passed}/{passed} passed")


if __name__ == "__main__":
    run_tests()
