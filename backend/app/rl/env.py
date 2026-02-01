from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, Tuple

import numpy as np

from ..sim.camera import CameraConfig, render_topdown
from ..sim.core import SimCore
from ..sim.world import WorldState
from ..vision.processor import VisionProcessor
from .config import RLConfig
from .policy import PolicyModel


def _normalize(value: float, min_v: float, max_v: float) -> float:
    if max_v == min_v:
        return 0.0
    return max(-1.0, min(1.0, 2.0 * (value - min_v) / (max_v - min_v) - 1.0))


def build_observation(
    sim: SimCore, vision: Dict[str, object], world: WorldState, cfg: RLConfig
) -> np.ndarray:
    min_xyz = world.bounds.min_xyz
    max_xyz = world.bounds.max_xyz
    pos = sim.drone.position
    vel = sim.drone.velocity
    rot = sim.drone.rotation
    target_visible = 1.0 if vision.get("target_visible") else 0.0
    offset = vision.get("target_offset") or [0.0, 0.0]
    obs = [
        _normalize(pos[0], min_xyz[0], max_xyz[0]),
        _normalize(pos[1], min_xyz[1], max_xyz[1]),
        _normalize(pos[2], min_xyz[2], max_xyz[2]),
        max(-1.0, min(1.0, vel[0] / cfg.vel_scale)),
        max(-1.0, min(1.0, vel[1] / cfg.vel_scale)),
        max(-1.0, min(1.0, vel[2] / cfg.vel_scale)),
        max(-1.0, min(1.0, rot[0] / math.pi)),
        max(-1.0, min(1.0, rot[1] / math.pi)),
        max(-1.0, min(1.0, rot[2] / math.pi)),
        target_visible,
        float(offset[0]),
        float(offset[1]),
    ]
    return np.array(obs, dtype=np.float32)


@dataclass
class StepResult:
    obs: np.ndarray
    reward: float
    done: bool
    info: Dict[str, object]


class RLEnv:
    def __init__(self, world: WorldState, camera: CameraConfig, cfg: RLConfig) -> None:
        self._base_world = world
        self._camera = camera
        self._cfg = cfg
        self._vision = VisionProcessor()
        self._sim = SimCore()
        self._sim.world = world
        self._rng = np.random.default_rng(42)
        self._steps = 0
        self._prev_dist = 0.0
        self._stable_frames = 0

    def reset(self) -> np.ndarray:
        self._sim.reset()
        self._sim.world = self._base_world
        min_xyz = self._sim.world.bounds.min_xyz
        max_xyz = self._sim.world.bounds.max_xyz
        center_x = (min_xyz[0] + max_xyz[0]) / 2
        center_y = (min_xyz[1] + max_xyz[1]) / 2
        x = center_x + self._rng.uniform(-self._cfg.start_xy_range, self._cfg.start_xy_range)
        y = center_y + self._rng.uniform(-self._cfg.start_xy_range, self._cfg.start_xy_range)
        z = max(min_xyz[2], min(max_xyz[2], self._cfg.start_z))
        self._sim.drone.position = [x, y, z]
        self._sim.drone.velocity = [0.0, 0.0, 0.0]
        self._sim.drone.rotation = [
            0.0,
            0.0,
            self._rng.uniform(-math.pi, math.pi),
        ]
        self._steps = 0
        self._stable_frames = 0
        self._prev_dist = self._distance_to_goal()
        vision = self._compute_vision()
        return build_observation(self._sim, vision, self._sim.world, self._cfg)

    def step(self, action: np.ndarray) -> StepResult:
        command = PolicyModel.action_to_command(action, self._cfg)
        self._sim.command = command
        self._sim.step(self._cfg.dt)
        self._steps += 1

        vision = self._compute_vision()
        obs = build_observation(self._sim, vision, self._sim.world, self._cfg)
        dist = self._distance_to_goal()
        reward = (self._prev_dist - dist) * self._cfg.reward_goal_gain
        self._prev_dist = dist

        roll, pitch, yaw = self._sim.drone.rotation
        reward -= self._cfg.reward_angle_penalty * (abs(roll) + abs(pitch) + abs(yaw))

        done = False
        if self._sim.drone.collided:
            reward += self._cfg.reward_collision
            done = True

        target_visible = bool(vision.get("target_visible"))
        offset = vision.get("target_offset") or [0.0, 0.0]
        if target_visible and abs(float(offset[0])) <= self._cfg.target_offset_max and abs(
            float(offset[1])
        ) <= self._cfg.target_offset_max:
            self._stable_frames += 1
        else:
            self._stable_frames = 0

        if self._stable_frames >= self._cfg.stable_frames_required:
            reward += self._cfg.reward_stable_bonus
            done = True

        if self._steps >= self._cfg.episode_steps:
            done = True

        info = {
            "distance": dist,
            "stable_frames": self._stable_frames,
        }
        return StepResult(obs=obs, reward=reward, done=done, info=info)

    def _compute_vision(self) -> Dict[str, object]:
        frame = render_topdown(self._sim.drone, self._sim.world, self._camera)
        vision = self._vision.process(frame)
        return vision.to_dict()

    def _distance_to_goal(self) -> float:
        goal = self._camera.goal_world
        dx = self._sim.drone.position[0] - goal[0]
        dy = self._sim.drone.position[1] - goal[1]
        dz = self._sim.drone.position[2] - goal[2]
        return math.sqrt(dx * dx + dy * dy + dz * dz)
