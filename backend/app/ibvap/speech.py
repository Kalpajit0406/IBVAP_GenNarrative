"""
ibvap/speech.py — Tactical Voice Dispatch & Audio Announcement Synthesizer.

Generates concise, phonetically clear spoken voice dispatches for border command posts
and field radio relays, announcing critical security alerts and boundary intrusions
without requiring continuous visual monitor observation.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, Optional


_NATO_PHONETIC = {
    "A": "Alfa", "B": "Bravo", "C": "Charlie", "D": "Delta", "E": "Echo",
    "F": "Foxtrot", "G": "Golf", "H": "Hotel", "I": "India", "J": "Juliett",
    "K": "Kilo", "L": "Lima", "M": "Mike", "N": "November", "O": "Oscar",
    "P": "Papa", "Q": "Quebec", "R": "Romeo", "S": "Sierra", "T": "Tango",
    "U": "Uniform", "V": "Victor", "W": "Whiskey", "X": "X-ray", "Y": "Yankee",
    "Z": "Zulu", "0": "Zero", "1": "One", "2": "Two", "3": "Three",
    "4": "Four", "5": "Five", "6": "Six", "7": "Seven", "8": "Eight", "9": "Nine"
}


@dataclass
class SpeechAnnouncement:
    alert_level: str
    voice_script: str
    priority: int               # 1 (Highest/Interrupt) to 4 (Advisory)
    cam_id: int
    sector: str

    def to_ssml(self) -> str:
        """Produce standard SSML for speech synthesizers."""
        emphasis = "strong" if self.priority == 1 else "moderate"
        rate = "medium" if self.priority == 1 else "medium"
        return (
            f"<speak><emphasis level='{emphasis}'>{self.alert_level} Alert.</emphasis> "
            f"<prosody rate='{rate}'>{self.voice_script}</prosody></speak>"
        )


def spell_phonetic(text: str) -> str:
    """Spell alphanumeric tokens using NATO/ICAO phonetics for radio clarity."""
    tokens = []
    for ch in str(text).upper():
        if ch in _NATO_PHONETIC:
            tokens.append(_NATO_PHONETIC[ch])
        elif ch.isspace() or ch in ("-", "_"):
            continue
    return " ".join(tokens)


class SpeechDispatcher:
    """
    Synthesizes tactical voice scripts from surveillance events.
    """

    @staticmethod
    def format_announcement(event: Dict[str, Any]) -> SpeechAnnouncement:
        cam_id = int(event.get("cam_id") or 0)
        cam_name = str(event.get("cam_name") or f"Camera {cam_id}")
        site = str(event.get("post_name") or "Border Post")
        sev = str(event.get("severity") or "Info").upper()
        cat = str(event.get("category") or "activity").lower()
        details = event.get("details") or {}
        if isinstance(details, str):
            details = {}

        is_armed = bool(details.get("armed"))
        has_weapon = bool(details.get("weapon")) or cat == "weapon"
        is_breach = bool(details.get("breach")) or cat in ("intrusion", "crossing")
        plate = details.get("plate")

        if is_armed:
            script = f"Red Alert. Armed hostile threat confirmed at {cam_name}. Immediate tactical response required."
            priority = 1
        elif has_weapon:
            script = f"Warning. Weapon detected at {cam_name}. Alerting sector patrol."
            priority = 1
        elif is_breach:
            fence = details.get("fence_name", "perimeter boundary")
            script = f"Intrusion alarm. Physical breach across {fence} at {cam_name}."
            priority = 1 if sev in ("CRITICAL", "HIGH") else 2
        elif plate:
            phonetic_plate = spell_phonetic(plate)
            script = f"Vehicle identified at {cam_name}. Plate: {phonetic_plate}."
            priority = 3
        else:
            script = f"Security notice. Elevated activity recorded at {cam_name}."
            priority = 3

        return SpeechAnnouncement(
            alert_level=sev,
            voice_script=script,
            priority=priority,
            cam_id=cam_id,
            sector=site,
        )
