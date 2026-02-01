from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Tuple

import cv2
import numpy as np

from .drone import DroneState
from .world import SphereObstacle, WorldState


@dataclass
class CameraConfig:
    width: int = 320
    height: int = 240
    meters_per_pixel: float = 0.1
    goal_world: List[float] = field(default_factory=lambda: [8.0, -6.0, 0.0])
    obstacle_color_bgr: Tuple[int, int, int] = (0, 128, 255)
    goal_color_bgr: Tuple[int, int, int] = (0, 0, 255)
    drone_color_bgr: Tuple[int, int, int] = (255, 0, 0)
    background_bgr: Tuple[int, int, int] = (20, 20, 20)


def _world_to_body(
    drone: DroneState, point_xyz: List[float]
) -> Tuple[float, float]:
    dx = point_xyz[0] - drone.position[0]
    dy = point_xyz[1] - drone.position[1]
    yaw = drone.rotation[2]
    cos_yaw = math.cos(yaw)
    sin_yaw = math.sin(yaw)
    x_body = cos_yaw * dx + sin_yaw * dy
    y_body = -sin_yaw * dx + cos_yaw * dy
    return x_body, y_body


def _world_to_pixel(
    drone: DroneState, point_xyz: List[float], cfg: CameraConfig
) -> Tuple[int, int]:
    x_body, y_body = _world_to_body(drone, point_xyz)
    # Map body right (y) to image x, body forward (x) to image up.
    px = int(cfg.width / 2 + y_body / cfg.meters_per_pixel)
    py = int(cfg.height / 2 - x_body / cfg.meters_per_pixel)
    return px, py


def _draw_obstacle(
    img: np.ndarray, obstacle: SphereObstacle, drone: DroneState, cfg: CameraConfig
) -> None:
    px, py = _world_to_pixel(drone, obstacle.center, cfg)
    radius_px = max(1, int(obstacle.radius / cfg.meters_per_pixel))
    cv2.circle(img, (px, py), radius_px, cfg.obstacle_color_bgr, -1)


def render_topdown(
    drone: DroneState, world: WorldState, cfg: CameraConfig
) -> np.ndarray:
    img = np.zeros((cfg.height, cfg.width, 3), dtype=np.uint8)
    img[:] = cfg.background_bgr

    for obstacle in world.obstacles:
        _draw_obstacle(img, obstacle, drone, cfg)

    goal_px, goal_py = _world_to_pixel(drone, cfg.goal_world, cfg)
    cv2.circle(img, (goal_px, goal_py), 5, cfg.goal_color_bgr, -1)

    center = (cfg.width // 2, cfg.height // 2)
    cv2.circle(img, center, 4, cfg.drone_color_bgr, -1)
    heading_len = 12
    yaw = drone.rotation[2]
    ahead_world = [
        drone.position[0] + math.cos(yaw) * (heading_len * cfg.meters_per_pixel),
        drone.position[1] + math.sin(yaw) * (heading_len * cfg.meters_per_pixel),
        drone.position[2],
    ]
    hx, hy = _world_to_pixel(drone, ahead_world, cfg)
    cv2.line(img, center, (hx, hy), cfg.drone_color_bgr, 2)

    return img
