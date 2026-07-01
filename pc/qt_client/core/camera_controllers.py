"""Shared camera controllers: RGB / Depth / Bridge / Ground perception."""

from __future__ import annotations

import logging
import os
import platform
import subprocess
import time
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Optional, Set

from PyQt5.QtCore import QObject, QTimer, pyqtSignal
from PyQt5.QtGui import QImage

from core.camera_depth_http_worker import DepthPreviewPacket
from core.camera_depth_preview_manager import CameraDepthPreviewManager
from core.camera_depth_source import DepthSourceConfig
from core.camera_ground_config import GroundPerceptionConfig
from core.camera_ground_overlay import GroundPerceptionOverlay
from core.camera_ground_plane import (
    GroundPlaneEstimate,
    estimate_ground_plane,
    plane_angle_deg,
)
from core.camera_ground_trapezoid import TrapezoidOverlay
from core.camera_mjpeg_url import QT_MJPEG_TOPIC, resolve_mjpeg_url_for_robot
from core.camera_preview_config import camera_qt_preview_enabled
from core.ros2_runtime import auto_camera_bridge_enabled
from ui.widgets.mjpeg_stream import MjpegStreamController

if TYPE_CHECKING:
    from core.ros2_bridge_manager import Ros2BridgeManager
    from ui.models.robot_info import RobotInfo

logger = logging.getLogger(__name__)

_DEFAULT_CAMERA_SNAPSHOT_DIR = "data/camera_snapshots"
_GROUND_RENDER_LOG_INTERVAL_S = 5.0
_GROUND_PLANE_ESTIMATE_INTERVAL_S = 1.0
_GROUND_PLANE_LOG_INTERVAL_S = 5.0


def open_url_nonblocking(url: str) -> bool:
    """Open browser without blocking Qt."""
    try:
        if os.name == "nt":
            os.startfile(url)  # type: ignore[attr-defined]
            return True
        release = platform.release().lower()
        proc_version = ""
        try:
            with open("/proc/version", "r", encoding="utf-8", errors="ignore") as f:
                proc_version = f.read().lower()
        except OSError:
            pass
        if "microsoft" in release or "microsoft" in proc_version:
            subprocess.Popen(
                ["cmd.exe", "/c", "start", "", url],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            return True
        subprocess.Popen(
            ["xdg-open", url],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return True
    except OSError:
        logger.exception("open url failed: %s", url)
        return False


class RgbCameraController(QObject):
    """MJPEG RGB stream: connect, cache latest frame, snapshot, web open."""

    frame = pyqtSignal(bytes)
    status_changed = pyqtSignal(str)
    connected_changed = pyqtSignal(bool)
    fps_changed = pyqtSignal(float)

    def __init__(
        self,
        robot: "RobotInfo",
        ros2_bridge: Optional["Ros2BridgeManager"] = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._robot = robot
        self._ros2_bridge = ros2_bridge
        self._stream = MjpegStreamController(self, timeout_s=5.0, max_fps=8.0)
        self._latest_rgb_jpeg: Optional[bytes] = None
        self._latest_rgb_frame: Optional[QImage] = None
        self._user_connected = False
        self._manual_disconnect = False
        if ros2_bridge is not None:
            ros2_bridge.register_rgb_stream(self._stream)
        self._stream.frame.connect(self._on_frame)
        self._stream.status_changed.connect(self.status_changed.emit)
        self._stream.connected_changed.connect(self._on_connected)
        self._stream.fps_changed.connect(self.fps_changed.emit)

    @property
    def stream(self) -> MjpegStreamController:
        return self._stream

    @property
    def latest_jpeg(self) -> Optional[bytes]:
        return self._latest_rgb_jpeg

    @property
    def latest_frame(self) -> Optional[QImage]:
        return self._latest_rgb_frame

    @property
    def user_connected(self) -> bool:
        return self._user_connected

    def rgb_url(self) -> str:
        return resolve_mjpeg_url_for_robot(self._robot)

    def refresh_robot(self, robot: "RobotInfo") -> None:
        self._robot = robot

    def connect(self) -> None:
        self._user_connected = True
        self._manual_disconnect = False
        self._stream.connect(self.rgb_url())

    def disconnect(self) -> None:
        self._user_connected = False
        self._manual_disconnect = True
        self._stream.disconnect()
        self._latest_rgb_jpeg = None
        self._latest_rgb_frame = None

    def reconnect(self) -> None:
        self._user_connected = True
        self._manual_disconnect = False
        self._stream.reconnect(self.rgb_url())

    def set_max_fps(self, fps: float) -> None:
        self._stream.set_max_fps(fps)

    def resume(self) -> None:
        self._stream.resume()

    def is_streaming(self) -> bool:
        return self._stream.is_streaming()

    def take_snapshot(self) -> tuple[bool, str, Optional[Path]]:
        if not self._stream.is_streaming():
            return False, "RGB 未连接，无法截图", None
        if self._latest_rgb_frame is None or self._latest_rgb_frame.isNull():
            if not self._latest_rgb_jpeg:
                return False, "暂无 RGB 帧，无法截图", None
            image = QImage.fromData(self._latest_rgb_jpeg)
            if image.isNull():
                return False, "RGB 帧解码失败，无法截图", None
        else:
            image = self._latest_rgb_frame.copy()
        snapshot_dir = self._snapshot_dir()
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        path = snapshot_dir / f"rgb_{stamp}.png"
        if not image.save(str(path), "PNG"):
            return False, "截图保存失败", None
        return True, f"截图已保存: {path.name}", path

    def open_rgb_web(self) -> tuple[bool, str]:
        url = self.rgb_url()
        if not url:
            return False, "RGB URL 为空"
        if not open_url_nonblocking(url):
            return False, "无法打开 RGB Web URL"
        return True, ""

    def shutdown(self) -> None:
        self.disconnect()
        if self._ros2_bridge is not None:
            self._ros2_bridge.register_rgb_stream(None)
        self._stream.shutdown()

    def _on_frame(self, jpeg: bytes) -> None:
        self._latest_rgb_jpeg = bytes(jpeg)
        img = QImage.fromData(jpeg)
        if not img.isNull():
            self._latest_rgb_frame = img
        self.frame.emit(jpeg)

    def _on_connected(self, ok: bool) -> None:
        if not ok and not self._manual_disconnect:
            self._user_connected = False
        self.connected_changed.emit(ok)

    @staticmethod
    def _snapshot_dir() -> Path:
        qt_client_root = Path(__file__).resolve().parents[1]
        configured = os.environ.get("CAMERA_SNAPSHOT_DIR", "").strip()
        raw_path = Path(configured or _DEFAULT_CAMERA_SNAPSHOT_DIR).expanduser()
        if raw_path.is_absolute():
            return raw_path
        return qt_client_root / raw_path


class DepthCameraController(QObject):
    """Raw depth HTTP stream with consumer-based lifecycle."""

    preview_ready = pyqtSignal(object)
    stats_updated = pyqtSignal(object)
    status_changed = pyqtSignal(str)
    source_kind_changed = pyqtSignal(str)
    worker_failed = pyqtSignal(str)

    def __init__(
        self,
        robot: "RobotInfo",
        ros2_bridge: Optional["Ros2BridgeManager"] = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._robot = robot
        self._ros2_bridge = ros2_bridge
        self._config = DepthSourceConfig.from_env(
            master_uri=getattr(robot, "master_uri", "") or ""
        )
        self._preview = CameraDepthPreviewManager(config=self._config, parent=self)
        if ros2_bridge is not None:
            self._preview.set_bridge_sink(ros2_bridge.offer_depth_bridge_frame)
        self._consumers: Set[str] = set()
        self._consumer_decode: dict[str, bool] = {}
        self._latest_packet: Optional[DepthPreviewPacket] = None
        self._preview.preview_ready.connect(self._on_preview)
        self._preview.stats_updated.connect(self.stats_updated.emit)
        self._preview.status_changed.connect(self.status_changed.emit)
        self._preview.source_kind_changed.connect(self.source_kind_changed.emit)
        self._preview.worker_failed.connect(self.worker_failed.emit)

    @property
    def config(self) -> DepthSourceConfig:
        return self._config

    @property
    def preview_manager(self) -> CameraDepthPreviewManager:
        return self._preview


    @property
    def latest_packet(self) -> Optional[DepthPreviewPacket]:
        return self._latest_packet

    def refresh_robot(self, robot: "RobotInfo") -> None:
        self._robot = robot
        new_config = DepthSourceConfig.from_env(
            master_uri=getattr(robot, "master_uri", "") or ""
        )
        if new_config == self._config:
            return
        consumers = dict(self._consumer_decode)
        was_active = bool(self._consumers)
        if self._preview.is_running() or self._preview.is_starting():
            self._preview.stop()
        try:
            self._preview.preview_ready.disconnect(self._on_preview)
            self._preview.stats_updated.disconnect(self.stats_updated.emit)
            self._preview.status_changed.disconnect(self.status_changed.emit)
            self._preview.source_kind_changed.disconnect(self.source_kind_changed.emit)
            self._preview.worker_failed.disconnect(self.worker_failed.emit)
        except TypeError:
            pass
        self._config = new_config
        self._preview = CameraDepthPreviewManager(config=self._config, parent=self)
        if self._ros2_bridge is not None:
            self._preview.set_bridge_sink(self._ros2_bridge.offer_depth_bridge_frame)
        self._preview.preview_ready.connect(self._on_preview)
        self._preview.stats_updated.connect(self.stats_updated.emit)
        self._preview.status_changed.connect(self.status_changed.emit)
        self._preview.source_kind_changed.connect(self.source_kind_changed.emit)
        self._preview.worker_failed.connect(self.worker_failed.emit)
        self._consumer_decode = consumers
        self._consumers = set(consumers.keys())
        if was_active:
            self._sync_stream()

    def http_frame_url(self) -> str:
        return self._config.http_frame_url

    def open_depth_api(self) -> tuple[bool, str]:
        url = self._config.http_frame_url
        if not url:
            return False, "Depth URL 为空"
        if not open_url_nonblocking(url):
            return False, "无法打开 Depth API URL"
        return True, ""

    def add_consumer(self, name: str, *, decode: bool) -> None:
        self._consumers.add(name)
        self._consumer_decode[name] = decode
        self._sync_stream()

    def remove_consumer(self, name: str) -> None:
        self._consumers.discard(name)
        self._consumer_decode.pop(name, None)
        self._sync_stream()

    def has_consumer(self, name: str) -> bool:
        return name in self._consumers

    def is_running(self) -> bool:
        return self._preview.is_running()

    def is_starting(self) -> bool:
        return self._preview.is_starting()

    def restart(self) -> None:
        decode = any(self._consumer_decode.values()) if self._consumers else False
        self._preview.set_preview_decode_enabled(decode)
        self._preview.restart()
        self._sync_stream()

    def force_stop(self) -> None:
        self._consumers.clear()
        self._consumer_decode.clear()
        self._preview.stop()

    def shutdown(self) -> None:
        self.force_stop()
        self._preview.shutdown()

    def cache_packet(self, packet: DepthPreviewPacket) -> None:
        self._latest_packet = packet

    def _on_preview(self, packet: object) -> None:
        if isinstance(packet, DepthPreviewPacket):
            self._latest_packet = packet
        self.preview_ready.emit(packet)

    def _sync_stream(self) -> None:
        if not self._consumers:
            if self._preview.is_running() or self._preview.is_starting():
                self._preview.set_preview_decode_enabled(False)
                self._preview.pause()
            return
        decode = any(self._consumer_decode.values())
        self._preview.set_preview_decode_enabled(decode)
        if self._preview.is_running() or self._preview.is_starting():
            self._preview.resume()
        else:
            self._preview.start()


class CameraBridgeCoordinator(QObject):
    """Keep ROS2 bridge RGB/Depth tee stable across page switches."""

    def __init__(
        self,
        ros2_bridge: Optional["Ros2BridgeManager"],
        rgb: RgbCameraController,
        depth: DepthCameraController,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._bridge = ros2_bridge
        self._rgb = rgb
        self._depth = depth
        self._was_bridge_running = False
        self._bridge_start_queued = False
        if ros2_bridge is not None:
            ros2_bridge.snapshot_updated.connect(self._on_snapshot)

    def refresh_display_hook(self) -> None:
        self._sync_capabilities()

    def ensure_depth_bridge_running(self) -> None:
        """Depth page: tee depth only, keep raw HTTP, start bridge async."""
        if self._bridge is None:
            return
        self._set_capabilities(rgb=False, depth=True)
        if not self._depth.has_consumer("bridge"):
            self._depth.add_consumer("bridge", decode=False)
        if not self._bridge_running() and not self._bridge_start_queued:
            self._bridge_start_queued = True
            QTimer.singleShot(0, self._start_bridge_once)

    def maybe_auto_start_bridge(self) -> None:
        if self._bridge is None or not auto_camera_bridge_enabled():
            return
        if not self._rgb.is_streaming():
            return
        if not self._bridge.camera_snapshot().bridge_running:
            self._bridge.start_bridge()

    def on_bridge_started(self) -> None:
        self._set_capabilities(rgb=True, depth=True)
        self._depth.add_consumer("bridge", decode=False)

    def on_bridge_stopped(self) -> None:
        self._depth.remove_consumer("bridge")
        self._sync_capabilities()

    def shutdown(self) -> None:
        if self._bridge is not None:
            try:
                self._bridge.snapshot_updated.disconnect(self._on_snapshot)
            except TypeError:
                pass

    def _bridge_running(self) -> bool:
        if self._bridge is None:
            return False
        return bool(self._bridge.camera_snapshot().bridge_running)

    def _set_capabilities(self, *, rgb: bool, depth: bool) -> None:
        if self._bridge is None:
            return
        self._bridge.set_rgb_bridge_enabled(rgb)
        self._bridge.set_depth_bridge_enabled(depth)

    def _sync_capabilities(self) -> None:
        if self._bridge_running():
            self._set_capabilities(rgb=False, depth=True)
            if not self._depth.has_consumer("bridge"):
                self._depth.add_consumer("bridge", decode=False)

    def _start_bridge_once(self) -> None:
        self._bridge_start_queued = False
        if self._bridge is None or self._bridge_running():
            return
        self._bridge.start_bridge()

    def _on_snapshot(self, _snapshot: object) -> None:
        running = self._bridge_running()
        if running:
            self._bridge_start_queued = False
        if running:
            self._sync_capabilities()
        elif self._was_bridge_running:
            self._set_capabilities(rgb=False, depth=False)
            self._depth.remove_consumer("bridge")
        self._was_bridge_running = running


class GroundPerceptionController(QObject):
    """Ground overlay: consumes RGB/Depth taps without owning bridge/RViz."""

    overlay_ready = pyqtSignal(object)
    running_changed = pyqtSignal(bool)
    calibration_status = pyqtSignal(str, bool)
    valid_pixels = pyqtSignal(float)

    def __init__(
        self,
        rgb: RgbCameraController,
        depth: DepthCameraController,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._rgb = rgb
        self._depth = depth
        self._config = GroundPerceptionConfig.from_env()
        self._config.log_summary()
        self._overlay = self._create_overlay(self._config.overlay_method)
        self._running = False
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
            max_workers=1, thread_name_prefix="ground-plane"
        )
        self._plane_timer = QTimer(self)
        self._plane_timer.setInterval(50)
        self._plane_timer.timeout.connect(self._poll_ground_plane_result)
        self._rgb.frame.connect(self._on_rgb_frame)
        self._depth.preview_ready.connect(self._on_depth_packet)

    @property
    def config(self) -> GroundPerceptionConfig:
        return self._config

    def is_running(self) -> bool:
        return self._running

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._ground_rgb_logged = False
        self._ground_depth_logged = False
        self._ground_render_log_mono = 0.0
        self._overlay.reset_session_logs()
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
        self._plane_timer.start()
        self._rgb.set_max_fps(float(self._config.max_fps))
        self._depth.add_consumer("ground_perception", decode=True)
        if not self._rgb.is_streaming():
            self._rgb.connect()
        elif self._rgb.latest_frame is not None:
            self._render_overlay()
        self.running_changed.emit(True)
        logger.info("ground perception started")

    def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        self._ground_plane_generation += 1
        if self._ground_plane_future is not None and not self._ground_plane_future.done():
            self._ground_plane_future.cancel()
        self._ground_plane_future = None
        self._plane_timer.stop()
        self._depth.remove_consumer("ground_perception")
        self.running_changed.emit(False)
        logger.info("ground perception stopped")
        self.overlay_ready.emit(self._overlay.draw_idle_screen(width=800, height=450))

    def set_overlay_method(self, method: str) -> None:
        if method == self._config.overlay_method:
            return
        logger.info(
            "ground overlay method changed: %s -> %s",
            self._config.overlay_method,
            method,
        )
        self._config.overlay_method = method
        self._overlay = self._create_overlay(method)
        self._overlay.reset_session_logs()
        if self._running and self._rgb.latest_frame is not None:
            self._ground_rgb_logged = False
            self._render_overlay()

    def shutdown(self) -> None:
        self.stop()
        self._ground_executor.shutdown(wait=False, cancel_futures=True)

    def _create_overlay(self, method: str):
        if method == "trapezoid":
            return TrapezoidOverlay(self._config)
        return GroundPerceptionOverlay(self._config)

    def _on_rgb_frame(self, _jpeg: bytes) -> None:
        if not self._running:
            return
        frame = self._rgb.latest_frame
        if frame is None or frame.isNull():
            return
        if not self._ground_rgb_logged:
            logger.info(
                "ground perception RGB tap: %dx%d", frame.width(), frame.height()
            )
            self._ground_rgb_logged = True
        self._render_overlay()

    def _on_depth_packet(self, packet: object) -> None:
        if not self._running or not isinstance(packet, DepthPreviewPacket):
            return
        if not self._ground_depth_logged:
            logger.info(
                "ground perception depth tap: %dx%d bytes=%d",
                packet.width,
                packet.height,
                len(packet.rgb_bytes),
            )
            self._ground_depth_logged = True
        if self._config.overlay_method == "geometric":
            self._update_ground_plane(packet)

    def _render_overlay(self) -> None:
        frame = self._rgb.latest_frame
        if frame is None:
            return
        ground_plane = (
            self._latest_ground_plane
            if self._latest_ground_plane is not None
            and self._latest_ground_plane.valid
            else None
        )
        draw_corridor = (
            self._config.overlay_method == "trapezoid" or ground_plane is not None
        )
        status = (
            f"Running | corridor: {self._config.corridor_width_m:.2f}m | "
            f"range: {self._config.overlay_max_range_m:.1f}m"
        )
        if self._config.overlay_method == "trapezoid":
            status += " | trapezoid overlay"
        elif ground_plane is not None:
            status += " | depth ground OK"
        else:
            status += " | waiting depth ground"
        result, draw_meta = self._overlay.draw_overlay(
            frame,
            draw_corridor=draw_corridor,
            status_text=status,
            ground_plane=ground_plane,
        )
        now = time.monotonic()
        if now - self._ground_render_log_mono >= _GROUND_RENDER_LOG_INTERVAL_S:
            if draw_meta.corridor_drawn:
                logger.info(
                    "ground overlay render: corridor=%d verts frame=%dx%d",
                    draw_meta.corridor_vertices,
                    draw_meta.image_width,
                    draw_meta.image_height,
                )
            self._ground_render_log_mono = now
        self.overlay_ready.emit(result)

    def _update_ground_plane(self, packet: DepthPreviewPacket) -> None:
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
            self.calibration_status.emit("等待 raw depth", True)
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
            config=self._config,
            camera_info=camera_info,
            raw_width=raw_width,
            raw_height=raw_height,
            max_depth_m=self._depth.config.max_depth_m,
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
            self.calibration_status.emit("ground fit failed", True)
            return
        if generation != self._ground_plane_generation or not self._running:
            return
        accepted = self._accept_ground_plane(plane)
        now = time.monotonic()
        if (
            elapsed_ms >= 30.0
            or now - self._ground_plane_last_log_mono >= _GROUND_PLANE_LOG_INTERVAL_S
        ):
            logger.info(
                "ground plane estimate: %.1fms valid=%s accepted=%s",
                elapsed_ms,
                plane.valid,
                accepted is not None,
            )
            self._ground_plane_last_log_mono = now
        self.valid_pixels.emit(valid_ratio * 100.0)
        if accepted is not None and accepted.valid:
            self.calibration_status.emit(
                f"ground locked {accepted.inlier_ratio * 100:.0f}% / "
                f"RMS {accepted.rms_error_m * 100:.1f}cm",
                False,
            )
            self._render_overlay()
        else:
            self.calibration_status.emit(
                f"ground fit weak {plane.reason or 'low confidence'}",
                True,
            )

    def _accept_ground_plane(
        self, plane: GroundPlaneEstimate
    ) -> Optional[GroundPlaneEstimate]:
        current = self._latest_ground_plane
        if not plane.valid:
            if current is not None:
                self._ground_plane_hold_frames += 1
                return current
            self._latest_ground_plane = None
            self._ground_plane_candidate = None
            self._ground_plane_candidate_count = 0
            return None
        if current is not None:
            angle = plane_angle_deg(current, plane)
            offset_jump = abs(current.offset - plane.offset)
            if angle > 12.0 or offset_jump > 0.12:
                self._ground_plane_hold_frames += 1
                return current
        else:
            if plane.inlier_ratio >= 0.32 and plane.rms_error_m <= 0.025:
                self._latest_ground_plane = plane
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
        return plane


class CameraServices(QObject):
    """Workspace-level camera services shared by RGB / Depth / Ground pages."""

    def __init__(
        self,
        robot: "RobotInfo",
        ros2_bridge: Optional["Ros2BridgeManager"] = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._robot = robot
        self.rgb = RgbCameraController(robot, ros2_bridge, parent=self)
        self.depth = DepthCameraController(robot, ros2_bridge, parent=self)
        self.bridge = CameraBridgeCoordinator(
            ros2_bridge, self.rgb, self.depth, parent=self
        )
        self.ground = GroundPerceptionController(
            self.rgb, self.depth, parent=self
        )
        self._ros2_bridge = ros2_bridge

    def refresh_robot(self, robot: "RobotInfo") -> None:
        self._robot = robot
        self.rgb.refresh_robot(robot)
        self.depth.refresh_robot(robot)

    def topic_hint_rgb(self) -> str:
        return f"RGB {QT_MJPEG_TOPIC}"

    def topic_hint_depth(self) -> str:
        return (
            f"Depth Raw HTTP :8082 ({self.depth.config.image_topic}) | "
            "ROS2 diagnostics below"
        )

    def shutdown(self) -> None:
        self.ground.shutdown()
        self.bridge.shutdown()
        self.depth.shutdown()
        self.rgb.shutdown()
