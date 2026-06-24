from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Tuple

from core.odom_compare_math import align_pose_to_origin, normalize_angle

Origin = Tuple[float, float, float]
Pose = Tuple[float, float, float]

_MAX_TRAJECTORY_POINTS = 2500
_MIN_POINT_DISTANCE_M = 0.01


class OdomStreamTracker:
    """Track one JSON odom stream: freshness, rate, zero frame, and trail."""

    def __init__(self, label: str, *, stale_sec: float = 1.0) -> None:
        self.label = label
        self.stale_sec = stale_sec
        self.visible = True
        self.last_msg: Optional[Dict[str, Any]] = None
        self.last_mono = 0.0
        self.origin: Optional[Origin] = None
        self.trajectory: List[Tuple[float, float]] = []
        self._stamp_history: List[float] = []

    def on_message(self, msg: Dict[str, Any]) -> None:
        self.last_msg = msg
        self.last_mono = time.monotonic()
        stamp_ms = float(msg.get("stamp_ms", 0.0))
        if stamp_ms > 0.0:
            self._stamp_history.append(stamp_ms)
            if len(self._stamp_history) > 20:
                self._stamp_history = self._stamp_history[-20:]

        if self.origin is None:
            return

        aligned = self.aligned_pose()
        if aligned is None:
            return
        self._append_trajectory_point((aligned[0], aligned[1]))

    def _append_trajectory_point(self, point: Tuple[float, float]) -> None:
        if self.trajectory:
            last_x, last_y = self.trajectory[-1]
            dx = point[0] - last_x
            dy = point[1] - last_y
            if dx * dx + dy * dy < _MIN_POINT_DISTANCE_M * _MIN_POINT_DISTANCE_M:
                return
        self.trajectory.append(point)
        if len(self.trajectory) <= _MAX_TRAJECTORY_POINTS:
            return
        overflow = len(self.trajectory) - _MAX_TRAJECTORY_POINTS
        # Keep the zero-origin anchor and drop the oldest interior samples.
        self.trajectory = [self.trajectory[0]] + self.trajectory[1 + overflow :]

    def raw_pose(self) -> Optional[Pose]:
        if self.last_msg is None:
            return None
        return (
            float(self.last_msg.get("x", 0.0)),
            float(self.last_msg.get("y", 0.0)),
            float(self.last_msg.get("yaw", 0.0)),
        )

    def aligned_pose(self) -> Optional[Pose]:
        raw = self.raw_pose()
        if raw is None or self.origin is None:
            return None
        x, y, yaw = raw
        x0, y0, yaw0 = self.origin
        return align_pose_to_origin(x, y, yaw, x0, y0, yaw0)

    def is_online(self) -> bool:
        return self.last_mono > 0.0

    def is_stale(self) -> bool:
        if not self.is_online():
            return True
        return (time.monotonic() - self.last_mono) > self.stale_sec

    def frequency_hz(self) -> float:
        if len(self._stamp_history) < 2:
            return 0.0
        dt = (self._stamp_history[-1] - self._stamp_history[0]) / 1000.0
        if dt <= 0.0:
            return 0.0
        return (len(self._stamp_history) - 1) / dt

    def ready_for_zero(self) -> bool:
        return self.last_msg is not None and not self.is_stale()

    def set_origin_from_current(self) -> bool:
        raw = self.raw_pose()
        if raw is None or self.is_stale():
            return False
        self.origin = raw
        self.trajectory = [(0.0, 0.0)]
        return True

    def clear_trajectory(self) -> None:
        self.trajectory = []
        aligned = self.aligned_pose()
        if aligned is not None:
            self.trajectory.append((aligned[0], aligned[1]))

    def reset(self) -> None:
        self.last_msg = None
        self.last_mono = 0.0
        self.origin = None
        self.trajectory = []
        self._stamp_history = []
