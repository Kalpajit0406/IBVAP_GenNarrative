# Generative Incident Narrative (GenNarrative)

The **GenNarrative** module (`ibvap/narrative.py`) synthesizes low-level surveillance telemetry, multi-stream detections, posture heuristics, geofence breaches, weapon alerts, and ANPR results into actionable, human-readable natural language operational narratives.

---

## 1. Motivation

Surveillance operators and border commanders face alert fatigue when parsing dry telemetry strings:
```json
{"cam_id": 2, "category": "weapon", "score": 92.4, "details": {"armed": true, "posture": "AIM"}}
```

The Generative Narrative engine translates this into tactical intelligence:
> **[CRITICAL] ARMED THREAT in CAM-02 (Sector North)**  
> *At 2026-11-13T21:00:00Z, an armed subject was detected on CAM-02 actively holding a confirmed weapon in a tactical aiming stance (AIM posture). Threat severity is evaluated at Critical (Score: 92.4/100).*  
> **Recommended Action:** Immediate Red Alert: Dispatch Quick Reaction Team (QRT) to sector with armed escort. Alert adjacent BOPs.

---

## 2. API Endpoints

### Single Event Narrative
`GET /api/events/{event_id}/narrative`

Returns:
```json
{
  "ok": true,
  "event_id": "01HX98Z123456789ABCDEF001",
  "narrative": {
    "headline": "[CRITICAL] ARMED THREAT in CAM-01",
    "summary": "At 2026-11-13T21:00:00Z, an armed subject was detected on CAM-01...",
    "recommended_action": "Immediate Red Alert: Dispatch Quick Reaction Team (QRT)...",
    "tactical_priority": 1,
    "severity": "Critical",
    "category": "weapon",
    "cam_id": 1,
    "cam_name": "CAM-01",
    "timestamp_utc": "2026-11-13T21:00:00Z",
    "details": { "armed": true, "posture": "AIM" }
  }
}
```

### Shift Operational Handover Export
`GET /api/events/export?fmt=narrative` (or `fmt=markdown`)

Generates a complete Markdown shift briefing report compiling all incidents across cameras, with severity breakdowns, executive summary, and cryptographic audit hash notes.

### Command-Line Report Generator
Run directly from terminal without opening the desktop GUI:
```bash
python scripts/generate_narrative_report.py --sample
python scripts/generate_narrative_report.py --db data/events.db --hours 12 --out shift_report.md
```

---

## 3. Architecture & LLM/VLM Extension

* **Current Implementation:** Fast, deterministic template-synthesis engine optimized for edge compute (zero extra GPU/VRAM overhead).
* **Roadmap Extension:** Pluggable connector to local Vision-Language Models (e.g. SmolVLM, Qwen2-VL, or Ollama) running asynchronously to generate deep multi-frame visual reasoning.

