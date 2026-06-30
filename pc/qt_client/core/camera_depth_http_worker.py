"""PC-side pull client for xtark raw depth HTTP service on port 8082."""

from __future__ import annotations

import json
import logging
import struct
import time
from dataclasses import dataclass
from http.client import HTTPConnection, HTTPException
from typing import Callable, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import urlopen

from PyQt5.QtCore import QObject, QTimer, pyqtSignal, pyqtSlot

from core.camera_depth_colormap import ros_image_to_depth_preview
from core.camera_depth_frame import DepthFrameStats, DepthSourceKind
from core.camera_depth_source import DepthSourceConfig

logger = logging.getLogger(__name__)

_MAGIC = b"XTD1"
_MAX_HEADER_BYTES = 64 * 1024
_MAX_FRAME_BYTES = 32 * 1024 * 1024


@dataclass(frozen=True)
class DepthPreviewPacket:
    width: int
    height: int
    raw_width: int
    raw_height: int
    rgb_bytes: bytes
    stats: DepthFrameStats
    depth_meters: object = None
    timestamp_ns: int = 0
    camera_info: Optional[dict] = None
    source_kind: DepthSourceKind = DepthSourceKind.RAW_HTTP


def _read_depth_response(body: bytes) -> tuple[dict, bytes]:
    if len(body) < 8 or body[:4] != _MAGIC:
        raise ValueError("invalid depth HTTP magic")
    header_size = struct.unpack("!I", body[4:8])[0]
    if not 0 < header_size <= _MAX_HEADER_BYTES:
        raise ValueError("invalid depth HTTP header length")
    offset = 8 + header_size
    if offset > len(body):
        raise ValueError("truncated depth HTTP header")
    header = json.loads(body[8:offset].decode("utf-8"))
    data = body[offset:]
    expected = int(header.get("data_bytes", -1))
    if expected != len(data) or len(data) > _MAX_FRAME_BYTES:
        raise ValueError("invalid depth HTTP payload length")
    return header, data


class CameraDepthHttpWorker(QObject):
    """Runs in a QThread and keeps HTTP requests out of the UI thread."""

    preview_ready = pyqtSignal(object)
    status_changed = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(
        self,
        config: Optional[DepthSourceConfig] = None,
        delivery_gate: Optional[object] = None,
        bridge_sink: Optional[Callable[[dict, bytes, Optional[dict]], None]] = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._config = config or DepthSourceConfig.from_env()
        self._delivery_gate = delivery_gate
        self._bridge_sink = bridge_sink
        self._timer = QTimer(self)
        self._timer.setInterval(self._config.http_poll_ms)
        self._timer.timeout.connect(self._poll_once)
        self._running = False
        self._paused = False
        self._last_stamp_ns = 0
        self._last_emit_mono = 0.0
        self._min_emit_interval_s = 1.0 / max(self._config.max_preview_fps, 0.1)
        self._window_start = time.monotonic()
        self._frame_count = 0
        self._last_fps = 0.0
        self._camera_info_online = False
        self._camera_info_payload: Optional[dict] = None
        self._last_info_try = 0.0
        self._last_error = ""
        self._connected_announced = False
        self._http: Optional[HTTPConnection] = None
        self._http_key = ""

    def is_active(self) -> bool:
        return self._running

    def _delivery_enabled(self) -> bool:
        gate = self._delivery_gate
        if gate is None:
            return True
        return bool(getattr(gate, "enabled", True))

    def _close_http(self) -> None:
        conn = self._http
        self._http = None
        self._http_key = ""
        if conn is None:
            return
        try:
            conn.close()
        except Exception:
            pass

    def _http_parts(self) -> Tuple[str, int, str]:
        parsed = urlparse(self._config.http_base_url)
        host = parsed.hostname or ""
        port = int(parsed.port or 80)
        return host, port, parsed.scheme or "http"

    def _ensure_http(self) -> HTTPConnection:
        host, port, scheme = self._http_parts()
        key = "%s://%s:%d" % (scheme, host, port)
        if self._http is not None and self._http_key == key:
            return self._http
        self._close_http()
        self._http = HTTPConnection(
            host,
            port,
            timeout=self._config.http_timeout_s,
        )
        self._http_key = key
        return self._http

    def _fetch_frame(self) -> Tuple[dict, bytes, float]:
        host, port, _scheme = self._http_parts()
        path = urlparse(self._config.http_frame_url).path or "/v1/depth/latest"
        t0 = time.monotonic()
        try:
            conn = self._ensure_http()
            conn.request(
                "GET",
                path,
                headers={
                    "Accept": "application/x-xtark-depth",
                    "Connection": "keep-alive",
                },
            )
            response = conn.getresponse()
            if response.status != 200:
                raise ValueError("HTTP %s" % response.status)
            length = int(response.getheader("Content-Length", "0") or "0")
            if not 8 <= length <= _MAX_FRAME_BYTES + _MAX_HEADER_BYTES + 8:
                raise ValueError("invalid depth HTTP content length")
            body = bytearray()
            while len(body) < length:
                if not self._running:
                    raise ValueError("aborted")
                chunk = response.read(min(65536, length - len(body)))
                if not chunk:
                    raise ValueError("truncated depth HTTP body")
                body.extend(chunk)
            body = bytes(body)
        except (HTTPException, OSError, ValueError) as exc:
            self._close_http()
            raise exc
        transport_ms = (time.monotonic() - t0) * 1000.0
        header, data = _read_depth_response(body)
        return header, data, transport_ms

    @pyqtSlot()
    def start_worker(self) -> None:
        if self._running:
            return
        if not self._config.http_base_url:
            self._fail("未配置 xtark depth HTTP URL")
            return
        self._running = True
        self._paused = False
        self._connected_announced = False
        self._timer.start()
        self.status_changed.emit("Raw Depth HTTP 连接中…")
        self._poll_once()

    @pyqtSlot()
    def stop_worker(self) -> None:
        self._running = False
        self._timer.stop()
        self._paused = False
        self._close_http()
        self.status_changed.emit("已停止")

    @pyqtSlot()
    def pause_worker(self) -> None:
        if not self._running or self._paused:
            return
        self._paused = True
        self._timer.stop()
        self._close_http()
        self.status_changed.emit("Raw Depth HTTP 已暂停")

    @pyqtSlot()
    def resume_worker(self) -> None:
        if not self._running or not self._paused:
            return
        self._paused = False
        self._timer.start()
        self.status_changed.emit("Raw Depth HTTP 连接中…")
        self._poll_once()

    def set_bridge_sink(
        self, sink: Optional[Callable[[dict, bytes, Optional[dict]], None]]
    ) -> None:
        self._bridge_sink = sink

    def _fetch_camera_info(self) -> None:
        now = time.monotonic()
        if self._camera_info_online or now - self._last_info_try < 5.0:
            return
        self._last_info_try = now
        try:
            with urlopen(self._config.http_info_url, timeout=self._config.http_timeout_s) as response:
                info = json.loads(response.read(_MAX_HEADER_BYTES).decode("utf-8"))
            self._camera_info_payload = info
            self._camera_info_online = bool(info.get("k"))
        except (HTTPError, URLError, OSError, ValueError):
            self._camera_info_online = False
            self._camera_info_payload = None

    def _poll_once(self) -> None:
        if not self._running or self._paused or not self._delivery_enabled():
            return
        now_mono = time.monotonic()
        if self._last_emit_mono and now_mono - self._last_emit_mono < self._min_emit_interval_s:
            return
        self._fetch_camera_info()
        try:
            header, data, transport_ms = self._fetch_frame()
        except HTTPError as exc:
            if exc.code not in (204, 503):
                self._report_waiting("HTTP %s" % exc.code)
            return
        except (URLError, OSError, ValueError) as exc:
            self._report_waiting(str(exc))
            return

        if self._paused:
            return

        stamp_ns = int(header["stamp_sec"]) * 1_000_000_000 + int(header["stamp_nsec"])
        if stamp_ns <= self._last_stamp_ns:
            return
        self._last_stamp_ns = stamp_ns

        bridge_sink = self._bridge_sink
        if bridge_sink is not None:
            try:
                bridge_sink(header, data, self._camera_info_payload)
            except Exception:
                logger.exception("depth bridge tee failed")

        self._frame_count += 1
        elapsed = max(now_mono - self._window_start, 0.001)
        if elapsed >= 1.0:
            self._last_fps = self._frame_count / elapsed
            self._frame_count = 0
            self._window_start = now_mono
        try:
            frame, rgb = ros_image_to_depth_preview(
                data=data,
                width=int(header["width"]),
                height=int(header["height"]),
                encoding=str(header["encoding"]),
                timestamp_ns=stamp_ns,
                min_depth_m=self._config.min_depth_m,
                max_depth_m=self._config.max_depth_m,
                camera_info_online=self._camera_info_online,
                fps=self._last_fps,
                latency_ms=transport_ms,
                preview_downscale=self._config.preview_downscale,
            )
        except Exception as exc:
            self._report_waiting("depth decode: %s" % exc)
            return
        if self._paused or not self._delivery_enabled():
            return
        self._last_emit_mono = now_mono
        stats = DepthFrameStats(
            center_distance_m=frame.stats.center_distance_m,
            nearest_valid_m=frame.stats.nearest_valid_m,
            valid_ratio=frame.stats.valid_ratio,
            min_depth_m=frame.stats.min_depth_m,
            max_depth_m=frame.stats.max_depth_m,
            fps=self._last_fps,
            latency_ms=transport_ms,
            encoding=frame.encoding,
            camera_info_online=self._camera_info_online,
        )
        self.preview_ready.emit(
            DepthPreviewPacket(
                width=int(rgb.shape[1]),
                height=int(rgb.shape[0]),
                raw_width=int(header["width"]),
                raw_height=int(header["height"]),
                rgb_bytes=rgb.tobytes(),
                stats=stats,
                depth_meters=frame.depth_meters,
                timestamp_ns=stamp_ns,
                camera_info=self._camera_info_payload,
            )
        )
        self._last_error = ""
        if not self._connected_announced:
            self._connected_announced = True
            self.status_changed.emit("Raw Depth HTTP 已连接")

    def _report_waiting(self, detail: str) -> None:
        if detail == self._last_error:
            return
        self._last_error = detail
        self._connected_announced = False
        self.status_changed.emit("等待 Raw Depth HTTP (%s)" % detail)

    def _fail(self, detail: str) -> None:
        self._running = False
        self._timer.stop()
        self._close_http()
        self.failed.emit(detail)
