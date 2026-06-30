from __future__ import annotations

import logging
import time
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Optional

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QImage
from PyQt5.QtWidgets import QFrame, QHBoxLayout, QScrollArea, QSizePolicy, QVBoxLayout, QWidget

from core.camera_depth_frame import DepthFrameStats, DepthSourceKind
from core.camera_depth_http_worker import DepthPreviewPacket
from core.camera_depth_preview_manager import CameraDepthPreviewManager
from core.camera_depth_source import DepthSourceConfig
from core.camera_ground_config import GroundPerceptionConfig
from core.camera_ground_overlay import GroundPerceptionOverlay
from core.camera_ground_trapezoid import TrapezoidOverlay
from core.camera_ground_plane import (
    GroundPlaneEstimate,
    estimate_ground_plane,
    plane_angle_deg,
)
from core.camera_mjpeg_url import QT_MJPEG_TOPIC, resolve_mjpeg_url_for_robot
from core.camera_topic_probe import CameraTopicProbeResult
from core.robot_telemetry_binder import RobotTelemetryBinder
from core.ros2_bridge_manager import Ros2BridgeManager
from core.ros2_runtime import auto_camera_bridge_enabled
from ui.models.robot_info import RobotInfo
from ui.models.robot_settings import effective_manual_speeds
from ui.widgets.camera_depth_panel import CameraDepthPanel
from ui.widgets.camera_ros2_panel import CameraRos2Panel
from ui.widgets.camera_scan_panel import CameraScanPanel
from ui.widgets.camera_toolbar import CameraToolbar
from ui.widgets.camera_view_mode_bar import CameraViewModeBar
from ui.widgets.camera_viewport import CameraViewport
from ui.widgets.ground_perception_panel import GroundPerceptionPanel
from ui.widgets.manual_control_strip import ManualControlStrip
from ui.widgets.mjpeg_stream import MjpegStreamController
from ui.widgets.telemetry_details_strip import TelemetryDetailsStrip

logger = logging.getLogger(__name__)

_GROUND_RENDER_LOG_INTERVAL_S = 5.0
_GROUND_PLANE_ESTIMATE_INTERVAL_S = 1.0
_GROUND_PLANE_LOG_INTERVAL_S = 5.0


class CameraPage(QWidget):
    """Camera module: RGB MJPEG + raw-depth HTTP preview + ground perception overlay."""

    def __init__(
        self,
        robot: RobotInfo,
        telemetry_binder: Optional[RobotTelemetryBinder] = None,
        ros2_bridge: Optional[Ros2BridgeManager] = None,
        parent=None,
    ):
        super().__init__(parent)
        self._robot = robot
        self._binder = telemetry_binder
        self._ros2_bridge = ros2_bridge
        self._view_mode = "rgb"

        self._stream = MjpegStreamController(self, timeout_s=5.0, max_fps=8.0)
        self._depth_config = DepthSourceConfig.from_env(
            master_uri=getattr(robot, "master_uri", "") or ""
        )
        self._depth_preview = CameraDepthPreviewManager(
            config=self._depth_config,
            parent=self,
        )

        # 地面感知（Phase 1）
        self._ground_config = GroundPerceptionConfig.from_env()
        self._ground_config.log_summary()
        self._ground_overlay = self._create_ground_overlay(self._ground_config.overlay_method)
        self._ground_panel: Optional[GroundPerceptionPanel] = None
        self._ground_panel_scroll: Optional[QScrollArea] = None
        self._ground_running = False  # 感知算法是否在运行
        self._latest_rgb_frame: Optional[QImage] = None  # 最新 RGB 帧缓存
        self._latest_depth_frame: Optional[DepthPreviewPacket] = None  # 最新 Depth 帧缓存
        self._latest_ground_plane: Optional[GroundPlaneEstimate] = None
        self._ground_plane_candidate: Optional[GroundPlaneEstimate] = None
        self._ground_plane_candidate_count = 0
        self._ground_plane_future: Optional[Future] = None
        self._ground_plane_generation = 0
        self._ground_plane_hold_frames = 0
        self._ground_plane_last_estimate_mono = 0.0
        self._ground_plane_last_log_mono = 0.0
        self._ground_render_log_mono = 0.0
        self._ground_rgb_logged = False
        self._ground_depth_logged = False
        self._ground_executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="ground-plane",
        )

        self._depth_raw_frame_received = False
        self._ground_plane_result_timer = QTimer(self)
        self._ground_plane_result_timer.setInterval(50)
        self._ground_plane_result_timer.timeout.connect(self._poll_ground_plane_result)
        self._depth_raw_wait_timer = QTimer(self)
        self._depth_raw_wait_timer.setSingleShot(True)
        self._depth_raw_wait_timer.timeout.connect(self._on_depth_raw_wait_timeout)
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
        if self._ros2_bridge is not None:
            self._ros2_panel.set_manager(self._ros2_bridge)
            self._ros2_bridge.register_rgb_stream(self._stream)
            self._depth_preview.set_bridge_sink(
                self._ros2_bridge.offer_depth_bridge_frame
            )
        self._manual = ManualControlStrip()

        # 地面感知面板
        self._ground_panel = GroundPerceptionPanel(self._ground_config)

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
        # 感知面板内容较多：用右栏内滚动承载，避免切模式时撑大顶层窗口。
        side_col.addWidget(self._ground_panel_scroll)
        side_col.addWidget(self._scan_panel)
        side_col.addStretch(1)
        preview_row.addLayout(side_col, 1)
        root.addLayout(preview_row, 1)

        # 初始状态：隐藏感知面板
        if self._ground_panel_scroll is not None:
            self._ground_panel_scroll.setVisible(False)

        root.addWidget(self._ros2_panel)
        root.addWidget(self._telemetry)
        root.addWidget(self._manual)

    def _wire_signals(self) -> None:
        self._toolbar.connect_requested.connect(self._on_connect)
        self._toolbar.disconnect_requested.connect(self._on_disconnect_all)
        self._toolbar.reconnect_requested.connect(self._on_reconnect)

        self._view_mode_bar.mode_changed.connect(self._on_view_mode_changed)

        self._stream.frame.connect(self._on_rgb_frame)  # 先缓存帧，再决定怎么显示
        self._stream.status_changed.connect(self._on_rgb_status)
        self._stream.connected_changed.connect(self._on_rgb_connected)
        self._stream.fps_changed.connect(self._toolbar.set_fps)

        self._depth_preview.preview_ready.connect(self._on_depth_preview_packet)
        self._depth_preview.stats_updated.connect(self._on_depth_stats)
        self._depth_preview.status_changed.connect(self._on_depth_worker_status)
        self._depth_preview.source_kind_changed.connect(self._on_depth_source_kind)
        self._depth_preview.worker_failed.connect(self._on_depth_worker_failed)

        if self._ros2_bridge is not None:
            self._ros2_bridge.snapshot_updated.connect(self._on_ros2_snapshot)

        self._manual.velocity_requested.connect(self._on_velocity_requested)
        self._manual.stop_requested.connect(self._on_stop_requested)

        # 地面感知面板信号
        if self._ground_panel is not None:
            self._ground_panel.start_clicked.connect(self._on_ground_start)
            self._ground_panel.stop_clicked.connect(self._on_ground_stop)
            self._ground_panel.method_changed.connect(self._on_ground_method_changed)

    def _apply_robot_defaults(self) -> None:
        self._apply_stream_url_display()
        self._toolbar.set_topic_hint(
            f"RGB {QT_MJPEG_TOPIC} | Depth Raw HTTP :8082 "
            f"({self._depth_config.image_topic}) | ROS2 diagnostics below"
        )
        self._apply_manual_speed_defaults()
        self._depth_panel.set_stream_status("未接入")
        self._depth_panel.set_source_kind(DepthSourceKind.OFFLINE)
        self._viewport.set_depth_empty()

    def _apply_manual_speed_defaults(self) -> None:
        linear, angular = effective_manual_speeds(self._robot)
        self._manual.set_speeds(linear=linear, angular=angular)

    def refresh_robot_settings(self) -> None:
        self._apply_stream_url_display()
        self._apply_manual_speed_defaults()

    def _apply_stream_url_display(self) -> None:
        rgb_url = resolve_mjpeg_url_for_robot(self._robot)
        self._toolbar.set_stream_urls(rgb_url, self._depth_config.http_frame_url)

    def on_page_activated(self) -> None:
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
        self._sync_bridge_capabilities()

    def on_page_deactivated(self) -> None:
        self._manual.set_keyboard_enabled(False)
        self._set_bridge_capabilities(rgb=False, depth=False)
        self._on_disconnect_all()

    def shutdown(self) -> None:
        self._manual.set_keyboard_enabled(False)
        self._depth_stats_timer.stop()
        self._ground_plane_result_timer.stop()
        self._ground_executor.shutdown(wait=False, cancel_futures=True)
        self._depth_preview.shutdown()
        self._set_bridge_capabilities(rgb=False, depth=False)
        if self._ros2_bridge is not None:
            self._ros2_bridge.register_rgb_stream(None)
        if self._binder is not None:
            self._binder.unregister_panel(self._telemetry.telemetry_panel)
            self._binder.session.stop_motion()
        self._stream.shutdown()

    def _on_view_mode_changed(self, mode: str) -> None:
        prev = self._view_mode
        self._view_mode = mode
        self._viewport.set_view_mode(mode)
        logger.info(
            "camera view mode: %s -> %s (ground_running=%s)",
            prev,
            mode,
            self._ground_running,
        )

        # 切换面板可见性
        if mode == "perception":
            self._depth_panel.setVisible(False)
            if self._ground_panel_scroll is not None:
                self._ground_panel_scroll.setVisible(True)
            # 暂停 RGB 推送到 viewport，由感知模式自己处理显示
            self._stream.set_max_fps(self._ground_config.max_fps)
            self._stream.resume()
            # 确保 depth 流在跑（供 tap），但不推送到 UI
            self._start_depth_preview_for_perception()
            # 显示 Idle 画面
            if not self._ground_running:
                self._show_ground_idle()
        else:
            self._depth_panel.setVisible(True)
            if self._ground_panel_scroll is not None:
                self._ground_panel_scroll.setVisible(False)
            # 停止感知（如果在运行）
            if self._ground_running:
                self._on_ground_stop()

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

        self._sync_bridge_capabilities()
        if (
            mode == "depth"
            and not self._depth_preview.is_running()
            and not self._depth_preview.is_starting()
        ):
            self._viewport.set_depth_empty()

    def _stop_depth_preview_for_rgb(self) -> None:
        self._depth_raw_wait_timer.stop()
        self._depth_preview.pause()

    def _start_depth_preview_for_perception(self) -> None:
        """为感知模式启动 depth 流（只取帧，不推送到 viewport）"""
        self._depth_raw_frame_received = False
        self._depth_raw_wait_timer.stop()
        if not self._depth_preview.is_running() and not self._depth_preview.is_starting():
            self._depth_preview.start()
        else:
            self._depth_preview.resume()

    # ============================================================
    # 地面感知相关方法
    # ============================================================

    def _on_rgb_frame(self, jpeg: bytes) -> None:
        """收到 RGB 帧：缓存 + 模式分发"""
        # 解析为 QImage
        img = QImage.fromData(jpeg)
        if img.isNull():
            return

        self._latest_rgb_frame = img

        if (
            self._view_mode == "perception"
            and self._ground_running
            and not self._ground_rgb_logged
        ):
            logger.info(
                "ground perception RGB tap: %dx%d fmt=%s",
                img.width(),
                img.height(),
                int(img.format()),
            )
            self._ground_rgb_logged = True

        # 根据模式分发
        if self._view_mode == "perception" and self._ground_running:
            self._render_ground_overlay()
        elif self._view_mode in ("rgb", "split"):
            self._viewport.set_frame_jpeg(jpeg)

    def _on_ground_start(self) -> None:
        """开始感知"""
        self._ground_running = True
        self._ground_rgb_logged = False
        self._ground_depth_logged = False
        self._ground_render_log_mono = 0.0
        self._ground_overlay.reset_session_logs()
        self._latest_ground_plane = None
        self._ground_plane_candidate = None
        self._ground_plane_candidate_count = 0
        self._ground_plane_generation += 1
        if self._ground_plane_future is not None and not self._ground_plane_future.done():
            self._ground_plane_future.cancel()
        self._ground_plane_future = None
        self._ground_plane_hold_frames = 0
        self._ground_plane_last_estimate_mono = 0.0
        self._ground_plane_last_log_mono = 0.0
        self._ground_plane_result_timer.start()
        rgb_ready = self._latest_rgb_frame is not None and not self._latest_rgb_frame.isNull()
        depth_ready = self._latest_depth_frame is not None
        logger.info(
            "ground perception started: rgb_cached=%s depth_cached=%s max_fps=%d "
            "a=%.2fm range=%.1fm",
            rgb_ready,
            depth_ready,
            self._ground_config.max_fps,
            self._ground_config.corridor_width_m,
            self._ground_config.overlay_max_range_m,
        )
        if not rgb_ready:
            logger.warning(
                "ground perception: no RGB frame yet — waiting for MJPEG stream"
            )
        # 如果还没连接，自动连接
        if not self._stream.is_streaming():
            self._on_connect()

    def _on_ground_stop(self) -> None:
        """停止感知"""
        self._ground_running = False
        self._ground_plane_generation += 1
        if self._ground_plane_future is not None and not self._ground_plane_future.done():
            self._ground_plane_future.cancel()
        self._ground_plane_future = None
        self._ground_plane_result_timer.stop()
        if self._ground_panel is not None:
            self._ground_panel.set_running(False)
        logger.info("ground perception stopped (view_mode=%s)", self._view_mode)
        # 显示 Idle 画面
        if self._view_mode == "perception":
            self._show_ground_idle()

    def _show_ground_idle(self) -> None:
        """显示感知模式 Idle 画面"""
        idle_img = self._ground_overlay.draw_idle_screen(
            width=800, height=450  # 默认大小，viewport 会缩放
        )
        self._viewport.set_frame_rgb(idle_img)

    def _render_ground_overlay(self) -> None:
        """渲染感知 Overlay 到 viewport"""
        if self._latest_rgb_frame is None:
            return

        # Phase 1: 只绘制灯带
        status = (
            f"Running | "
            f"corridor: {self._ground_config.corridor_width_m:.2f}m | "
            f"range: {self._ground_config.overlay_max_range_m:.1f}m"
        )
        ground_plane = (
            self._latest_ground_plane
            if self._latest_ground_plane is not None
            and self._latest_ground_plane.valid
            else None
        )
        draw_corridor = (
            self._ground_config.overlay_method == "trapezoid"
            or ground_plane is not None
        )
        if self._ground_config.overlay_method == "trapezoid":
            status += " | trapezoid overlay"
        elif ground_plane is not None:
            status += " | depth ground OK"
        else:
            status += " | waiting depth ground"
        result, draw_meta = self._ground_overlay.draw_overlay(
            self._latest_rgb_frame,
            draw_corridor=draw_corridor,
            status_text=status,
            ground_plane=ground_plane,
        )

        now = time.monotonic()
        if draw_meta.corridor_drawn:
            if now - self._ground_render_log_mono >= _GROUND_RENDER_LOG_INTERVAL_S:
                logger.info(
                    "ground overlay render: corridor=%d verts frame=%dx%d "
                    "depth_cached=%s",
                    draw_meta.corridor_vertices,
                    draw_meta.image_width,
                    draw_meta.image_height,
                    self._latest_depth_frame is not None,
                )
                self._ground_render_log_mono = now
        elif now - self._ground_render_log_mono >= _GROUND_RENDER_LOG_INTERVAL_S:
            logger.warning(
                "ground overlay render: corridor not drawn frame=%dx%d raw_pts=%d",
                draw_meta.image_width,
                draw_meta.image_height,
                draw_meta.raw_corridor_points,
            )
            self._ground_render_log_mono = now

        # 显示到 viewport
        self._viewport.set_frame_rgb(result)

    def _on_depth_preview_packet(self, packet: object) -> None:
        """收到 Depth 帧：缓存 + 模式分发"""
        if not isinstance(packet, DepthPreviewPacket):
            return

        self._latest_depth_frame = packet
        self._depth_raw_frame_received = True
        self._depth_raw_wait_timer.stop()
        self._depth_panel.set_stream_status("已连接")
        self._depth_panel.set_source_kind(DepthSourceKind.RAW_HTTP)

        if (
            self._view_mode == "perception"
            and self._ground_running
            and not self._ground_depth_logged
        ):
            logger.info(
                "ground perception depth tap: %dx%d raw=%dx%d bytes=%d depth=%s",
                packet.width,
                packet.height,
                packet.raw_width,
                packet.raw_height,
                len(packet.rgb_bytes),
                packet.depth_meters is not None,
            )
            self._ground_depth_logged = True
        if (
            self._view_mode == "perception"
            and self._ground_running
            and self._ground_config.overlay_method == "geometric"
        ):
            self._update_ground_plane(packet)

        # 只有非感知模式才推送到 viewport
        if self._view_mode == "depth":
            try:
                self._viewport.set_depth_frame_rgb(
                    packet.width, packet.height, packet.rgb_bytes
                )
            except Exception:
                logger.exception("depth preview frame render failed")
        elif self._view_mode == "split":
            # split 模式也正常显示
            try:
                self._viewport.set_depth_frame_rgb(
                    packet.width, packet.height, packet.rgb_bytes
                )
            except Exception:
                logger.exception("depth preview frame render failed")

    def _update_ground_plane(self, packet: DepthPreviewPacket) -> None:
        """Fit the visible floor plane from raw depth for perception diagnostics."""
        now = time.monotonic()
        if (
            self._ground_plane_last_estimate_mono
            and now - self._ground_plane_last_estimate_mono
            < _GROUND_PLANE_ESTIMATE_INTERVAL_S
        ):
            return
        self._ground_plane_last_estimate_mono = now

        if packet.depth_meters is None:
            self._latest_ground_plane = None
            if self._ground_panel is not None:
                self._ground_panel.set_calibration_status("等待 raw depth", True)
            return
        if self._ground_plane_future is not None and not self._ground_plane_future.done():
            return

        generation = self._ground_plane_generation
        self._ground_plane_future = self._ground_executor.submit(
            self._estimate_ground_plane_task,
            generation,
            packet.depth_meters,
            packet.camera_info,
            packet.raw_width,
            packet.raw_height,
            packet.stats.valid_ratio,
        )
        if not self._ground_plane_result_timer.isActive():
            self._ground_plane_result_timer.start()
        return

    def _estimate_ground_plane_task(
        self,
        generation: int,
        depth_meters: object,
        camera_info: Optional[dict],
        raw_width: int,
        raw_height: int,
        valid_ratio: float,
    ) -> tuple[int, GroundPlaneEstimate, float, float]:
        t0 = time.monotonic()
        plane = estimate_ground_plane(
            depth_meters,
            config=self._ground_config,
            camera_info=camera_info,
            raw_width=raw_width,
            raw_height=raw_height,
            max_depth_m=self._depth_config.max_depth_m,
            max_samples=1200,
            iterations=18,
        )
        elapsed_ms = (time.monotonic() - t0) * 1000.0
        return generation, plane, elapsed_ms, valid_ratio

    def _poll_ground_plane_result(self) -> None:
        future = self._ground_plane_future
        if future is None or not future.done():
            return
        self._ground_plane_future = None
        try:
            generation, plane, elapsed_ms, valid_ratio = future.result()
        except Exception:
            logger.exception("ground plane estimation failed")
            if self._ground_panel is not None:
                self._ground_panel.set_calibration_status("ground fit failed", True)
            return
        if generation != self._ground_plane_generation or not self._ground_running:
            return

        now = time.monotonic()
        accepted_plane = self._accept_ground_plane(plane)
        if (
            elapsed_ms >= 30.0
            or now - self._ground_plane_last_log_mono >= _GROUND_PLANE_LOG_INTERVAL_S
        ):
            logger.info(
                "ground plane estimate: %.1fms valid=%s accepted=%s ratio=%.2f "
                "rms=%.3f samples=%d inliers=%d reason=%s",
                elapsed_ms,
                plane.valid,
                accepted_plane is not None,
                plane.inlier_ratio,
                plane.rms_error_m,
                plane.sample_count,
                plane.inlier_count,
                plane.reason,
            )
            self._ground_plane_last_log_mono = now
        if self._ground_panel is not None:
            self._ground_panel.update_valid_pixels(valid_ratio * 100.0)
            if accepted_plane is not None and accepted_plane.valid:
                self._ground_panel.set_calibration_status(
                    f"ground locked {accepted_plane.inlier_ratio * 100:.0f}% / RMS {accepted_plane.rms_error_m * 100:.1f}cm",
                    False,
                )
            else:
                self._ground_panel.set_calibration_status(
                    f"ground fit weak {plane.reason or 'low confidence'}",
                    True,
                )

    def _accept_ground_plane(
        self, plane: GroundPlaneEstimate
    ) -> Optional[GroundPlaneEstimate]:
        """Reject single-frame plane jumps so the overlay does not fly away."""
        current = self._latest_ground_plane
        if not plane.valid:
            if current is not None:
                self._ground_plane_hold_frames += 1
                return current
            self._latest_ground_plane = None
            self._ground_plane_candidate = None
            self._ground_plane_candidate_count = 0
            self._ground_plane_hold_frames = 0
            return None

        if current is not None:
            angle = plane_angle_deg(current, plane)
            offset_jump = abs(current.offset - plane.offset)
            if angle > 12.0 or offset_jump > 0.12:
                now = time.monotonic()
                if now - self._ground_plane_last_log_mono >= _GROUND_PLANE_LOG_INTERVAL_S:
                    logger.info(
                        "ground plane jump rejected: angle=%.1fdeg offset=%.3fm "
                        "ratio=%.2f rms=%.3f",
                        angle,
                        offset_jump,
                        plane.inlier_ratio,
                        plane.rms_error_m,
                    )
                    self._ground_plane_last_log_mono = now
                self._ground_plane_hold_frames += 1
                return current
        else:
            if plane.inlier_ratio >= 0.32 and plane.rms_error_m <= 0.025:
                self._latest_ground_plane = plane
                self._ground_plane_candidate = None
                self._ground_plane_candidate_count = 0
                self._ground_plane_hold_frames = 0
                return plane
            candidate = self._ground_plane_candidate
            if (
                candidate is not None
                and plane_angle_deg(candidate, plane) <= 10.0
                and abs(candidate.offset - plane.offset) <= 0.25
            ):
                self._ground_plane_candidate_count += 1
            else:
                self._ground_plane_candidate = plane
                self._ground_plane_candidate_count = 1
            if self._ground_plane_candidate_count < 2:
                return None

        self._latest_ground_plane = plane
        self._ground_plane_candidate = None
        self._ground_plane_candidate_count = 0
        self._ground_plane_hold_frames = 0
        return plane

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
        if self._view_mode in ("depth", "split"):
            self._depth_preview.restart()
            self._start_depth_preview()
        else:
            self._depth_preview.pause()

    def _on_disconnect_all(self) -> None:
        if self._ground_running:
            self._on_ground_stop()
        self._depth_raw_wait_timer.stop()
        self._depth_raw_frame_received = False
        self._stream.disconnect()
        self._depth_preview.stop()
        self._depth_panel.set_stream_status("未接入")
        self._depth_panel.set_source_kind(DepthSourceKind.OFFLINE)

    def _start_depth_preview(self) -> None:
        if self._view_mode not in ("depth", "split"):
            return
        self._depth_raw_frame_received = False
        self._depth_raw_wait_timer.stop()
        self._depth_panel.set_stream_status("连接中")
        self._depth_panel.set_source_kind(DepthSourceKind.OFFLINE)
        self._viewport.set_depth_loading()
        if self._depth_preview.is_running() or self._depth_preview.is_starting():
            self._depth_preview.resume()
        else:
            self._depth_preview.start()
        self._depth_raw_wait_timer.start(int(self._depth_config.raw_wait_s * 1000))

    def _on_depth_raw_wait_timeout(self) -> None:
        if self._depth_raw_frame_received:
            return
        logger.info("depth raw HTTP wait expired; showing offline")
        self._show_depth_offline()

    def _on_depth_worker_status(self, text: str) -> None:
        self._depth_panel.set_stream_status(text)

    def _show_depth_offline(self) -> None:
        if self._depth_raw_frame_received:
            return
        self._viewport.set_depth_empty("Raw depth HTTP :8082 未连接")
        self._depth_panel.set_stream_status("离线")
        self._depth_panel.set_source_kind(DepthSourceKind.OFFLINE)

    def _on_depth_stats(self, stats: object) -> None:
        if self._view_mode not in ("depth", "split"):
            return
        self._depth_stats_pending = stats
        if not self._depth_stats_timer.isActive():
            self._flush_depth_stats()
            self._depth_stats_timer.start()

    def _flush_depth_stats(self) -> None:
        stats = self._depth_stats_pending
        self._depth_stats_pending = None
        if isinstance(stats, DepthFrameStats):
            self._depth_panel.apply_stats(stats)

    def _on_depth_source_kind(self, kind: str) -> None:
        self._depth_panel.set_source_kind(kind)

    def _on_depth_worker_failed(self, detail: str) -> None:
        self._depth_panel.set_stream_status(f"Raw Depth 离线 ({detail})")
        if self._depth_raw_frame_received:
            return
        if not self._depth_raw_wait_timer.isActive():
            self._show_depth_offline()

    def _on_rgb_status(self, text: str) -> None:
        self._toolbar.set_status(text)
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

    def _on_ros2_snapshot(self, snapshot: object) -> None:
        del snapshot
        if self._ros2_bridge is None:
            return
        self._apply_probe_panels(self._ros2_bridge.camera_snapshot().topic_probe_result)
        self._ros2_panel.refresh_display()

    def _apply_probe_panels(
        self, result: Optional[CameraTopicProbeResult]
    ) -> None:
        self._depth_panel.apply_probe(result)
        self._scan_panel.apply_probe(result)

    def _maybe_auto_start_camera_bridge(self) -> None:
        if self._ros2_bridge is None or not auto_camera_bridge_enabled():
            return
        if not self._stream.is_streaming():
            return
        if not self._ros2_bridge.snapshot().bridge_running:
            self._ros2_bridge.start_bridge()

    def _set_bridge_capabilities(self, *, rgb: bool, depth: bool) -> None:
        if self._ros2_bridge is None:
            return
        self._ros2_bridge.set_rgb_bridge_enabled(rgb)
        self._ros2_bridge.set_depth_bridge_enabled(depth)

    def _sync_bridge_capabilities(self) -> None:
        if self._view_mode == "rgb":
            self._set_bridge_capabilities(rgb=True, depth=False)
        elif self._view_mode == "depth":
            self._set_bridge_capabilities(rgb=False, depth=True)
        else:
            self._set_bridge_capabilities(rgb=True, depth=True)

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

    def _create_ground_overlay(self, method: str):
        """
        工厂方法：根据绘制方法创建对应的 Overlay 实例
        """
        if method == "trapezoid":
            logger.info("creating ground overlay: trapezoid (hardcoded)")
            return TrapezoidOverlay(self._ground_config)
        else:
            logger.info("creating ground overlay: geometric (camera projection)")
            return GroundPerceptionOverlay(self._ground_config)

    def _on_ground_method_changed(self, method: str) -> None:
        """
        绘制方法切换回调
        支持运行时动态切换，无需重启感知
        """
        if method == self._ground_config.overlay_method:
            return

        logger.info("ground overlay method changed: %s -> %s",
                    self._ground_config.overlay_method, method)

        # 更新配置
        self._ground_config.overlay_method = method

        # 创建新的 Overlay 实例
        self._ground_overlay = self._create_ground_overlay(method)

        # 重置日志状态
        self._ground_overlay.reset_session_logs()

        # 如果正在运行，立即触发一次重绘以显示新效果
        if self._ground_running and self._latest_rgb_frame is not None:
            logger.info("redrawing overlay with new method immediately")
            self._ground_rgb_logged = False
            # ground_plane 参数对 trapezoid 方法无效，直接传 None 即可
            self._render_ground_overlay()
        else:
            logger.info("overlay will switch when perception starts")
