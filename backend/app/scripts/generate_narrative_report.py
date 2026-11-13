"""
scripts/generate_narrative_report.py — Command-line Incident Narrative Report Generator.

Allows border operators, post commanders, and auditors to query local incident records
from events.db (or simulate synthetic incidents) and compile an executive narrative report
directly in terminal or as a Markdown file without requiring the desktop GUI console.

Usage:
    python scripts/generate_narrative_report.py --sample
    python scripts/generate_narrative_report.py --db data/events.db --hours 12 --out report.md
    python scripts/generate_narrative_report.py --db data/events.db --severity Critical
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# Add backend/app to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ibvap.event_store import EventStore
from ibvap.narrative import generate_event_narrative, generate_shift_narrative


def sample_events() -> list[dict]:
    """Synthetic events for offline demonstration and testing."""
    now_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    return [
        {
            "event_id": "01HXDEMO000000000000000001",
            "ts_utc": now_utc,
            "cam_id": 1,
            "cam_name": "Sector North Fence",
            "post_name": "BOP Sector Alpha",
            "severity": "Critical",
            "category": "weapon",
            "score": 98.5,
            "persons": 1,
            "vehicles": 0,
            "details": {"armed": True, "weapon": True, "posture": "AIM"},
            "ev_hash": "a1b2c3d4e5f67890123456789abcdef0",
        },
        {
            "event_id": "01HXDEMO000000000000000002",
            "ts_utc": now_utc,
            "cam_id": 2,
            "cam_name": "Checkpost South Gate",
            "post_name": "BOP Sector Alpha",
            "severity": "High",
            "category": "intrusion",
            "score": 82.0,
            "persons": 2,
            "vehicles": 0,
            "details": {"breach": True, "fence_name": "Perimeter Exclusion Wire"},
            "ev_hash": "b2c3d4e5f6a17890123456789abcdef0",
        },
        {
            "event_id": "01HXDEMO000000000000000003",
            "ts_utc": now_utc,
            "cam_id": 0,
            "cam_name": "Main Approach Road",
            "post_name": "BOP Sector Alpha",
            "severity": "Info",
            "category": "plate",
            "score": 12.0,
            "persons": 0,
            "vehicles": 1,
            "details": {"plate": "DL-01-AX-9922", "vehicle_type": "light commercial truck"},
            "ev_hash": "c3d4e5f6a1b27890123456789abcdef0",
        },
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description="IBVAP Operational Incident Narrative Generator")
    parser.add_argument("--db", default="data/events.db", help="Path to SQLite events.db")
    parser.add_argument("--post", default="BOP Sector Alpha", help="Site / BOP post display name")
    parser.add_argument("--hours", type=float, default=24.0, help="Analyze events from last N hours")
    parser.add_argument("--severity", help="Filter by minimum severity (Info, Low, Medium, High, Critical)")
    parser.add_argument("--cam", type=int, help="Filter by specific camera ID")
    parser.add_argument("--sample", action="store_true", help="Generate report from demonstration samples")
    parser.add_argument("--out", help="Write report to markdown file path instead of stdout")
    args = parser.parse_args()

    if args.sample:
        events = sample_events()
    else:
        db_path = Path(args.db)
        if not db_path.is_file():
            print(f"Database file not found: {args.db}")
            print("Tip: Run with --sample to generate a demonstration report.")
            sys.exit(1)
        store = EventStore(str(db_path))
        since_ts = time.time() - (args.hours * 3600.0)
        events = store.query(
            limit=2000,
            cam_id=args.cam,
            since=since_ts,
            severity=args.severity,
            include_unconfirmed=True,
        )

    report_md = generate_shift_narrative(events, site_name=args.post)

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(report_md, encoding="utf-8")
        print(f"Operational narrative report written to {out_path.resolve()}")
    else:
        print(report_md)


if __name__ == "__main__":
    main()
