"""
heatmap.py — Border sector spatial threat density and infiltration heatmap.

Aggregates historical and real-time surveillance intrusion events onto a 2D spatial grid.
Applies threat-weighted kernel smoothing to identify vulnerable border crossing corridors,
providing ASCII terminal visualization and GeoJSON density clusters for tactical redeployment.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

SEVERITY_WEIGHTS = {
    "critical": 3.5,
    "high": 2.0,
    "medium": 1.2,
    "low": 0.5,
    "info": 0.2,
}

CATEGORY_MULTIPLIERS = {
    "weapon_ready": 2.0,
    "armed": 2.0,
    "geofence_breach": 1.8,
    "crawling_prone": 1.6,
    "anpr_alert": 1.2,
    "loitering": 1.0,
}


@dataclass
class ThreatHotspot:
    col: int
    row: int
    norm_x: float
    norm_y: float
    intensity: float
    level: str                  # "CRITICAL", "HIGH", "ELEVATED", "NOMINAL"
    primary_category: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "col": self.col,
            "row": self.row,
            "norm_x": round(self.norm_x, 3),
            "norm_y": round(self.norm_y, 3),
            "intensity": round(self.intensity, 2),
            "level": self.level,
            "primary_category": self.primary_category,
        }


class SpatialThreatHeatmap:
    """2D spatial grid accumulator with kernel smoothing for tactical border heatmaps."""

    def __init__(self, cols: int = 20, rows: int = 10):
        self.cols = max(3, cols)
        self.rows = max(3, rows)
        self._raw_grid = [[0.0 for _ in range(self.cols)] for _ in range(self.rows)]
        self._category_grid = [[{} for _ in range(self.cols)] for _ in range(self.rows)]
        self._event_count = 0

    def add_event(
        self,
        norm_x: float,
        norm_y: float,
        severity: str = "High",
        category: str = "general",
        custom_weight: Optional[float] = None,
    ) -> None:
        """Accumulates an incident at normalized (x, y) coordinates."""
        px = max(0.0, min(0.999, norm_x))
        py = max(0.0, min(0.999, norm_y))
        c = int(px * self.cols)
        r = int(py * self.rows)

        sev_key = severity.lower()
        base_w = SEVERITY_WEIGHTS.get(sev_key, 1.0)
        cat_mult = CATEGORY_MULTIPLIERS.get(category.lower(), 1.0)
        w = custom_weight if custom_weight is not None else (base_w * cat_mult)

        self._raw_grid[r][c] += w
        cat_dict = self._category_grid[r][c]
        cat_dict[category] = cat_dict.get(category, 0.0) + w
        self._event_count += 1

    def compute_smoothed_grid(self, kernel_radius: int = 1) -> List[List[float]]:
        """Applies 2D box/Gaussian smoothing kernel to spread threat influence."""
        smoothed = [[0.0 for _ in range(self.cols)] for _ in range(self.rows)]
        for r in range(self.rows):
            for c in range(self.cols):
                total_w = 0.0
                accum = 0.0
                for dr in range(-kernel_radius, kernel_radius + 1):
                    for dc in range(-kernel_radius, kernel_radius + 1):
                        nr, nc = r + dr, c + dc
                        if 0 <= nr < self.rows and 0 <= nc < self.cols:
                            dist = math.hypot(dr, dc)
                            kernel_w = max(0.0, 1.0 - (dist / (kernel_radius + 1.0)))
                            accum += self._raw_grid[nr][nc] * kernel_w
                            total_w += kernel_w
                smoothed[r][c] = accum / max(0.001, total_w)
        return smoothed

    def get_top_hotspots(self, top_k: int = 3, kernel_radius: int = 1) -> List[ThreatHotspot]:
        """Finds highest threat concentration clusters."""
        grid = self.compute_smoothed_grid(kernel_radius=kernel_radius)
        cells = []
        for r in range(self.rows):
            for c in range(self.cols):
                if grid[r][c] > 0.1:
                    cells.append((grid[r][c], r, c))
        cells.sort(key=lambda item: item[0], reverse=True)

        hotspots: List[ThreatHotspot] = []
        for intensity, r, c in cells[:top_k]:
            cat_dict = self._category_grid[r][c]
            top_cat = max(cat_dict.keys(), key=lambda k: cat_dict[k]) if cat_dict else "general"

            if intensity >= 5.0:
                level = "CRITICAL"
            elif intensity >= 2.5:
                level = "HIGH"
            elif intensity >= 1.0:
                level = "ELEVATED"
            else:
                level = "NOMINAL"

            norm_x = (c + 0.5) / self.cols
            norm_y = (r + 0.5) / self.rows
            hotspots.append(ThreatHotspot(
                col=c,
                row=r,
                norm_x=norm_x,
                norm_y=norm_y,
                intensity=intensity,
                level=level,
                primary_category=top_cat,
            ))
        return hotspots

    def render_ascii(self) -> str:
        """Renders an ASCII tactical threat heat matrix for terminal / logs."""
        grid = self.compute_smoothed_grid(kernel_radius=1)
        max_val = max((max(row) for row in grid), default=1.0)
        chars = " .:-=+*#%@"

        lines = [f"=== TACTICAL BORDER THREAT HEATMAP ({self.cols}x{self.rows}) — Events: {self._event_count} ==="]
        for r in range(self.rows):
            row_str = ""
            for c in range(self.cols):
                val = grid[r][c]
                ratio = val / max(1.0, max_val)
                char_idx = min(len(chars) - 1, int(ratio * (len(chars) - 1)))
                row_str += chars[char_idx] + " "
            lines.append(f"R{r:02d} | {row_str}|")
        lines.append("=" * len(lines[0]))
        return "\n".join(lines)

    def to_geojson(
        self,
        base_lat: float = 26.6852,
        base_lon: float = 88.1425,
        lat_span: float = 0.02,
        lon_span: float = 0.04,
    ) -> Dict[str, Any]:
        """Converts heatmap hotspots into RFC 7946 GeoJSON FeatureCollection."""
        hotspots = self.get_top_hotspots(top_k=10)
        features = []
        for h in hotspots:
            # Map normalized (x, y) to geographic (lon, lat)
            lon = base_lon + (h.norm_x - 0.5) * lon_span
            lat = base_lat - (h.norm_y - 0.5) * lat_span
            features.append({
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [round(lon, 6), round(lat, 6)],
                },
                "properties": h.to_dict(),
            })
        return {
            "type": "FeatureCollection",
            "features": features,
            "total_events": self._event_count,
        }
