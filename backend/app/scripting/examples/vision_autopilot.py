import time


def _clamp(value: float, limit: float) -> float:
    return max(-limit, min(limit, value))


def run(sdk) -> None:
    hover_throttle = 0.6
    rate_limit = 0.6
    gain = 0.9
    search_yaw = 0.4
    yaw_gain = 1.2
    offset_limit = 0.12
    area_min = 0.0
    required_stable = 8
    stable_frames = 0

    while not sdk.should_stop():
        vision = sdk.get_vision(timeout=0.2)
        if not vision or not vision.get("target_visible"):
            sdk.set_command(hover_throttle, 0.0, 0.0, search_yaw)
            stable_frames = 0
            time.sleep(0.02)
            continue

        offset_x, offset_y = vision.get("target_offset", [0.0, 0.0])
        area = float(vision.get("target_area", 0.0))
        if (
            abs(offset_x) <= offset_limit
            and abs(offset_y) <= offset_limit
            and area >= area_min
        ):
            stable_frames += 1
        else:
            stable_frames = 0

        if stable_frames >= required_stable:
            sdk.set_command(hover_throttle, 0.0, 0.0, 0.0)
            time.sleep(0.05)
            continue

        yaw_rate = _clamp(offset_x * yaw_gain, rate_limit)
        pitch_rate = _clamp(-offset_y * gain, rate_limit)
        sdk.set_command(hover_throttle, pitch_rate, 0.0, yaw_rate)
        time.sleep(0.02)
