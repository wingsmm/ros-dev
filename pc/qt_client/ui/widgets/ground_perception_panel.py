"""
地面感知右侧控制面板

包含：
- 开始/停止按钮
- 状态显示
- 参数只读显示
- 统计信息（FPS、有效像素%等）
"""

from __future__ import annotations

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.camera_ground_config import GroundPerceptionConfig


class GroundPerceptionPanel(QWidget):
    """地面感知控制面板"""

    start_clicked = pyqtSignal()
    stop_clicked = pyqtSignal()
    open_3d_clicked = pyqtSignal()
    close_3d_clicked = pyqtSignal()
    method_changed = pyqtSignal(str)  # 参数: "geometric" 或 "trapezoid"

    def __init__(self, config: GroundPerceptionConfig, parent=None) -> None:
        super().__init__(parent)
        self.config = config
        self._is_running = False
        self._is_3d_open = False
        self._current_method = config.overlay_method  # 当前绘制方法
        self._build_ui()
        self._update_state()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        # 控制按钮区
        btn_group = QGroupBox("控制")
        btn_layout = QVBoxLayout(btn_group)
        btn_layout.setSpacing(6)

        # 开始/停止按钮行
        start_stop_row = QHBoxLayout()
        self._btn_start = QPushButton("开始感知")
        self._btn_start.clicked.connect(self._on_start_clicked)
        self._btn_start.setStyleSheet(
            "QPushButton { background-color: #2ecc71; color: white; padding: 8px; }"
        )
        start_stop_row.addWidget(self._btn_start)

        self._btn_stop = QPushButton("停止")
        self._btn_stop.clicked.connect(self._on_stop_clicked)
        self._btn_stop.setStyleSheet(
            "QPushButton { background-color: #e74c3c; color: white; padding: 8px; }"
        )
        start_stop_row.addWidget(self._btn_stop)
        btn_layout.addLayout(start_stop_row)

        # 3D 按钮行
        _3d_row = QHBoxLayout()
        self._btn_open_3d = QPushButton("打开 3D")
        self._btn_open_3d.clicked.connect(self._on_open_3d_clicked)
        self._btn_open_3d.setEnabled(False)  # Phase 1 禁用
        _3d_row.addWidget(self._btn_open_3d)

        self._btn_close_3d = QPushButton("关闭 3D")
        self._btn_close_3d.clicked.connect(self._on_close_3d_clicked)
        self._btn_close_3d.setEnabled(False)  # Phase 1 禁用
        _3d_row.addWidget(self._btn_close_3d)
        btn_layout.addLayout(_3d_row)

        root.addWidget(btn_group)

        # 绘制方法选择
        method_group = QGroupBox("绘制方法")
        method_layout = QVBoxLayout(method_group)

        self._method_combo = QComboBox()
        self._method_combo.setFocusPolicy(Qt.NoFocus)
        self._method_combo.addItem("几何投影（精确）", "geometric")
        self._method_combo.addItem("硬编码梯形（简单）", "trapezoid")
        self._method_combo.setCurrentIndex(
            0 if self._current_method == "geometric" else 1
        )
        self._method_combo.currentIndexChanged.connect(self._on_method_changed)
        method_layout.addWidget(self._method_combo)

        # 方法说明
        self._method_desc = QLabel()
        self._method_desc.setWordWrap(True)
        self._method_desc.setStyleSheet("color: #7f8c8d; font-size: 11px;")
        method_layout.addWidget(self._method_desc)
        self._update_method_desc()

        root.addWidget(method_group)

        # 状态显示
        status_group = QGroupBox("状态")
        status_layout = QVBoxLayout(status_group)
        self._status_label = QLabel("Idle")
        self._status_label.setStyleSheet("color: #95a5a6; font-weight: bold;")
        status_layout.addWidget(self._status_label)
        root.addWidget(status_group)

        # 参数只读区
        params_group = QGroupBox("参数配置")
        params_layout = QVBoxLayout(params_group)

        def add_param_row(label: str, value: str) -> None:
            row = QHBoxLayout()
            lbl = QLabel(label)
            lbl.setStyleSheet("color: #7f8c8d;")
            val = QLabel(value)
            val.setStyleSheet("color: #3498db; font-family: monospace;")
            row.addWidget(lbl)
            row.addStretch()
            row.addWidget(val)
            params_layout.addLayout(row)

        add_param_row("车体宽度 (a)", f"{self.config.corridor_width_m:.2f} m")
        add_param_row("障碍距离 (b)", f"{self.config.obstacle_range_m:.1f} m")
        add_param_row("楼梯距离 (c)", f"{self.config.stair_range_m:.1f} m")
        add_param_row("FPS 限制", f"{self.config.max_fps}")

        root.addWidget(params_group)

        # 统计信息
        stats_group = QGroupBox("统计")
        stats_layout = QVBoxLayout(stats_group)
        self._fps_label = QLabel("FPS: --")
        self._fps_label.setStyleSheet("color: #7f8c8d;")
        self._pixel_label = QLabel("有效像素: --%")
        self._pixel_label.setStyleSheet("color: #7f8c8d;")
        self._obstacle_label = QLabel("检测到障碍: 0")
        self._obstacle_label.setStyleSheet("color: #7f8c8d;")
        self._stair_label = QLabel("检测到楼梯: 否")
        self._stair_label.setStyleSheet("color: #7f8c8d;")
        stats_layout.addWidget(self._fps_label)
        stats_layout.addWidget(self._pixel_label)
        stats_layout.addWidget(self._obstacle_label)
        stats_layout.addWidget(self._stair_label)
        root.addWidget(stats_group)

        # 标定状态
        calib_group = QGroupBox("标定状态")
        calib_layout = QVBoxLayout(calib_group)
        self._calib_label = QLabel("⚠️ 使用默认外参")
        self._calib_label.setStyleSheet("color: #f39c12;")
        calib_layout.addWidget(self._calib_label)
        root.addWidget(calib_group)

        root.addStretch()

    def _on_start_clicked(self) -> None:
        self.set_running(True)
        self.start_clicked.emit()

    def _on_stop_clicked(self) -> None:
        self.set_running(False)
        self.stop_clicked.emit()

    def _on_open_3d_clicked(self) -> None:
        self._is_3d_open = True
        self._update_state()
        self.open_3d_clicked.emit()

    def _on_close_3d_clicked(self) -> None:
        self._is_3d_open = False
        self._update_state()
        self.close_3d_clicked.emit()

    def _update_state(self) -> None:
        """更新按钮和状态显示"""
        self._btn_start.setEnabled(not self._is_running)
        self._btn_stop.setEnabled(self._is_running)
        # Phase 1 only provides 2D overlay; keep 3D entrypoints visibly disabled.
        self._btn_open_3d.setEnabled(False)
        self._btn_close_3d.setEnabled(False)

        if self._is_running:
            self._status_label.setText("Running")
            self._status_label.setStyleSheet("color: #2ecc71; font-weight: bold;")
        else:
            self._status_label.setText("Idle")
            self._status_label.setStyleSheet("color: #95a5a6; font-weight: bold;")

    def is_running(self) -> bool:
        return self._is_running

    def set_running(self, running: bool) -> None:
        self._is_running = running
        if not running:
            self._is_3d_open = False
        self._update_state()

    def update_fps(self, fps: float) -> None:
        self._fps_label.setText(f"FPS: {fps:.1f}")

    def update_valid_pixels(self, percent: float) -> None:
        color = "#2ecc71" if percent > 50 else "#f39c12" if percent > 20 else "#e74c3c"
        self._pixel_label.setText(f"有效像素: {percent:.1f}%")
        self._pixel_label.setStyleSheet(f"color: {color};")

    def update_obstacle_count(self, count: int) -> None:
        color = "#e74c3c" if count > 0 else "#7f8c8d"
        self._obstacle_label.setText(f"检测到障碍: {count}")
        self._obstacle_label.setStyleSheet(f"color: {color};")

    def update_stair_detected(self, detected: bool) -> None:
        color = "#e74c3c" if detected else "#7f8c8d"
        text = "是" if detected else "否"
        self._stair_label.setText(f"检测到楼梯: {text}")
        self._stair_label.setStyleSheet(f"color: {color};")

    def set_calibration_status(self, text: str, is_warning: bool = True) -> None:
        color = "#f39c12" if is_warning else "#2ecc71"
        prefix = "⚠️ " if is_warning else "✓ "
        self._calib_label.setText(prefix + text)
        self._calib_label.setStyleSheet(f"color: {color};")

    def _on_method_changed(self, index: int) -> None:
        """绘制方法切换"""
        method = self._method_combo.itemData(index)
        if method != self._current_method:
            self._current_method = method
            self._update_method_desc()
            self._method_combo.clearFocus()
            self.method_changed.emit(method)

    def _update_method_desc(self) -> None:
        """更新方法说明文字"""
        if self._current_method == "geometric":
            self._method_desc.setText(
                "基于相机标定参数的 3D 投影，透视准确，需要精确外参。"
            )
        else:
            self._method_desc.setText(
                "基于图像比例的硬编码梯形，简单直接，无需相机标定。"
            )

    def get_current_method(self) -> str:
        """获取当前绘制方法"""
        return self._current_method

    def set_method(self, method: str) -> None:
        """设置绘制方法（用于 .env 初始化）"""
        if method not in ("geometric", "trapezoid"):
            return
        index = 0 if method == "geometric" else 1
        self._method_combo.setCurrentIndex(index)
