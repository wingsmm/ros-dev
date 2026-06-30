from __future__ import annotations

import json
import logging
import queue
import socket
import threading
import time
from typing import Optional

from PyQt5.QtCore import QObject, pyqtSignal

CMD_TIMEOUT_SEC = 0.5
SEND_RATE_HZ = 10.0

logger = logging.getLogger(__name__)


class JsonClientSignals(QObject):
    """Thread-safe Qt signals emitted by the JSON TCP client."""

    log_line = pyqtSignal(str)
    message = pyqtSignal(object)
    connection_changed = pyqtSignal(bool, str)


class JsonTcpClient:
    """TCP NDJSON client for xtark_json_bridge (:8765)."""

    def __init__(self, signals: JsonClientSignals):
        self._signals = signals
        self._sock: Optional[socket.socket] = None
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._recv_thread: Optional[threading.Thread] = None
        self._send_thread: Optional[threading.Thread] = None
        self._send_queue: "queue.Queue[tuple[bytes, tuple[float, float, float], str, bool]]" = queue.Queue(
            maxsize=1
        )
        self._seq = 0
        self._connected = False
        self.last_send_time = 0.0
        self.last_feedback_time = 0.0
        self.last_sent_cmd = (0.0, 0.0, 0.0)

    @property
    def connected(self) -> bool:
        return self._connected

    def connect(self, host: str, port: int, timeout: float = 5.0) -> None:
        self.disconnect(send_stop=False)
        sock = socket.create_connection((host, int(port)), timeout=timeout)
        sock.settimeout(0.5)
        with self._lock:
            self._sock = sock
            self._connected = True
            self._stop_event.clear()
        self._send_thread = threading.Thread(target=self._send_loop, daemon=True)
        self._send_thread.start()
        self._recv_thread = threading.Thread(target=self._recv_loop, daemon=True)
        self._recv_thread.start()
        self._emit_connection(True, f"connected {host}:{port}")
        self._emit_log(f"CONNECT {host}:{port}")

    def disconnect(self, send_stop: bool = True) -> None:
        if send_stop and self._connected:
            try:
                self._drain_send_queue()
                self._send_cmd_vel_sync(0.0, 0.0, 0.0)
            except OSError:
                pass
        self._stop_event.set()
        with self._lock:
            sock = self._sock
            self._sock = None
            self._connected = False
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass
        if self._recv_thread is not None:
            self._recv_thread.join(timeout=1.0)
            self._recv_thread = None
        if self._send_thread is not None:
            self._send_thread.join(timeout=1.0)
            self._send_thread = None
        self._drain_send_queue()
        self.last_sent_cmd = (0.0, 0.0, 0.0)
        self._emit_connection(False, "disconnected")
        self._emit_log("DISCONNECT")

    def send_cmd_vel(
        self,
        linear_x: float,
        linear_y: float,
        angular_z: float,
        *,
        log_tx: bool = True,
    ) -> bool:
        data, cmd, line = self._build_cmd_vel(linear_x, linear_y, angular_z)
        with self._lock:
            if self._sock is None:
                return False
        self._replace_pending_send(data, cmd, line, log_tx)
        return True

    def _build_cmd_vel(
        self, linear_x: float, linear_y: float, angular_z: float
    ) -> tuple[bytes, tuple[float, float, float], str]:
        payload = {
            "type": "cmd_vel",
            "seq": self._seq,
            "stamp_ms": int(time.time() * 1000),
            "linear_x": float(linear_x),
            "linear_y": float(linear_y),
            "angular_z": float(angular_z),
        }
        self._seq += 1
        line = json.dumps(payload, separators=(",", ":")) + "\n"
        data = line.encode("utf-8")
        return data, (linear_x, linear_y, angular_z), line

    def _replace_pending_send(
        self,
        data: bytes,
        cmd: tuple[float, float, float],
        line: str,
        log_tx: bool,
    ) -> None:
        try:
            self._send_queue.put_nowait((data, cmd, line, log_tx))
            return
        except queue.Full:
            pass
        try:
            self._send_queue.get_nowait()
            self._send_queue.task_done()
        except queue.Empty:
            pass
        try:
            self._send_queue.put_nowait((data, cmd, line, log_tx))
        except queue.Full:
            logger.debug("cmd_vel send queue still full; dropping newest command")

    def _send_cmd_vel_sync(
        self,
        linear_x: float,
        linear_y: float,
        angular_z: float,
        *,
        log_tx: bool = True,
    ) -> bool:
        data, cmd, line = self._build_cmd_vel(linear_x, linear_y, angular_z)
        return self._send_prebuilt(data, cmd, line, log_tx)

    def _send_prebuilt(
        self,
        data: bytes,
        cmd: tuple[float, float, float],
        line: str,
        log_tx: bool,
    ) -> bool:
        send_error: Optional[OSError] = None
        with self._lock:
            sock = self._sock
        if sock is None:
            return False
        try:
            sock.sendall(data)
        except OSError as exc:
            send_error = exc
        if send_error is not None:
            self._emit_log(f"SEND ERR {send_error}")
            self._handle_disconnect()
            return False
        self.last_send_time = time.time()
        self.last_sent_cmd = cmd
        if log_tx:
            self._emit_log("TX " + line.strip())
        return True

    def _send_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                data, cmd, line, log_tx = self._send_queue.get(timeout=0.1)
            except queue.Empty:
                continue
            try:
                self._send_prebuilt(data, cmd, line, log_tx)
            finally:
                self._send_queue.task_done()

    def _drain_send_queue(self) -> None:
        while True:
            try:
                self._send_queue.get_nowait()
                self._send_queue.task_done()
            except queue.Empty:
                return

    def control_state(self) -> str:
        if not self._connected:
            return "disconnected"
        now = time.time()
        lx, ly, az = self.last_sent_cmd
        if abs(lx) > 1e-6 or abs(ly) > 1e-6 or abs(az) > 1e-6:
            if now - self.last_send_time <= CMD_TIMEOUT_SEC:
                return "controlling"
        if self.last_feedback_time <= 0:
            return "idle(no feedback)"
        if now - self.last_feedback_time > 2.0:
            return "idle(feedback timeout)"
        return "idle"

    def _recv_loop(self) -> None:
        buffer = ""
        while not self._stop_event.is_set():
            with self._lock:
                sock = self._sock
            if sock is None:
                break
            try:
                chunk = sock.recv(4096)
            except socket.timeout:
                continue
            except OSError as exc:
                if not self._stop_event.is_set():
                    self._emit_log(f"RECV ERR {exc}")
                self._handle_disconnect()
                break
            if not chunk:
                self._handle_disconnect()
                break
            buffer += chunk.decode("utf-8", errors="replace")
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                line = line.strip()
                if line:
                    self._handle_line(line)

    def _handle_line(self, line: str) -> None:
        try:
            msg = json.loads(line)
        except ValueError:
            self._emit_log("RX INVALID " + line)
            return
        self.last_feedback_time = time.time()
        msg_type = msg.get("type")
        if msg_type not in (
            "odom_base",
            "odom_raw",
            "odom_laser",
            "scan_warning",
            "laser_scan",
        ):
            self._emit_log("RX " + line)
        self._signals.message.emit(msg)

    def _handle_disconnect(self) -> None:
        if not self._connected:
            return
        with self._lock:
            sock = self._sock
            self._sock = None
            self._connected = False
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass
        self._emit_connection(False, "connection lost")
        self._emit_log("CONNECTION LOST")

    def _emit_log(self, text: str) -> None:
        self._signals.log_line.emit(text)

    def _emit_connection(self, ok: bool, detail: str) -> None:
        self._signals.connection_changed.emit(ok, detail)
