"""RGB-D camera ROS topic names — single source for Qt camera module Phase 1."""

from __future__ import annotations

from core.robot_frames import CAMERA_ROS_TOPIC

# RGB (matches qt_stack web_video_server preview)
CAMERA_RGB_TOPIC = CAMERA_ROS_TOPIC

# Depth camera (xtark astra / Orbbec when DEPTH_CAMERA_ENABLE=1)
CAMERA_DEPTH_IMAGE_TOPIC = "/camera/depth/image_raw"
CAMERA_DEPTH_INFO_TOPIC = "/camera/depth/camera_info"
CAMERA_DEPTH_POINTS_TOPIC = "/camera/depth_registered/points"
CAMERA_SCAN_DEPTH_TOPIC = "/camera/scan_depth"

# Main navigation laser — must stay independent from depth scan
MAIN_SCAN_TOPIC = "/scan"

# xtark fallback MJPEG candidates. Prefer pseudo-color preview when available;
# raw depth is a second fallback for PROFILE=camera_raw where preview is skipped.
QT_MJPEG_DEPTH_TOPIC = "/camera/depth/preview"
QT_MJPEG_DEPTH_RAW_TOPIC = CAMERA_DEPTH_IMAGE_TOPIC

# Topics shown in ROS2 diagnostic panel (Phase 1: status only, no nav coupling)
CAMERA_DIAGNOSTIC_TOPICS: tuple[str, ...] = (
    CAMERA_RGB_TOPIC,
    CAMERA_DEPTH_IMAGE_TOPIC,
    CAMERA_DEPTH_INFO_TOPIC,
    CAMERA_DEPTH_POINTS_TOPIC,
    CAMERA_SCAN_DEPTH_TOPIC,
)

# Topics probed by ROS2 diagnostic worker (includes main /scan for comparison)
CAMERA_PROBE_TOPICS: tuple[str, ...] = CAMERA_DIAGNOSTIC_TOPICS + (MAIN_SCAN_TOPIC,)
