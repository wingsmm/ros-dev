from __future__ import print_function

import math

MIN_SCAN_RANGE_M = 0.25
FRONT_ARC_HALF_ANGLE_RAD = math.radians(40.0)


def _is_finite(value):
    return value == value and abs(value) != float("inf")


def compute_front_min_range(ranges, angle_min, angle_increment):
    if not ranges:
        return float("inf")

    shortest = float("inf")
    angle = float(angle_min)
    for value in ranges:
        distance = float(value)
        if (
            _is_finite(distance)
            and distance > MIN_SCAN_RANGE_M
            and distance < shortest
            and -FRONT_ARC_HALF_ANGLE_RAD < angle < FRONT_ARC_HALF_ANGLE_RAD
        ):
            shortest = distance
        angle += angle_increment
    return shortest
