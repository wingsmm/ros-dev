"""
地面感知 Overlay 绘制模块
在 RGB 帧上绘制半透明灯带、障碍框、楼梯棱线

依赖：PyQt5 QPainter
"""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass
from typing import List, Optional, Tuple

from PyQt5.QtCore import QPointF, Qt
from PyQt5.QtGui import QColor, QImage, QPainter, QPen, QPolygonF

from core.camera_ground_config import GroundPerceptionConfig
from core.camera_ground_geometry import GroundPerceptionGeometry

logger = logging.getLogger(__name__)

_CORRIDOR_LOG_INTERVAL_S = 3.0


@dataclass(frozen=True)
class OverlayDrawResult:
    """单次 overlay 绘制摘要（供日志与后续 UI 统计）。"""

    corridor_drawn: bool
    corridor_vertices: int
    raw_corridor_points: int
    image_width: int
    image_height: int
    scale_x: float
    scale_y: float


class GroundPerceptionOverlay:
    """地面感知 Overlay 绘制器"""

    CORRIDOR_COLOR = QColor(255, 220, 0, 120)
    CORRIDOR_BORDER_COLOR = QColor(255, 255, 0, 240)
    OBSTACLE_COLOR = QColor(255, 80, 80, 200)
    STAIR_COLOR = QColor(255, 140, 0, 220)
    TEXT_BG_COLOR = QColor(0, 0, 0, 160)

    def __init__(self, config: GroundPerceptionConfig) -> None:
        self.config = config
        self.geometry = GroundPerceptionGeometry(config)
        self._last_corridor_log_mono = 0.0
        self._corridor_ok_logged = False

    def _corridor_polygon_for_image(
        self, width: int, height: int, ground_plane: object = None
    ) -> tuple[Optional[QPolygonF], OverlayDrawResult]:
        points = self.geometry.generate_corridor_polygon(ground_plane)
        ref_w = max(self.config.rgb_ref_width, 1)
        ref_h = max(self.config.rgb_ref_height, 1)
        sx = width / float(ref_w)
        sy = height / float(ref_h)

        meta = OverlayDrawResult(
            corridor_drawn=False,
            corridor_vertices=0,
            raw_corridor_points=len(points),
            image_width=width,
            image_height=height,
            scale_x=sx,
            scale_y=sy,
        )

        if len(points) < 3:
            self._log_corridor(
                "corridor polygon: insufficient 3D points raw=%d (check pitch/range)",
                len(points),
                level=logging.WARNING,
            )
            return None, meta

        poly = QPolygonF()
        for p in points:
            u = p.u * sx
            v = p.v * sy
            if not math.isfinite(u) or not math.isfinite(v):
                continue
            poly.append(QPointF(u, v))

        vertices = poly.size()
        if vertices < 3:
            self._log_corridor(
                "corridor polygon: clipped to %d vertices (frame=%dx%d scale=%.2f,%.2f "
                "raw=%d) — likely RGB/depth misalignment",
                vertices,
                width,
                height,
                sx,
                sy,
                len(points),
                level=logging.WARNING,
            )
            return None, meta

        drawn_meta = OverlayDrawResult(
            corridor_drawn=True,
            corridor_vertices=vertices,
            raw_corridor_points=len(points),
            image_width=width,
            image_height=height,
            scale_x=sx,
            scale_y=sy,
        )
        if not self._corridor_ok_logged:
            logger.info(
                "corridor polygon OK: vertices=%d frame=%dx%d scale=%.2f,%.2f "
                "raw_points=%d a=%.2fm range=%.1fm",
                vertices,
                width,
                height,
                sx,
                sy,
                len(points),
                self.config.corridor_width_m,
                self.config.overlay_max_range_m,
            )
            self._corridor_ok_logged = True
        else:
            self._log_corridor(
                "corridor polygon OK: vertices=%d frame=%dx%d scale=%.2f,%.2f",
                vertices,
                width,
                height,
                sx,
                sy,
            )
        return poly, drawn_meta

    def _log_corridor(self, msg: str, *args, level: int = logging.INFO) -> None:
        now = time.monotonic()
        if level >= logging.WARNING or (
            now - self._last_corridor_log_mono >= _CORRIDOR_LOG_INTERVAL_S
        ):
            logger.log(level, msg, *args)
            self._last_corridor_log_mono = now

    def draw_overlay(
        self,
        image: QImage,
        *,
        draw_corridor: bool = True,
        obstacles: Optional[List[Tuple[int, int, int, int]]] = None,
        stair_lines: Optional[List[Tuple[int, int, int, int]]] = None,
        status_text: Optional[str] = None,
        ground_plane: object = None,
    ) -> tuple[QImage, OverlayDrawResult]:
        result = image.copy()
        painter = QPainter(result)
        painter.setRenderHint(QPainter.Antialiasing)

        draw_meta = OverlayDrawResult(
            corridor_drawn=False,
            corridor_vertices=0,
            raw_corridor_points=0,
            image_width=result.width(),
            image_height=result.height(),
            scale_x=1.0,
            scale_y=1.0,
        )

        if draw_corridor:
            corridor_poly, draw_meta = self._corridor_polygon_for_image(
                result.width(), result.height(), ground_plane
            )
            if corridor_poly is not None:
                painter.setBrush(self.CORRIDOR_COLOR)
                painter.setPen(Qt.NoPen)
                painter.drawPolygon(corridor_poly)

                painter.setBrush(Qt.NoBrush)
                painter.setPen(QPen(self.CORRIDOR_BORDER_COLOR, 3))
                painter.drawPolygon(corridor_poly)

        if obstacles:
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(self.OBSTACLE_COLOR, 2))
            for x, y, w, h in obstacles:
                painter.drawRect(x, y, w, h)

        if stair_lines:
            painter.setPen(QPen(self.STAIR_COLOR, 3))
            for x1, y1, x2, y2 in stair_lines:
                painter.drawLine(x1, y1, x2, y2)

        if status_text:
            painter.setPen(QColor(255, 255, 255, 255))
            rect = painter.fontMetrics().boundingRect(status_text)
            rect.moveTo(20, result.height() - 40)
            rect.adjust(-8, -4, 8, 4)
            painter.fillRect(rect, self.TEXT_BG_COLOR)
            painter.drawText(20, result.height() - 40, status_text)

        painter.end()
        return result, draw_meta

    def draw_idle_screen(self, width: int, height: int) -> QImage:
        image = QImage(width, height, QImage.Format_RGB888)
        image.fill(QColor(30, 30, 40))

        painter = QPainter(image)
        painter.setRenderHint(QPainter.Antialiasing)

        font = painter.font()
        font.setPointSize(16)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor(200, 200, 200))
        painter.drawText(width // 2 - 60, height // 2 - 60, "地面感知模式")

        font.setPointSize(10)
        font.setBold(False)
        painter.setFont(font)
        painter.setPen(QColor(150, 150, 150))
        painter.drawText(
            width // 2 - 120,
            height // 2 - 20,
            "点击右侧「开始感知」按钮开始地面检测",
        )

        y = height // 2 + 30
        painter.setPen(QColor(100, 200, 255))
        painter.drawText(50, y, f"车体宽度 (a): {self.config.corridor_width_m:.2f} m")
        painter.drawText(
            50, y + 25, f"障碍检测 (b): {self.config.obstacle_range_m:.1f} m"
        )
        painter.drawText(
            50, y + 50, f"楼梯检测 (c): {self.config.stair_range_m:.1f} m"
        )
        painter.drawText(
            50, y + 75, f"灯带最大距离: {self.config.overlay_max_range_m:.1f} m"
        )

        painter.setPen(QColor(255, 180, 0))
        painter.drawText(50, y + 110, "标定状态: 使用默认外参（需实机标定）")

        painter.end()
        return image

    def reset_session_logs(self) -> None:
        """新感知会话开始时重置一次性日志标志。"""
        self._corridor_ok_logged = False
        self._last_corridor_log_mono = 0.0

    def update_config(self) -> None:
        self.geometry = GroundPerceptionGeometry(self.config)
        self.reset_session_logs()
