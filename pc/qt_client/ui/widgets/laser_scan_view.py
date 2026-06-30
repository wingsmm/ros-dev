from __future__ import annotations

import math
import time
from typing import Optional

from PyQt5.QtCore import QPointF, QRectF, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import (
    QBrush,
    QColor,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPolygonF,
)
from PyQt5.QtWidgets import QCheckBox, QHBoxLayout, QPushButton, QWidget

from core.laser_scan_frame import LaserScanFrame
from core.robot_frames import LASER_X, LASER_Y, LASER_YAW
from core.laser_scan_geometry import (
    DEFAULT_PIXELS_PER_METER,
    clamp_pixels_per_meter,
    ros_to_screen,
    scan_point_to_local,
    world_to_robot_frame,
)

_STALE_SEC = 1.0
_ZOOM_FACTOR = 1.15
_SCAN_BACKGROUND = QColor(31, 34, 38)
_ANDROID_SCAN_BLUE = (0x37, 0x7D, 0xFA)
_ANDROID_ROBOT_BLUE = QColor(0x11, 0x33, 0xFF)
_ANDROID_ORIGIN_COLOR = QColor(0xCC, 0xCC, 0xDD)
_MAX_COLOR_DISTANCE_M = 10.0
_MAX_FAN_SECTORS = 240
_SCAN_POINT_SIZE = 10.0
_ORIGIN_SIZE = 32.0
_MIN_POINT_DISTANCE_SQUARED = 0.20

# Laser extrinsic: base_link -> laser (see core/robot_frames.py).

class LaserToolbar(QWidget):
    center_requested = pyqtSignal()
    heading_lock_changed = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self._center_btn = QPushButton("居中")
        self._center_btn.clicked.connect(self.center_requested.emit)
        layout.addWidget(self._center_btn)

        self._lock_checkbox = QCheckBox("锁定机器人朝向")
        self._lock_checkbox.setChecked(True)
        self._lock_checkbox.toggled.connect(self.heading_lock_changed.emit)
        layout.addWidget(self._lock_checkbox)

        layout.addStretch(1)

    def is_heading_locked(self) -> bool:
        return self._lock_checkbox.isChecked()


class LaserScanView(QWidget):
    """2D laser scan display with pan/zoom and heading lock."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._frame: Optional[LaserScanFrame] = None
        self._received_mono = 0.0
        self._odom_x = 0.0
        self._odom_y = 0.0
        self._odom_yaw = 0.0
        self._heading_locked = True
        self._unlocked_heading_reference = 0.0
        self._scan_detail = 1.0
        self._pixels_per_meter = DEFAULT_PIXELS_PER_METER
        self._pan_x = 0.0
        self._pan_y = 0.0
        self._dragging = False
        self._drag_last = QPointF()
        self._repaint_enabled = False
        self._last_stale_state = False
        self._warning_enabled = False
        self._warning_half_angle_rad = math.radians(40.0)
        self._warning_min_distance_m = 3.0
        self._warning_front_min_m = float("inf")
        self._warning_warn_amount = 0.0
        self._warning_hit_angle_rad = float("nan")
        self._stale_timer = QTimer(self)
        self._stale_timer.setInterval(250)
        self._stale_timer.timeout.connect(self._refresh_stale_state)
        self.setMinimumHeight(240)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)

    def is_scan_stale(self) -> bool:
        return self._is_stale()

    def set_warning_sector(
        self,
        enabled: bool,
        *,
        half_angle_rad: float = 0.0,
        min_distance_m: float = 3.0,
        front_min_m: float = float("inf"),
        warn_amount: float = 0.0,
        hit_angle_rad: float = float("nan"),
    ) -> None:
        self._warning_enabled = bool(enabled)
        self._warning_half_angle_rad = float(half_angle_rad)
        self._warning_min_distance_m = max(0.1, float(min_distance_m))
        self._warning_front_min_m = float(front_min_m)
        self._warning_warn_amount = max(0.0, min(1.0, float(warn_amount)))
        self._warning_hit_angle_rad = float(hit_angle_rad)
        if self._repaint_enabled:
            self.update()

    def set_repaint_enabled(self, enabled: bool) -> None:
        self._repaint_enabled = bool(enabled)
        if enabled:
            if not self._stale_timer.isActive():
                self._stale_timer.start()
            self._last_stale_state = self._is_stale()
            self.update()
        else:
            self._stale_timer.stop()

    def set_heading_locked(self, locked: bool) -> None:
        locked = bool(locked)
        if self._heading_locked and not locked:
            # Android freezes the current heading as the world-view reference
            # when camera following is disabled.
            self._unlocked_heading_reference = self._odom_yaw
        self._heading_locked = locked
        self.update()

    def set_scan_detail(self, detail: float) -> None:
        try:
            self._scan_detail = max(1.0, float(detail))
        except (TypeError, ValueError):
            self._scan_detail = 1.0
        if self._repaint_enabled:
            self.update()

    def center_view(self) -> None:
        self._pan_x = 0.0
        self._pan_y = 0.0
        self._pixels_per_meter = DEFAULT_PIXELS_PER_METER
        if not self._heading_locked:
            self._unlocked_heading_reference = self._odom_yaw
        self.update()

    def set_odom(self, x: float, y: float, yaw: float) -> None:
        self._odom_x = float(x)
        self._odom_y = float(y)
        self._odom_yaw = float(yaw)
        if self._repaint_enabled:
            self.update()

    def update_scan(self, frame: Optional[LaserScanFrame]) -> None:
        self._frame = frame
        if frame is not None:
            self._received_mono = time.monotonic()
            self._last_stale_state = False
        if self._repaint_enabled:
            self.update()

    def replay_last_scan(self) -> None:
        if self._frame is not None and self._repaint_enabled:
            self.update()

    def _is_stale(self) -> bool:
        if self._frame is None or self._received_mono <= 0.0:
            return False
        return (time.monotonic() - self._received_mono) > _STALE_SEC

    def _refresh_stale_state(self) -> None:
        if not self._repaint_enabled or self._frame is None:
            return
        stale = self._is_stale()
        if stale != self._last_stale_state:
            self._last_stale_state = stale
            self.update()

    def _center_point(self) -> tuple[float, float]:
        w = float(self.width())
        h = float(self.height())
        return w * 0.5 + self._pan_x, h * 0.5 + self._pan_y

    def _map_base_point(self, local_x: float, local_y: float) -> QPointF:
        cx, cy = self._center_point()
        sx, sy = ros_to_screen(local_x, local_y, cx, cy, self._pixels_per_meter)
        return QPointF(sx, sy)

    def _heading_delta(self) -> float:
        delta = self._odom_yaw - self._unlocked_heading_reference
        return math.atan2(math.sin(delta), math.cos(delta))

    def _map_scan_point(self, local_x: float, local_y: float) -> QPointF:
        if self._heading_locked:
            return self._map_base_point(local_x, local_y)
        delta = self._heading_delta()
        cos_delta = math.cos(delta)
        sin_delta = math.sin(delta)
        view_x = local_x * cos_delta - local_y * sin_delta
        view_y = local_x * sin_delta + local_y * cos_delta
        return self._map_base_point(view_x, view_y)

    def wheelEvent(self, event) -> None:
        delta = event.angleDelta().y()
        if delta == 0:
            return
        factor = _ZOOM_FACTOR if delta > 0 else 1.0 / _ZOOM_FACTOR
        self._pixels_per_meter = clamp_pixels_per_meter(
            self._pixels_per_meter * factor
        )
        self.update()
        event.accept()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._dragging = True
            self._drag_last = event.pos()
            event.accept()

    def mouseMoveEvent(self, event) -> None:
        if self._dragging:
            delta = event.pos() - self._drag_last
            self._drag_last = event.pos()
            self._pan_x += delta.x()
            self._pan_y += delta.y()
            self.update()
            event.accept()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._dragging = False
            event.accept()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = self.rect()

        painter.fillRect(rect, _SCAN_BACKGROUND)

        if self._frame is None:
            painter.setPen(QColor(105, 105, 105))
            painter.drawText(rect, Qt.AlignCenter, "等待激光数据")
            return

        if self._is_stale():
            painter.setPen(QColor(255, 180, 80))
            painter.drawText(rect, Qt.AlignCenter, "激光数据超时")
            return

        self._draw_warning_sector(painter)
        self._draw_scan(painter)
        self._draw_origin(painter)
        self._draw_robot(painter)

    @staticmethod
    def _scan_color(distance: float, alpha: int) -> QColor:
        """Mirror Android's near-red to far-blue LaserScan color ramp."""
        p = max(0.0, min(1.0, float(distance) / _MAX_COLOR_DISTANCE_M))
        base_r, base_g, base_b = _ANDROID_SCAN_BLUE
        red = int(round(p * base_r + (1.0 - p) * 255.0))
        green = int(round(p * base_g))
        blue = int(round(p * base_b))
        return QColor(red, green, blue, alpha)

    def _scan_segments(self):
        assert self._frame is not None
        raw_segments = []
        raw_segment = []
        angle = self._frame.angle_min
        for distance in self._frame.ranges:
            if distance is None:
                if raw_segment:
                    raw_segments.append(raw_segment)
                    raw_segment = []
            else:
                local_x, local_y = scan_point_to_local(
                    angle,
                    distance,
                    LASER_YAW,
                )
                local_x += LASER_X
                local_y += LASER_Y
                raw_segment.append(
                    (
                        self._map_scan_point(local_x, local_y),
                        distance,
                        local_x,
                        local_y,
                    )
                )
            angle += self._frame.angle_increment
        if raw_segment:
            raw_segments.append(raw_segment)

        # Keep the full-resolution point chains for the original Qt wall/fan
        # layer.  Android-style endpoint filtering is applied separately so
        # it cannot make the continuous wall outline sparse.
        wall_segments = [
            [(item[0], item[1]) for item in segment]
            for segment in raw_segments
        ]

        # Match Android LaserScanRenderer's spatial detail filter: higher
        # detail retains more endpoints, while first/last points remain.
        segments = []
        detail_squared = self._scan_detail * self._scan_detail
        for raw_segment in raw_segments:
            if len(raw_segment) <= 2:
                segments.append([(item[0], item[1]) for item in raw_segment])
                continue

            first = raw_segment[0]
            filtered = [(first[0], first[1])]
            previous_x = first[2]
            previous_y = first[3]
            for point, distance, local_x, local_y in raw_segment[1:-1]:
                scale = max(1.0, distance)
                threshold = (
                    scale / detail_squared
                ) * _MIN_POINT_DISTANCE_SQUARED
                delta_squared = (
                    (local_x - previous_x) ** 2
                    + (local_y - previous_y) ** 2
                )
                if delta_squared > threshold:
                    filtered.append((point, distance))
                    previous_x = local_x
                    previous_y = local_y

            last = raw_segment[-1]
            if filtered[-1][0] != last[0]:
                filtered.append((last[0], last[1]))
            segments.append(filtered)
        return segments, wall_segments

    def _draw_scan(self, painter: QPainter) -> None:
        assert self._frame is not None
        segments, wall_segments = self._scan_segments()
        cx, cy = self._center_point()
        center = QPointF(cx, cy)

        # Restore the original Qt presentation as the base layer: dark blue
        # scan sectors and a continuous bright-blue wall outline.  The newer
        # Android-style rays and endpoint squares are drawn on top.
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor(42, 75, 100, 105)))
        for segment in wall_segments:
            if len(segment) < 2:
                continue
            fan_path = QPainterPath()
            fan_path.moveTo(center)
            for point, _distance in segment:
                fan_path.lineTo(point)
            fan_path.closeSubpath()
            painter.drawPath(fan_path)

        # Android uses a smooth GL triangle fan. Limit the number of Qt fan
        # sectors while retaining its near-red / far-blue radial appearance.
        total_pairs = sum(max(0, len(segment) - 1) for segment in segments)
        fan_step = max(1, int(math.ceil(total_pairs / float(_MAX_FAN_SECTORS))))
        for segment in segments:
            for index in range(0, len(segment) - 1, fan_step):
                end_index = min(index + fan_step, len(segment) - 1)
                point_a, distance_a = segment[index]
                point_b, distance_b = segment[end_index]
                midpoint = QPointF(
                    (point_a.x() + point_b.x()) * 0.5,
                    (point_a.y() + point_b.y()) * 0.5,
                )
                gradient = QLinearGradient(center, midpoint)
                gradient.setColorAt(0.0, QColor(*_ANDROID_SCAN_BLUE, 20))
                gradient.setColorAt(
                    1.0,
                    self._scan_color((distance_a + distance_b) * 0.5, 34),
                )
                triangle = QPainterPath()
                triangle.moveTo(center)
                triangle.lineTo(point_a)
                triangle.lineTo(point_b)
                triangle.closeSubpath()
                painter.setPen(Qt.NoPen)
                painter.setBrush(QBrush(gradient))
                painter.drawPath(triangle)

                ray_color = self._scan_color(distance_a, 28)
                ray_pen = QPen(ray_color)
                ray_pen.setWidthF(0.8)
                painter.setPen(ray_pen)
                painter.drawLine(center, point_a)

        # Preserve the continuous wall-like outline that is clearer in the Qt
        # preview, but never bridge across invalid scan gaps.
        outline_path = QPainterPath()
        for segment in wall_segments:
            if not segment:
                continue
            outline_path.moveTo(segment[0][0])
            for point, _distance in segment[1:]:
                outline_path.lineTo(point)
        outline_pen = QPen(QColor(0x52, 0xC7, 0xFF, 245))
        outline_pen.setWidthF(1.8)
        painter.setPen(outline_pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(outline_path)

        # Android renders every retained laser endpoint as a square GL point.
        half_point = _SCAN_POINT_SIZE * 0.5
        for segment in segments:
            for point, distance in segment:
                painter.fillRect(
                    QRectF(
                        point.x() - half_point,
                        point.y() - half_point,
                        _SCAN_POINT_SIZE,
                        _SCAN_POINT_SIZE,
                    ),
                    self._scan_color(distance, 105),
                )

    def _draw_origin(self, painter: QPainter) -> None:
        # RobotPage supplies x/y relative to the first odom frame of the
        # current connection, mirroring Android RobotController startPos.
        if self._heading_locked:
            ox, oy = world_to_robot_frame(
                0.0, 0.0, self._odom_x, self._odom_y, self._odom_yaw
            )
        else:
            ox, oy = world_to_robot_frame(
                0.0,
                0.0,
                self._odom_x,
                self._odom_y,
                self._unlocked_heading_reference,
            )
        pt = self._map_base_point(ox, oy)
        half_origin = _ORIGIN_SIZE * 0.5
        painter.setPen(QPen(QColor(0xAA, 0xAA, 0xC0), 1))
        painter.setBrush(QBrush(_ANDROID_ORIGIN_COLOR))
        painter.drawRect(
            QRectF(
                pt.x() - half_origin,
                pt.y() - half_origin,
                _ORIGIN_SIZE,
                _ORIGIN_SIZE,
            )
        )

    def _draw_robot(self, painter: QPainter) -> None:
        cx, cy = self._center_point()
        # Match Android's concave five-vertex robot indicator rather than a
        # generic triangle. Forward is the pointed end at the top.
        triangle = QPolygonF(
            [
                QPointF(cx, cy - 30.0),
                QPointF(cx + 20.0, cy + 24.0),
                QPointF(cx, cy + 7.0),
                QPointF(cx - 20.0, cy + 24.0),
            ]
        )
        if not self._heading_locked:
            painter.save()
            painter.translate(cx, cy)
            painter.rotate(-math.degrees(self._heading_delta()))
            painter.translate(-cx, -cy)
            painter.setPen(QPen(QColor(0x08, 0x20, 0xCC), 1.5))
            painter.setBrush(QBrush(_ANDROID_ROBOT_BLUE))
            painter.drawPolygon(triangle)
            painter.restore()
            return

        painter.setPen(QPen(QColor(0x08, 0x20, 0xCC), 1.5))
        painter.setBrush(QBrush(_ANDROID_ROBOT_BLUE))
        painter.drawPolygon(triangle)

    def _draw_warning_sector(self, painter: QPainter) -> None:
        if not self._warning_enabled:
            return

        cx, cy = self._center_point()
        center = QPointF(cx, cy)
        half = self._warning_half_angle_rad
        radius_m = self._warning_min_distance_m
        steps = 32
        path = QPainterPath()
        path.moveTo(center)
        for index in range(steps + 1):
            bearing = -half + (2.0 * half) * (index / steps)
            base_x = radius_m * math.cos(bearing)
            base_y = radius_m * math.sin(bearing)
            path.lineTo(self._map_scan_point(base_x, base_y))
        path.closeSubpath()

        danger = self._warning_warn_amount >= 0.15
        if danger:
            fill = QColor(220, 40, 40, 72)
            border = QColor(220, 40, 40, 210)
        else:
            fill = QColor(55, 125, 250, 42)
            border = QColor(255, 200, 60, 110)

        painter.setPen(QPen(border, 1.6))
        painter.setBrush(QBrush(fill))
        painter.drawPath(path)

        front_min = self._warning_front_min_m
        if not math.isfinite(front_min) or front_min >= float("inf"):
            return
        if front_min > self._warning_min_distance_m:
            return

        if math.isfinite(self._warning_hit_angle_rad):
            local_x, local_y = scan_point_to_local(
                self._warning_hit_angle_rad,
                front_min,
                LASER_YAW,
            )
            local_x += LASER_X
            local_y += LASER_Y
        else:
            local_x, local_y = front_min, 0.0
        hit_pt = self._map_scan_point(local_x, local_y)
        painter.setPen(QPen(QColor(255, 40, 40), 2.0))
        painter.setBrush(QBrush(QColor(255, 60, 60, 220)))
        painter.drawEllipse(hit_pt, 7.0, 7.0)
        painter.setPen(QPen(QColor(255, 120, 120, 180), 1.2))
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(hit_pt, 11.0, 11.0)
