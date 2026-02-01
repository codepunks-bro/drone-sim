from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RLConfig:
    dt: float = 0.02
    episode_steps: int = 400
    obs_size: int = 12
    action_size: int = 4
    throttle_base: float = 0.6
    throttle_gain: float = 0.35
    rate_limit: float = 1.0
    vel_scale: float = 5.0
    start_xy_range: float = 6.0
    start_z: float = 2.0
    reward_goal_gain: float = 1.0
    reward_collision: float = -2.0
    reward_stable_bonus: float = 2.0
    reward_angle_penalty: float = 0.05
    target_offset_max: float = 0.12
    stable_frames_required: int = 8
