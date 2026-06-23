from __future__ import annotations

import math

DEFAULT_PIXELS_PER_METER = 80.0
MIN_PIXELS_PER_METER = 20.0
MAX_PIXELS_PER_METER = 400.0


def clamp_pixels_per_meter(value: float) -> float:
    return max(MIN_PIXELS_PER_METER, min(MAX_PIXELS_PER_METER, float(value)))


def ros_to_screen(
    local_x: float,
    local_y: float,
    center_x: float,
    center_y: float,
    pixels_per_meter: float,
) -> tuple[float, float]:
    """Map ROS base frame (x forward, y left) to screen coordinates."""
    screen_x = center_x - local_y * pixels_per_meter
    screen_y = center_y - local_x * pixels_per_meter
    return screen_x, screen_y


def world_to_robot_frame(
    world_x: float,
    world_y: float,
    robot_x: float,
    robot_y: float,
    robot_yaw: float,
) -> tuple[float, float]:
    dx = world_x - robot_x
    dy = world_y - robot_y
    cos_yaw = math.cos(robot_yaw)
    sin_yaw = math.sin(robot_yaw)
    local_x = dx * cos_yaw + dy * sin_yaw
    local_y = -dx * sin_yaw + dy * cos_yaw
    return local_x, local_y


def scan_point_to_local(
    angle: float,
    distance: float,
    yaw_offset: float = 0.0,
) -> tuple[float, float]:
    total = angle + yaw_offset
    return distance * math.cos(total), distance * math.sin(total)
