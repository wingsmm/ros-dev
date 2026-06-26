"""Shared HTTP/MJPEG stream worker and session controller (legacy + workspace)."""

from __future__ import annotations

import socket
import time
import urllib.error
from dataclasses import dataclass
from typing import List, Optional
from urllib.parse import urlsplit

from PyQt5.QtCore import QObject, QThread, QTimer, pyqtSignal, pyqtSlot, QMetaObject, Qt


@dataclass
class CameraStats:
    fps: float = 0.0
    last_frame_ts: float = 0.0
    connected: bool = False
    status: str = "No Camera"


class MjpegWorker(QObject):
    frame = pyqtSignal(int, bytes, float)
    status = pyqtSignal(int, str)
    connected = pyqtSignal(int, bool)
    finished = pyqtSignal(int)

    def __init__(
        self,
        session_id: int,
        url: str,
        timeout_s: float = 2.0,
        max_fps: float = 8.0,
    ):
        super().__init__()
        self._session_id = session_id
        self._url = url
        self._timeout_s = timeout_s
        self._min_emit_interval_s = 1.0 / max(max_fps, 0.1)
        self._stop = False
        self._paused = False
        self._sock: Optional[socket.socket] = None

    @pyqtSlot()
    def pause_worker(self) -> None:
        self._paused = True

    @pyqtSlot()
    def resume_worker(self) -> None:
        self._paused = False

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
                        if now - last_emit < self._min_emit_interval_s:
                            continue
                        if self._paused:
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


class MjpegStreamController(QObject):
    """MJPEG connect/disconnect state machine; UI binds to signals."""

    frame = pyqtSignal(bytes)
    status_changed = pyqtSignal(str)
    connected_changed = pyqtSignal(bool)
    fps_changed = pyqtSignal(float)
    log_line = pyqtSignal(str)

    def __init__(self, parent=None, *, timeout_s: float = 2.0, max_fps: float = 8.0):
        super().__init__(parent)
        self._timeout_s = timeout_s
        self._max_fps = max_fps
        self._thread: Optional[QThread] = None
        self._worker: Optional[MjpegWorker] = None
        self._stopping = False
        self._session_id = 0
        self._pending_connect_url: Optional[str] = None
        self._current_url = ""
        self._stats = CameraStats()
        self._fps_window: List[float] = []
        self._deliver_frames = True

        self._watchdog = QTimer(self)
        self._watchdog.setInterval(200)
        self._watchdog.timeout.connect(self._tick_watchdog)
        self._watchdog.start()

    @property
    def stats(self) -> CameraStats:
        return self._stats

    @property
    def current_url(self) -> str:
        return self._current_url

    def is_streaming(self) -> bool:
        return self._thread is not None or self._worker is not None

    def connect(self, url: str) -> None:
        url = url.strip()
        if not url:
            return
        if self.is_streaming():
            self._pending_connect_url = url
            self._stop_current()
            return
        self._start_stream(url)

    def disconnect(self, block: bool = False) -> None:
        self._pending_connect_url = None
        self._stop_current(block=block)

    def reconnect(self, url: str) -> None:
        url = url.strip()
        if not url:
            return
        self._pending_connect_url = url
        if not self.is_streaming():
            self._pending_connect_url = None
            self._start_stream(url)
            return
        self._stop_current()

    def shutdown(self) -> None:
        self.disconnect(block=False)
        thread = self._thread
        worker = self._worker
        if worker is not None:
            try:
                worker.stop()
            except Exception:
                pass
        if thread is not None:
            thread.quit()
            if thread.isRunning() and not thread.wait(600):
                thread.terminate()
                thread.wait(300)
        self._thread = None
        self._worker = None
        self._stopping = False
        self._reset_stats()
        self._emit_status("No Camera", connected=False)

    def pause(self) -> None:
        """Stop emitting frames to the UI (socket keeps draining)."""
        self._deliver_frames = False
        if self._worker is not None:
            QMetaObject.invokeMethod(
                self._worker, "pause_worker", Qt.QueuedConnection
            )

    def resume(self) -> None:
        self._deliver_frames = True
        if self._worker is not None:
            QMetaObject.invokeMethod(
                self._worker, "resume_worker", Qt.QueuedConnection
            )

    def set_max_fps(self, max_fps: float) -> None:
        self._max_fps = max(max_fps, 0.5)
        worker = self._worker
        if worker is not None:
            worker._min_emit_interval_s = 1.0 / self._max_fps

    def _start_stream(self, url: str) -> None:
        self._session_id += 1
        session_id = self._session_id
        self._current_url = url
        self._stopping = False
        self._deliver_frames = True
        self._reset_stats()
        self._emit_status(f"Connecting: {url}", connected=False)
        self.log_line.emit(f"CAMERA connect {url}")

        thread = QThread(self)
        worker = MjpegWorker(
            session_id=session_id,
            url=url,
            timeout_s=self._timeout_s,
            max_fps=self._max_fps,
        )
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
        thread.start()

    def _stop_current(self, block: bool = False) -> None:
        if not self.is_streaming():
            self._reset_stats()
            self._emit_status("No Camera", connected=False)
            return

        self._stopping = True
        self._emit_status("Disconnecting...", connected=self._stats.connected)

        if self._worker is not None:
            try:
                self._worker.stop()
            except Exception:
                pass
        if self._thread is not None:
            self._thread.quit()
            if block:
                self._thread.wait(2500)
                if not self._thread.isRunning():
                    self._thread = None
                    self._worker = None
                    self._stopping = False
                    self._reset_stats()
                    self._emit_status("No Camera", connected=False)

    def _reset_stats(self) -> None:
        self._stats.last_frame_ts = 0.0
        self._stats.fps = 0.0
        self._fps_window.clear()
        self.fps_changed.emit(0.0)

    def _is_current_session(self, session_id: int) -> bool:
        return session_id == self._session_id

    def _emit_status(self, text: str, connected: bool) -> None:
        self._stats.status = text
        self._stats.connected = connected
        self.status_changed.emit(text)
        self.connected_changed.emit(connected)

    def _on_worker_finished(self, session_id: int) -> None:
        if not self._is_current_session(session_id):
            return
        self._thread = None
        self._worker = None
        self._stopping = False
        self._reset_stats()
        self._emit_status("No Camera", connected=False)
        if self._pending_connect_url:
            url = self._pending_connect_url
            self._pending_connect_url = None
            self._start_stream(url)

    def _on_worker_status(self, session_id: int, text: str) -> None:
        if not self._is_current_session(session_id) or self._stopping:
            return
        self._emit_status(text, connected=self._stats.connected)
        self.log_line.emit(f"CAMERA status {text}")

    def _on_worker_connected(self, session_id: int, ok: bool) -> None:
        if not self._is_current_session(session_id) or self._stopping:
            return
        self._stats.connected = ok
        self.connected_changed.emit(ok)

    def _on_frame(self, session_id: int, jpeg: bytes, ts: float) -> None:
        if not self._is_current_session(session_id) or self._stopping:
            return
        if not self._deliver_frames:
            return
        self._stats.last_frame_ts = ts
        if not self._stats.connected:
            self._stats.connected = True
            self.connected_changed.emit(True)

        self.frame.emit(jpeg)
        if self._stats.status != "OK":
            self._emit_status("OK", connected=True)

        self._fps_window.append(ts)
        cutoff = ts - 1.0
        while self._fps_window and self._fps_window[0] < cutoff:
            self._fps_window.pop(0)
        if len(self._fps_window) >= 2:
            fps = float(len(self._fps_window) - 1) / max(
                1e-6, (self._fps_window[-1] - self._fps_window[0])
            )
            if abs(fps - self._stats.fps) > 0.2:
                self._stats.fps = fps
                self.fps_changed.emit(fps)

    def _tick_watchdog(self) -> None:
        if self._stats.last_frame_ts <= 0:
            return
        if time.time() - self._stats.last_frame_ts <= 4.0:
            return
        if self._stats.status != "No frames (timeout)" or self._stats.connected:
            self._emit_status("No frames (timeout)", connected=False)
        if self._stats.fps > 0:
            self._stats.fps = 0.0
            self.fps_changed.emit(0.0)
