from __future__ import annotations

import math


def normalize_angle(angle: float) -> float:
    while angle > math.pi:
        angle -= 2.0 * math.pi
    while angle < -math.pi:
        angle += 2.0 * math.pi
    return angle


def align_pose_to_origin(
    x: float,
    y: float,
    yaw: float,
    x0: float,
    y0: float,
    yaw0: float,
) -> tuple[float, float, float]:
    """Translate and rotate a pose into the local frame of (x0, y0, yaw0)."""
    dx = x - x0
    dy = y - y0
    cos_neg = math.cos(-yaw0)
    sin_neg = math.sin(-yaw0)
    local_x = dx * cos_neg - dy * sin_neg
    local_y = dx * sin_neg + dy * cos_neg
    local_yaw = normalize_angle(yaw - yaw0)
    return local_x, local_y, local_yaw
