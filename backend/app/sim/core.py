from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

from .drone import ControlCommand, DroneState
from .physics import PhysicsConfig, integrate
from .world import WorldState


@dataclass
class SimCore:
    world: WorldState = field(default_factory=WorldState)
    drone: DroneState = field(default_factory=DroneState)
    physics: PhysicsConfig = field(default_factory=PhysicsConfig)
    command: ControlCommand = field(default_factory=ControlCommand)
    time_s: float = 0.0
    last_step: Optional[float] = None

    def reset(self) -> None:
        self.drone = DroneState()
        self.command = ControlCommand()
        self.time_s = 0.0
        self.last_step = None

    def step(self, dt: float) -> None:
        integrate(self.drone, self.command, dt, self.physics)
        self.drone.position, hit_bounds = self.world.clamp_position(self.drone.position)
        hit_obstacles = self.world.check_obstacles(self.drone.position)
        self.drone.collided = hit_bounds or hit_obstacles
        self.time_s += dt

    def step_real_time(self, target_dt: float) -> None:
        now = time.perf_counter()
        if self.last_step is None:
            self.last_step = now
            return
        dt = min(target_dt, now - self.last_step)
        self.last_step = now
        self.step(dt)
