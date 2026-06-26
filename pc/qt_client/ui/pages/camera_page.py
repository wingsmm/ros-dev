from __future__ import annotations

import logging
from typing import Optional

from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from core.camera_depth_frame import DepthSourceKind
from core.camera_depth_preview_manager import CameraDepthPreviewManager
from core.camera_depth_source import DepthSourceConfig
from core.camera_mjpeg_url import (
    QT_MJPEG_DEPTH_TOPIC,
    QT_MJPEG_TOPIC,
    resolve_depth_mjpeg_url_for_robot,
    resolve_depth_mjpeg_url_for_robot_topic,
    resolve_mjpeg_url_for_robot,
)
from core.camera_ros2_bridge_manager import CameraRos2BridgeManager
from core.camera_topic_probe import CameraTopicProbeResult
from core.camera_depth_http_worker import DepthPreviewPacket
from core.robot_telemetry_binder import RobotTelemetryBinder
from core.ros2_runtime import auto_camera_bridge_enabled
from ui.models.robot_info import RobotInfo
from ui.models.robot_settings import effective_manual_speeds
from ui.widgets.camera_depth_panel import CameraDepthPanel
from ui.widgets.camera_ros2_panel import CameraRos2Panel
from ui.widgets.camera_scan_panel import CameraScanPanel
from ui.widgets.camera_toolbar import CameraToolbar
from ui.widgets.camera_view_mode_bar import CameraViewModeBar
from ui.widgets.camera_viewport import CameraViewport
from ui.widgets.manual_control_strip import ManualControlStrip
from ui.widgets.mjpeg_stream import MjpegStreamController
from ui.widgets.telemetry_details_strip import TelemetryDetailsStrip

logger = logging.getLogger(__name__)


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
        self._view_mode = "rgb"
        self._stream = MjpegStreamController(self, timeout_s=5.0, max_fps=8.0)
        self._depth_stream = MjpegStreamController(self, timeout_s=5.0, max_fps=5.0)
        self._depth_config = DepthSourceConfig.from_env(
            master_uri=getattr(robot, "master_uri", "") or ""
        )
        self._depth_preview = CameraDepthPreviewManager(
            config=self._depth_config,
            parent=self,
        )
        self._depth_raw_frame_received = False
        self._depth_mjpeg_frame_received = False
        self._depth_using_mjpeg_fallback = False
        self._depth_mjpeg_candidate_index = 0
        self._depth_mjpeg_current_topic = ""
        self._depth_raw_wait_timer = QTimer(self)
        self._depth_raw_wait_timer.setSingleShot(True)
        self._depth_raw_wait_timer.timeout.connect(self._maybe_start_depth_mjpeg_fallback)
        self._depth_mjpeg_wait_timer = QTimer(self)
        self._depth_mjpeg_wait_timer.setSingleShot(True)
        self._depth_mjpeg_wait_timer.timeout.connect(self._on_depth_mjpeg_wait_timeout)
        self._depth_stats_pending: Optional[object] = None
        self._depth_stats_timer = QTimer(self)
        self._depth_stats_timer.setInterval(350)
        self._depth_stats_timer.timeout.connect(self._flush_depth_stats)
        self._toolbar = CameraToolbar()
        self._view_mode_bar = CameraViewModeBar()
        self._viewport = CameraViewport()
        self._depth_panel = CameraDepthPanel()
        self._depth_panel.set_http_info(self._depth_config.http_frame_url)
        self._scan_panel = CameraScanPanel()
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
        root.addWidget(self._view_mode_bar)

        preview_row = QHBoxLayout()
        preview_row.setSpacing(12)
        preview_col = QVBoxLayout()
        preview_col.addWidget(self._viewport, 1)
        preview_row.addLayout(preview_col, 3)

        side_col = QVBoxLayout()
        side_col.addWidget(self._depth_panel)
        side_col.addWidget(self._scan_panel)
        side_col.addStretch(1)
        preview_row.addLayout(side_col, 1)
        root.addLayout(preview_row, 1)

        root.addWidget(self._ros2_panel)
        root.addWidget(self._telemetry)
        root.addWidget(self._manual)

    def _wire_signals(self) -> None:
        self._toolbar.connect_requested.connect(self._on_connect)
        self._toolbar.disconnect_requested.connect(self._on_disconnect_all)
        self._toolbar.reconnect_requested.connect(self._on_reconnect)

        self._view_mode_bar.mode_changed.connect(self._on_view_mode_changed)

        self._stream.frame.connect(self._viewport.set_frame_jpeg)
        self._stream.status_changed.connect(self._on_rgb_status)
        self._stream.connected_changed.connect(self._on_rgb_connected)
        self._stream.fps_changed.connect(self._toolbar.set_fps)

        self._depth_stream.frame.connect(self._on_depth_mjpeg_frame)
        self._depth_stream.status_changed.connect(self._on_depth_mjpeg_status)
        self._depth_stream.connected_changed.connect(self._on_depth_mjpeg_connected)
        self._depth_stream.log_line.connect(
            lambda line: logger.info("depth MJPEG: %s", line)
        )

        self._depth_preview.preview_ready.connect(self._on_depth_preview_packet)
        self._depth_preview.stats_updated.connect(self._on_depth_stats)
        self._depth_preview.status_changed.connect(self._on_depth_worker_status)
        self._depth_preview.source_kind_changed.connect(self._on_depth_source_kind)
        self._depth_preview.worker_failed.connect(self._on_depth_worker_failed)

        self._ros2_bridge.snapshot_updated.connect(self._on_ros2_snapshot)

        self._manual.velocity_requested.connect(self._on_velocity_requested)
        self._manual.stop_requested.connect(self._on_stop_requested)

    def _apply_robot_defaults(self) -> None:
        self._apply_stream_url_display()
        self._toolbar.set_topic_hint(
            f"RGB {QT_MJPEG_TOPIC} | Depth Raw {self._depth_config.image_topic} "
            f"→ MJPEG fallback 链见右侧 | ROS2 诊断：展开下方联调区"
        )
        depth_url = resolve_depth_mjpeg_url_for_robot(self._robot)
        fallback_topics = " -> ".join(self._depth_config.mjpeg_fallback_topics)
        self._depth_panel.set_fallback_info(depth_url, fallback_topics)
        self._apply_manual_speed_defaults()
        self._depth_panel.set_stream_status("未接入")
        self._depth_panel.set_source_kind(DepthSourceKind.OFFLINE)
        self._viewport.set_depth_empty()

    def _apply_manual_speed_defaults(self) -> None:
        linear, angular = effective_manual_speeds(self._robot)
        self._manual.set_speeds(linear=linear, angular=angular)

    def refresh_robot_settings(self) -> None:
        """Re-read per-robot settings after SettingsPage save."""
        self._apply_stream_url_display()
        self._apply_manual_speed_defaults()

    def _apply_stream_url_display(self) -> None:
        rgb_url = resolve_mjpeg_url_for_robot(self._robot)
        depth_url = resolve_depth_mjpeg_url_for_robot(self._robot)
        self._toolbar.set_stream_urls(rgb_url, depth_url)

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
        self._start_depth_preview()

    def on_page_deactivated(self) -> None:
        self._manual.set_keyboard_enabled(False)
        self._on_disconnect_all()

    def shutdown(self) -> None:
        self._manual.set_keyboard_enabled(False)
        self._depth_stats_timer.stop()
        self._depth_preview.shutdown()
        self._ros2_bridge.shutdown()
        if self._binder is not None:
            self._binder.unregister_panel(self._telemetry.telemetry_panel)
            self._binder.session.stop_motion()
        self._stream.shutdown()
        self._depth_stream.shutdown()

    def _on_view_mode_changed(self, mode: str) -> None:
        self._view_mode = mode
        self._viewport.set_view_mode(mode)
        if mode == "rgb":
            self._stream.set_max_fps(8.0)
            self._stream.resume()
            self._stop_depth_preview_for_rgb()
        elif mode == "depth":
            self._stream.pause()
            self._start_depth_preview()
        elif mode == "split":
            self._stream.set_max_fps(5.0)
            self._stream.resume()
            self._start_depth_preview()
        if mode == "depth" and not self._depth_preview.is_running() and not self._depth_preview.is_starting():
            if not self._depth_using_mjpeg_fallback:
                self._viewport.set_depth_empty()

    def _stop_depth_preview_for_rgb(self) -> None:
        """Release raw-depth HTTP work while the depth pane is hidden."""
        self._depth_raw_wait_timer.stop()
        self._depth_mjpeg_wait_timer.stop()
        self._depth_using_mjpeg_fallback = False
        self._depth_stream.disconnect()
        self._depth_preview.pause()

    def _on_connect(self) -> None:
        url = resolve_mjpeg_url_for_robot(self._robot)
        self._toolbar.set_connecting()
        self._viewport.set_loading()
        self._stream.connect(url)
        self._start_depth_preview()

    def _on_reconnect(self) -> None:
        url = resolve_mjpeg_url_for_robot(self._robot)
        self._toolbar.set_connecting()
        self._viewport.set_loading()
        self._stream.reconnect(url)
        self._depth_raw_frame_received = False
        self._depth_mjpeg_frame_received = False
        self._depth_using_mjpeg_fallback = False
        self._depth_mjpeg_candidate_index = 0
        self._depth_mjpeg_current_topic = ""
        self._depth_preview.restart()
        self._start_depth_preview()

    def _on_disconnect_all(self) -> None:
        self._depth_raw_wait_timer.stop()
        self._depth_mjpeg_wait_timer.stop()
        self._depth_raw_frame_received = False
        self._depth_mjpeg_frame_received = False
        self._stream.disconnect()
        self._depth_stream.disconnect()
        self._depth_preview.stop()
        self._depth_using_mjpeg_fallback = False
        self._depth_panel.set_stream_status("未接入")
        self._depth_panel.set_source_kind(DepthSourceKind.OFFLINE)

    def _start_depth_preview(self) -> None:
        if self._view_mode not in ("depth", "split"):
            return
        self._depth_raw_frame_received = False
        self._depth_mjpeg_frame_received = False
        self._depth_using_mjpeg_fallback = False
        self._depth_raw_wait_timer.stop()
        self._depth_mjpeg_wait_timer.stop()
        self._depth_stream.disconnect()
        self._depth_panel.set_stream_status("连接中…")
        self._depth_panel.set_source_kind(DepthSourceKind.OFFLINE)
        self._viewport.set_depth_loading()
        if self._depth_preview.is_running() or self._depth_preview.is_starting():
            self._depth_preview.resume()
        else:
            self._depth_preview.start()
        wait_ms = int(self._depth_config.raw_wait_s * 1000)
        self._depth_raw_wait_timer.start(wait_ms)

    def _maybe_start_depth_mjpeg_fallback(self) -> None:
        if self._depth_raw_frame_received:
            return
        if not self._depth_config.allow_mjpeg_fallback:
            logger.info("depth MJPEG fallback disabled; showing offline")
            self._show_depth_offline(tried_mjpeg=False)
            return
        if self._depth_stream.is_streaming():
            return
        logger.info(
            "depth raw wait expired (%.1fs); starting MJPEG fallback %s",
            self._depth_config.raw_wait_s,
            resolve_depth_mjpeg_url_for_robot(self._robot),
        )
        if self._depth_preview.is_running() or self._depth_preview.is_starting():
            self._depth_preview.stop_for_handoff()
        self._depth_using_mjpeg_fallback = True
        self._depth_preview.set_mjpeg_fallback_active(True)
        self._depth_mjpeg_candidate_index = 0
        self._start_next_depth_mjpeg_candidate()

    def _start_next_depth_mjpeg_candidate(self) -> None:
        topics = self._depth_config.mjpeg_fallback_topics
        if self._depth_mjpeg_candidate_index >= len(topics):
            self._show_depth_offline(tried_mjpeg=True)
            return
        topic = topics[self._depth_mjpeg_candidate_index]
        self._depth_mjpeg_candidate_index += 1
        self._depth_mjpeg_current_topic = topic
        depth_url = resolve_depth_mjpeg_url_for_robot_topic(self._robot, topic)
        self._depth_panel.set_fallback_info(depth_url, topic)
        self._depth_panel.set_stream_status(f"MJPEG fallback 连接中… ({topic})")
        self._depth_panel.set_source_kind(DepthSourceKind.MJPEG_FALLBACK)
        self._viewport.set_depth_loading("正在连接 MJPEG 深度流…")
        self._depth_mjpeg_wait_timer.stop()
        self._depth_stream.connect(depth_url)

    def _arm_depth_mjpeg_wait_timer(self) -> None:
        if not self._depth_using_mjpeg_fallback or self._depth_mjpeg_frame_received:
            return
        wait_ms = int(self._depth_config.mjpeg_wait_s * 1000)
        self._depth_mjpeg_wait_timer.start(wait_ms)

    def _on_depth_worker_status(self, text: str) -> None:
        if self._depth_using_mjpeg_fallback:
            return
        self._depth_panel.set_stream_status(text)

    def _on_depth_mjpeg_wait_timeout(self) -> None:
        if self._depth_raw_frame_received or self._depth_mjpeg_frame_received:
            return
        if not self._depth_using_mjpeg_fallback:
            return
        logger.warning(
            "depth MJPEG fallback timeout (%.1fs); no frames from %s",
            self._depth_config.mjpeg_wait_s,
            self._depth_mjpeg_current_topic or QT_MJPEG_DEPTH_TOPIC,
        )
        self._depth_mjpeg_wait_timer.stop()
        if self._depth_stream.is_streaming():
            self._depth_stream.disconnect()
        else:
            self._start_next_depth_mjpeg_candidate()

    def _show_depth_offline(self, *, tried_mjpeg: bool) -> None:
        if self._depth_raw_frame_received:
            return
        # Stop handling depth MJPEG signals before disconnect(); otherwise
        # synchronous "No Camera" re-enters _start_next_depth_mjpeg_candidate().
        self._depth_using_mjpeg_fallback = False
        self._depth_preview.set_mjpeg_fallback_active(False)
        self._depth_mjpeg_wait_timer.stop()
        if self._depth_stream.is_streaming():
            self._depth_stream.disconnect()
        if tried_mjpeg:
            message = (
                "Raw depth 未桥接；MJPEG fallback 不可用"
                "（已尝试 preview/raw depth MJPEG）"
            )
        else:
            message = "Raw depth 未桥接；MJPEG fallback 未启动"
        self._viewport.set_depth_empty(message)
        self._depth_panel.set_stream_status("离线")
        self._depth_panel.set_source_kind(DepthSourceKind.OFFLINE)
        self._depth_mjpeg_current_topic = ""

    def _on_depth_preview_packet(self, packet: object) -> None:
        if self._view_mode not in ("depth", "split"):
            return
        if not isinstance(packet, DepthPreviewPacket):
            return
        try:
            self._depth_raw_frame_received = True
            self._depth_raw_wait_timer.stop()
            self._depth_mjpeg_wait_timer.stop()
            self._depth_using_mjpeg_fallback = False
            if self._depth_stream.is_streaming():
                self._depth_stream.disconnect()
            if self._view_mode in ("depth", "split"):
                self._viewport.set_depth_frame_rgb(
                    packet.width, packet.height, packet.rgb_bytes
                )
            self._depth_panel.set_stream_status("已连接")
            self._depth_panel.set_source_kind(DepthSourceKind.RAW_HTTP)
        except Exception:
            logger.exception("depth preview frame render failed")

    def _on_depth_stats(self, stats: object) -> None:
        if self._view_mode not in ("depth", "split"):
            return
        self._depth_stats_pending = stats
        if not self._depth_stats_timer.isActive():
            self._flush_depth_stats()
            self._depth_stats_timer.start()

    def _flush_depth_stats(self) -> None:
        from core.camera_depth_frame import DepthFrameStats

        stats = self._depth_stats_pending
        self._depth_stats_pending = None
        if isinstance(stats, DepthFrameStats):
            self._depth_panel.apply_stats(stats)

    def _on_depth_mjpeg_frame(self, jpeg: bytes) -> None:
        if not self._depth_using_mjpeg_fallback:
            return
        if not self._depth_mjpeg_frame_received:
            logger.info(
                "depth MJPEG first frame (%d bytes) topic=%s",
                len(jpeg),
                self._depth_mjpeg_current_topic or QT_MJPEG_DEPTH_TOPIC,
            )
        self._depth_mjpeg_frame_received = True
        self._depth_mjpeg_wait_timer.stop()
        self._viewport.set_depth_frame_jpeg(jpeg)
        if self._depth_mjpeg_current_topic:
            self._depth_panel.set_stream_status(
                f"MJPEG fallback 已连接 ({self._depth_mjpeg_current_topic})"
            )

    def _on_depth_source_kind(self, kind: str) -> None:
        if self._depth_using_mjpeg_fallback and kind == DepthSourceKind.RAW_HTTP.value:
            return
        self._depth_panel.set_source_kind(kind)

    def _on_depth_worker_failed(self, detail: str) -> None:
        self._depth_panel.set_stream_status(f"Raw Depth 离线 ({detail})")
        if self._depth_raw_frame_received:
            return
        if not self._depth_raw_wait_timer.isActive():
            self._maybe_start_depth_mjpeg_fallback()

    def _on_rgb_status(self, text: str) -> None:
        self._toolbar.set_status(text)
        # RGB status must not clobber depth-only viewport.
        if self._view_mode == "depth":
            return
        lower = text.lower()
        if text.startswith("Connecting"):
            self._viewport.set_loading()
        elif "timeout" in lower or text == "EOF" or text.startswith("Error"):
            self._viewport.set_stalled(text)
        elif text == "No Camera":
            self._viewport.set_empty()

    def _on_rgb_connected(self, ok: bool) -> None:
        self._toolbar.set_streaming(ok)
        if not ok and self._stream.stats.last_frame_ts <= 0:
            if self._stream.stats.status == "No Camera":
                self._viewport.set_empty()

    def _on_depth_mjpeg_status(self, text: str) -> None:
        if not self._depth_using_mjpeg_fallback:
            return
        if text.startswith("Connecting"):
            topic = self._depth_mjpeg_current_topic or QT_MJPEG_DEPTH_TOPIC
            self._viewport.set_depth_loading("正在连接 MJPEG 深度流…")
            self._depth_panel.set_stream_status(f"MJPEG fallback 连接中… ({topic})")
        elif text == "No Camera":
            if not self._depth_mjpeg_frame_received:
                self._depth_mjpeg_wait_timer.stop()
                topics = self._depth_config.mjpeg_fallback_topics
                if self._depth_mjpeg_candidate_index >= len(topics):
                    return
                self._start_next_depth_mjpeg_candidate()
        elif (
            not self._depth_mjpeg_frame_received
            and (text.startswith("HTTPError") or text.startswith("URL error"))
        ):
            self._depth_mjpeg_wait_timer.stop()
            if self._depth_stream.is_streaming():
                self._depth_stream.disconnect()
            else:
                self._start_next_depth_mjpeg_candidate()

    def _on_depth_mjpeg_connected(self, ok: bool) -> None:
        if not self._depth_using_mjpeg_fallback:
            return
        if not ok:
            # Worker emits connected(False) at session start; do not treat that as
            # failure. Offline / next-candidate is driven by No Camera, HTTP errors,
            # and the MJPEG wait timer.
            return
        topic = self._depth_mjpeg_current_topic or QT_MJPEG_DEPTH_TOPIC
        self._depth_panel.set_stream_status(f"MJPEG fallback 已连接 ({topic})")
        self._depth_panel.set_source_kind(DepthSourceKind.MJPEG_FALLBACK)
        self._arm_depth_mjpeg_wait_timer()

    def _on_ros2_snapshot(self, snapshot: object) -> None:
        from core.camera_ros2_bridge_manager import CameraRos2PanelSnapshot

        if not isinstance(snapshot, CameraRos2PanelSnapshot):
            return
        result = snapshot.topic_probe_result
        self._apply_probe_panels(result)

    def _apply_probe_panels(
        self, result: Optional[CameraTopicProbeResult]
    ) -> None:
        self._depth_panel.apply_probe(result)
        self._scan_panel.apply_probe(result)

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
        try:
            self._binder.session.send_velocity(lx, ly, az)
        except Exception:
            logger.exception("manual velocity failed")

    def _on_stop_requested(self) -> None:
        if self._binder is not None:
            self._binder.session.stop_motion()
