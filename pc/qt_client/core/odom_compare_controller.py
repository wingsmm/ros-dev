from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from PyQt5.QtCore import QObject, pyqtSignal

from core.odom_compare_math import normalize_angle
from core.odom_stream_tracker import OdomStreamTracker, Pose

STREAM_ODOM = "odom"
STREAM_RAW = "odom_raw"
STREAM_LASER = "odom_laser"


@dataclass(frozen=True)
class StreamSnapshot:
    key: str
    label: str
    online: bool
    stale: bool
    frequency_hz: float
    visible: bool
    has_origin: bool
    raw_pose: Optional[Pose]
    aligned_pose: Optional[Pose]
    trajectory: Tuple[Tuple[float, float], ...]


@dataclass(frozen=True)
class CompareSnapshot:
    streams: Dict[str, StreamSnapshot]
    zero_pending: bool
    zero_status: str
    delta_xy_m: Optional[float]
    delta_yaw_deg: Optional[float]


class OdomCompareController(QObject):
    """Owns three odom streams for the compare page only."""

    state_changed = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._streams = {
            STREAM_RAW: OdomStreamTracker("编码器 /odom_raw"),
            STREAM_ODOM: OdomStreamTracker("融合 /odom"),
            STREAM_LASER: OdomStreamTracker("激光 /odom_laser"),
        }
        self._zero_pending = False
        self._auto_zero_armed = True
        self._zero_status = "等待三路数据…"

    def stream(self, key: str) -> OdomStreamTracker:
        return self._streams[key]

    def on_odom_base(self, msg: object) -> None:
        self._on_message(STREAM_ODOM, msg)

    def on_odom_raw(self, msg: object) -> None:
        self._on_message(STREAM_RAW, msg)

    def on_odom_laser(self, msg: object) -> None:
        self._on_message(STREAM_LASER, msg)

    def _on_message(self, key: str, msg: object) -> None:
        if not isinstance(msg, dict):
            return
        tracker = self._streams[key]
        tracker.on_message(msg)
        if self._zero_pending and self._all_ready_for_zero():
            self._apply_zero(manual=True)
        else:
            self._try_auto_zero()
        self.state_changed.emit()

    def try_auto_zero(self) -> None:
        """Re-attempt auto zero after page activate or session replay."""
        self._try_auto_zero()
        self.state_changed.emit()

    def _try_auto_zero(self) -> None:
        if not self._auto_zero_armed or self._is_zeroed():
            return
        if not self._all_ready_for_zero():
            self._zero_status = "等待三路数据…"
            return
        self._apply_zero(manual=False)

    def _is_zeroed(self) -> bool:
        return all(tracker.origin is not None for tracker in self._streams.values())

    def request_zero(self) -> None:
        if self._all_ready_for_zero():
            self._apply_zero(manual=True)
            return
        self._zero_pending = True
        self._auto_zero_armed = False
        self._zero_status = "等待三路数据到齐（请保持小车静止）"
        self.state_changed.emit()

    def clear_trajectories(self) -> None:
        for tracker in self._streams.values():
            tracker.clear_trajectory()
        self.state_changed.emit()

    def set_visible(self, key: str, visible: bool) -> None:
        self._streams[key].visible = bool(visible)
        self.state_changed.emit()

    def reset_all(self) -> None:
        self._zero_pending = False
        self._auto_zero_armed = True
        self._zero_status = "等待三路数据…"
        for tracker in self._streams.values():
            tracker.reset()
        self.state_changed.emit()

    def snapshot(self) -> CompareSnapshot:
        stream_snaps = {
            key: StreamSnapshot(
                key=key,
                label=tracker.label,
                online=tracker.is_online(),
                stale=tracker.is_stale(),
                frequency_hz=tracker.frequency_hz(),
                visible=tracker.visible,
                has_origin=tracker.origin is not None,
                raw_pose=tracker.raw_pose(),
                aligned_pose=tracker.aligned_pose(),
                trajectory=tuple(tracker.trajectory),
            )
            for key, tracker in self._streams.items()
        }
        delta_xy, delta_yaw = self._delta_laser_minus_odom()
        return CompareSnapshot(
            streams=stream_snaps,
            zero_pending=self._zero_pending,
            zero_status=self._zero_status,
            delta_xy_m=delta_xy,
            delta_yaw_deg=delta_yaw,
        )

    def _all_ready_for_zero(self) -> bool:
        return all(tracker.ready_for_zero() for tracker in self._streams.values())

    def _apply_zero(self, *, manual: bool) -> None:
        if not self._all_ready_for_zero():
            return
        ok = all(tracker.set_origin_from_current() for tracker in self._streams.values())
        self._zero_pending = False
        self._auto_zero_armed = False
        if not ok:
            self._zero_status = "归零失败"
        elif manual:
            self._zero_status = "已归零"
        else:
            self._zero_status = "已自动归零"
        self.state_changed.emit()

    def _delta_laser_minus_odom(self) -> Tuple[Optional[float], Optional[float]]:
        laser = self._streams[STREAM_LASER].aligned_pose()
        odom = self._streams[STREAM_ODOM].aligned_pose()
        if laser is None or odom is None:
            return None, None
        dx = laser[0] - odom[0]
        dy = laser[1] - odom[1]
        delta_xy = (dx * dx + dy * dy) ** 0.5
        delta_yaw = normalize_angle(laser[2] - odom[2])
        return delta_xy, delta_yaw * 180.0 / 3.141592653589793
