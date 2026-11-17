"""
qrt_dispatch.py — Tactical Quick Reaction Team (QRT) mission brief and vector dispatch generator.

Synthesizes high-priority border intrusion events into actionable tactical mission cards (TMC)
and VHF/UHF radio broadcast dispatches in English and Hindi for immediate operational deployment.
Specifies threat armament profile, recommended tactical approach vector, and equipment loadout.
"""
from __future__ import annotations

import datetime
import uuid
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class QRTDispatchCard:
    mission_id: str
    call_sign: str
    target_sector: str
    target_landmark: str
    coords: Tuple[float, float]        # (lat, lon)
    threat_level: str                  # "CRITICAL", "HIGH", "ELEVATED"
    intruder_count: int
    is_armed: bool
    recommended_approach: str          # "CONCEALED_FLANKING_APPROACH", "RAPID_INTERCEPTION_LIGHTS"
    equipment_loadout: List[str]
    radio_script_en: str
    radio_script_hi: str
    timestamp_utc: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class QRTDispatchEngine:
    """Generates structured tactical mission cards for immediate QRT dispatch."""

    def __init__(self, post_name: str = "BOP Sector-IV Alpha", post_id: str = "SSB-BN-41-BOP-04"):
        self.post_name = post_name
        self.post_id = post_id

    def generate_mission_card(
        self,
        incident: Dict[str, Any],
        call_sign: str = "QRT-ALPHA",
        base_coords: Tuple[float, float] = (26.6852, 88.1425),
    ) -> QRTDispatchCard:
        """Transforms an IBVAP surveillance incident into an operational QRT dispatch brief."""
        now_dt = datetime.datetime.now(datetime.timezone.utc)
        ts_str = now_dt.strftime("%Y-%m-%d %H:%M:%S UTC")
        mission_id = f"QRT-MSN-{uuid.uuid4().hex[:6].upper()}"

        cat = str(incident.get("category") or "").lower()
        details = incident.get("details") or {}
        sev = str(incident.get("severity") or "High").upper()

        is_armed = ("weapon" in cat or "armed" in cat or details.get("is_armed") or details.get("weapon_class"))
        intruders = int(details.get("persons_detected") or details.get("intruders") or 1)

        cam_name = incident.get("cam_name") or f"Sector-{incident.get('cam_id', 1)}"
        landmark = details.get("zone") or incident.get("headline") or "Perimeter Fence Corridor"

        # Determine approach vector and equipment loadout
        if is_armed:
            approach = "CONCEALED_FLANKING_APPROACH"
            loadout = [
                "Service Rifles (INSAS / AK-47)",
                "Level-III+ Ballistic Body Armor & Helmets",
                "Tactical Ballistic Breaching Shield",
                "Thermal Monoculars / Night Vision Goggles",
                "Medical Trauma Hemostatic Kit",
            ]
        elif "crawling" in cat or "night" in cat:
            approach = "COORDINATED_CORDON_SEARCH"
            loadout = [
                "High-Intensity Searchlights",
                "Thermal Imaging Scopes",
                "Canine Patrol Unit",
                "Zip-Tie Tactical Restraints",
                "Lethal & Less-Lethal Ordnance",
            ]
        else:
            approach = "RAPID_INTERCEPTION_LIGHTS"
            loadout = [
                "Quick Reaction Vehicle (4x4)",
                "Portable Spike Belt Roadblock",
                "High-Decibel Siren & PA System",
                "Tactical Restraints & Body Armor",
            ]

        # Coordinates offset based on sector
        cam_id = int(incident.get("cam_id") or 1)
        lat = round(base_coords[0] + (cam_id * 0.0015), 5)
        lon = round(base_coords[1] + (cam_id * 0.0020), 5)

        # Radio scripts
        weapon_status_en = "SUSPECT CONFIRMED ARMED" if is_armed else "SUSPECT APPARENT UNARMED"
        weapon_status_hi = "संदिग्ध हथियारबंद है, सतर्क रहें" if is_armed else "संदिग्ध के पास हथियार की पुष्टि नहीं है"

        script_en = (
            f"ALL STATIONS, ALL STATIONS, THIS IS CONTROL. {call_sign} DISPATCH IMMEDIATELY TO {cam_name.upper()} "
            f"AT COORDINATES {lat}, {lon}. THREAT: {sev}, {intruders} TARGET(S). {weapon_status_en}. "
            f"APPROACH PROTOCOL: {approach}. ACKNOWLEDGE OVER."
        )

        script_hi = (
            f"सभी स्टेशन ध्यान दें, यह कंट्रोल है। {call_sign} तुरंत {cam_name} की ओर रवाना हों, "
            f"स्थान निर्देशांक {lat}, {lon}। खतरा स्तर: {sev}, {intruders} संदिग्ध। {weapon_status_hi}। "
            f"निर्देश: {approach} का पालन करें। रसीद दें, ओवर।"
        )

        return QRTDispatchCard(
            mission_id=mission_id,
            call_sign=call_sign,
            target_sector=cam_name,
            target_landmark=str(landmark),
            coords=(lat, lon),
            threat_level=sev,
            intruder_count=intruders,
            is_armed=bool(is_armed),
            recommended_approach=approach,
            equipment_loadout=loadout,
            radio_script_en=script_en,
            radio_script_hi=script_hi,
            timestamp_utc=ts_str,
        )
