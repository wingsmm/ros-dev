from __future__ import annotations

import logging
import time
from typing import Optional

from PyQt5.QtWidgets import QVBoxLayout, QWidget

from core.camera_controllers import CameraServices
from core.camera_preview_config import camera_qt_preview_enabled
from core.robot_telemetry_binder import RobotTelemetryBinder
from core.ros2_bridge_manager import Ros2BridgeManager
from ui.models.robot_info import RobotInfo
from ui.pages.camera_chassis_mixin import CameraChassisMixin
from ui.widgets.camera_toolbar import CameraToolbar
from ui.widgets.camera_viewport import CameraViewport

logger = logging.getLogger(__name__)

_RGB_PREVIEW_OFF_HINT = "Qt 预览已关闭，请使用「打开 RGB Web」查看画面"


class RgbCameraPage(CameraChassisMixin, QWidget):
    """RGB MJPEG only — no Depth / Bridge / RViz / ground perception."""

    def __init__(
        self,
        robot: RobotInfo,
        services: CameraServices,
        telemetry_binder: Optional[RobotTelemetryBinder] = None,
        ros2_bridge: Optional[Ros2BridgeManager] = None,
        parent=None,
    ):
        super().__init__(parent)
        self._ros2_bridge = ros2_bridge
        self._qt_preview_enabled = camera_qt_preview_enabled()
        self._preview_active = False
        self._rgb_preview_skipped_logged = False
        self._init_camera_chassis(robot, services, telemetry_binder)
        self._toolbar = CameraToolbar()
        self._toolbar.configure_for_rgb()
        self._viewport = CameraViewport()
        self._viewport.set_view_mode("rgb")
        self._build_ui()
        self._wire_signals()
        self._apply_defaults()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(8)
        root.addWidget(self._toolbar)
        root.addWidget(self._viewport, 1)
        root.addWidget(self._telemetry)
        root.addWidget(self._manual)

    def _wire_signals(self) -> None:
        rgb = self._services.rgb
        self._toolbar.connect_requested.connect(rgb.connect)
        self._toolbar.disconnect_requested.connect(rgb.disconnect)
        self._toolbar.reconnect_requested.connect(rgb.reconnect)
        self._toolbar.snapshot_requested.connect(self._on_snapshot)
        self._toolbar.open_rgb_web_requested.connect(self._on_open_rgb_web)
        rgb.frame.connect(self._on_rgb_frame)
        rgb.status_changed.connect(self._on_rgb_status)
        rgb.connected_changed.connect(self._toolbar.set_streaming)
        rgb.fps_changed.connect(self._toolbar.set_fps)

    def _apply_defaults(self) -> None:
        rgb = self._services.rgb
        self._toolbar.set_rgb_url(rgb.rgb_url())
        self._toolbar.set_topic_hint(self._services.topic_hint_rgb())
        if self._qt_preview_enabled:
            self._viewport.set_empty()
        else:
            self._viewport.set_empty(_RGB_PREVIEW_OFF_HINT)

    def refresh_robot_settings(self) -> None:
        CameraChassisMixin.refresh_robot_settings(self)
        self._services.refresh_robot(self._robot)
        self._toolbar.set_rgb_url(self._services.rgb.rgb_url())

    def on_page_activated(self) -> None:
        t0 = time.perf_counter()
        self._on_chassis_activate()
        self._preview_active = True
        rgb = self._services.rgb
        if not rgb.is_streaming() and not rgb.user_connected:
            rgb.connect()
        else:
            self._services.bridge.maybe_auto_start_bridge()
        self._services.bridge.refresh_display_hook()
        logger.info(
            "CAMERA_FLOW rgb_page_activate elapsed=%.1fms streaming=%s",
            (time.perf_counter() - t0) * 1000.0,
            rgb.is_streaming(),
        )

    def on_page_deactivated(self) -> None:
        self._preview_active = False
        self._on_chassis_deactivate()

    def shutdown(self) -> None:
        self._preview_active = False
        self._on_chassis_shutdown()

    def _on_rgb_frame(self, jpeg: bytes) -> None:
        if not self._preview_active:
            return
        if not self._qt_preview_enabled:
            if not self._rgb_preview_skipped_logged:
                logger.info("camera RGB preview skipped: qt preview disabled")
                self._rgb_preview_skipped_logged = True
            return
        self._viewport.set_frame_jpeg(jpeg)

    def _on_rgb_status(self, text: str) -> None:
        self._toolbar.set_status(text)
        if not self._preview_active:
            return
        if not self._qt_preview_enabled:
            self._viewport.set_empty(_RGB_PREVIEW_OFF_HINT)
            return
        lower = text.lower()
        if text.startswith("Connecting"):
            self._viewport.set_loading()
        elif "timeout" in lower or text == "EOF" or text.startswith("Error"):
            self._viewport.set_stalled(text)
        elif text == "No Camera":
            self._viewport.set_empty()

    def _on_snapshot(self) -> None:
        ok, message, _path = self._services.rgb.take_snapshot()
        self._toolbar.set_status(message)
        if ok:
            logger.info("camera snapshot: %s", message)

    def _on_open_rgb_web(self) -> None:
        ok, message = self._services.rgb.open_rgb_web()
        if not ok:
            self._toolbar.set_status(message)
