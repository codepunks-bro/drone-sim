from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class ControlCommand:
    throttle: float = 0.0  # 0..1
    pitch: float = 0.0  # radians
    roll: float = 0.0  # radians
    yaw: float = 0.0  # radians

    def clamp(self) -> None:
        self.throttle = max(0.0, min(1.0, self.throttle))


@dataclass
class DroneState:
    position: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    velocity: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    rotation: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])  # roll, pitch, yaw
    battery: float = 1.0  # 0..1
    collided: bool = False

    def to_telemetry(self, sim_time: float) -> Dict[str, object]:
        return {
            "pos": self.position,
            "vel": self.velocity,
            "rot": self.rotation,
            "battery": self.battery,
            "time": sim_time,
            "collided": self.collided,
        }
