from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np

from ..sim.camera import CameraConfig
from ..sim.world import WorldState
from .config import RLConfig
from .env import RLEnv
from .policy import PolicyModel, PolicyParams


@dataclass
class RLStatus:
    running: bool = False
    iterations: int = 0
    episodes: int = 0
    last_reward: float = 0.0
    best_reward: float = -1e9
    last_save_time_s: float = 0.0

    def to_dict(self) -> dict:
        return {
            "running": self.running,
            "iterations": self.iterations,
            "episodes": self.episodes,
            "last_reward": self.last_reward,
            "best_reward": self.best_reward,
            "last_save_time_s": self.last_save_time_s,
        }


class RLTrainer:
    def __init__(
        self,
        world: WorldState,
        camera: CameraConfig,
        cfg: Optional[RLConfig] = None,
        model_path: Optional[Path] = None,
    ) -> None:
        self._cfg = cfg or RLConfig()
        self._policy = PolicyModel(self._cfg.obs_size, self._cfg.action_size)
        self._env = RLEnv(world=world, camera=camera, cfg=self._cfg)
        self._model_path = model_path or Path(__file__).resolve().parents[1] / "data" / "rl_policy.npz"
        self._status = RLStatus()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._rng = np.random.default_rng(123)

    @property
    def policy(self) -> PolicyModel:
        return self._policy

    @property
    def config(self) -> RLConfig:
        return self._cfg

    @property
    def status(self) -> RLStatus:
        return self._status

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._status.running = True
        self._thread = threading.Thread(target=self._train_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._status.running = False

    def _train_loop(self) -> None:
        while not self._stop_event.is_set():
            self.train_iteration()
            time.sleep(0.01)
        self._status.running = False

    def train_iteration(self) -> None:
        population = 10
        sigma = 0.15
        best_reward = -1e9
        best_params: Optional[PolicyParams] = None

        base_params = self._policy.get_params()
        for _ in range(population):
            noise_w = self._rng.normal(0.0, sigma, size=base_params.weights.shape).astype(
                np.float32
            )
            noise_b = self._rng.normal(0.0, sigma, size=base_params.bias.shape).astype(
                np.float32
            )
            params = PolicyParams(
                weights=base_params.weights + noise_w, bias=base_params.bias + noise_b
            )
            reward = self._evaluate_params(params)
            if reward > best_reward:
                best_reward = reward
                best_params = params

        if best_params is not None:
            self._policy.set_params(best_params)
            if best_reward > self._status.best_reward:
                self._policy.save(self._model_path)
                self._status.best_reward = best_reward
                self._status.last_save_time_s = time.time()

        self._status.last_reward = best_reward
        self._status.iterations += 1

    def _evaluate_params(self, params: PolicyParams) -> float:
        obs = self._env.reset()
        total_reward = 0.0
        for _ in range(self._cfg.episode_steps):
            action = PolicyModel.act_with_params(obs, params.weights, params.bias)
            step = self._env.step(action)
            total_reward += step.reward
            obs = step.obs
            if step.done:
                break
        self._status.episodes += 1
        return total_reward

    def load(self) -> bool:
        return self._policy.load(self._model_path)
