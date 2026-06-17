from __future__ import annotations

from typing import Optional
from urllib.parse import urlparse

from PyQt5.QtWidgets import QVBoxLayout, QWidget

from core import RobotSession
from ui.models.robot_info import RobotInfo
from ui.widgets.camera_toolbar import CameraToolbar
from ui.widgets.camera_viewport import CameraViewport
from ui.widgets.manual_control_strip import ManualControlStrip
from ui.widgets.mjpeg_stream import MjpegStreamController
from ui.widgets.robot_hud_bar import RobotHudBar


def default_mjpeg_url(robot: RobotInfo) -> str:
    if robot.camera_url.strip():
        return robot.camera_url.strip()
    parsed = urlparse(robot.master_uri)
    host = parsed.hostname or "192.168.1.169"
    # The Android/ROS contract topic is /image_raw/compressed, but the
    # temporary HTTP/MJPEG path is served by web_video_server from the
    # republished raw image topic, matching the legacy CameraPanel default.
    topic = "/camera/image_raw"
    return f"http://{host}:8080/stream?topic={topic}"


class CameraPage(QWidget):
    def __init__(
        self,
        robot: RobotInfo,
        session: Optional[RobotSession] = None,
        parent=None,
    ):
        super().__init__(parent)
        self._robot = robot
        self._session = session  # reserved for ros1_gateway / ros2_native camera backend
        self._stream = MjpegStreamController(self)
        self._hud = RobotHudBar()
        self._toolbar = CameraToolbar()
        self._viewport = CameraViewport()
        self._manual = ManualControlStrip()
        self._build_ui()
        self._wire_signals()
        self._apply_robot_defaults()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(8)

        root.addWidget(self._hud)
        root.addWidget(self._toolbar)
        root.addWidget(self._viewport, 1)
        root.addWidget(self._manual)

    def _wire_signals(self) -> None:
        self._toolbar.connect_requested.connect(self._on_connect)
        self._toolbar.disconnect_requested.connect(self._stream.disconnect)
        self._toolbar.reconnect_requested.connect(self._on_reconnect)

        self._stream.frame.connect(self._viewport.set_frame_jpeg)
        self._stream.status_changed.connect(self._on_status)
        self._stream.connected_changed.connect(self._on_connected)
        self._stream.fps_changed.connect(self._toolbar.set_fps)

        self._hud.emergency_stop_requested.connect(self._manual.stop)
        self._manual.stop_requested.connect(
            lambda: self._hud.set_motion("0.00", "0.00")
        )
        self._manual.velocity_requested.connect(self._on_velocity_placeholder)

    def _apply_robot_defaults(self) -> None:
        url = default_mjpeg_url(self._robot)
        self._toolbar.set_url(url)
        self._toolbar.set_topic_hint(self._robot.camera_topic)
        self._hud.set_connection(True, self._robot.name)
        self._hud.set_motion("0.00", "0.00")
        self._hud.set_pose("(x, y, yaw) 占位")

    def on_page_activated(self) -> None:
        """Called by RobotWorkspacePage when this tab becomes visible."""
        if not self._stream.is_streaming():
            self._on_connect()

    def on_page_deactivated(self) -> None:
        """Called by RobotWorkspacePage when leaving this tab; stops MJPEG only."""
        self._stream.disconnect()

    def _on_connect(self) -> None:
        url = self._toolbar.url() or default_mjpeg_url(self._robot)
        self._toolbar.set_connecting()
        self._viewport.set_loading()
        self._stream.connect(url)

    def _on_reconnect(self) -> None:
        url = self._toolbar.url() or default_mjpeg_url(self._robot)
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

    def _on_velocity_placeholder(self, lx: float, ly: float, az: float) -> None:
        self._hud.set_motion(f"{lx:.2f}", f"{az:.2f}")

    def shutdown(self) -> None:
        self._stream.shutdown()
