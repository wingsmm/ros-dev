"""Throttled client-side logging for JSON odom telemetry."""

from __future__ import annotations

import logging
import math
import threading
import time
from typing import Any, Dict

from core.logging_config import load_logging_settings

logger = logging.getLogger(__name__)

_STREAM_LABELS = {
    "odom_raw": "编码器",
    "odom_base": "融合",
    "odom_laser": "激光",
}


class OdomTelemetrySampler:
    """Sample each odom stream at most once per configured interval."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._last_mono: Dict[str, float] = {}
        self._enabled = False
        self._interval_sec = 1.0

    def configure(self, *, enabled: bool, interval_sec: float) -> None:
        with self._lock:
            self._enabled = enabled
            self._interval_sec = interval_sec

    def reset(self) -> None:
        with self._lock:
            self._last_mono.clear()

    def maybe_log(self, stream: str, msg: Dict[str, Any]) -> None:
        now = time.monotonic()
        with self._lock:
            if not self._enabled:
                return
            last = self._last_mono.get(stream, 0.0)
            if now - last < self._interval_sec:
                return
            self._last_mono[stream] = now

        x = float(msg.get("x", 0.0))
        y = float(msg.get("y", 0.0))
        yaw = float(msg.get("yaw", 0.0))
        vx = float(msg.get("linear_x", 0.0))
        vy = float(msg.get("linear_y", 0.0))
        wz = float(msg.get("angular_z", 0.0))
        stamp_ms = int(msg.get("stamp_ms", 0) or 0)
        label = _STREAM_LABELS.get(stream, stream)
        logger.info(
            "odom %s (%s) x=%.3f y=%.3f yaw_deg=%+.1f "
            "vx=%.3f vy=%.3f wz=%.3f stamp_ms=%s",
            stream,
            label,
            x,
            y,
            math.degrees(yaw),
            vx,
            vy,
            wz,
            stamp_ms,
        )


_sampler = OdomTelemetrySampler()


def configure_odom_telemetry(*, enabled: bool, interval_sec: float) -> None:
    _sampler.configure(enabled=enabled, interval_sec=interval_sec)


def reload_odom_telemetry_settings() -> None:
    """Re-read .env / environment and apply odom sampling settings."""
    settings = load_logging_settings()
    configure_odom_telemetry(
        enabled=settings.odom_log_enabled,
        interval_sec=settings.odom_log_interval_sec,
    )


def maybe_log_odom(stream: str, msg: Dict[str, Any]) -> None:
    _sampler.maybe_log(stream, msg)


def reset_odom_telemetry_log() -> None:
    _sampler.reset()
