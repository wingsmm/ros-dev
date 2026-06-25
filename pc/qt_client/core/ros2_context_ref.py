"""Shared rclpy init/shutdown so robot and camera bridges can run independently."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_refcount = 0


def acquire_rclpy() -> None:
    global _refcount
    import rclpy

    if not rclpy.ok():
        rclpy.init()
        logger.debug("rclpy.init()")
    _refcount += 1


def release_rclpy() -> None:
    global _refcount
    import rclpy

    if _refcount <= 0:
        return
    _refcount -= 1
    if _refcount == 0 and rclpy.ok():
        rclpy.shutdown()
        logger.debug("rclpy.shutdown()")
