"""Resolve HTTP/MJPEG RGB preview URL for Qt camera page."""

from __future__ import annotations

from urllib.parse import urlparse

# ROS topic name on qt_stack web_video_server (also used as MJPEG query param)
QT_MJPEG_TOPIC = "/camera/image_raw"
ANDROID_CAMERA_TOPIC = "/image_raw/compressed"


def resolve_mjpeg_url(
    *,
    camera_url: str = "",
    master_uri: str = "",
    default_host: str = "192.168.1.169",
) -> str:
    if camera_url.strip():
        return camera_url.strip()
    parsed = urlparse(master_uri)
    host = parsed.hostname or default_host
    return f"http://{host}:8080/stream?topic={QT_MJPEG_TOPIC}"


def resolve_mjpeg_url_for_robot(robot) -> str:
    """robot: RobotInfo-like object with camera_url and master_uri."""
    return resolve_mjpeg_url(
        camera_url=getattr(robot, "camera_url", "") or "",
        master_uri=getattr(robot, "master_uri", "") or "",
    )
