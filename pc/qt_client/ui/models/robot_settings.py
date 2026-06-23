from __future__ import annotations

from typing import Dict, Optional, Tuple

# Align with Android ManualSpeedPreferences / prefs.xml defaults.
MANUAL_LINEAR_MIN = 0.03
MANUAL_LINEAR_MAX = 0.30
MANUAL_ANGULAR_MIN = 0.05
MANUAL_ANGULAR_MAX = 0.80
DEFAULT_MANUAL_LINEAR = 0.12
DEFAULT_MANUAL_ANGULAR = 0.50

ANDROID_DEFAULTS: Dict[str, object] = {
    "joystick_topic": "/cmd_vel",
    "laser_topic": "/scan",
    "camera_topic": "/image_raw/compressed",
    "navsat_topic": "/navsat/fix",
    "odometry_topic": "/odom",
    "pose_topic": "/pose",
    "map_topic": "/map",
    "slam_xmin": -2.0,
    "slam_xmax": 2.0,
    "slam_ymin": -2.0,
    "slam_ymax": 2.0,
    "warning_enabled": False,
    "warning_safemode": True,
    "warning_beep": True,
    "warning_min_distance": 3.0,
    "laser_scan_detail": 1,
    "random_walk_range_proximity": 2.0,
    "reverse_laser_scan": False,
    "invert_x": False,
    "invert_y": False,
    "invert_angular_velocity": False,
    "manual_linear_speed": DEFAULT_MANUAL_LINEAR,
    "manual_angular_speed": DEFAULT_MANUAL_ANGULAR,
}


def clamp_manual_linear(value: float) -> float:
    return max(MANUAL_LINEAR_MIN, min(MANUAL_LINEAR_MAX, float(value)))


def clamp_manual_angular(value: float) -> float:
    return max(MANUAL_ANGULAR_MIN, min(MANUAL_ANGULAR_MAX, float(value)))


def validate_manual_speeds(
    linear: float, angular: float
) -> Optional[str]:
    if linear < MANUAL_LINEAR_MIN or linear > MANUAL_LINEAR_MAX:
        return (
            f"线速度须在 {MANUAL_LINEAR_MIN:.2f} ~ {MANUAL_LINEAR_MAX:.2f} m/s 之间。"
        )
    if angular < MANUAL_ANGULAR_MIN or angular > MANUAL_ANGULAR_MAX:
        return (
            f"角速度须在 {MANUAL_ANGULAR_MIN:.2f} ~ {MANUAL_ANGULAR_MAX:.2f} rad/s 之间。"
        )
    return None


def effective_manual_speeds(robot) -> Tuple[float, float]:
    linear = robot.manual_linear_speed
    angular = robot.manual_angular_speed
    if linear is None:
        linear = DEFAULT_MANUAL_LINEAR
    if angular is None:
        angular = DEFAULT_MANUAL_ANGULAR
    return clamp_manual_linear(linear), clamp_manual_angular(angular)
