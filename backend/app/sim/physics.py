from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List

from .drone import ControlCommand, DroneState


@dataclass
class PhysicsConfig:
    mass: float = 1.2
    max_thrust: float = 18.0  # Newtons
    drag_coeff: float = 0.4
    gravity: float = 9.81


def _body_up_vector(roll: float, pitch: float, yaw: float) -> List[float]:
    # Approximate rotation: Z(yaw) * Y(pitch) * X(roll)
    cr = math.cos(roll)
    sr = math.sin(roll)
    cp = math.cos(pitch)
    sp = math.sin(pitch)
    cy = math.cos(yaw)
    sy = math.sin(yaw)

    # Body up axis after rotation
    x = cy * sp * cr + sy * sr
    y = sy * sp * cr - cy * sr
    z = cp * cr
    return [x, y, z]


def integrate(state: DroneState, command: ControlCommand, dt: float, cfg: PhysicsConfig) -> None:
    command.clamp()
    roll, pitch, yaw = state.rotation

    up = _body_up_vector(roll, pitch, yaw)
    thrust = command.throttle * cfg.max_thrust
    ax = (up[0] * thrust) / cfg.mass
    ay = (up[1] * thrust) / cfg.mass
    az = (up[2] * thrust) / cfg.mass - cfg.gravity

    # Simple drag
    ax -= cfg.drag_coeff * state.velocity[0] / cfg.mass
    ay -= cfg.drag_coeff * state.velocity[1] / cfg.mass
    az -= cfg.drag_coeff * state.velocity[2] / cfg.mass

    state.velocity[0] += ax * dt
    state.velocity[1] += ay * dt
    state.velocity[2] += az * dt

    state.position[0] += state.velocity[0] * dt
    state.position[1] += state.velocity[1] * dt
    state.position[2] += state.velocity[2] * dt

    # Apply angular rates directly for simplicity
    state.rotation[0] += command.roll * dt
    state.rotation[1] += command.pitch * dt
    state.rotation[2] += command.yaw * dt
