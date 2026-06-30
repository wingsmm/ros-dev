"""
地面感知 Overlay - 硬编码梯形绘制（deep-learning 风格）
与 GroundPerceptionOverlay 保持相同接口，便于无缝切换
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Optional, Tuple

from PyQt5.QtCore import QPointF, Qt
from PyQt5.QtGui import QColor, QImage, QPainter, QPen, QPolygonF

from core.camera_ground_config import GroundPerceptionConfig

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TrapezoidDrawResult:
    """单次 overlay 绘制摘要（与 OverlayDrawResult 接口兼容）"""

    corridor_drawn: bool
    corridor_vertices: int = 4
    raw_corridor_points: int = 4
    image_width: int = 0
    image_height: int = 0
    scale_x: float = 1.0
    scale_y: float = 1.0


class TrapezoidOverlay:
    """
    硬编码梯形 Overlay（deep-learning 风格）
    在图像底部绘制一个梯形表示"可行驶区域"
    不依赖相机标定参数，纯基于图像比例计算
    """

    # 颜色与几何方法保持一致，便于对比
    CORRIDOR_COLOR = QColor(255, 220, 0, 120)
    CORRIDOR_BORDER_COLOR = QColor(255, 255, 0, 240)
    OBSTACLE_COLOR = QColor(255, 80, 80, 200)
    TEXT_BG_COLOR = QColor(0, 0, 0, 160)

    def __init__(self, config: GroundPerceptionConfig) -> None:
        self.config = config
        self._method_logged = False

    def _trapezoid_for_image(
        self, width: int, height: int
    ) -> Tuple[QPolygonF, TrapezoidDrawResult]:
        """
        根据图像尺寸计算梯形四个顶点
        与 deep-learning 算法相同的比例逻辑
        """
        bottom_y_ratio = self.config.trapezoid_bottom_y_ratio
        top_y_ratio = self.config.trapezoid_top_y_ratio
        top_width_ratio = self.config.trapezoid_top_width_ratio

        # 底边位置（离底部的距离）
        bottom_offset = int(height * bottom_y_ratio)
        bottom_y = height - bottom_offset

        # 顶边位置
        top_y = int(height * top_y_ratio)

        # 顶边宽度
        top_half_width = int(width * top_width_ratio / 2)
        top_center_x = width // 2

        # 四个顶点（按多边形顺序：左下 -> 左上 -> 右上 -> 右下）
        poly = QPolygonF()
        poly.append(QPointF(0, bottom_y))           # 左下
        poly.append(QPointF(top_center_x - top_half_width, top_y))  # 左上
        poly.append(QPointF(top_center_x + top_half_width, top_y))  # 右上
        poly.append(QPointF(width, bottom_y))       # 右下

        result = TrapezoidDrawResult(
            corridor_drawn=True,
            corridor_vertices=4,
            raw_corridor_points=4,
            image_width=width,
            image_height=height,
            scale_x=1.0,
            scale_y=1.0,
        )

        if not self._method_logged:
            logger.info(
                "trapezoid overlay: ratio=(bottom_y=%.2f top_y=%.2f top_w=%.2f) "
                "coords=(bottom_y=%d top_y=%d top_half_w=%d) frame=%dx%d",
                bottom_y_ratio,
                top_y_ratio,
                top_width_ratio,
                bottom_y,
                top_y,
                top_half_width,
                width,
                height,
            )
            self._method_logged = True

        return poly, result

    def draw_overlay(
        self,
        image: QImage,
        *,
        draw_corridor: bool = True,
        obstacles: Optional[List[Tuple[int, int, int, int]]] = None,
        stair_lines: Optional[List[Tuple[int, int, int, int]]] = None,
        status_text: Optional[str] = None,
        ground_plane: object = None,
    ) -> Tuple[QImage, TrapezoidDrawResult]:
        """
        绘制 Overlay，接口与 GroundPerceptionOverlay 完全兼容
        ground_plane 参数被忽略（梯形方法不需要）
        """
        result = image.copy()
        painter = QPainter(result)
        painter.setRenderHint(QPainter.Antialiasing)

        draw_result = TrapezoidDrawResult(
            corridor_drawn=False,
            image_width=result.width(),
            image_height=result.height(),
        )

        if draw_corridor:
            corridor_poly, draw_result = self._trapezoid_for_image(
                result.width(), result.height()
            )

            # 绘制半透明填充
            painter.setBrush(self.CORRIDOR_COLOR)
            painter.setPen(Qt.NoPen)
            painter.drawPolygon(corridor_poly)

            # 绘制边框（3条线：左、上、右，底边在图像底部不显示）
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(self.CORRIDOR_BORDER_COLOR, 3))
            painter.drawPolyline(corridor_poly[:3])  # 左下 -> 左上 -> 右上
            painter.drawLine(corridor_poly[2], corridor_poly[3])  # 右上 -> 右下

        # 障碍物框（接口兼容，实际梯形模式下障碍检测不工作）
        if obstacles:
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(self.OBSTACLE_COLOR, 2))
            for x, y, w, h in obstacles:
                painter.drawRect(x, y, w, h)

        # 状态文本
        if status_text:
            painter.setPen(QColor(255, 255, 255, 255))
            rect = painter.fontMetrics().boundingRect(status_text)
            rect.moveTo(20, result.height() - 40)
            rect.adjust(-8, -4, 8, 4)
            painter.fillRect(rect, self.TEXT_BG_COLOR)
            painter.drawText(20, result.height() - 40, status_text)

        painter.end()
        return result, draw_result

    def draw_idle_screen(self, width: int, height: int) -> QImage:
        """绘制空闲状态屏幕，与 GroundPerceptionOverlay 相同接口"""
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

        font.setPointSize(12)
        font.setBold(False)
        painter.setFont(font)
        painter.setPen(QColor(100, 200, 255))
        painter.drawText(width // 2 - 80, height // 2 - 20, "绘制方法: 硬编码梯形")

        font.setPointSize(10)
        painter.setFont(font)
        painter.setPen(QColor(150, 150, 150))
        y = height // 2 + 20
        painter.drawText(50, y, f"底边位置比例: {self.config.trapezoid_bottom_y_ratio:.2f}")
        painter.drawText(50, y + 25, f"顶边位置比例: {self.config.trapezoid_top_y_ratio:.2f}")
        painter.drawText(50, y + 50, f"顶边宽度比例: {self.config.trapezoid_top_width_ratio:.2f}")

        painter.setPen(QColor(255, 180, 0))
        painter.drawText(50, y + 85, "说明: 无需相机标定，基于图像比例绘制")

        painter.end()
        return image

    def reset_session_logs(self) -> None:
        """重置会话日志标志"""
        self._method_logged = False

    def update_config(self) -> None:
        """配置更新时调用（接口兼容）"""
        self.reset_session_logs()
