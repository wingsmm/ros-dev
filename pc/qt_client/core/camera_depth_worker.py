"""ROS2 depth subscriber + PC-side preview (QThread worker)."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Optional

from PyQt5.QtCore import QObject, QTimer, pyqtSignal, pyqtSlot

from core.camera_depth_colormap import downscale_rgb, ros_image_to_depth_frame
from core.camera_depth_frame import DepthFrameStats, DepthSourceKind
from core.camera_depth_source import DepthSourceConfig
from core.ros2_context_ref import acquire_rclpy, release_rclpy
from core.ros2_runtime import Ros2RuntimeError, require_ros2_bridge

logger = logging.getLogger(__name__)

try:
    import rclpy
    from rclpy.qos import qos_profile_sensor_data
    from sensor_msgs.msg import CameraInfo, Image

    _ROS2_AVAILABLE = True
except ImportError:
    _ROS2_AVAILABLE = False


@dataclass(frozen=True)
class DepthPreviewPacket:
    width: int
    height: int
    rgb_bytes: bytes
    stats: DepthFrameStats
    source_kind: DepthSourceKind = DepthSourceKind.RAW_ROS2


class _DepthRos2Node:
    def __init__(self, config: DepthSourceConfig, on_image) -> None:
        if not _ROS2_AVAILABLE:
            raise RuntimeError("ROS2 dependencies not available")
        acquire_rclpy()
        self._config = config
        self._on_image = on_image
        self._camera_info_online = False
        self._node = rclpy.create_node("xtark_depth_preview_worker")
        self._image_sub = self._node.create_subscription(
            Image,
            config.image_topic,
            self._on_ros_image,
            qos_profile_sensor_data,
        )
        self._info_sub = self._node.create_subscription(
            CameraInfo,
            config.camera_info_topic,
            self._on_camera_info,
            qos_profile_sensor_data,
        )
        self._frame_count = 0
        self._window_start = time.monotonic()
        self._last_fps = 0.0
        self._last_emit_mono = 0.0
        min_interval = 1.0 / max(config.max_preview_fps, 0.1)
        self._min_emit_interval_s = min_interval

    def destroy(self) -> None:
        if rclpy.ok():
            self._node.destroy_node()
        release_rclpy()

    def spin_once(self) -> None:
        rclpy.spin_once(self._node, timeout_sec=0)

    def _on_camera_info(self, _msg: CameraInfo) -> None:
        self._camera_info_online = True

    def _on_ros_image(self, msg: Image) -> None:
        now_mono = time.monotonic()
        if (
            self._last_emit_mono > 0.0
            and (now_mono - self._last_emit_mono) < self._min_emit_interval_s
        ):
            return

        self._frame_count += 1
        elapsed = max(now_mono - self._window_start, 0.001)
        if elapsed >= 1.0:
            self._last_fps = self._frame_count / elapsed
            self._frame_count = 0
            self._window_start = now_mono

        recv_ns = time.time_ns()
        stamp_ns = int(msg.header.stamp.sec) * 1_000_000_000 + int(
            msg.header.stamp.nanosec
        )
        latency_ms = max(0.0, (recv_ns - stamp_ns) / 1_000_000.0)

        try:
            frame, rgb = ros_image_to_depth_frame(
                data=msg.data,
                width=int(msg.width),
                height=int(msg.height),
                encoding=str(msg.encoding),
                timestamp_ns=stamp_ns,
                min_depth_m=self._config.min_depth_m,
                max_depth_m=self._config.max_depth_m,
                camera_info_online=self._camera_info_online,
                fps=self._last_fps,
                latency_ms=latency_ms,
            )
        except Exception as exc:
            logger.warning("depth frame decode failed: %s", exc)
            return

        rgb = downscale_rgb(rgb, self._config.preview_downscale)
        self._last_emit_mono = now_mono

        stats = DepthFrameStats(
            center_distance_m=frame.stats.center_distance_m,
            nearest_valid_m=frame.stats.nearest_valid_m,
            valid_ratio=frame.stats.valid_ratio,
            min_depth_m=frame.stats.min_depth_m,
            max_depth_m=frame.stats.max_depth_m,
            fps=self._last_fps,
            latency_ms=latency_ms,
            encoding=frame.encoding,
            camera_info_online=self._camera_info_online,
        )
        packet = DepthPreviewPacket(
            width=int(rgb.shape[1]),
            height=int(rgb.shape[0]),
            rgb_bytes=rgb.tobytes(),
            stats=stats,
        )
        self._on_image(packet)


class CameraDepthWorker(QObject):
    """Runs in dedicated QThread — subscribes raw depth, emits PC preview."""

    preview_ready = pyqtSignal(object)
    status_changed = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(
        self,
        config: Optional[DepthSourceConfig] = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._config = config or DepthSourceConfig.from_env()
        self._node: Optional[_DepthRos2Node] = None
        self._spin_timer = QTimer(self)
        self._spin_timer.setInterval(self._config.spin_interval_ms)
        self._spin_timer.timeout.connect(self._spin_once)
        self._running = False
        self._connected_announced = False

    def is_active(self) -> bool:
        return self._running and self._node is not None

    @pyqtSlot()
    def start_worker(self) -> None:
        if self._running:
            return
        try:
            require_ros2_bridge()
        except Ros2RuntimeError as exc:
            self._fail_worker(str(exc))
            return
        if not _ROS2_AVAILABLE:
            self._fail_worker("ROS2 依赖未安装")
            return
        try:
            self._node = _DepthRos2Node(self._config, self._on_preview)
        except Exception as exc:
            logger.exception("depth worker start failed")
            self._fail_worker(str(exc))
            self._node = None
            return
        self._running = True
        self._connected_announced = False
        self._spin_timer.start()
        self.status_changed.emit("Raw Depth 订阅中…")
        logger.info("camera depth worker started topics=%s", self._config.image_topic)

    @pyqtSlot()
    def stop_worker(self) -> None:
        self._spin_timer.stop()
        if self._node is not None:
            try:
                self._node.destroy()
            except Exception:
                logger.exception("depth worker destroy failed")
            self._node = None
        self._running = False
        self._connected_announced = False
        self.status_changed.emit("已停止")
        logger.info("camera depth worker stopped")

    def _on_preview(self, packet: DepthPreviewPacket) -> None:
        self.preview_ready.emit(packet)
        if not self._connected_announced:
            self._connected_announced = True
            self.status_changed.emit("Raw Depth 已连接")

    def _fail_worker(self, detail: str) -> None:
        self._spin_timer.stop()
        self._running = False
        self._connected_announced = False
        self.failed.emit(detail)

    def _spin_once(self) -> None:
        if self._node is None:
            return
        try:
            self._node.spin_once()
        except Exception as exc:
            logger.exception("depth worker spin failed")
            self._fail_worker(str(exc))
