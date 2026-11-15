# Command and Control (C2) Integration Specification

This document provides the formal wire format, streaming semantics, and authentication contracts for integrating IBVAP with external Command and Control (C2) platforms, SOC SIEMs (Splunk, ArcSight), and GIS digital border mapping layers.

---

## 1. Authentication & Scoped Authorization

All administrative or state-altering requests require authentication via the `X-IBVAP-Token` HTTP header:

```http
X-IBVAP-Token: ibvap_YOUR_SCOPED_TOKEN
```

### Granular Permission Scopes
API tokens are registered in `data/api_clients.json` with role-based scopes:
* **`read`**: Grants access to event feeds, health telemetry, and incident narrative reports.
* **`ack`**: Grants permission to acknowledge alerts and record operator disposition notes.
* **`admin`**: Full administrative access (camera configuration, virtual geofencing, shutdown, and hot-swap model retraining).

---

## 2. Real-Time Streaming & Event Polling

### Server-Sent Events (SSE) Live Feed
Subscribe to real-time incident telemetry with zero polling latency:

```bash
curl -N http://127.0.0.1:8090/api/events/stream
```

Streams standard `ibvap.event/2` JSON events as they are inferred and hash-chained.

### Cursor-Based Paginated Polling
Retrieve historical events chronologically using monotonic Crockford-base32 ULID cursors:

```http
GET /api/events?since_id=01HX98Z123456789ABCDEF000&limit=100
```

---

## 3. Wire Schema (`ibvap.event/2`)

Every incident emitted across SSE, Webhooks, or REST matches this schema:

```json
{
  "schema": "ibvap.event/2",
  "event_id": "01HX98Z123456789ABCDEF001",
  "ts_utc": "2026-11-15T04:30:00.123Z",
  "severity": "Critical",
  "category": "weapon",
  "score": 96.5,
  "site": {
    "site_id": "BOP_SECTOR_04",
    "post_name": "BOP Sector Alpha"
  },
  "camera": {
    "cam_id": 2,
    "name": "North Gate Perimeter",
    "lat": 26.8524,
    "lon": 88.3512
  },
  "counts": {
    "persons": 1,
    "vehicles": 0
  },
  "evidence": {
    "sha256": "a1b2c3d4e5f67890123456789abcdef0123456789abcdef0123456789abcdef0"
  },
  "details": {
    "armed": true,
    "weapon": true,
    "posture": "AIM",
    "fence_name": "Zone Bravo"
  }
}
```

---

## 4. GIS Digital Map Export (RFC 7946 GeoJSON)

To plot live and historical alerts on tactical maps (Leaflet, QGIS, ArcGIS):

```http
GET /api/events/export?fmt=geojson
```

Returns standard GeoJSON `FeatureCollection` with GPS `Point` geometries (`[lon, lat]`) and styling colors based on alert severity (`marker_color`).

---

## 5. Explainable AI Incident Narratives

Generate executive operational briefings for shift commanders:

```http
GET /api/events/{event_id}/narrative
GET /api/events/export?fmt=narrative
GET /api/events/export?fmt=narrative&lang=hi
```

---

## 6. Cryptographic Chain-of-Custody Verification

Verify that an incident payload has not been modified after capture:

```bash
python scripts/verify_evidence_chain.py --event-id 01HX98Z123456789ABCDEF001
```
