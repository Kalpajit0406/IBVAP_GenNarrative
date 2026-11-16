# IBVAP Border Operations Runbook & Tactical Incident Guide

This runbook outlines standard operating procedures (SOP), field deployment configuration, resilient offline operations, and incident escalation protocols for **Sashastra Seema Bal (SSB)** and border outpost duty officers utilizing the **AI-Based Intelligent Video Analytics Platform (IBVAP)**.

---

## 1. System Topology & Outpost Hardware Architecture

At each Border Outpost (BOP) or Tactical Operation Center (TOC):
```
                      ┌──────────────────────────────────────────────┐
                      │              SSB Border Outpost              │
                      │                                              │
                      │  [CAM-01 Zero-Line]   [CAM-02 Depth Fence]   │
                      │  [CAM-03 Riverine]    [CAM-04 Tower PTZ]     │
                      └──────────────────────┬───────────────────────┘
                                             │ RTSP / ONVIF / WebRTC
                                             ▼
                      ┌──────────────────────────────────────────────┐
                      │             IBVAP Edge Server Node           │
                      │  * YOLOv8 / Pose Estimation / Weapon Fused   │
                      │  * ByteTrack Kinematic Trajectory Analyzer   │
                      │  * Tactical Zone Escalation Engine           │
                      │  * Substream Bandwidth Auto-Negotiator       │
                      │  * SQLite WAL Store & Merkle Hash Chain      │
                      └──────────────────────┬───────────────────────┘
                                             │
                       ┌─────────────────────┴─────────────────────┐
                       │ Local Egress & Spooler                    │
                       ▼                                           ▼
      ┌──────────────────────────────────┐        ┌──────────────────────────────────┐
      │ Primary High-Speed Uplink        │        │ Resilient Offline Spooler        │
      │ (Fiber / Microwave / 5G)         │        │ (SQLite WAL + Circuit Breaker)   │
      │ -> Battalion / Sector HQ C2      │        │ * Zero loss during VSAT blackout │
      └──────────────────────────────────┘        └──────────────────────────────────┘
```

---

## 2. Tactical Zone Escalation Matrix Configuration

The tactical zone escalation matrix (`ibvap/zones.py`) maps camera visual coordinates to physical terrain sensitivity levels.

### 2.1 Zone Classifications & Threat Multipliers
| Zone Type | Terrain Meaning | Threat Multiplier | Default Action | Escaped Level |
|---|---|---|---|---|
| `primary_wire` | International zero-line boundary fence | **2.5x** | `DEPLOY_QRT` | CRITICAL |
| `bop_perimeter` | Base compound perimeter & ammo depot | **3.0x** | `LOCKDOWN_ALARM` | CRITICAL |
| `riverine_flank` | Unfenced nullahs, culverts, watercourses | **2.0x** | `ILLUMINATE_SECTOR` | HIGH |
| `buffer_corridor` | Depth strip between primary and secondary wire | **1.8x** | `SECTOR_SEARCH` | HIGH |
| `patrol_road` | Designated security force vehicular track | **1.3x** | `TRACK_MOVEMENT` | ELEVATED |
| `neutral_zone` | Demarcated bilateral treaty strip | **1.0x** | `LOG_TRANSIT` | NOMINAL |

### 2.2 Time-of-Day Arming Schedules
Zones can be scheduled for automatic night-only activation (e.g. riverine ambush points):
```python
TacticalZone(
    zone_id="zone_nullah_04",
    name="Nullah Ambush Corridor",
    zone_type="riverine_flank",
    polygon=[(0.1, 0.4), (0.4, 0.4), (0.4, 0.8), (0.1, 0.8)],
    schedule_start_hour=19,  # 19:00 IST
    schedule_end_hour=6,     # 06:00 IST
)
```
During off-hours (06:01–18:59), the zone is disarmed to prevent false alarms from legitimate daytime maintenance patrols.

---

## 3. Kinematic Trajectory & Perimeter Approach Vectors

The `TrajectoryAnalyzer` (`ibvap/trajectory.py`) evaluates target tracks to determine kinetic intent:
- **`SPRINT_TO_BOUNDARY`**: Target speed > 0.08 units/sec with direct vector toward perimeter fence. Automatically computes **Time-To-Boundary (TTB)** countdown for QRT interception.
- **`PARALLEL_PROBING`**: Target moving laterally along the fence line (>60° offset from fence normal), characteristic of reconnaissance or weakness searching.
- **`ZIGZAG_EVASION`**: Target exhibiting sharp directional heading variance (>2 alternating sign changes), indicating evasive crawling or dodging thermal spotlights.
- **`RECEDING`**: Target heading away from the border perimeter into depth territory.

---

## 4. Bandwidth Auto-Negotiation & Tactical Burst

Under adverse network weather or GPU inference stress, `SubstreamNegotiator` (`ibvap/stream_negotiator.py`) regulates ingestion:
- **`nominal`**: 720p @ 15 FPS, JPEG quality 75 (1,800 kbps) — standard 24/7 monitoring.
- **`eco`**: 360p @ 10 FPS, JPEG quality 55 (500 kbps) — engaged during satellite backhaul saturation.
- **`hd`**: 1080p @ 25 FPS, JPEG quality 85 (4,500 kbps) — engaged when compute pipeline is idle.
- **`tactical_burst`**: 1080p @ 30 FPS, JPEG quality 95 (8,000 kbps) — **automatically triggered** on weapon detection or fence breach for 15 seconds to ensure forensic-grade evidential capture.

---

## 5. Resilient Offline Spooler & Circuit Breaker

During adverse border conditions (VSAT dish ice build-up, fiber cut, or electromagnetic jamming), outbound network forwarders trip their **Circuit Breaker** (`ibvap/spooler.py`):
1. **Tripped to `OPEN`**: Halts connection hammering to prevent socket leaks and thread starvation.
2. **Prioritized In-Disk Spooling**: New alerts are queued in SQLite WAL (`data/spool.db`). Priority 1 (Critical threats) precede Priority 3 (Info) records.
3. **Probe Recovery (`HALF_OPEN`)**: Once recovery timeout elapses, trial alerts probe link health. Upon confirmation, the spooler automatically flushes backlogged alerts to Battalion C2 without dropping a single event.

---

## 6. Shift Handover & A4 HTML Dossiers

Duty officers generate verifiable, print-ready handover documents at shift transition:
- **Web UI & Direct API**: `GET /api/events/export/html` or `GET /api/events/export?fmt=html`
- **Output features**:
  - Outgoing and incoming officer verification lines.
  - KPI cards: Total incidents, Critical P1 alarms, fence breaches, weapons detected.
  - Full natural language chronological event narrative.
  - SHA-256 Merkle root digital evidence stamp for legal admissibility.
  - Print-optimized CSS (`@media print`) formatted for standard A4 paper.

---

## 7. Operator Training & Drill Simulation CLI

Run mock intrusion scenarios using `scripts/simulate_border_activity.py`:

```bash
# Simulate stealth night crawling intrusion in Sector 3
python scripts/simulate_border_activity.py --scenario night_crawl --dry-run

# Simulate unholstered weapon detection drill
python scripts/simulate_border_activity.py --scenario armed_breach --count 3 --output-json data/drill_armed.json

# Simulate optical camera tamper / spray occlusion attack
python scripts/simulate_border_activity.py --scenario tamper_attack --dry-run

# Multi-sector coordinated diversion drill
python scripts/simulate_border_activity.py --scenario multi_sector --count 2 --dry-run
```
