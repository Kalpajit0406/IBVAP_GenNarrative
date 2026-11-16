#!/usr/bin/env python3
"""
scripts/simulate_border_activity.py — Border activity and incident load simulator CLI.

Generates realistic tactical surveillance events for drills, operator training,
and Command and Control (C2) stress testing:
  * Scenario 'night_crawl'     : Low-illumination stealth crawling towards primary wire.
  * Scenario 'vehicle_drop'    : High-speed blacklisted vehicle drop-off on patrol road.
  * Scenario 'armed_breach'    : Unholstered assault weapon identified near border pillar.
  * Scenario 'tamper_attack'   : Camera lens occlusion / frozen feed attack during ingress.
  * Scenario 'multi_sector'    : Coordinated multi-camera diversionary breach.

Usage:
    python scripts/simulate_border_activity.py --scenario night_crawl --dry-run
    python scripts/simulate_border_activity.py --scenario armed_breach --count 4 --output-json events.json
"""
from __future__ import annotations

import argparse
import datetime
import json
import random
import sys
import time
import uuid
from pathlib import Path

# Add app root to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ibvap.narrative import generate_event_narrative

SCENARIOS = {
    "night_crawl": {
        "headline": "Stealth prone crawling towards zero-line fence",
        "cam_id": 3,
        "cam_name": "Sector-3 Riverine Zero-Line",
        "category": "crawling_prone",
        "severity": "Critical",
        "tactical_priority": 1,
        "base_risk": 0.92,
        "details": {
            "posture": "crawling",
            "zone": "primary_wire",
            "illumination_lux": 1.4,
            "weather_visibility": "dense_fog",
            "approach_vector_deg": 12.0,
            "speed_mps": 0.4,
        },
        "action": "Dispatch Quick Reaction Team (QRT) Alpha to Pillar 41/2; illuminate sector with searchlights.",
    },
    "vehicle_drop": {
        "headline": "Blacklisted vehicle stopped on zero-line patrol road; passengers disembarking",
        "cam_id": 1,
        "cam_name": "Sector-1 Checkpost North",
        "category": "anpr_alert",
        "severity": "High",
        "tactical_priority": 2,
        "base_risk": 0.84,
        "details": {
            "plate": "WB-74-E-9012",
            "vehicle_type": "SUV / 4WD",
            "watchlist_match": "SUSPECT_SMUGGLING_SYNDICATE",
            "zone": "patrol_road",
            "persons_detected": 3,
        },
        "action": "Deploy road spike barrier at Checkpoint 1; alert sector foot patrols.",
    },
    "armed_breach": {
        "headline": "Unholstered assault rifle identified with ready-aim stance",
        "cam_id": 2,
        "cam_name": "Sector-2 Main Perimeter Fence",
        "category": "weapon_ready",
        "severity": "Critical",
        "tactical_priority": 1,
        "base_risk": 0.98,
        "details": {
            "weapon_class": "assault_rifle",
            "confidence": 0.94,
            "posture": "aim_standing",
            "zone": "buffer_corridor",
            "trajectory_speed": 1.8,
        },
        "action": "Immediate tactical post alarm; dispatch armed QRT team with ballistic shields.",
    },
    "tamper_attack": {
        "headline": "Sudden lens occlusion and optical blackout detected",
        "cam_id": 4,
        "cam_name": "Sector-4 High Tower PTZ",
        "category": "camera_tamper",
        "severity": "High",
        "tactical_priority": 2,
        "base_risk": 0.79,
        "details": {
            "tamper_type": "optical_spray_occlusion",
            "confidence": 0.96,
            "edge_loss_pct": 88.5,
            "adjacent_cam": "CAM-03",
        },
        "action": "Slew adjacent PTZ CAM-03 to Sector-4; dispatch sentry to verify optical mast integrity.",
    },
    "multi_sector": {
        "headline": "Coordinated multi-camera perimeter diversion",
        "cam_id": 1,
        "cam_name": "Sector-1 Flank",
        "category": "geofence_breach",
        "severity": "Critical",
        "tactical_priority": 1,
        "base_risk": 0.95,
        "details": {
            "correlated_cameras": [1, 3],
            "zone": "primary_wire",
            "tactical_assessment": "Diversionary breach detected across simultaneous flanks",
        },
        "action": "Initiate full post defensive lockdown; dispatch secondary reserve unit.",
    },
}


def build_event(scenario_key: str, index: int = 1, lang: str = "en") -> dict:
    scen = SCENARIOS.get(scenario_key, SCENARIOS["night_crawl"])
    now_utc = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=index * 15)
    ts_str = now_utc.strftime("%Y-%m-%d %H:%M:%S UTC")
    event_id = f"SIM-{scenario_key.upper()[:4]}-{uuid.uuid4().hex[:6]}"

    event = {
        "event_id": event_id,
        "timestamp_utc": ts_str,
        "timestamp": now_utc.timestamp(),
        "site_id": "SSB-PANITANKI-01",
        "post_name": "BOP Sector-IV Alpha",
        "cam_id": scen["cam_id"],
        "cam_name": scen["cam_name"],
        "severity": scen["severity"],
        "tactical_priority": scen["tactical_priority"],
        "category": scen["category"],
        "score": scen["base_risk"],
        "summary": scen["headline"],
        "recommended_action": scen["action"],
        "details": scen["details"],
    }

    # Generate explainable natural language narrative
    narrative_doc = generate_event_narrative(event, lang=lang)
    event["narrative"] = narrative_doc.get("summary") or scen["headline"]
    return event


def main():
    parser = argparse.ArgumentParser(description="Simulate tactical border activity and incident load.")
    parser.add_argument("--scenario", choices=list(SCENARIOS.keys()), default="night_crawl",
                        help="Tactical scenario to simulate")
    parser.add_argument("--count", type=int, default=3, help="Number of sequential incident pulses to generate")
    parser.add_argument("--lang", choices=["en", "hi"], default="en", help="Narrative language (English/Hindi)")
    parser.add_argument("--dry-run", action="store_true", help="Print simulated incidents to console")
    parser.add_argument("--output-json", type=str, default="", help="Save generated events array to JSON file")
    args = parser.parse_args()

    events = [build_event(args.scenario, i + 1, lang=args.lang) for i in range(args.count)]

    if args.dry_run or not args.output_json:
        print(f"\n=======================================================")
        print(f"  IBVAP BORDER INCIDENT DRILL SIMULATOR — [{args.scenario.upper()}]")
        print(f"  Generated {len(events)} synthetic tactical events")
        print(f"=======================================================\n")
        for ev in events:
            print(f"[{ev['timestamp_utc']}] {ev['event_id']} — {ev['cam_name']} ({ev['severity']})")
            print(f"  Category : {ev['category']}")
            print(f"  Narrative: {ev['narrative']}")
            print(f"  Action   : {ev['recommended_action']}\n")

    if args.output_json:
        out_path = Path(args.output_json)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(events, indent=2), encoding="utf-8")
        print(f"[+] Successfully exported {len(events)} events to {out_path}")


if __name__ == "__main__":
    main()
