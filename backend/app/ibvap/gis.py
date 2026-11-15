"""
ibvap/gis.py — RFC 7946 GeoJSON Spatial Feature Converter for GIS Digital Map.

Supports GIS Layer integration (Leaflet frontend / QGIS / PostGIS):
Transforms surveillance events and perimeter alerts containing latitude/longitude coordinates
into standard GeoJSON FeatureCollections with tactical styling properties.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional


_SEVERITY_COLORS = {
    "Critical": "#EF4444",   # Red
    "High": "#F97316",       # Orange
    "Medium": "#EAB308",     # Yellow
    "Low": "#3B82F6",        # Blue
    "Info": "#10B981",       # Green
}


def to_geojson_feature(event: Dict[str, Any]) -> Dict[str, Any]:
    """Convert an individual event into a GeoJSON Feature."""
    lat = event.get("lat")
    lon = event.get("lon")
    sev = str(event.get("severity") or event.get("level") or "Info").capitalize()
    color = _SEVERITY_COLORS.get(sev, "#6B7280")

    geometry = None
    if lat is not None and lon is not None:
        try:
            geometry = {
                "type": "Point",
                "coordinates": [float(lon), float(lat)],
            }
        except (ValueError, TypeError):
            geometry = None

    details = event.get("details") or {}
    if isinstance(details, str):
        import json
        try:
            details = json.loads(details)
        except Exception:
            details = {}

    properties = {
        "event_id": event.get("event_id"),
        "ts_utc": event.get("ts_utc"),
        "site_id": event.get("site_id"),
        "post_name": event.get("post_name"),
        "cam_id": event.get("cam_id"),
        "cam_name": event.get("cam_name"),
        "severity": sev,
        "category": event.get("category"),
        "score": event.get("score"),
        "persons": event.get("persons", 0),
        "vehicles": event.get("vehicles", 0),
        "ev_hash": event.get("ev_hash"),
        "marker_color": color,
        "details": details,
    }

    return {
        "type": "Feature",
        "geometry": geometry,
        "properties": properties,
    }


def to_geojson_feature_collection(
    events: List[Dict[str, Any]],
    site_name: str = "BOP Sector Alpha",
) -> Dict[str, Any]:
    """Compile multiple events into a standard GeoJSON FeatureCollection."""
    features = [to_geojson_feature(ev) for ev in events]
    return {
        "type": "FeatureCollection",
        "metadata": {
            "site_name": site_name,
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "total_features": len(features),
            "spatial_features": sum(1 for f in features if f["geometry"] is not None),
        },
        "features": features,
    }
