"""Single source of truth for robot TF frames and laser extrinsic (xtark MEC)."""

from __future__ import annotations

import math

# ROS2 / Qt / RViz2 统一约定：odom -> base_link -> laser
ODOM_FRAME = "odom"
BASE_FRAME = "base_link"
LASER_FRAME = "laser"

# ROS2 image topic (matches qt_stack web_video_server preview topic name)
CAMERA_ROS_TOPIC = "/camera/image_raw"
CAMERA_FRAME = "camera_link"

# Static extrinsic: base_link -> camera_link (m, rad); placeholder until calibrated
CAMERA_X = 0.10
CAMERA_Y = 0.0
CAMERA_Z = 0.20
CAMERA_ROLL = 0.0
CAMERA_PITCH = 0.0
CAMERA_YAW = 0.0

# Static extrinsic: base_link -> laser (m, rad)
LASER_X = 0.05
LASER_Y = 0.0
LASER_Z = 0.10
LASER_ROLL = 0.0
LASER_PITCH = 0.0
LASER_YAW = math.pi


def tf_chain_line() -> str:
    return f"{ODOM_FRAME} → {BASE_FRAME} → {LASER_FRAME} / {CAMERA_FRAME}"


def camera_extrinsic_line() -> str:
    yaw_deg = math.degrees(CAMERA_YAW)
    return (
        f"camera 外参: x={CAMERA_X:.2f} y={CAMERA_Y:.2f} z={CAMERA_Z:.2f} "
        f"yaw={yaw_deg:.0f}°"
    )


def laser_extrinsic_line() -> str:
    yaw_deg = math.degrees(LASER_YAW)
    return (
        f"laser 外参: x={LASER_X:.2f} y={LASER_Y:.2f} z={LASER_Z:.2f} "
        f"yaw={yaw_deg:.0f}°"
    )


def robot_frames_summary() -> str:
    return f"{ODOM_FRAME} → {BASE_FRAME} → {LASER_FRAME} | {laser_extrinsic_line()}"


def camera_frames_summary() -> str:
    return (
        f"{BASE_FRAME} → {CAMERA_FRAME} | {CAMERA_ROS_TOPIC} | "
        f"{camera_extrinsic_line()}"
    )


def frames_summary() -> str:
    return f"{robot_frames_summary()}; {camera_frames_summary()}"


def euler_to_quaternion(
    roll: float, pitch: float, yaw: float
) -> tuple[float, float, float, float]:
    cy = math.cos(yaw * 0.5)
    sy = math.sin(yaw * 0.5)
    cp = math.cos(pitch * 0.5)
    sp = math.sin(pitch * 0.5)
    cr = math.cos(roll * 0.5)
    sr = math.sin(roll * 0.5)
    qw = cr * cp * cy + sr * sp * sy
    qx = sr * cp * cy - cr * sp * sy
    qy = cr * sp * cy + sr * cp * sy
    qz = cr * cp * sy - sr * sp * cy
    return qx, qy, qz, qw
