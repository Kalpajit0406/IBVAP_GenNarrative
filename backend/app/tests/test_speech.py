"""
test_speech.py — Tactical voice dispatch synthesizer tests.

    python tests/test_speech.py
    pytest  tests/test_speech.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ibvap.speech import SpeechDispatcher, spell_phonetic  # noqa: E402

CASES = []


def case(name):
    def deco(fn):
        CASES.append((name, fn))
        return fn
    return deco


@case("phonetic spelling maps letters and numbers to NATO standard")
def _():
    assert spell_phonetic("HR-26") == "Hotel Romeo Two Six"
    assert spell_phonetic("BOP1") == "Bravo Oscar Papa One"


@case("armed threat event formats priority 1 tactical voice script")
def _():
    event = {
        "cam_id": 2,
        "cam_name": "Sector North Gate",
        "post_name": "BOP Alpha",
        "severity": "Critical",
        "category": "weapon",
        "details": {"armed": True},
    }
    ann = SpeechDispatcher.format_announcement(event)
    assert ann.priority == 1
    assert "Red Alert" in ann.voice_script
    assert "Armed hostile threat" in ann.voice_script
    assert "<emphasis level='strong'>" in ann.to_ssml()


@case("perimeter breach event mentions fence name")
def _():
    event = {
        "cam_id": 1,
        "cam_name": "Camera One",
        "severity": "High",
        "category": "intrusion",
        "details": {"breach": True, "fence_name": "Zone Bravo Line"},
    }
    ann = SpeechDispatcher.format_announcement(event)
    assert "Intrusion alarm" in ann.voice_script
    assert "Zone Bravo Line" in ann.voice_script


@case("vehicle plate event formats phonetic announcement")
def _():
    event = {
        "cam_id": 0,
        "cam_name": "Entry",
        "severity": "Info",
        "category": "plate",
        "details": {"plate": "DL-01"},
    }
    ann = SpeechDispatcher.format_announcement(event)
    assert "Delta Lima Zero One" in ann.voice_script
    assert ann.priority == 3


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
