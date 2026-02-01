from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class Telemetry:
    data: Dict[str, Any]


class DroneSDK:
    def __init__(self, command_queue, telemetry_queue, stop_event) -> None:
        self._command_queue = command_queue
        self._telemetry_queue = telemetry_queue
        self._stop_event = stop_event

    def set_command(self, throttle: float, pitch: float, roll: float, yaw: float) -> None:
        self._command_queue.put(
            {"throttle": throttle, "pitch": pitch, "roll": roll, "yaw": yaw}
        )

    def hover(self, throttle: float = 0.6) -> None:
        self.set_command(throttle=throttle, pitch=0.0, roll=0.0, yaw=0.0)

    def get_telemetry(self, timeout: float = 0.1) -> Optional[Telemetry]:
        end_time = time.time() + timeout
        while time.time() < end_time and not self._stop_event.is_set():
            try:
                data = self._telemetry_queue.get(timeout=timeout)
                return Telemetry(data=data)
            except Exception:
                return None
        return None

    def get_vision(self, timeout: float = 0.1) -> Optional[Dict[str, Any]]:
        telemetry = self.get_telemetry(timeout=timeout)
        if telemetry is None:
            return None
        return telemetry.data.get("vision")

    def should_stop(self) -> bool:
        return self._stop_event.is_set()
