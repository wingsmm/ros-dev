from __future__ import annotations

import logging
import time
from typing import Optional

from PyQt5.QtCore import QEvent, Qt, QTimer
from PyQt5.QtWidgets import QApplication, QHBoxLayout, QVBoxLayout, QWidget

from core.camera_controllers import CameraServices
from core.camera_depth_frame import DepthFrameStats, DepthSourceKind
from core.camera_preview_config import camera_qt_preview_enabled
from core.camera_topic_probe import CameraTopicProbeResult
from core.camera_topics import (
    CAMERA_DEPTH_INFO_TOPIC,
    CAMERA_DEPTH_POINTS_TOPIC,
    DEPTH_PAGE_PROBE_TOPICS,
)
from core.robot_telemetry_binder import RobotTelemetryBinder
from core.ros2_bridge_manager import Ros2BridgeManager
from ui.models.robot_info import RobotInfo
from ui.pages.camera_chassis_mixin import CameraChassisMixin
from ui.widgets.camera_ros2_panel import CameraRos2Panel
from ui.widgets.camera_viewport import CameraViewport
from ui.widgets.depth_camera_diagnostic_panel import DepthCameraDiagnosticPanel
from ui.widgets.depth_camera_status_strip import DepthCameraStatusStrip

logger = logging.getLogger(__name__)

_DEPTH_PREVIEW_OFF_HINT = (
    "Qt Depth 预览已关闭；Depth raw 仍可供点云/Bridge 使用"
)
_CONSUMER = "depth_page"


class DepthCameraPage(CameraChassisMixin, QWidget):
    """Depth diagnostics: auto raw HTTP + Bridge; manual RViz only."""

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
        self._depth_preview_skipped_logged = False
        self._depth_raw_frame_received = False
        self._depth_stats_pending: Optional[object] = None
        self._pointcloud_stream_active: Optional[bool] = None
        self._last_depth_raw_ui_mono = 0.0
        self._source_kind = DepthSourceKind.OFFLINE
        self._init_camera_chassis(robot, services, telemetry_binder)
        self._status_strip = DepthCameraStatusStrip()
        self._viewport = CameraViewport()
        self._viewport.set_view_mode("depth")
        self._diag_panel = DepthCameraDiagnosticPanel()
        self._diag_panel.set_http_url(self._services.depth.http_frame_url())
        self._ros2_panel = CameraRos2Panel(mode="depth_compact")
        if ros2_bridge is not None:
            self._ros2_panel.set_manager(ros2_bridge)
        self._depth_raw_wait_timer = QTimer(self)
        self._depth_raw_wait_timer.setSingleShot(True)
        self._depth_raw_wait_timer.timeout.connect(self._on_depth_raw_wait_timeout)
        self._depth_stats_timer = QTimer(self)
        self._depth_stats_timer.setInterval(350)
        self._depth_stats_timer.timeout.connect(self._flush_depth_stats)
        self._manual.set_focus_hint(
            "键盘/按钮仅在 Qt 窗口获焦时可用；切到 RViz 或其他窗口会自动停止运动。"
        )
        app = QApplication.instance()
        if app is not None:
            app.applicationStateChanged.connect(self._on_app_state_changed)
        self._build_ui()
        self._wire_signals()
        self._apply_defaults()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(8)
        root.addWidget(self._status_strip)
        preview_row = QHBoxLayout()
        preview_row.setSpacing(12)
        preview_row.addWidget(self._viewport, 3)
        preview_row.addWidget(self._diag_panel, 1)
        root.addLayout(preview_row, 1)
        root.addWidget(self._ros2_panel)
        root.addWidget(self._telemetry)
        root.addWidget(self._manual)

    def changeEvent(self, event) -> None:
        if event.type() == QEvent.WindowActivate and self._preview_active:
            self._manual.set_keyboard_enabled(True)
            self._set_pointcloud_stream_for_qt_focus(False, "window_activate")
            logger.info(
                "MANUAL_FLOW depth_page window_activate keyboard_enabled=True "
                "preview_active=True"
            )
        elif event.type() == QEvent.WindowDeactivate and self._preview_active:
            self._set_pointcloud_stream_for_qt_focus(True, "window_deactivate")
        super().changeEvent(event)

    def _wire_signals(self) -> None:
        depth = self._services.depth
        depth.preview_ready.connect(self._on_depth_preview_packet)
        depth.stats_updated.connect(self._on_depth_stats)
        depth.status_changed.connect(self._on_depth_worker_status)
        depth.source_kind_changed.connect(self._on_source_kind_changed)
        depth.worker_failed.connect(self._on_depth_worker_failed)
        if self._ros2_bridge is not None:
            self._ros2_bridge.snapshot_updated.connect(self._on_ros2_snapshot)
            self._ros2_bridge.action_message.connect(self._on_ros2_action)

    def _apply_defaults(self) -> None:
        self._diag_panel.set_raw_stream_status("未接入", DepthSourceKind.OFFLINE)
        if self._qt_preview_enabled:
            self._viewport.set_depth_empty()
        else:
            self._viewport.set_depth_empty(_DEPTH_PREVIEW_OFF_HINT)
        self._refresh_status_strip()

    def refresh_robot_settings(self) -> None:
        CameraChassisMixin.refresh_robot_settings(self)
        self._services.refresh_robot(self._robot)
        url = self._services.depth.http_frame_url()
        self._diag_panel.set_http_url(url)

    def on_page_activated(self) -> None:
        t0 = time.perf_counter()
        self._on_chassis_activate()
        self._preview_active = True
        decode = self._qt_preview_enabled
        self._services.depth.add_consumer(_CONSUMER, decode=decode)
        self._services.bridge.ensure_depth_bridge_running()
        self._set_pointcloud_stream_for_qt_focus(False, "page_activate")
        self._depth_raw_frame_received = False
        self._diag_panel.set_raw_stream_status("连接中", DepthSourceKind.OFFLINE)
        if self._qt_preview_enabled:
            self._viewport.set_depth_loading()
        else:
            self._viewport.set_depth_empty(_DEPTH_PREVIEW_OFF_HINT)
        cfg = self._services.depth.config
        self._depth_raw_wait_timer.start(int(cfg.raw_wait_s * 1000))
        self._ros2_panel.refresh_display()
        QTimer.singleShot(0, self._trigger_topic_probe)
        self._refresh_status_strip()
        logger.info(
            "CAMERA_FLOW depth_page_activate elapsed=%.1fms running=%s "
            "keyboard_enabled=%s",
            (time.perf_counter() - t0) * 1000.0,
            self._services.depth.is_running(),
            self._manual.keyboard_enabled(),
        )

    def on_page_deactivated(self) -> None:
        self._preview_active = False
        self._depth_raw_wait_timer.stop()
        self._depth_stats_timer.stop()
        self._services.depth.remove_consumer(_CONSUMER)
        self._set_pointcloud_stream_for_qt_focus(False, "page_deactivate")
        self._on_chassis_deactivate()

    def shutdown(self) -> None:
        self._preview_active = False
        self._depth_stats_timer.stop()
        self._depth_raw_wait_timer.stop()
        self._services.depth.remove_consumer(_CONSUMER)
        self._set_pointcloud_stream_for_qt_focus(False, "page_shutdown")
        self._on_chassis_shutdown()

    def _on_app_state_changed(self, state: Qt.ApplicationState) -> None:
        if not self._preview_active:
            return
        if state == Qt.ApplicationActive:
            self._set_pointcloud_stream_for_qt_focus(False, "application_active")
        else:
            self._set_pointcloud_stream_for_qt_focus(True, "application_inactive")

    def _set_pointcloud_stream_for_qt_focus(self, enabled: bool, reason: str) -> None:
        if self._ros2_bridge is None:
            return
        enabled = bool(enabled)
        if self._pointcloud_stream_active == enabled:
            return
        self._pointcloud_stream_active = enabled
        self._ros2_bridge.set_pointcloud_stream_enabled(enabled)
        logger.info(
            "CAMERA_FLOW depth_page pointcloud_stream enabled=%s reason=%s",
            enabled,
            reason,
        )

    def _trigger_topic_probe(self) -> None:
        if self._ros2_bridge is not None:
            self._ros2_bridge.refresh_camera_topic_status(
                topics=DEPTH_PAGE_PROBE_TOPICS
            )

    def _on_depth_preview_packet(self, packet: object) -> None:
        if not self._preview_active:
            return
        from core.camera_depth_http_worker import DepthPreviewPacket

        if not isinstance(packet, DepthPreviewPacket):
            return
        first_frame = not self._depth_raw_frame_received
        self._depth_raw_frame_received = True
        self._depth_raw_wait_timer.stop()
        now = time.monotonic()
        if (
            self._qt_preview_enabled
            or first_frame
            or now - self._last_depth_raw_ui_mono >= 1.0
        ):
            self._diag_panel.set_raw_stream_status("已连接", DepthSourceKind.RAW_HTTP)
            self._refresh_status_strip()
            self._last_depth_raw_ui_mono = now
        if self._qt_preview_enabled:
            try:
                self._viewport.set_depth_frame_rgb(
                    packet.width, packet.height, packet.rgb_bytes
                )
            except Exception:
                logger.exception("depth preview frame render failed")
        elif not self._depth_preview_skipped_logged:
            logger.info("camera depth preview skipped: qt preview disabled")
            self._depth_preview_skipped_logged = True

    def _on_depth_stats(self, stats: object) -> None:
        if not self._preview_active:
            return
        self._depth_stats_pending = stats
        if not self._depth_stats_timer.isActive():
            self._flush_depth_stats()
            self._depth_stats_timer.start()

    def _flush_depth_stats(self) -> None:
        stats = self._depth_stats_pending
        self._depth_stats_pending = None
        if isinstance(stats, DepthFrameStats):
            self._diag_panel.apply_stats(stats)
            self._refresh_status_strip()

    def _on_depth_worker_status(self, text: str) -> None:
        if text.startswith("Raw Depth HTTP 已连接"):
            self._depth_raw_frame_received = True
            self._depth_raw_wait_timer.stop()
            self._source_kind = DepthSourceKind.RAW_HTTP
            self._diag_panel.set_raw_stream_status("已连接", DepthSourceKind.RAW_HTTP)
        else:
            self._diag_panel.set_raw_stream_status(text, self._source_kind)
        self._refresh_status_strip()

    def _on_source_kind_changed(self, kind: str) -> None:
        try:
            self._source_kind = DepthSourceKind(kind)
        except ValueError:
            self._source_kind = DepthSourceKind.OFFLINE

    def _on_depth_worker_failed(self, detail: str) -> None:
        self._diag_panel.set_raw_stream_status(
            f"离线 ({detail})", DepthSourceKind.OFFLINE
        )
        if not self._depth_raw_frame_received and not self._depth_raw_wait_timer.isActive():
            self._show_depth_offline()

    def _on_depth_raw_wait_timeout(self) -> None:
        if self._depth_raw_frame_received:
            return
        self._show_depth_offline()

    def _show_depth_offline(self) -> None:
        if self._depth_raw_frame_received:
            return
        if not self._qt_preview_enabled:
            self._viewport.set_depth_empty(_DEPTH_PREVIEW_OFF_HINT)
        else:
            self._viewport.set_depth_empty("Raw depth HTTP :8082 未连接")
        self._diag_panel.set_raw_stream_status("离线", DepthSourceKind.OFFLINE)
        self._refresh_status_strip()

    def _on_ros2_snapshot(self, _snapshot: object) -> None:
        if self._ros2_bridge is None:
            return
        snap = self._ros2_bridge.camera_snapshot()
        self._apply_probe(snap.topic_probe_result)
        self._diag_panel.apply_bridge_snapshot(snap)
        self._ros2_panel.refresh_display()
        self._refresh_status_strip()

    def _on_ros2_action(self, text: str) -> None:
        if self._ros2_bridge is not None:
            self._diag_panel.apply_bridge_snapshot(self._ros2_bridge.camera_snapshot())
        if text:
            self._diag_panel.set_status_message(text)
        self._refresh_status_strip()

    def _apply_probe(self, result: Optional[CameraTopicProbeResult]) -> None:
        self._diag_panel.apply_probe(result)

    def _refresh_status_strip(self) -> None:
        if self._depth_raw_frame_received:
            raw = "已连接(raw-only)" if not self._qt_preview_enabled else "已连接"
        elif self._services.depth.is_running() or self._services.depth.is_starting():
            raw = "连接中"
        else:
            raw = "离线"

        camera_info = "—"
        pointcloud = "—"
        if self._ros2_bridge is not None:
            snap = self._ros2_bridge.camera_snapshot()
            probe = snap.topic_probe_result
            if probe is not None:
                camera_info = _probe_short(
                    probe.entries.get(CAMERA_DEPTH_INFO_TOPIC)
                )
                pointcloud = _probe_short(
                    probe.entries.get(CAMERA_DEPTH_POINTS_TOPIC)
                )
            elif snap.bridge_running:
                bridge = snap.bridge_status
                if bridge.last_source_ms.get("depth_camera_info", 0) > 0:
                    camera_info = "online"
                img_age = bridge.last_source_ms.get("depth_image", 0)
                if img_age > 0:
                    pointcloud = _format_hz(
                        bridge.publish_hz, CAMERA_DEPTH_POINTS_TOPIC
                    )
            rviz = "running" if snap.rviz_running else "stopped"
        else:
            rviz = "—"

        self._status_strip.set_status(
            raw_http=raw,
            camera_info=camera_info,
            pointcloud=pointcloud,
            rviz=rviz,
        )


def _probe_short(entry) -> str:
    if entry is None:
        return "—"
    return "online" if entry.online else "offline"


def _format_hz(hz_map: dict, topic: str) -> str:
    value = hz_map.get(topic)
    if value is None or value <= 0.01:
        return "—"
    return f"{value:.1f} Hz"
