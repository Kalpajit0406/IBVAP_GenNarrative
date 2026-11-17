"""
test_ptz_director.py — Unit tests for cross-camera slew-to-cue PTZ tracking director.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ibvap.ptz_director import CameraMountGeometry, PTZCommand, SlewToCueDirector


def run_tests():
    passed = 0
    director = SlewToCueDirector(ptz_cam_id=4, max_optical_zoom=30.0, lock_hold_duration_s=3.0)

    # Register CAM-01 looking North-East (azimuth 45 deg, tilt -10 deg, HFOV 90 deg, VFOV 60 deg)
    mount_cam1 = CameraMountGeometry(
        cam_id=1,
        azimuth_center_deg=45.0,
        tilt_center_deg=-10.0,
        hfov_deg=90.0,
        vfov_deg=60.0,
    )
    director.register_mount(mount_cam1)

    # 1. Target at dead center (0.5, 0.5)
    cmd_center = director.compute_slew(
        source_cam_id=1,
        target_point=(0.5, 0.5),
        target_bbox_height=0.04,  # small distant target
        target_track_id="trk_center",
        priority=2,
        now=10.0,
    )
    assert cmd_center is not None
    assert abs(cmd_center.pan_deg - 45.0) < 0.1
    assert abs(cmd_center.tilt_deg - (-10.0)) < 0.1
    assert cmd_center.zoom_factor == 10.0  # 0.40 / 0.04 = 10.0
    print("  PASS  center point computes exact mount azimuth and elevation tilt")
    passed += 1

    # 2. Target offset to upper-right (px=0.8, py=0.2)
    # pan: 45 + (0.8 - 0.5) * 90 = 45 + 27 = 72 deg
    # tilt: -10 - (0.2 - 0.5) * 60 = -10 - (-18) = +8 deg
    director._current_lock_target = None  # clear lock
    director._lock_expires_at = 0.0
    cmd_offset = director.compute_slew(
        source_cam_id=1,
        target_point=(0.8, 0.2),
        target_bbox_height=0.02,  # tiny target -> 20x zoom
        target_track_id="trk_far",
        priority=2,
        now=20.0,
    )
    assert cmd_offset is not None
    assert abs(cmd_offset.pan_deg - 72.0) < 0.1
    assert abs(cmd_offset.tilt_deg - 8.0) < 0.1
    assert cmd_offset.zoom_factor == 20.0  # 0.40 / 0.02 = 20.0
    print("  PASS  offset point accurately calculates target pan angle and high optical zoom")
    passed += 1

    # 3. Lock-on priority arbitration
    # While trk_far has lock (priority 2 until t=23.0), lower priority (priority 3) cannot steal
    cmd_low = director.compute_slew(
        source_cam_id=1,
        target_point=(0.2, 0.8),
        target_bbox_height=0.1,
        target_track_id="trk_loiter",
        priority=3,
        now=21.0,
    )
    assert cmd_low is None, "Lower priority target must not preempt active lock"

    # Higher priority (priority 1: weapon/breach) DOES preempt active lock
    cmd_high = director.compute_slew(
        source_cam_id=1,
        target_point=(0.2, 0.8),
        target_bbox_height=0.1,
        target_track_id="trk_weapon",
        priority=1,
        now=21.5,
    )
    assert cmd_high is not None
    assert cmd_high.target_track_id == "trk_weapon"
    print("  PASS  threat priority arbitration ensures Critical targets preempt lower locks")
    passed += 1

    # 4. Serialization
    d = cmd_high.to_dict()
    assert d["ptz_cam_id"] == 4
    assert d["target_priority"] == 1
    assert "pan_deg" in d
    assert "zoom_factor" in d
    print("  PASS  PTZ command serializes cleanly to operational telemetry dict")
    passed += 1

    print(f"\n{passed}/{passed} passed")


if __name__ == "__main__":
    run_tests()
