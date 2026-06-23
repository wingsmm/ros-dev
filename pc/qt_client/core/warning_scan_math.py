from __future__ import annotations

import math
from typing import Iterable, Sequence

MIN_SCAN_RANGE_M = 0.25
FRONT_ARC_HALF_ANGLE_RAD = math.radians(40.0)


def compute_front_min_range(
    ranges: Sequence[float],
    angle_min: float,
    angle_increment: float,
    *,
    min_valid_range: float = MIN_SCAN_RANGE_M,
    front_half_angle_rad: float = FRONT_ARC_HALF_ANGLE_RAD,
) -> float:
    """Mirror Android WarningSystem front-sector shortest range."""
    if not ranges:
        return float("inf")

    shortest = float("inf")
    angle = float(angle_min)
    for value in ranges:
        distance = float(value)
        if (
            math.isfinite(distance)
            and distance > min_valid_range
            and distance < shortest
            and -front_half_angle_rad < angle < front_half_angle_rad
        ):
            shortest = distance
        angle += angle_increment
    return shortest


def collision_threshold(min_range_m: float, speed_mps: float) -> float:
    return float(min_range_m) * max(0.5, float(speed_mps))


def should_warn(
    front_min_m: float,
    *,
    enabled: bool,
    speed_mps: float,
    min_range_m: float,
    min_valid_range: float = MIN_SCAN_RANGE_M,
) -> bool:
    if not enabled:
        return False
    if front_min_m <= min_valid_range or not math.isfinite(front_min_m):
        return False
    if speed_mps <= -0.1:
        return False
    return front_min_m < collision_threshold(min_range_m, speed_mps)
