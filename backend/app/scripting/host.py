from __future__ import annotations

import multiprocessing as mp
import queue
from dataclasses import dataclass
from typing import Any, Dict, Optional

from .sdk import DroneSDK


def _run_script(
    source: str,
    command_queue: mp.Queue,
    telemetry_queue: mp.Queue,
    stop_event: mp.Event,
) -> None:
    sdk = DroneSDK(command_queue, telemetry_queue, stop_event)
    safe_builtins = {
        "range": range,
        "min": min,
        "max": max,
        "abs": abs,
        "sum": sum,
        "len": len,
        "print": print,
        "__import__": __import__,
    }
    scope: Dict[str, Any] = {"sdk": sdk, "__builtins__": safe_builtins}
    exec(source, scope, scope)
    runner = scope.get("run") or scope.get("main")
    if callable(runner):
        runner(sdk)


@dataclass
class ScriptHost:
    process: Optional[mp.Process] = None
    command_queue: Optional[mp.Queue] = None
    telemetry_queue: Optional[mp.Queue] = None
    stop_event: Optional[mp.Event] = None

    def start(self, source: str) -> None:
        self.stop()
        self.command_queue = mp.Queue(maxsize=100)
        self.telemetry_queue = mp.Queue(maxsize=200)
        self.stop_event = mp.Event()
        self.process = mp.Process(
            target=_run_script,
            args=(source, self.command_queue, self.telemetry_queue, self.stop_event),
            daemon=True,
        )
        self.process.start()

    def stop(self) -> None:
        if self.stop_event is not None:
            self.stop_event.set()
        if self.process is not None and self.process.is_alive():
            self.process.terminate()
            self.process.join(timeout=1.0)
        self.process = None
        self.command_queue = None
        self.telemetry_queue = None
        self.stop_event = None

    def pull_latest_command(self) -> Optional[Dict[str, float]]:
        if self.command_queue is None:
            return None
        latest = None
        try:
            while True:
                latest = self.command_queue.get_nowait()
        except queue.Empty:
            return latest

    def push_telemetry(self, telemetry: Dict[str, Any]) -> None:
        if self.telemetry_queue is None:
            return
        try:
            self.telemetry_queue.put_nowait(telemetry)
        except queue.Full:
            pass
