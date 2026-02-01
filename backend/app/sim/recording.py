from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class Recorder:
    frames: List[Dict[str, Any]] = field(default_factory=list)
    recording: bool = False
    playback: bool = False
    playback_index: int = 0

    def start(self) -> None:
        self.frames = []
        self.recording = True
        self.playback = False
        self.playback_index = 0

    def stop(self) -> None:
        self.recording = False

    def clear(self) -> None:
        self.frames = []
        self.playback = False
        self.playback_index = 0

    def add_frame(self, frame: Dict[str, Any]) -> None:
        if self.recording:
            self.frames.append(frame)

    def start_playback(self) -> None:
        if self.frames:
            self.playback = True
            self.recording = False
            self.playback_index = 0

    def stop_playback(self) -> None:
        self.playback = False
        self.playback_index = 0

    def next_frame(self) -> Dict[str, Any]:
        if not self.frames:
            return {}
        frame = self.frames[self.playback_index]
        self.playback_index = (self.playback_index + 1) % len(self.frames)
        return frame
