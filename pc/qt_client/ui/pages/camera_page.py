from __future__ import annotations

from typing import Optional

from PyQt5.QtWidgets import QVBoxLayout, QWidget

from core.camera_ros2_bridge_manager import CameraRos2BridgeManager
from core.camera_mjpeg_url import (
    ANDROID_CAMERA_TOPIC,
    QT_MJPEG_TOPIC,
    resolve_mjpeg_url_for_robot,
)
from core.robot_telemetry_binder import RobotTelemetryBinder
from core.ros2_runtime import auto_camera_bridge_enabled
from ui.models.robot_info import RobotInfo
from ui.models.robot_settings import effective_manual_speeds
from ui.widgets.camera_ros2_panel import CameraRos2Panel
from ui.widgets.camera_toolbar import CameraToolbar
from ui.widgets.camera_viewport import CameraViewport
from ui.widgets.manual_control_strip import ManualControlStrip
from ui.widgets.mjpeg_stream import MjpegStreamController
from ui.widgets.telemetry_details_strip import TelemetryDetailsStrip


class CameraPage(QWidget):
    def __init__(
        self,
        robot: RobotInfo,
        telemetry_binder: Optional[RobotTelemetryBinder] = None,
        parent=None,
    ):
        super().__init__(parent)
        self._robot = robot
        self._binder = telemetry_binder
        self._stream = MjpegStreamController(self)
        self._toolbar = CameraToolbar()
        self._viewport = CameraViewport()
        self._telemetry = TelemetryDetailsStrip()
        self._ros2_panel = CameraRos2Panel()
        self._ros2_bridge = CameraRos2BridgeManager(robot=robot, parent=self)
        self._ros2_panel.set_manager(self._ros2_bridge)
        self._manual = ManualControlStrip()
        self._build_ui()
        self._wire_signals()
        self._apply_robot_defaults()
        if self._binder is not None:
            self._binder.register_panel(self._telemetry.telemetry_panel)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(8)

        root.addWidget(self._toolbar)
        root.addWidget(self._viewport, 1)
        root.addWidget(self._ros2_panel)
        root.addWidget(self._telemetry)
        root.addWidget(self._manual)

    def _wire_signals(self) -> None:
        self._toolbar.connect_requested.connect(self._on_connect)
        self._toolbar.disconnect_requested.connect(self._stream.disconnect)
        self._toolbar.reconnect_requested.connect(self._on_reconnect)

        self._stream.frame.connect(self._viewport.set_frame_jpeg)
        self._stream.status_changed.connect(self._on_status)
        self._stream.connected_changed.connect(self._on_connected)
        self._stream.fps_changed.connect(self._toolbar.set_fps)

        self._manual.velocity_requested.connect(self._on_velocity_requested)
        self._manual.stop_requested.connect(self._on_stop_requested)

    def _apply_robot_defaults(self) -> None:
        url = resolve_mjpeg_url_for_robot(self._robot)
        self._toolbar.set_url(url)
        self._toolbar.set_topic_hint(
            f"Android {ANDROID_CAMERA_TOPIC} | 预览 {QT_MJPEG_TOPIC} | "
            "ROS2：展开下方联调区，手动启 Camera Bridge"
        )
        self._apply_manual_speed_defaults()

    def _apply_manual_speed_defaults(self) -> None:
        linear, angular = effective_manual_speeds(self._robot)
        self._manual.set_speeds(linear=linear, angular=angular)

    def refresh_robot_settings(self) -> None:
        """Re-read per-robot settings after SettingsPage save."""
        self._apply_manual_speed_defaults()

    def on_page_activated(self) -> None:
        """Auto-connect MJPEG preview when entering camera tab (MVP)."""
        if self._binder is not None:
            self._binder.replay()
        self._apply_manual_speed_defaults()
        self._manual.set_keyboard_enabled(True)
        self._ros2_panel.refresh_display()
        if not self._stream.is_streaming():
            self._on_connect()
        elif auto_camera_bridge_enabled():
            self._maybe_auto_start_camera_bridge()

    def on_page_deactivated(self) -> None:
        self._manual.set_keyboard_enabled(False)
        self._stream.disconnect()

    def shutdown(self) -> None:
        self._manual.set_keyboard_enabled(False)
        self._ros2_bridge.shutdown()
        if self._binder is not None:
            self._binder.unregister_panel(self._telemetry.telemetry_panel)
            self._binder.session.stop_motion()
        self._stream.shutdown()

    def _on_connect(self) -> None:
        url = self._toolbar.url() or resolve_mjpeg_url_for_robot(self._robot)
        self._toolbar.set_connecting()
        self._viewport.set_loading()
        self._stream.connect(url)

    def _on_reconnect(self) -> None:
        url = self._toolbar.url() or resolve_mjpeg_url_for_robot(self._robot)
        self._toolbar.set_connecting()
        self._viewport.set_loading()
        self._stream.reconnect(url)

    def _on_status(self, text: str) -> None:
        self._toolbar.set_status(text)
        lower = text.lower()
        if text.startswith("Connecting"):
            self._viewport.set_loading()
        elif "timeout" in lower or text == "EOF" or text.startswith("Error"):
            self._viewport.set_stalled(text)
        elif text == "No Camera":
            self._viewport.set_empty()

    def _on_connected(self, ok: bool) -> None:
        self._toolbar.set_streaming(ok)
        if not ok and self._stream.stats.last_frame_ts <= 0:
            if self._stream.stats.status == "No Camera":
                self._viewport.set_empty()

    def _maybe_auto_start_camera_bridge(self) -> None:
        if not auto_camera_bridge_enabled():
            return
        if not self._stream.is_streaming():
            return
        if not self._ros2_bridge.snapshot().bridge_running:
            self._ros2_bridge.start_bridge()

    def _on_velocity_requested(self, lx: float, ly: float, az: float) -> None:
        if self._binder is None:
            return
        self._binder.session.send_velocity(lx, ly, az)

    def _on_stop_requested(self) -> None:
        if self._binder is not None:
            self._binder.session.stop_motion()
