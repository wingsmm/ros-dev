from __future__ import annotations

import math
from typing import Sequence

MIN_SCAN_RANGE_M = 0.25
FRONT_ARC_HALF_ANGLE_RAD = math.radians(40.0)


def compute_front_min_range(
    ranges: Sequence[float | None],
    angle_min: float,
    angle_increment: float,
    *,
    min_valid_range: float = MIN_SCAN_RANGE_M,
    front_half_angle_rad: float = FRONT_ARC_HALF_ANGLE_RAD,
    yaw_offset_rad: float = 0.0,
    x_offset_m: float = 0.0,
    y_offset_m: float = 0.0,
) -> float:
    """Mirror Android WarningSystem front-sector shortest range."""
    front_min, _hit_angle = compute_front_min_hit(
        ranges,
        angle_min,
        angle_increment,
        min_valid_range=min_valid_range,
        front_half_angle_rad=front_half_angle_rad,
        yaw_offset_rad=yaw_offset_rad,
        x_offset_m=x_offset_m,
        y_offset_m=y_offset_m,
    )
    return front_min


def compute_front_min_hit(
    ranges: Sequence[float | None],
    angle_min: float,
    angle_increment: float,
    *,
    min_valid_range: float = MIN_SCAN_RANGE_M,
    front_half_angle_rad: float = FRONT_ARC_HALF_ANGLE_RAD,
    yaw_offset_rad: float = 0.0,
    x_offset_m: float = 0.0,
    y_offset_m: float = 0.0,
) -> tuple[float, float]:
    """Return (front_min_m, scan_angle_rad) for the nearest base-front hit."""
    if not ranges:
        return float("inf"), float("nan")

    shortest = float("inf")
    hit_angle = float("nan")
    angle = float(angle_min)
    for value in ranges:
        if value is None:
            angle += angle_increment
            continue
        distance = float(value)
        local_x = distance * math.cos(angle + yaw_offset_rad) + x_offset_m
        local_y = distance * math.sin(angle + yaw_offset_rad) + y_offset_m
        base_bearing = math.atan2(local_y, local_x)
        if (
            math.isfinite(distance)
            and distance > min_valid_range
            and distance < shortest
            and -front_half_angle_rad < base_bearing < front_half_angle_rad
        ):
            shortest = distance
            hit_angle = angle
        angle += angle_increment
    return shortest, hit_angle


def collision_threshold(min_range_m: float, speed_mps: float = 0.0) -> float:
    del speed_mps
    return float(min_range_m)


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
