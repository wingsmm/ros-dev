"""PC session-local odom origin: Qt display and ROS2 /odom share the same zero."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from core.odom_compare_math import align_pose_to_origin

ORIGIN_POLICY_LABEL = "session start（首帧 odom_base）"


@dataclass
class OdomSessionOrigin:
    x0: Optional[float] = None
    y0: Optional[float] = None
    yaw0: Optional[float] = None

    def is_set(self) -> bool:
        return self.x0 is not None and self.y0 is not None and self.yaw0 is not None

    def reset(self) -> None:
        self.x0 = None
        self.y0 = None
        self.yaw0 = None

    def ensure_from_message(self, msg: Dict[str, Any]) -> None:
        if self.is_set():
            return
        self.x0 = float(msg.get("x", 0.0))
        self.y0 = float(msg.get("y", 0.0))
        self.yaw0 = float(msg.get("yaw", 0.0))

    def snapshot(self) -> Tuple[float, float, float]:
        if not self.is_set():
            return 0.0, 0.0, 0.0
        assert self.x0 is not None and self.y0 is not None and self.yaw0 is not None
        return self.x0, self.y0, self.yaw0

    def relative_pose(self, msg: Dict[str, Any]) -> Tuple[float, float, float]:
        """Pose in session frame; locks origin on first odom_base if needed."""
        self.ensure_from_message(msg)
        x0, y0, yaw0 = self.snapshot()
        return align_pose_to_origin(
            float(msg.get("x", 0.0)),
            float(msg.get("y", 0.0)),
            float(msg.get("yaw", 0.0)),
            x0,
            y0,
            yaw0,
        )

    def format_summary(self) -> str:
        if not self.is_set():
            return "未锁定（等待首帧 odom_base）"
        x0, y0, yaw0 = self.snapshot()
        yaw_deg = math.degrees(yaw0)
        return f"x0={x0:.3f}, y0={y0:.3f}, yaw0={yaw_deg:.1f}°"
