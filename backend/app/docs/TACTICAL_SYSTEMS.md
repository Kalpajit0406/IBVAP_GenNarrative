# IBVAP Tactical Subsystems & Counter-Intrusion Manual

This manual details the specialized counter-intrusion, acoustic, aerial drone defense, and force protection subsystems integrated into the **AI-Based Intelligent Video Analytics Platform (IBVAP)** for **Sashastra Seema Bal (SSB)** border surveillance.

---

## 1. Acoustic Sensor Array & Transient Gunshot Classifier (`ibvap/acoustic.py`)

In border sectors with dense vegetation, heavy fog, or zero-illumination nights, acoustic sensor arrays augment optical cameras by providing instant omnidirectional transient detection.

### 1.1 Acoustic Classification Decision Parameters
| Event Type | SPL Threshold | Rise Time | Decay Time | Spectral Centroid | Priority | Action |
|---|---|---|---|---|---|---|
| `gunshot` | >85 dB | <12 ms | <300 ms | 1,000–3,500 Hz | **1 (Critical)** | Armed cover & QRT dispatch |
| `explosion` | >92 dB | <15 ms | >350 ms | <700 Hz (Low rumble) | **1 (Critical)** | Post defensive lockdown |
| `drone_rotor` | >48 dB | >80 ms | Sustained | 200–900 Hz (Narrow harmonic) | **2 (High)** | Slew RF jammer to bearing |
| `wire_cut` | >55 dB | <25 ms | <100 ms | >3,500 Hz (Metallic snap) | **2 (High)** | Inspect perimeter fence |
| `engine_rev` | >60 dB | >100 ms | Sustained | <600 Hz | **3 (Elevated)**| Log vehicle transit |

### 1.2 Cross-Modal Direction of Arrival (DoA) Correlation
The acoustic classifier determines the compass bearing (0–360°) and automatically correlates the sound to the camera sector whose field of view covers that bearing (e.g., DoA 45° -> Sector-1 North-East CAM-01), enabling immediate optical verification.

---

## 2. Low-Altitude Rogue UAV & Payload Drop Tracker (`ibvap/drone_detector.py`)

Cross-border smuggling syndicates frequently deploy commercial multirotors to drop arms, narcotics, and ammunition across international zero-lines.

```
      [Rogue Drone: y < 0.35]
                 │
                 │ Hovering / Reconnaissance
                 ▼
          [Contraband Drop]  <─── High vertical velocity (dy/dt > 0.12)
                 │
                 ▼
      [Ground Target: y > 0.70] ───> Drop Coordinates (lat, lon) -> QRT Recovery
```

### 2.1 Aerial Kinetic Alert States
- **`UAV_INCURSION`**: High-speed aerial target (>0.08 units/sec) traversing upper frame sectors (`y < 0.65`).
- **`UAV_HOVERING`**: Airborne target stationary for >1.5 seconds, indicative of drop-zone alignment.
- **`PAYLOAD_DROP_DETECTED`**: Sudden vertical descent / decoupling of payload from sky to ground level. Immediately calculates ground drop coordinates for QRT seizure.

---

## 3. Sentry Duress, Man-Down, & Post Abandonment (`ibvap/sentry_duress.py`)

Protects lone sentries in watchtowers, morchas, and border gates from surprise attacks, sniper fire, or hostage situations.

### 3.1 Protection Modes
1. **Man-Down (`MAN_DOWN`)**: Sentry detected in prone/lying down posture with immobility exceeding 15 seconds. Generates Critical Priority 1 alarm for medical assistance.
2. **Duress / Surrender (`DURESS_HANDS_UP`)**: Sentry standing with both hands raised above shoulder/head height under armed threat. Generates instant Critical Priority 1 alarm.
3. **Post Abandonment (`POST_ABANDONED`)**: Sentry post polygon is vacant for >30 seconds during an armed shift, indicating unauthorized desertion or stealth abduction.

---

## 4. LWIR Thermal Radiometry & Concealed Engine Profiling (`ibvap/thermal_hotspot.py`)

Detects thermal emission from targets hidden from optical cameras by camouflage nets, foliage, or night shadows:
- **Vehicle Engine Exhaust Manifold**: Radiometric delta >30°C above ambient background.
- **Concealed Human Core**: Biological thermal signature (35–37°C, delta 12–25°C above ambient) detected within marked foliage or riverine reed masks (`is_concealed=True`).
- **Warm Smuggling Equipment**: Battery packs, communication repeaters, or fresh engine heat.

---

## 5. Multi-Sensor Slew-to-Cue PTZ Auto-Director (`ibvap/ptz_director.py`)

Fixed wide-angle and thermal cameras continuously compute steering vectors for tower-mounted 30x optical PTZ cameras:
- **Azimuth Pan & Tilt Elevation**:
  $$\text{Pan} = \theta_{\text{mount}} + (x - 0.5) \cdot \text{HFOV}$$
  $$\text{Tilt} = \phi_{\text{mount}} - (y - 0.5) \cdot \text{VFOV}$$
- **Adaptive Optical Magnification**: Automatically adjusts zoom (1.0x to 30.0x) inversely proportional to target bounding height to ensure facial and weapon recognition.
- **Priority Lock Arbitration**: Priority 1 targets (weapons, breaches) preemptively override existing camera locks on lower-priority targets.

---

## 6. Tactical QRT Interception Mission Cards (`ibvap/qrt_dispatch.py`)

Automates Quick Reaction Team (QRT) briefings to eliminate verbal confusion during alarms:
- **Approach Strategy**: Assigns `CONCEALED_FLANKING_APPROACH` for confirmed armed threats versus `RAPID_INTERCEPTION_LIGHTS` for vehicles.
- **Equipment Loadout**: Generates required tactical gear list (INSAS/AK-47, Level-III ballistic shields, NVG, trauma kits).
- **Dual-Language Radio Dispatch Scripts**: Formats clear, standardized phonetics in English and Hindi for direct broadcast over tactical VHF/UHF channels.

---

## 7. Spatial Infiltration Heatmap & Density Grid (`ibvap/heatmap.py`)

Aggregates historical breaches, weapon alerts, and loitering into a 2D spatial grid along border sectors:
- Applies Gaussian kernel smoothing to evaluate vulnerability corridors.
- Identifies weak crossing segments for patrol route repositioning.
- Generates ASCII matrices for command terminals and RFC 7946 GeoJSON FeatureCollections for C2 mapping.

---

## 8. Tactical REST API Reference

| Endpoint | Method | Payload / Params | Description |
|---|---|---|---|
| `/api/acoustic/event` | `POST` | `{peak_amplitude, rise_time_ms, spl_db, bearing_deg}` | Classify gunshot / blast acoustic transients |
| `/api/drone/update` | `POST` | `{track_id, bbox: [x1,y1,x2,y2], timestamp}` | Evaluate rogue UAV kinematics & payload drops |
| `/api/sentry/update` | `POST` | `{post_id, persons: [{posture}], timestamp}` | Evaluate sentry man-down & duress postures |
| `/api/ptz/slew` | `POST` | `{source_cam_id, point: [x,y], bbox_height}` | Compute slew-to-cue Pan-Tilt-Zoom command |
| `/api/qrt/dispatch` | `POST` | `{cam_id, category, severity, details}` | Generate QRT mission card & radio scripts |
| `/api/zones/matrix` | `GET` | — | Retrieve tactical border zone definitions |
| `/api/spooler/stats` | `GET` | — | Query offline alert spooler & circuit breaker |
| `/api/events/export/html`| `GET` | `?since=...&until=...` | Download A4 printable shift handover dossier |
