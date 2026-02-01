from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple

import cv2
import numpy as np


@dataclass
class VisionResult:
    target_visible: bool
    target_offset: Tuple[float, float]
    target_area: float

    def to_dict(self) -> Dict[str, object]:
        return {
            "target_visible": self.target_visible,
            "target_offset": [self.target_offset[0], self.target_offset[1]],
            "target_area": self.target_area,
        }


class VisionProcessor:
    def __init__(self) -> None:
        self._lower_red_1 = np.array([0, 80, 80], dtype=np.uint8)
        self._upper_red_1 = np.array([10, 255, 255], dtype=np.uint8)
        self._lower_red_2 = np.array([170, 80, 80], dtype=np.uint8)
        self._upper_red_2 = np.array([180, 255, 255], dtype=np.uint8)

    def process(self, frame_bgr: np.ndarray) -> VisionResult:
        if frame_bgr is None or frame_bgr.size == 0:
            return VisionResult(False, (0.0, 0.0), 0.0)

        hsv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)
        mask1 = cv2.inRange(hsv, self._lower_red_1, self._upper_red_1)
        mask2 = cv2.inRange(hsv, self._lower_red_2, self._upper_red_2)
        mask = cv2.bitwise_or(mask1, mask2)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return VisionResult(False, (0.0, 0.0), 0.0)

        contour = max(contours, key=cv2.contourArea)
        area = float(cv2.contourArea(contour))
        if area <= 0.0:
            return VisionResult(False, (0.0, 0.0), 0.0)

        moments = cv2.moments(contour)
        if moments["m00"] == 0:
            return VisionResult(False, (0.0, 0.0), 0.0)

        cx = float(moments["m10"] / moments["m00"])
        cy = float(moments["m01"] / moments["m00"])
        h, w = frame_bgr.shape[:2]
        offset_x = (cx - w / 2) / (w / 2)
        offset_y = (cy - h / 2) / (h / 2)
        return VisionResult(True, (offset_x, offset_y), area)
