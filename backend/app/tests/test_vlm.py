"""
test_vlm.py — Zero-shot VLM anomaly prompt synthesizer tests.

    python tests/test_vlm.py
    pytest  tests/test_vlm.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ibvap.vlm import TrackContext, VlmPromptBuilder, VlmSceneContext  # noqa: E402

CASES = []


def case(name):
    def deco(fn):
        CASES.append((name, fn))
        return fn
    return deco


@case("user prompt includes telemetry, tracks, and environmental state")
def _():
    ctx = VlmSceneContext(
        cam_id=1,
        cam_name="Sector North Gate",
        illumination="night_ir",
        weather="fog",
        visibility=0.45,
        fences=["Perimeter Line A"],
        tracks=[
            TrackContext(
                track_id=10,
                class_name="person",
                bbox=(100, 200, 150, 320),
                posture="AIM",
                weapon_confirmed=True,
            )
        ],
    )
    prompt = VlmPromptBuilder.build_user_prompt(ctx)
    assert "Sector North Gate" in prompt
    assert "night_ir" in prompt
    assert "Perimeter Line A" in prompt
    assert "AIM" in prompt
    assert '"weapon_confirmed": true' in prompt


@case("parse_response extracts JSON from raw VLM output")
def _():
    raw_vlm = (
        "Here is my tactical assessment:\n"
        "```json\n"
        "{\n"
        '  "anomaly_detected": true,\n'
        '  "threat_level": "Critical",\n'
        '  "reasoning": "Track #10 is in an aiming stance with a confirmed firearm during night IR conditions.",\n'
        '  "recommended_action": "Deploy Quick Reaction Team to Sector North Gate immediately."\n'
        "}\n"
        "```\n"
    )
    res = VlmPromptBuilder.parse_response(raw_vlm)
    assert res["anomaly_detected"] is True
    assert res["threat_level"] == "Critical"
    assert "aiming stance" in res["reasoning"]
    assert "Quick Reaction Team" in res["recommended_action"]


@case("parse_response handles malformed text gracefully")
def _():
    res = VlmPromptBuilder.parse_response("Sorry, I cannot process this image.")
    assert res["anomaly_detected"] is False
    assert res["threat_level"] == "Nominal"
    assert "Verify feed manually" in res["recommended_action"]


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
