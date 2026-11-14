# Generative Incident Narrative (GenNarrative)

The **GenNarrative** subsystem synthesizes low-level surveillance telemetry, multi-stream detections, posture heuristics, geofence breaches, weapon alerts, and ANPR results into actionable, human-readable natural language operational narratives and tactical voice dispatches.

---

## 1. Motivation

Surveillance operators and border commanders face alert fatigue when parsing raw telemetry strings:
```json
{"cam_id": 2, "category": "weapon", "score": 92.4, "details": {"armed": true, "posture": "AIM"}}
```

The Generative Narrative engine translates this into actionable tactical intelligence:
> **[CRITICAL] ARMED THREAT in CAM-02 (Sector North)**  
> *At 2026-11-13T21:00:00Z, an armed subject was detected on CAM-02 actively holding a confirmed weapon in a tactical aiming stance (AIM posture). Threat severity is evaluated at Critical (Score: 92.4/100).*  
> **Recommended Action:** Immediate Red Alert: Dispatch Quick Reaction Team (QRT) to sector with armed escort. Alert adjacent BOPs.

---

## 2. Key Capabilities

### A. Dual Language Localization (English & Hindi)
Border Out Posts (BOPs) along frontier regions operate in Hindi and regional languages. The narrative engine supports `lang="en"` (default) and `lang="hi"`:
> **[गंभीर / CRITICAL] सशस्त्र खतरा: CAM-02**  
> *2026-11-13T21:00:00Z पर, CAM-02 पर एक सशस्त्र व्यक्ति हथियार के साथ आक्रामक मुद्रा (AIM) में देखा गया। खतरा स्तर: गंभीर (स्कोर: 92.4/100)।*  
> **अनुशंसित कार्रवाई:** तत्काल रेड अलर्ट: त्वरित प्रतिक्रिया दल (QRT) को सशस्त्र सुरक्षा के साथ सेक्टर में तैनात करें। निकटवर्ती बीओपी को सतर्क करें।

### B. Multi-Camera Sequence Correlation (`ibvap/correlation.py`)
Correlates events across overlapping/adjacent cameras within a rolling operational window (e.g., vehicle arrival on CAM-00 ➔ boundary breach on CAM-01 ➔ armed threat on CAM-02) into a cohesive progression sequence.

### C. Tactical Voice Dispatch Synthesizer (`ibvap/speech.py`)
Generates phonetic, radio-ready verbal announcement scripts and SSML markup. Spells vehicle license plates using NATO/ICAO standard phonetics (e.g. `HR-26` ➔ `Hotel Romeo Two Six`) for audible dispatch in busy command rooms.

### D. Camera Tamper & Feed Health Auditing (`ibvap/tamper.py`)
Continuously audits surveillance feeds for:
1. **Lens Occlusion:** Physical obstruction, spray paint, or bagging (abnormally low spatial texture variance).
2. **Frozen Frame / Replay Attack:** Detection of static video loop or locked decode buffers.
3. **Signal Loss:** Stream timeout or camera power loss exceeding heartbeat tolerance.

### E. Blockchain Anchoring & Merkle Evidence Proofs (`ibvap/anchor.py`, `ibvap/blockchain_export.py`)
Aggregates local SHA-256 evidence chain tips into compact binary Merkle tree roots. Supports exporting OpenTimestamps Bitcoin calendar commitments and EVM testnet calldata (`anchorProof(bytes32,string)`) for immutable audit trails.

---

## 3. Operational APIs & CLIs

### Single Event Narrative
`GET /api/events/{event_id}/narrative`

### Shift Handover Report Export
`GET /api/events/export?fmt=narrative` (or `fmt=markdown`)

### Camera Health & Tamper Audit
`GET /api/cameras/health`

### Command-Line Tools
```bash
# Generate shift narrative reports
python scripts/generate_narrative_report.py --sample
python scripts/generate_narrative_report.py --db data/events.db --hours 12 --out shift_report.md

# Benchmark false-alarm rate per category
python scripts/false_alarm_report.py --sample
python scripts/false_alarm_report.py --db data/events.db --hours 24
```
