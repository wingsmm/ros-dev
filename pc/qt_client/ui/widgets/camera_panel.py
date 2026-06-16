from __future__ import annotations

import time
import socket
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Optional, Tuple
from urllib.parse import urlsplit

from PyQt5.QtCore import QObject, Qt, QThread, QTimer, pyqtSignal
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


@dataclass
class CameraStats:
    fps: float = 0.0
    last_frame_ts: float = 0.0
    connected: bool = False
    status: str = "No Camera"


class _MjpegWorker(QObject):
    frame = pyqtSignal(int, bytes, float)  # session_id, jpeg_bytes, ts
    status = pyqtSignal(int, str)
    connected = pyqtSignal(int, bool)
    finished = pyqtSignal(int)

    def __init__(self, session_id: int, url: str, timeout_s: float = 2.0):
        super().__init__()
        self._session_id = session_id
        self._url = url
        self._timeout_s = timeout_s
        self._stop = False
        self._sock: Optional[socket.socket] = None

    def stop(self) -> None:
        self._stop = True
        sock = self._sock
        if sock is None:
            return
        try:
            sock.shutdown(socket.SHUT_RDWR)
        except Exception:
            pass
        try:
            sock.close()
        except Exception:
            pass

    def _open_http10_stream(self):
        """
        web_video_server 在部分环境下对 HTTP/1.1 响应不稳定（会接收但不回包），
        这里用最朴素的 socket + HTTP/1.0 强制 close，确保能拿到响应体。
        """
        parts = urlsplit(self._url)
        if parts.scheme not in ("http", ""):
            raise ValueError(f"Unsupported scheme: {parts.scheme}")
        host = parts.hostname or ""
        port = int(parts.port or 80)
        path = parts.path or "/"
        if parts.query:
            path = f"{path}?{parts.query}"

        s = socket.create_connection((host, port), timeout=self._timeout_s)
        s.settimeout(self._timeout_s)
        self._sock = s
        req = (
            f"GET {path} HTTP/1.0\r\n"
            f"Host: {host}:{port}\r\n"
            "User-Agent: xtark-qt-client/0.1\r\n"
            "Accept: multipart/x-mixed-replace,image/jpeg,*/*\r\n"
            "Connection: close\r\n"
            "\r\n"
        ).encode("ascii", "replace")
        s.sendall(req)

        # Read headers
        data = bytearray()
        while b"\r\n\r\n" not in data:
            chunk = s.recv(4096)
            if not chunk:
                raise RuntimeError("EOF while reading headers")
            data.extend(chunk)
            if len(data) > 64 * 1024:
                raise RuntimeError("HTTP headers too large")
        header_blob, rest = data.split(b"\r\n\r\n", 1)
        header_text = header_blob.decode("iso-8859-1", "replace")
        return s, header_text, rest

    def run(self) -> None:
        self._stop = False
        self.connected.emit(self._session_id, False)
        self.status.emit(self._session_id, "Connecting...")

        try:
            sock, headers, rest = self._open_http10_stream()
            try:
                # Parse status code
                first = headers.splitlines()[0] if headers else ""
                if "200" not in first:
                    self.status.emit(self._session_id, first.strip() or "HTTP error")
                    self.connected.emit(self._session_id, False)
                    return

                ctype = ""
                for line in headers.splitlines()[1:]:
                    if line.lower().startswith("content-type:"):
                        ctype = line.split(":", 1)[1].strip()
                        break
                if "multipart" not in ctype.lower():
                    self.status.emit(self._session_id, "Streaming (non-multipart)")
                else:
                    self.status.emit(self._session_id, "Streaming")
                self.connected.emit(self._session_id, True)

                buf = bytearray(rest)
                last_emit = 0.0

                while not self._stop:
                    try:
                        chunk = sock.recv(4096)
                    except socket.timeout:
                        self.status.emit(self._session_id, "Error: timed out")
                        break
                    except OSError:
                        # Typically happens when stop() closes the socket.
                        break
                    if not chunk:
                        self.status.emit(self._session_id, "EOF")
                        break
                    buf.extend(chunk)

                    if len(buf) > 2_000_000:
                        buf = buf[-1_000_000:]

                    while True:
                        start = buf.find(b"\xff\xd8")
                        if start < 0:
                            break
                        end = buf.find(b"\xff\xd9", start + 2)
                        if end < 0:
                            if start > 0:
                                del buf[:start]
                            break
                        jpeg = bytes(buf[start : end + 2])
                        del buf[: end + 2]

                        now = time.time()
                        if now - last_emit < 0.0:
                            continue
                        last_emit = now
                        self.frame.emit(self._session_id, jpeg, now)
            finally:
                try:
                    sock.close()
                except Exception:
                    pass
                self._sock = None
                self.connected.emit(self._session_id, False)

        except urllib.error.HTTPError as exc:
            self.status.emit(self._session_id, f"HTTPError: {exc.code}")
            self.connected.emit(self._session_id, False)
        except urllib.error.URLError as exc:
            self.status.emit(self._session_id, f"URL error: {exc.reason}")
            self.connected.emit(self._session_id, False)
        except socket.timeout:
            self.status.emit(self._session_id, "Error: timed out")
            self.connected.emit(self._session_id, False)
        except Exception as exc:
            self.status.emit(self._session_id, f"Error: {exc}")
            self.connected.emit(self._session_id, False)
        finally:
            self._sock = None
            self.finished.emit(self._session_id)


class CameraPanel(QWidget):
    log = pyqtSignal(str)  # integrate with existing log panel

    def __init__(
        self,
        settings_key: str = "camera_http_url",
        default_url: str = "http://192.168.1.169:8080/stream?topic=/camera/image_raw",
        parent=None,
    ):
        super().__init__(parent)
        self._settings_key = settings_key
        self._default_url = default_url

        self._thread: Optional[QThread] = None
        self._worker: Optional[_MjpegWorker] = None
        self._stopping = False
        self._session_id = 0
        self._pending_connect_url: Optional[str] = None

        self._stats = CameraStats()
        self._fps_window = []
        self._last_ui_frame_ts = 0.0

        self._build_ui()

        self._watchdog = QTimer(self)
        self._watchdog.setInterval(200)
        self._watchdog.timeout.connect(self._tick_watchdog)
        self._watchdog.start()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        group = QGroupBox("相机（HTTP/MJPEG）")
        g = QVBoxLayout(group)

        row = QHBoxLayout()
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText(self._default_url)
        row.addWidget(QLabel("URL"))
        row.addWidget(self.url_edit, 1)
        self.connect_btn = QPushButton("连接")
        self.disconnect_btn = QPushButton("断开")
        self.reconnect_btn = QPushButton("重连")
        self.disconnect_btn.setEnabled(False)
        row.addWidget(self.connect_btn)
        row.addWidget(self.disconnect_btn)
        row.addWidget(self.reconnect_btn)
        g.addLayout(row)

        self.image_label = QLabel("No Camera")
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setMinimumHeight(200)
        self.image_label.setStyleSheet(
            "QLabel { background: #111; color: #ddd; border: 1px solid #333; }"
        )
        self.image_label.setScaledContents(False)
        g.addWidget(self.image_label, 1)

        info_row = QHBoxLayout()
        self.status_label = QLabel("No Camera")
        self.fps_label = QLabel("FPS: -")
        info_row.addWidget(self.status_label, 1)
        info_row.addWidget(self.fps_label, 0, Qt.AlignRight)
        g.addLayout(info_row)

        root.addWidget(group)

        self.connect_btn.clicked.connect(self.connect)
        self.disconnect_btn.clicked.connect(self.disconnect)
        self.reconnect_btn.clicked.connect(self.reconnect)

    def set_url(self, url: str) -> None:
        self.url_edit.setText(url)

    def url(self) -> str:
        text = self.url_edit.text().strip()
        return text or self._default_url

    def connect(self) -> None:
        if self._thread is not None or self._worker is not None:
            self._pending_connect_url = self.url()
            self._stop_current()
            return
        self._start_stream(self.url())

    def _start_stream(self, url: str) -> None:
        self._session_id += 1
        session_id = self._session_id
        self._stopping = False
        self._reset_stats()
        self._set_status(f"Connecting: {url}", connected=False)
        self.log.emit(f"CAMERA connect {url}")

        thread = QThread(self)
        worker = _MjpegWorker(session_id=session_id, url=url)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        worker.finished.connect(self._on_worker_finished)
        worker.frame.connect(self._on_frame)
        worker.status.connect(self._on_worker_status)
        worker.connected.connect(self._on_worker_connected)

        self._thread = thread
        self._worker = worker

        self.connect_btn.setEnabled(False)
        self.disconnect_btn.setEnabled(True)
        self.reconnect_btn.setEnabled(True)

        thread.start()

    def disconnect(self, block: bool = False) -> None:
        self._pending_connect_url = None
        self._stop_current(block=block)

    def _stop_current(self, block: bool = False) -> None:
        """
        Stop streaming without blocking the UI.
        If block=True, wait briefly for thread exit (used during app shutdown).
        """
        if self._thread is None and self._worker is None:
            self.connect_btn.setEnabled(True)
            self.disconnect_btn.setEnabled(False)
            self._reset_stats()
            self._set_status("No Camera", connected=False)
            return

        self._stopping = True
        self.connect_btn.setEnabled(False)
        self.disconnect_btn.setEnabled(False)
        self.reconnect_btn.setEnabled(False)
        self.status_label.setText("Disconnecting...")

        if self._worker is not None:
            try:
                self._worker.stop()
            except Exception:
                pass
        if self._thread is not None:
            self._thread.quit()
            if block:
                self._thread.wait(2500)

    def reconnect(self) -> None:
        self._pending_connect_url = self.url()
        if self._thread is None and self._worker is None:
            url = self._pending_connect_url
            self._pending_connect_url = None
            self._start_stream(url)
            return
        self._stop_current()

    def shutdown(self) -> None:
        self.disconnect(block=True)

    def load_settings(self, settings) -> None:
        url = str(settings.value(self._settings_key, self._default_url))
        self.set_url(url)

    def save_settings(self, settings) -> None:
        settings.setValue(self._settings_key, self.url())

    def _reset_stats(self) -> None:
        self._stats.last_frame_ts = 0.0
        self._stats.fps = 0.0
        self._fps_window.clear()
        self._last_ui_frame_ts = 0.0
        self.fps_label.setText("FPS: -")

    def _is_current_session(self, session_id: int) -> bool:
        return session_id == self._session_id

    def _on_worker_finished(self, session_id: int) -> None:
        if not self._is_current_session(session_id):
            return
        # Finalize UI state after the streaming thread actually stops.
        self._thread = None
        self._worker = None
        self._stopping = False
        self.connect_btn.setEnabled(True)
        self.disconnect_btn.setEnabled(False)
        self.reconnect_btn.setEnabled(True)
        self._reset_stats()
        self._set_status("No Camera", connected=False)
        if self._pending_connect_url:
            url = self._pending_connect_url
            self._pending_connect_url = None
            self._start_stream(url)

    def _on_worker_status(self, session_id: int, text: str) -> None:
        if not self._is_current_session(session_id) or self._stopping:
            return
        self._stats.status = text
        self.status_label.setText(text)
        self.log.emit(f"CAMERA status {text}")

    def _on_worker_connected(self, session_id: int, ok: bool) -> None:
        if not self._is_current_session(session_id) or self._stopping:
            return
        self._stats.connected = ok
        self.connect_btn.setEnabled(not ok)
        self.disconnect_btn.setEnabled(ok)
        if not ok:
            # keep No Camera message if no frames
            if self._stats.last_frame_ts <= 0:
                self.image_label.setText("No Camera")

    def _on_frame(self, session_id: int, jpeg: bytes, ts: float) -> None:
        if not self._is_current_session(session_id) or self._stopping:
            return
        self._stats.last_frame_ts = ts
        # Some environments may miss the early 'connected' signal; treat first frame as connected.
        if not self._stopping and not self._stats.connected:
            self._stats.connected = True
            self.connect_btn.setEnabled(False)
            self.disconnect_btn.setEnabled(True)
            self.reconnect_btn.setEnabled(True)

        img = QImage.fromData(jpeg)
        if img.isNull():
            return

        # Maintain aspect ratio within label.
        self._last_ui_frame_ts = ts
        pix = QPixmap.fromImage(img)
        target = self.image_label.size()
        if target.width() > 10 and target.height() > 10:
            pix = pix.scaled(target, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.image_label.setPixmap(pix)

        self._stats.status = "OK"
        self.status_label.setText("OK")

        # FPS over last ~1s
        self._fps_window.append(ts)
        cutoff = ts - 1.0
        while self._fps_window and self._fps_window[0] < cutoff:
            self._fps_window.pop(0)
        if len(self._fps_window) >= 2:
            fps = float(len(self._fps_window) - 1) / max(
                1e-6, (self._fps_window[-1] - self._fps_window[0])
            )
            self._stats.fps = fps
            self.fps_label.setText("FPS: {:.1f}".format(fps))

    def _tick_watchdog(self) -> None:
        # If no frames for ~2s, show No Camera / stalled status.
        if self._stats.last_frame_ts <= 0:
            self.fps_label.setText("FPS: -")
            return
        if time.time() - self._stats.last_frame_ts > 2.0:
            self.image_label.setPixmap(QPixmap())
            self.image_label.setText("No Camera")
            self.status_label.setText("No frames (timeout)")
            self.fps_label.setText("FPS: 0.0")

    def _set_status(self, text: str, connected: bool) -> None:
        self._stats.status = text
        self._stats.connected = connected
        self.status_label.setText(text)
        if not connected:
            self.image_label.setPixmap(QPixmap())
            self.image_label.setText("No Camera")
