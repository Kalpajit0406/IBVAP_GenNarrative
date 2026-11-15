"""
ibvap/vlm.py — Zero-Shot Vision-Language Model (VLM) Multi-Modal Anomaly Prompt Engine.

Directly addresses VLM Explainable Alerts (CLAUDE.md §11 & Context §8):
Constructs structured spatio-temporal prompt payloads for edge Vision-Language Models
(SmolVLM, Qwen2-VL, Ollama) by synthesizing:
  - Track bounding geometries, velocities, and skeletal postures
  - Environmental scene dynamics (illumination state, atmospheric visibility)
  - Active virtual fence boundaries and zone rules
Generates chain-of-thought (CoT) reasoning prompts and parses structured JSON anomaly outputs.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


VLM_SYSTEM_PROMPT = """You are an AI Border Surveillance Analyst for the Sashastra Seema Bal (SSB).
Your job is to analyze structured multi-track surveillance telemetry and explain whether an anomalous or hostile perimeter breach is occurring.

Evaluate:
1. Spatial positioning relative to restricted virtual fences.
2. Behavioral indicators (rapid running, crawling/lying posture, weapon-ready stances, vehicle loitering).
3. Environmental context (night darkness, low visibility fog).

Output strictly valid JSON matching this schema:
{
  "anomaly_detected": true/false,
  "threat_level": "Nominal" | "Elevated" | "Critical",
  "reasoning": "Detailed tactical explanation of what is observed",
  "recommended_action": "Tactical response directive for field operators"
}"""


@dataclass
class TrackContext:
    track_id: int
    class_name: str
    bbox: tuple[int, int, int, int]
    velocity: tuple[float, float] = (0.0, 0.0)
    posture: Optional[str] = None
    plate: Optional[str] = None
    weapon_confirmed: bool = False


@dataclass
class VlmSceneContext:
    cam_id: int
    cam_name: str
    illumination: str = "day"          # "day" | "low_light" | "night_ir"
    weather: str = "clear"             # "clear" | "fog" | "haze"
    visibility: float = 1.0
    fences: List[str] = field(default_factory=list)
    tracks: List[TrackContext] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cam_id": self.cam_id,
            "cam_name": self.cam_name,
            "illumination": self.illumination,
            "weather": self.weather,
            "visibility_index": round(self.visibility, 2),
            "virtual_fences": self.fences,
            "active_tracks": [asdict(t) for t in self.tracks],
        }


class VlmPromptBuilder:
    """
    Synthesizes and parses multi-modal VLM anomaly reasoning prompts.
    """

    @staticmethod
    def build_system_prompt() -> str:
        return VLM_SYSTEM_PROMPT

    @staticmethod
    def build_user_prompt(context: VlmSceneContext) -> str:
        data_json = json.dumps(context.to_dict(), indent=2)
        return (
            f"Analyze the following real-time border telemetry from {context.cam_name}:\n\n"
            f"```json\n{data_json}\n```\n\n"
            f"Provide your tactical assessment in the specified JSON format."
        )

    @staticmethod
    def parse_response(raw_text: str) -> Dict[str, Any]:
        """
        Extract and validate JSON block from VLM output text.
        """
        match = re.search(r"\{.*\}", raw_text, re.DOTALL)
        if not match:
            return {
                "anomaly_detected": False,
                "threat_level": "Nominal",
                "reasoning": raw_text.strip() or "No response from VLM",
                "recommended_action": "Verify feed manually",
            }

        try:
            parsed = json.loads(match.group(0))
            return {
                "anomaly_detected": bool(parsed.get("anomaly_detected", False)),
                "threat_level": str(parsed.get("threat_level", "Nominal")),
                "reasoning": str(parsed.get("reasoning", "")),
                "recommended_action": str(parsed.get("recommended_action", "")),
            }
        except Exception:
            return {
                "anomaly_detected": False,
                "threat_level": "Nominal",
                "reasoning": "Unparseable VLM response",
                "recommended_action": "Verify feed manually",
            }
