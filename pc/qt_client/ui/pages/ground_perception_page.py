from __future__ import annotations

import logging
import time
from typing import Optional

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QFrame, QHBoxLayout, QScrollArea, QSizePolicy, QVBoxLayout, QWidget

from core.camera_controllers import CameraServices
from core.robot_telemetry_binder import RobotTelemetryBinder
from core.ros2_bridge_manager import Ros2BridgeManager
from ui.models.robot_info import RobotInfo
from ui.pages.camera_chassis_mixin import CameraChassisMixin
from ui.widgets.camera_viewport import CameraViewport
from ui.widgets.ground_perception_panel import GroundPerceptionPanel

logger = logging.getLogger(__name__)


class GroundPerceptionPage(CameraChassisMixin, QWidget):
    """Ground perception overlay — consumes RGB/Depth, no Bridge/RViz controls."""

    def __init__(
        self,
        robot: RobotInfo,
        services: CameraServices,
        telemetry_binder: Optional[RobotTelemetryBinder] = None,
        ros2_bridge: Optional[Ros2BridgeManager] = None,
        parent=None,
    ):
        super().__init__(parent)
        del ros2_bridge  # ground page does not own bridge lifecycle
        self._preview_active = False
        self._init_camera_chassis(robot, services, telemetry_binder)
        self._viewport = CameraViewport()
        self._viewport.set_view_mode("perception")
        self._ground_panel = GroundPerceptionPanel(self._services.ground.config)
        self._ground_panel_scroll = QScrollArea()
        self._ground_panel_scroll.setWidgetResizable(True)
        self._ground_panel_scroll.setFrameShape(QFrame.NoFrame)
        self._ground_panel_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._ground_panel_scroll.setSizePolicy(
            QSizePolicy.Preferred, QSizePolicy.Expanding
        )
        self._ground_panel_scroll.setMinimumHeight(220)
        self._ground_panel_scroll.setMaximumHeight(360)
        self._ground_panel_scroll.setWidget(self._ground_panel)
        self._build_ui()
        self._wire_signals()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(8)
        preview_row = QHBoxLayout()
        preview_row.setSpacing(12)
        preview_row.addWidget(self._viewport, 3)
        side = QVBoxLayout()
        side.addWidget(self._ground_panel_scroll)
        side.addStretch(1)
        preview_row.addLayout(side, 1)
        root.addLayout(preview_row, 1)
        root.addWidget(self._telemetry)
        root.addWidget(self._manual)

    def _wire_signals(self) -> None:
        ground = self._services.ground
        self._ground_panel.method_changed.connect(ground.set_overlay_method)
        ground.overlay_ready.connect(self._on_overlay_ready)
        ground.running_changed.connect(self._ground_panel.set_running)
        ground.calibration_status.connect(self._ground_panel.set_calibration_status)
        ground.valid_pixels.connect(self._ground_panel.update_valid_pixels)
        self._services.rgb.fps_changed.connect(self._ground_panel.update_fps)

    def refresh_robot_settings(self) -> None:
        CameraChassisMixin.refresh_robot_settings(self)

    def on_page_activated(self) -> None:
        t0 = time.perf_counter()
        self._on_chassis_activate()
        self._preview_active = True
        self._services.ground.start()
        logger.info(
            "CAMERA_FLOW ground_page_activate elapsed=%.1fms",
            (time.perf_counter() - t0) * 1000.0,
        )

    def on_page_deactivated(self) -> None:
        self._preview_active = False
        self._services.ground.stop()
        self._on_chassis_deactivate()

    def shutdown(self) -> None:
        self._preview_active = False
        self._services.ground.stop()
        self._on_chassis_shutdown()

    def _on_overlay_ready(self, image: object) -> None:
        if not self._preview_active:
            return
        from PyQt5.QtGui import QImage

        if isinstance(image, QImage):
            self._viewport.set_frame_rgb(image)
