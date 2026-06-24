from __future__ import annotations

import math
from typing import Dict, Optional, Tuple

from PyQt5.QtCore import QPointF, QRectF, Qt, pyqtSignal
from PyQt5.QtGui import QBrush, QColor, QPainter, QPen, QPolygonF
from PyQt5.QtWidgets import (
    QCheckBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.laser_scan_geometry import (
    DEFAULT_PIXELS_PER_METER,
    clamp_pixels_per_meter,
    ros_to_screen,
)
from core.odom_compare_controller import (
    STREAM_LASER,
    STREAM_ODOM,
    STREAM_RAW,
    CompareSnapshot,
    StreamSnapshot,
)

_ZOOM_FACTOR = 1.15
_BACKGROUND = QColor(31, 34, 38)
_ORIGIN_COLOR = QColor(0xCC, 0xCC, 0xDD)
_STREAM_COLORS = {
    STREAM_RAW: QColor(0x99, 0x99, 0x99),
    STREAM_ODOM: QColor(0x11, 0x33, 0xFF),
    STREAM_LASER: QColor(0xFF, 0x88, 0x00),
}
_STREAM_LABELS = {
    STREAM_RAW: "编码器",
    STREAM_ODOM: "融合",
    STREAM_LASER: "激光",
}


class OdomCompareToolbar(QWidget):
    zero_requested = pyqtSignal()
    clear_requested = pyqtSignal()
    center_requested = pyqtSignal()
    visibility_changed = pyqtSignal(str, bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._status_labels: Dict[str, QLabel] = {}
        self._pose_labels: Dict[str, QLabel] = {}
        self._visibility_boxes: Dict[str, QCheckBox] = {}
        self._delta_label = QLabel("Δ(激光-融合): --")
        self._zero_status = QLabel("等待三路数据…")
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)

        action_row = QHBoxLayout()
        action_row.setSpacing(8)
        for text, slot in (
            ("重新归零", self.zero_requested.emit),
            ("清除轨迹", self.clear_requested.emit),
            ("居中", self.center_requested.emit),
        ):
            btn = QPushButton(text)
            btn.clicked.connect(slot)
            action_row.addWidget(btn)
        action_row.addStretch(1)
        self._zero_status.setStyleSheet("color: #666;")
        action_row.addWidget(self._zero_status)
        root.addLayout(action_row)

        status_grid = QGridLayout()
        status_grid.setHorizontalSpacing(12)
        status_grid.setVerticalSpacing(4)
        headers = ("数据源", "在线", "频率", "超时", "x", "y", "yaw°", "显示")
        for col, title in enumerate(headers):
            label = QLabel(title)
            label.setStyleSheet("font-weight: 600; color: #444;")
            status_grid.addWidget(label, 0, col)

        for row, key in enumerate((STREAM_RAW, STREAM_ODOM, STREAM_LASER), start=1):
            status_grid.addWidget(QLabel(_STREAM_LABELS[key]), row, 0)
            online = QLabel("--")
            pose_x = QLabel("--")
            pose_y = QLabel("--")
            pose_yaw = QLabel("--")
            freq = QLabel("--")
            stale = QLabel("--")
            box = QCheckBox()
            box.setChecked(True)
            box.toggled.connect(
                lambda checked, stream=key: self.visibility_changed.emit(
                    stream, checked
                )
            )
            self._status_labels[key] = online
            self._pose_labels[key] = pose_x
            self._pose_labels[f"{key}_y"] = pose_y
            self._pose_labels[f"{key}_yaw"] = pose_yaw
            self._pose_labels[f"{key}_freq"] = freq
            self._pose_labels[f"{key}_stale"] = stale
            self._visibility_boxes[key] = box
            status_grid.addWidget(online, row, 1)
            status_grid.addWidget(freq, row, 2)
            status_grid.addWidget(stale, row, 3)
            status_grid.addWidget(pose_x, row, 4)
            status_grid.addWidget(pose_y, row, 5)
            status_grid.addWidget(pose_yaw, row, 6)
            status_grid.addWidget(box, row, 7)
        root.addLayout(status_grid)

        self._delta_label.setStyleSheet("color: #333;")
        root.addWidget(self._delta_label)

        note = QLabel(
            "/odom_laser 也是估计值，不是真值；三路不一致只能说明估计器存在差异。"
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #777; font-size: 12px;")
        root.addWidget(note)

    def update_snapshot(self, snapshot: CompareSnapshot) -> None:
        self._zero_status.setText(snapshot.zero_status)
        for key, stream in snapshot.streams.items():
            online = self._status_labels.get(key)
            if online is not None:
                online.setText("是" if stream.online else "否")
                online.setStyleSheet(
                    "color: #2e7d32;" if stream.online else "color: #c62828;"
                )
            freq = self._pose_labels.get(f"{key}_freq")
            if freq is not None:
                freq.setText(f"{stream.frequency_hz:.1f} Hz" if stream.online else "--")
            stale = self._pose_labels.get(f"{key}_stale")
            if stale is not None:
                if not stream.online:
                    stale.setText("--")
                    stale.setStyleSheet("")
                elif stream.stale:
                    stale.setText("是")
                    stale.setStyleSheet("color: #c62828; font-weight: 600;")
                else:
                    stale.setText("否")
                    stale.setStyleSheet("color: #2e7d32;")
            pose = stream.aligned_pose if stream.has_origin else stream.raw_pose
            pose_x = self._pose_labels.get(key)
            pose_y = self._pose_labels.get(f"{key}_y")
            pose_yaw = self._pose_labels.get(f"{key}_yaw")
            if pose is None:
                if pose_x is not None:
                    pose_x.setText("--")
                if pose_y is not None:
                    pose_y.setText("--")
                if pose_yaw is not None:
                    pose_yaw.setText("--")
            else:
                if pose_x is not None:
                    pose_x.setText(f"{pose[0]:+.3f}")
                if pose_y is not None:
                    pose_y.setText(f"{pose[1]:+.3f}")
                if pose_yaw is not None:
                    pose_yaw.setText(f"{math.degrees(pose[2]):+.1f}")

        if snapshot.delta_xy_m is None or snapshot.delta_yaw_deg is None:
            self._delta_label.setText("Δ(激光-融合): --")
        else:
            self._delta_label.setText(
                "Δ(激光-融合): "
                f"位置 {snapshot.delta_xy_m:.3f} m, "
                f"角度 {snapshot.delta_yaw_deg:+.1f}°"
            )


class OdomCompareView(QWidget):
    """Shared canvas for three aligned odometry trails."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._snapshot: Optional[CompareSnapshot] = None
        self._pixels_per_meter = DEFAULT_PIXELS_PER_METER
        self._pan_x = 0.0
        self._pan_y = 0.0
        self._dragging = False
        self._drag_last = QPointF()
        self._repaint_enabled = False
        self.setMinimumHeight(280)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)

    def set_repaint_enabled(self, enabled: bool) -> None:
        self._repaint_enabled = bool(enabled)
        if enabled:
            self.update()

    def center_view(self) -> None:
        self._pan_x = 0.0
        self._pan_y = 0.0
        self._pixels_per_meter = DEFAULT_PIXELS_PER_METER
        self.update()

    def update_snapshot(self, snapshot: CompareSnapshot) -> None:
        self._snapshot = snapshot
        if self._repaint_enabled:
            self.update()

    def _center_point(self) -> tuple[float, float]:
        return (
            float(self.width()) * 0.5 + self._pan_x,
            float(self.height()) * 0.5 + self._pan_y,
        )

    def _map_point(self, local_x: float, local_y: float) -> QPointF:
        cx, cy = self._center_point()
        sx, sy = ros_to_screen(local_x, local_y, cx, cy, self._pixels_per_meter)
        return QPointF(sx, sy)

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
        painter.fillRect(rect, _BACKGROUND)

        snapshot = self._snapshot
        if snapshot is None:
            painter.setPen(QColor(120, 120, 120))
            painter.drawText(rect, Qt.AlignCenter, "等待里程计数据")
            return

        if not any(stream.online for stream in snapshot.streams.values()):
            painter.setPen(QColor(120, 120, 120))
            painter.drawText(rect, Qt.AlignCenter, "等待里程计数据")
            return

        zeroed = all(stream.has_origin for stream in snapshot.streams.values())
        if not zeroed:
            painter.setPen(QColor(180, 180, 180))
            hint = snapshot.zero_status or "等待三路数据…"
            painter.drawText(rect, Qt.AlignCenter, hint)
            return

        self._draw_origin_marker(painter)
        for key in (STREAM_RAW, STREAM_ODOM, STREAM_LASER):
            stream = snapshot.streams[key]
            if not stream.visible or not stream.has_origin or not stream.online:
                continue
            color = _STREAM_COLORS[key]
            self._draw_trajectory(painter, stream, color, dimmed=stream.stale)
            if not stream.stale:
                self._draw_pose_arrow(painter, stream, color)

    def _draw_origin_marker(self, painter: QPainter) -> None:
        pt = self._map_point(0.0, 0.0)
        size = 18.0
        painter.setPen(QPen(QColor(0xAA, 0xAA, 0xC0), 1))
        painter.setBrush(QBrush(_ORIGIN_COLOR))
        painter.drawRect(
            QRectF(pt.x() - size * 0.5, pt.y() - size * 0.5, size, size)
        )

    def _draw_trajectory(
        self,
        painter: QPainter,
        stream: StreamSnapshot,
        color: QColor,
        *,
        dimmed: bool = False,
    ) -> None:
        if len(stream.trajectory) < 2:
            return
        draw_color = QColor(color)
        if dimmed:
            draw_color.setAlpha(140)
        pen = QPen(draw_color, 2.0)
        if dimmed:
            pen.setStyle(Qt.DashLine)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        first = self._map_point(stream.trajectory[0][0], stream.trajectory[0][1])
        for x, y in stream.trajectory[1:]:
            point = self._map_point(x, y)
            painter.drawLine(first, point)
            first = point

    def _draw_pose_arrow(
        self, painter: QPainter, stream: StreamSnapshot, color: QColor
    ) -> None:
        pose = stream.aligned_pose
        if pose is None:
            return
        center = self._map_point(pose[0], pose[1])
        painter.save()
        painter.translate(center)
        painter.rotate(-math.degrees(pose[2]))
        triangle = QPolygonF(
            [
                QPointF(0.0, -16.0),
                QPointF(12.0, 12.0),
                QPointF(0.0, 4.0),
                QPointF(-12.0, 12.0),
            ]
        )
        painter.setPen(QPen(color.darker(120), 1.2))
        painter.setBrush(QBrush(color))
        painter.drawPolygon(triangle)
        painter.restore()
