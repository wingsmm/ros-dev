"""Depth data source configuration (ROS2 topics on PC/WSL)."""

from __future__ import annotations

import os
from dataclasses import dataclass

from core.camera_topics import (
    CAMERA_DEPTH_IMAGE_TOPIC,
    CAMERA_DEPTH_INFO_TOPIC,
    QT_MJPEG_DEPTH_TOPIC,
    QT_MJPEG_DEPTH_RAW_TOPIC,
)

# Seconds to wait for PC raw depth before trying MJPEG fallback.
DEPTH_RAW_WAIT_S = float(os.environ.get("DEPTH_RAW_WAIT_S", "3") or "3")
DEPTH_MJPEG_WAIT_S = float(os.environ.get("DEPTH_MJPEG_WAIT_S", "3") or "3")


def depth_mjpeg_fallback_enabled() -> bool:
    """MJPEG /camera/depth/preview after raw wait (default on; set XTARK_DEPTH_MJPEG_FALLBACK=0 to disable)."""
    raw = os.environ.get("XTARK_DEPTH_MJPEG_FALLBACK", "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def depth_mjpeg_fallback_topics() -> tuple[str, ...]:
    """Ordered MJPEG fallback topics.

    Default tries xtark pseudo-color preview first, then raw depth through
    web_video_server. The raw fallback lets PROFILE=camera_raw still display
    something when ROS1->ROS2 depth bridging is not available.
    """
    raw = os.environ.get(
        "DEPTH_MJPEG_FALLBACK_TOPICS",
        f"{QT_MJPEG_DEPTH_TOPIC},{QT_MJPEG_DEPTH_RAW_TOPIC}",
    )
    topics = tuple(t.strip() for t in raw.split(",") if t.strip())
    return topics or (QT_MJPEG_DEPTH_TOPIC, QT_MJPEG_DEPTH_RAW_TOPIC)


@dataclass(frozen=True)
class DepthSourceConfig:
    image_topic: str = CAMERA_DEPTH_IMAGE_TOPIC
    camera_info_topic: str = CAMERA_DEPTH_INFO_TOPIC
    mjpeg_fallback_topic: str = QT_MJPEG_DEPTH_TOPIC
    mjpeg_fallback_topics: tuple[str, ...] = (
        QT_MJPEG_DEPTH_TOPIC,
        QT_MJPEG_DEPTH_RAW_TOPIC,
    )
    min_depth_m: float = 0.2
    max_depth_m: float = 5.0
    spin_interval_ms: int = 20
    max_preview_fps: float = 10.0
    preview_downscale: int = 1
    allow_mjpeg_fallback: bool = True
    raw_wait_s: float = DEPTH_RAW_WAIT_S
    mjpeg_wait_s: float = DEPTH_MJPEG_WAIT_S

    @classmethod
    def from_env(cls) -> "DepthSourceConfig":
        max_fps = float(os.environ.get("DEPTH_PREVIEW_MAX_FPS", "10") or "10")
        if max_fps <= 0:
            max_fps = 10.0
        downscale = int(os.environ.get("DEPTH_PREVIEW_DOWNSCALE", "1") or "1")
        if downscale not in (1, 2):
            downscale = 1
        raw_wait = float(os.environ.get("DEPTH_RAW_WAIT_S", "3") or "3")
        mjpeg_wait = float(os.environ.get("DEPTH_MJPEG_WAIT_S", "8") or "8")
        return cls(
            max_preview_fps=max_fps,
            preview_downscale=downscale,
            allow_mjpeg_fallback=depth_mjpeg_fallback_enabled(),
            mjpeg_fallback_topics=depth_mjpeg_fallback_topics(),
            raw_wait_s=max(raw_wait, 0.5),
            mjpeg_wait_s=max(mjpeg_wait, 1.0),
        )
