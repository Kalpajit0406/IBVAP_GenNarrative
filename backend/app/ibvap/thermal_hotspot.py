"""
thermal_hotspot.py — Thermal hotspot and concealed vehicle engine heat signature profiler.

Analyzes Long-Wave Infrared (LWIR) / radiometric thermal camera telemetry to detect:
  * Running vehicle engines hidden under camouflage netting or dense foliage
    (exhaust manifold / radiator heat delta >30°C above ambient).
  * Human core thermal signatures (~36°C) concealed in tall riverine grass.
  * Smuggling equipment / battery / electronic heat sources.
"""
from __future__ import annotations

import logging
import math
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("ibvap.thermal_hotspot")


@dataclass
class ThermalHotspot:
    hotspot_id: str
    centroid: Tuple[float, float]       # normalized (x, y) 0.0 to 1.0
    relative_temp_delta_c: float        # Celsius above ambient background
    estimated_source: str               # "VEHICLE_ENGINE", "HUMAN_CORE", "EQUIPMENT_WARM", "UNKNOWN"
    is_concealed: bool                  # True if located in dense foliage / masked sector
    severity: str                       # "Critical", "High", "Medium"
    tactical_priority: int              # 1 or 2
    advisory: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "hotspot_id": self.hotspot_id,
            "centroid": (round(self.centroid[0], 3), round(self.centroid[1], 3)),
            "relative_temp_delta_c": round(self.relative_temp_delta_c, 1),
            "estimated_source": self.estimated_source,
            "is_concealed": self.is_concealed,
            "severity": self.severity,
            "tactical_priority": self.tactical_priority,
            "advisory": self.advisory,
        }


class ThermalHotspotAnalyzer:
    """Detects and classifies thermal anomaly clusters from radiometric temperature grids."""

    def __init__(
        self,
        engine_threshold_delta_c: float = 30.0,
        human_threshold_delta_c: float = 12.0,
        equipment_threshold_delta_c: float = 6.0,
    ):
        self.engine_threshold_delta_c = engine_threshold_delta_c
        self.human_threshold_delta_c = human_threshold_delta_c
        self.equipment_threshold_delta_c = equipment_threshold_delta_c

    def analyze_grid(
        self,
        temp_grid: List[List[float]],
        ambient_temp_c: float = 20.0,
        foliage_mask: Optional[List[List[bool]]] = None,
    ) -> List[ThermalHotspot]:
        """Analyzes a 2D temperature matrix (values in Celsius) for tactical hotspots."""
        rows = len(temp_grid)
        if rows == 0:
            return []
        cols = len(temp_grid[0])
        if cols == 0:
            return []

        visited = [[False for _ in range(cols)] for _ in range(rows)]
        hotspots: List[ThermalHotspot] = []

        # Find connected components exceeding equipment threshold
        min_delta = self.equipment_threshold_delta_c
        for r in range(rows):
            for c in range(cols):
                val = temp_grid[r][c]
                delta = val - ambient_temp_c
                if delta >= min_delta and not visited[r][c]:
                    # BFS component search
                    component: List[Tuple[int, int]] = []
                    queue = [(r, c)]
                    visited[r][c] = True
                    max_delta = delta

                    while queue:
                        curr_r, curr_c = queue.pop(0)
                        component.append((curr_r, curr_c))
                        for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                            nr, nc = curr_r + dr, curr_c + dc
                            if 0 <= nr < rows and 0 <= nc < cols and not visited[nr][nc]:
                                n_delta = temp_grid[nr][nc] - ambient_temp_c
                                if n_delta >= min_delta:
                                    visited[nr][nc] = True
                                    queue.append((nr, nc))
                                    if n_delta > max_delta:
                                        max_delta = n_delta

                    # Compute centroid in normalized coordinates
                    avg_r = sum(pt[0] for pt in component) / len(component)
                    avg_c = sum(pt[1] for pt in component) / len(component)
                    norm_x = (avg_c + 0.5) / cols
                    norm_y = (avg_r + 0.5) / rows

                    # Check if within foliage or camouflage mask
                    is_foliage = False
                    if foliage_mask and len(foliage_mask) == rows and len(foliage_mask[0]) == cols:
                        foliage_hits = sum(1 for pt in component if foliage_mask[pt[0]][pt[1]])
                        is_foliage = (foliage_hits / len(component)) >= 0.5

                    # Classify source by maximum thermal delta
                    if max_delta >= self.engine_threshold_delta_c:
                        src = "VEHICLE_ENGINE"
                        sev = "Critical"
                        prio = 1
                        advisory = f"High-temperature thermal hotspot (+{max_delta:.1f}°C) matches running vehicle engine."
                        if is_foliage:
                            advisory += " TARGET CONCEALED UNDER FOLIAGE / CAMOUFLAGE."
                    elif max_delta >= self.human_threshold_delta_c:
                        src = "HUMAN_CORE"
                        sev = "High" if is_foliage else "Medium"
                        prio = 2
                        advisory = f"Biological thermal signature (+{max_delta:.1f}°C) detected."
                        if is_foliage:
                            advisory += " Concealed human crawling in ground foliage."
                    else:
                        src = "EQUIPMENT_WARM"
                        sev = "Medium"
                        prio = 3
                        advisory = f"Secondary heat source (+{max_delta:.1f}°C) identified."

                    hotspot = ThermalHotspot(
                        hotspot_id=f"THOT-{uuid.uuid4().hex[:6]}",
                        centroid=(norm_x, norm_y),
                        relative_temp_delta_c=max_delta,
                        estimated_source=src,
                        is_concealed=is_foliage,
                        severity=sev,
                        tactical_priority=prio,
                        advisory=advisory,
                    )
                    hotspots.append(hotspot)

        return hotspots
