from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Tuple

import numpy as np

from ..sim.drone import ControlCommand
from .config import RLConfig


@dataclass
class PolicyParams:
    weights: np.ndarray
    bias: np.ndarray


class PolicyModel:
    def __init__(self, obs_size: int, action_size: int, seed: int = 7) -> None:
        rng = np.random.default_rng(seed)
        self._weights = rng.normal(0.0, 0.2, size=(action_size, obs_size)).astype(
            np.float32
        )
        self._bias = np.zeros((action_size,), dtype=np.float32)
        self._lock = threading.Lock()

    def get_params(self) -> PolicyParams:
        with self._lock:
            return PolicyParams(self._weights.copy(), self._bias.copy())

    def set_params(self, params: PolicyParams) -> None:
        with self._lock:
            self._weights = params.weights.copy()
            self._bias = params.bias.copy()

    def act(self, obs: np.ndarray) -> np.ndarray:
        with self._lock:
            return self.act_with_params(obs, self._weights, self._bias)

    @staticmethod
    def act_with_params(
        obs: np.ndarray, weights: np.ndarray, bias: np.ndarray
    ) -> np.ndarray:
        logits = weights @ obs + bias
        return np.tanh(logits)

    @staticmethod
    def action_to_command(action: np.ndarray, cfg: RLConfig) -> ControlCommand:
        throttle = cfg.throttle_base + cfg.throttle_gain * float(action[0])
        throttle = max(0.0, min(1.0, throttle))
        pitch = float(action[1]) * cfg.rate_limit
        roll = float(action[2]) * cfg.rate_limit
        yaw = float(action[3]) * cfg.rate_limit
        return ControlCommand(throttle=throttle, pitch=pitch, roll=roll, yaw=yaw)

    def save(self, path: Path) -> None:
        params = self.get_params()
        path.parent.mkdir(parents=True, exist_ok=True)
        np.savez(path, weights=params.weights, bias=params.bias)

    def load(self, path: Path) -> bool:
        if not path.exists():
            return False
        data = np.load(path)
        weights = data.get("weights")
        bias = data.get("bias")
        if weights is None or bias is None:
            return False
        self.set_params(PolicyParams(weights=weights, bias=bias))
        return True
