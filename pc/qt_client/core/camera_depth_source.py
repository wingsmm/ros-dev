"""Depth data source configuration (xtark raw-depth HTTP on port 8082)."""

from __future__ import annotations

import os
from urllib.parse import urlparse
from dataclasses import dataclass

from core.camera_topics import (
    CAMERA_DEPTH_IMAGE_TOPIC,
    CAMERA_DEPTH_INFO_TOPIC,
    QT_MJPEG_DEPTH_TOPIC,
    QT_MJPEG_DEPTH_RAW_TOPIC,
)

DEPTH_HTTP_PORT = int(os.environ.get("XTARK_DEPTH_HTTP_PORT", "8082") or "8082")
DEPTH_HTTP_POLL_MS = int(os.environ.get("DEPTH_HTTP_POLL_MS", "200") or "200")
DEPTH_HTTP_TIMEOUT_S = float(os.environ.get("DEPTH_HTTP_TIMEOUT_S", "1.5") or "1.5")


def depth_http_base_url(*, master_uri: str = "", default_host: str = "192.168.1.169") -> str:
    configured = os.environ.get("XTARK_DEPTH_HTTP_BASE_URL", "").strip().rstrip("/")
    if configured:
        return configured
    host = urlparse(master_uri).hostname or os.environ.get("XTARK_HOST", default_host)
    return "http://%s:%d" % (host, DEPTH_HTTP_PORT)


@dataclass(frozen=True)
class DepthSourceConfig:
    image_topic: str = CAMERA_DEPTH_IMAGE_TOPIC
    camera_info_topic: str = CAMERA_DEPTH_INFO_TOPIC
    http_base_url: str = ""
    # Legacy fields keep the existing UI state machine inert. The HTTP raw
    # transport is the only enabled path; MJPEG depth fallback stays off.
    allow_mjpeg_fallback: bool = False
    raw_wait_s: float = 3.0
    mjpeg_wait_s: float = 3.0
    mjpeg_fallback_topics: tuple[str, ...] = (
        QT_MJPEG_DEPTH_TOPIC,
        QT_MJPEG_DEPTH_RAW_TOPIC,
    )
    min_depth_m: float = 0.2
    max_depth_m: float = 5.0
    http_poll_ms: int = DEPTH_HTTP_POLL_MS
    http_timeout_s: float = DEPTH_HTTP_TIMEOUT_S
    max_preview_fps: float = 10.0
    preview_downscale: int = 1
    @property
    def http_frame_url(self) -> str:
        return self.http_base_url.rstrip("/") + "/v1/depth/latest"

    @property
    def http_info_url(self) -> str:
        return self.http_base_url.rstrip("/") + "/v1/depth/camera_info"

    @classmethod
    def from_env(cls, *, master_uri: str = "") -> "DepthSourceConfig":
        max_fps = float(os.environ.get("DEPTH_PREVIEW_MAX_FPS", "4") or "4")
        if max_fps <= 0:
            max_fps = 4.0
        downscale = int(os.environ.get("DEPTH_PREVIEW_DOWNSCALE", "2") or "2")
        if downscale not in (1, 2, 4):
            downscale = 2
        poll_ms = int(os.environ.get("DEPTH_HTTP_POLL_MS", "0") or "0")
        if poll_ms <= 0:
            poll_ms = int(1000.0 / max_fps) + 80
        return cls(
            http_base_url=depth_http_base_url(master_uri=master_uri),
            max_preview_fps=max_fps,
            preview_downscale=downscale,
            http_poll_ms=max(120, poll_ms),
            http_timeout_s=max(0.5, DEPTH_HTTP_TIMEOUT_S),
        )
