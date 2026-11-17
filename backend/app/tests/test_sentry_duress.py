"""
test_sentry_duress.py — Unit tests for sentry duress, man-down, and post abandonment monitor.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ibvap.sentry_duress import SentryDuressMonitor, SentryPostConfig


def run_tests():
    passed = 0

    post = SentryPostConfig(
        post_id="post_morcha_1",
        name="Tower Morcha Alpha",
        cam_id=2,
        man_down_timeout_s=5.0,
        abandon_timeout_s=10.0,
    )
    monitor = SentryDuressMonitor([post])

    # 1. Normal active sentry
    res_norm = monitor.update("post_morcha_1", [{"track_id": "s1", "posture": "standing"}], timestamp=0.0)
    assert res_norm is None
    print("  PASS  active standing sentry operates in nominal state without false alarms")
    passed += 1

    # 2. Duress / Hostage posture (hands up) triggers immediate alert
    res_dur = monitor.update("post_morcha_1", [{"track_id": "s1", "posture": "hands_up"}], timestamp=1.0)
    assert res_dur is not None
    assert res_dur.status == "DURESS_HANDS_UP"
    assert res_dur.tactical_priority == 1
    assert "hands raised" in res_dur.advisory.lower()
    print("  PASS  hands-up posture triggers immediate DURESS_HANDS_UP alert")
    passed += 1

    # 3. Man-Down detection after immobility timeout
    # Initial fall at t=10.0
    res_fall_start = monitor.update("post_morcha_1", [{"track_id": "s1", "posture": "lying_down"}], timestamp=10.0)
    assert res_fall_start is None, "Should wait for timeout before declaring man-down"

    # At t=12.0 (2s elapsed < 5s timeout)
    res_fall_mid = monitor.update("post_morcha_1", [{"track_id": "s1", "posture": "lying_down"}], timestamp=12.0)
    assert res_fall_mid is None

    # At t=16.0 (6s elapsed > 5s timeout)
    res_man_down = monitor.update("post_morcha_1", [{"track_id": "s1", "posture": "lying_down"}], timestamp=16.0)
    assert res_man_down is not None
    assert res_man_down.status == "MAN_DOWN"
    assert res_man_down.tactical_priority == 1
    assert res_man_down.duration_s >= 5.0
    print("  PASS  prolonged lying posture triggers MAN_DOWN critical alert")
    passed += 1

    # 4. Sentry stands back up (recovery)
    res_recovery = monitor.update("post_morcha_1", [{"track_id": "s1", "posture": "standing"}], timestamp=20.0)
    assert res_recovery is None, "Recovery to standing resets alert"
    print("  PASS  sentry recovery to standing resets distress timers")
    passed += 1

    # 5. Post Abandonment / Vacancy past timeout
    # Vacant at t=30.0
    monitor.update("post_morcha_1", [], timestamp=30.0)
    # Vacant at t=35.0 (5s < 10s)
    res_v1 = monitor.update("post_morcha_1", [], timestamp=35.0)
    assert res_v1 is None
    # Vacant at t=42.0 (12s > 10s)
    res_abandon = monitor.update("post_morcha_1", [], timestamp=42.0)
    assert res_abandon is not None
    assert res_abandon.status == "POST_ABANDONED"
    assert res_abandon.tactical_priority == 1
    assert "vacant" in res_abandon.advisory.lower()
    print("  PASS  unattended post past abandonment timeout triggers POST_ABANDONED")
    passed += 1

    # 6. Serialization
    d = res_abandon.to_dict()
    assert d["status"] == "POST_ABANDONED"
    assert d["post_id"] == "post_morcha_1"
    assert d["tactical_priority"] == 1
    print("  PASS  sentry distress alert serializes cleanly to dict")
    passed += 1

    print(f"\n{passed}/{passed} passed")


if __name__ == "__main__":
    run_tests()
