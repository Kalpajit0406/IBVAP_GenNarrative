"""
ibvap/narrative.py — Explainable AI Generative Incident Narrative Engine.

Transforms raw surveillance telemetry, multi-stream bounding detections,
postures, geofence breaches, weapon confirmations, and ANPR events into
actionable, human-readable natural language operational narratives for
border commanders and shift handovers.
"""
from __future__ import annotations

import datetime
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional


@dataclass
class NarrativeReport:
    """Structured operational narrative for a single surveillance event."""
    event_id: str
    headline: str
    summary: str
    recommended_action: str
    tactical_priority: int       # 1 (Highest/Immediate) to 5 (Informational)
    severity: str
    category: str
    cam_id: int
    cam_name: str
    timestamp_utc: str
    details: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _format_cam_label(cam_id: int, cam_name: Optional[str] = None) -> str:
    cam_str = f"CAM-{cam_id:02d}"
    if cam_name and cam_name.strip() and cam_name.strip() != cam_str:
        return f"{cam_name.strip()} ({cam_str})"
    return cam_str


def generate_event_narrative(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate an explainable, human-readable natural language narrative
    from a single stored or live event record.
    """
    event_id = str(event.get("event_id") or "UNKNOWN")
    cam_id = int(event.get("cam_id") or 0)
    cam_name = event.get("cam_name")
    cam_label = _format_cam_label(cam_id, cam_name)

    severity = str(event.get("severity") or event.get("level") or "Info").capitalize()
    category = str(event.get("category") or "risk").lower()
    score = float(event.get("score") or 0.0)
    persons = int(event.get("persons") or 0)
    vehicles = int(event.get("vehicles") or 0)
    ts_utc = str(event.get("ts_utc") or datetime.datetime.now(datetime.timezone.utc).isoformat())

    details = event.get("details") or {}
    if isinstance(details, str):
        import json
        try:
            details = json.loads(details)
        except Exception:
            details = {}

    # Category & detail extraction
    is_armed = bool(details.get("armed"))
    has_weapon = bool(details.get("weapon")) or category == "weapon"
    posture = str(details.get("posture") or "").upper()
    is_breach = bool(details.get("breach")) or category in ("intrusion", "crossing")
    fence_name = details.get("fence_name") or details.get("fence") or "Restricted Border Perimeter"
    face_match = bool(details.get("criminal_match")) or category == "face_match"
    identity = details.get("criminal_name") or details.get("identity")
    plate = details.get("plate")
    v_type = details.get("vehicle_type") or "vehicle"
    loiter_dur = details.get("duration")

    # Generate Narrative based on primary threat drivers
    if is_armed or (has_weapon and posture == "AIM"):
        headline = f"[CRITICAL] ARMED THREAT in {cam_label}"
        summary = (
            f"At {ts_utc}, an armed subject was detected on {cam_label} actively holding a confirmed weapon "
            f"in a tactical aiming stance (AIM posture). Threat severity is evaluated at Critical (Score: {score:.1f}/100)."
        )
        action = "Immediate Red Alert: Dispatch Quick Reaction Team (QRT) to sector with armed escort. Alert adjacent BOPs."
        priority = 1

    elif has_weapon:
        headline = f"[CRITICAL] Weapon Confirmed on {cam_label}"
        summary = (
            f"Surveillance neural network confirmed a firearm/weapon carried by a tracked individual on {cam_label}. "
            f"Present in frame: {persons} person(s). Threat score: {score:.1f}/100."
        )
        action = "Deploy sector patrol to intercept and establish visual perimeter. Vector long-range PTZ cameras."
        priority = 1

    elif face_match and identity:
        headline = f"[HIGH] Watchlist Match on {cam_label}: {identity}"
        summary = (
            f"Facial biometrics engine flagged a positive match for enrolled watchlist individual '{identity}' on {cam_label} "
            f"following multi-frame burst feature verification. Timestamp: {ts_utc}."
        )
        action = "Cross-verify identity against Central Crime & Criminal Tracking (CrPI/CCTNS) database; initiate covert surveillance."
        priority = 2

    elif is_breach:
        fence_desc = f"virtual boundary '{fence_name}'"
        headline = f"[{severity.upper()}] Perimeter Intrusion on {cam_label}"
        summary = (
            f"An intrusion breach was triggered across {fence_desc} on {cam_label}. "
            f"Tracked targets currently in restricted zone: {persons} person(s), {vehicles} vehicle(s). Overall score: {score:.1f}."
        )
        action = "Notify border fence response patrol to investigate point of breach and check physical fence integrity."
        priority = 1 if severity == "Critical" else 2

    elif category == "plate" or plate:
        plate_str = str(plate).strip().upper() if plate else "UNREADABLE"
        headline = f"[INFO] Vehicle Ingress on {cam_label}: [{plate_str}]"
        summary = (
            f"Automated License Plate Recognition (ANPR) registered a {v_type} with license plate [{plate_str}] "
            f"at {cam_label} (UTC: {ts_utc})."
        )
        action = "Verify registration against regional VAHAN stolen/suspicious vehicle registry."
        priority = 4 if severity in ("Info", "Low") else 3

    elif category == "loiter" or (loiter_dur and float(loiter_dur or 0) > 0):
        dur_str = f"{float(loiter_dur):.0f}s" if loiter_dur else "extended time"
        headline = f"[ALERT] Loitering Detected on {cam_label}"
        summary = (
            f"Target has remained stationary or paced inside restricted surveillance zone on {cam_label} for {dur_str}, "
            f"exceeding normal transit thresholds."
        )
        action = "Issue verbal warning over remote PA system or direct guard to challenge individual."
        priority = 3

    elif category == "running":
        headline = f"[ALERT] High-Velocity Transit on {cam_label}"
        summary = (
            f"Rapid sprinting/running movement observed on {cam_label} ({persons} individual(s)), "
            f"deviating from standard pedestrian baseline."
        )
        action = "Track direction of flight and monitor egress gates."
        priority = 3

    elif category == "group" or (persons >= 3 and score >= 40):
        headline = f"[ALERT] Group Congregation on {cam_label}"
        summary = (
            f"A cluster of {persons} individuals gathered in surveillance sector {cam_label} with an aggregate risk score of {score:.1f}."
        )
        action = "Monitor group for unlawful assembly or coordinated contraband transfer."
        priority = 3

    elif posture in ("LYING", "CROUCH"):
        headline = f"[CAUTION] Concealment Posture on {cam_label}"
        summary = (
            f"A tracked person on {cam_label} assumed a {posture.lower()} stance near the ground, "
            f"consistent with concealment or crawl maneuvers."
        )
        action = "Inspect terrain camera feed for hidden approaches or perimeter wire cutting."
        priority = 3

    else:
        headline = f"[{severity.upper()}] Anomaly Recorded on {cam_label}"
        summary = (
            f"Elevated risk score ({score:.1f}/100) detected on {cam_label} at {ts_utc}. "
            f"Detected counts: {persons} person(s), {vehicles} vehicle(s)."
        )
        action = "Routine operator review in command dashboard."
        priority = 4 if severity in ("Info", "Low") else 3

    report = NarrativeReport(
        event_id=event_id,
        headline=headline,
        summary=summary,
        recommended_action=action,
        tactical_priority=priority,
        severity=severity,
        category=category,
        cam_id=cam_id,
        cam_name=cam_name or f"CAM-{cam_id:02d}",
        timestamp_utc=ts_utc,
        details=details,
    )
    return report.to_dict()


def generate_shift_narrative(events: List[Dict[str, Any]], site_name: str = "BOP Sector Alpha") -> str:
    """
    Synthesize an entire shift or query batch of events into an executive
    operational Markdown narrative report for command handovers.
    """
    total = len(events)
    if total == 0:
        return (
            f"# 📋 IBVAP Shift Incident & Operational Report\n\n"
            f"**Site:** {site_name}  \n"
            f"**Report Generated:** {datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}  \n\n"
            f"### Executive Summary\n"
            f"Zero security anomalies or border intrusions were recorded during this observation window. "
            f"All sectors report nominal status.\n"
        )

    # Calculate statistics
    severities: Dict[str, int] = {}
    categories: Dict[str, int] = {}
    cams: set[int] = set()

    narratives = [generate_event_narrative(ev) for ev in events]

    for n in narratives:
        sev = n["severity"]
        cat = n["category"]
        cams.add(n["cam_id"])
        severities[sev] = severities.get(sev, 0) + 1
        categories[cat] = categories.get(cat, 0) + 1

    crit_count = severities.get("Critical", 0)
    high_count = severities.get("High", 0)
    med_count = severities.get("Medium", 0)

    gen_time = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')

    lines = [
        f"# 📋 IBVAP Shift Incident & Operational Report",
        f"",
        f"**Surveillance Command Post:** {site_name}  ",
        f"**Report Generated:** {gen_time}  ",
        f"**Total Events Analyzed:** {total} across {len(cams)} camera feed(s)  ",
        f"",
        f"---",
        f"",
        f"## 1. Executive Summary",
        f"",
        f"During this surveillance period, the IBVAP platform logged **{total}** events. "
        f"Security posture breakdown: **{crit_count} Critical**, **{high_count} High**, **{med_count} Medium**, "
        f"and **{total - crit_count - high_count - med_count} Low/Info** detections.",
    ]

    if crit_count > 0:
        lines.append(
            f"\n> ⚠️ **CRITICAL ALERTS DETECTED:** {crit_count} incident(s) required immediate tactical intervention. "
            f"Command attention is urgently required for verified breaches or armed presences."
        )
    else:
        lines.append(
            f"\n> ✅ **PERIMETER SECURE:** No Critical breaches or armed hostile threats occurred during this window."
        )

    lines.extend([
        f"",
        f"## 2. Key Tactical Incident Timeline",
        f"",
        f"| Time (UTC) | Level | Camera | Incident Summary | Recommended Action |",
        f"|---|---|---|---|---|",
    ])

    # Show top incidents (prioritize priority 1 and 2, up to 25 items)
    sorted_narratives = sorted(narratives, key=lambda x: (x["tactical_priority"], x["event_id"]))
    display_items = sorted_narratives[:25]

    for item in display_items:
        ts_short = item["timestamp_utc"].split("T")[-1][:8] if "T" in item["timestamp_utc"] else item["timestamp_utc"]
        lines.append(
            f"| `{ts_short}` | **{item['severity']}** | {item['cam_name']} | {item['summary']} | {item['recommended_action']} |"
        )

    if len(narratives) > 25:
        lines.append(f"\n*(Showing 25 highest-priority incidents out of {len(narratives)} total logged)*")

    lines.extend([
        f"",
        f"## 3. Cryptographic Audit & Verification",
        f"",
        f"- All logged incidents above are anchored to the local SHA-256 tamper-evident hash chain (`data/hash_chain.jsonl`).",
        f"- Shift officers can verify chain cryptographic integrity via `python main.py --verify-chain`.",
        f"",
        f"---",
        f"*Report automatically compiled by IBVAP Generative Narrative Engine.*",
    ])

    return "\n".join(lines)
