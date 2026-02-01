from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Tuple


@dataclass
class SphereObstacle:
    center: List[float]
    radius: float


@dataclass
class WorldBounds:
    min_xyz: List[float] = field(default_factory=lambda: [-20.0, -20.0, 0.0])
    max_xyz: List[float] = field(default_factory=lambda: [20.0, 20.0, 20.0])


@dataclass
class WorldState:
    bounds: WorldBounds = field(default_factory=WorldBounds)
    obstacles: List[SphereObstacle] = field(default_factory=list)

    def clamp_position(self, pos: List[float]) -> Tuple[List[float], bool]:
        collided = False
        for i in range(3):
            if pos[i] < self.bounds.min_xyz[i]:
                pos[i] = self.bounds.min_xyz[i]
                collided = True
            if pos[i] > self.bounds.max_xyz[i]:
                pos[i] = self.bounds.max_xyz[i]
                collided = True
        return pos, collided

    def check_obstacles(self, pos: List[float]) -> bool:
        for obstacle in self.obstacles:
            dx = pos[0] - obstacle.center[0]
            dy = pos[1] - obstacle.center[1]
            dz = pos[2] - obstacle.center[2]
            if (dx * dx + dy * dy + dz * dz) <= obstacle.radius * obstacle.radius:
                return True
        return False
