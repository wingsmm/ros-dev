"""Blocking HTTP/MJPEG reader for ROS2 bridge (no Qt dependency)."""

from __future__ import annotations

import logging
import socket
import threading
import time
import urllib.error
from typing import Callable, Optional
from urllib.parse import urlsplit

logger = logging.getLogger(__name__)

OnJpeg = Callable[[bytes], None]
OnStatus = Callable[[str], None]


class MjpegReaderThread(threading.Thread):
    """Read multipart MJPEG in a background thread; invoke on_jpeg per frame."""

    def __init__(
        self,
        url: str,
        on_jpeg: OnJpeg,
        *,
        on_status: Optional[OnStatus] = None,
        timeout_s: float = 2.0,
        min_frame_interval_s: float = 0.0,
    ) -> None:
        super().__init__(name="mjpeg-ros2-bridge", daemon=True)
        self._url = url
        self._on_jpeg = on_jpeg
        self._on_status = on_status
        self._timeout_s = timeout_s
        self._min_frame_interval_s = min_frame_interval_s
        self._stop_event = threading.Event()
        self._sock: Optional[socket.socket] = None

    def stop(self) -> None:
        self._stop_event.set()
        sock = self._sock
        if sock is None:
            return
        try:
            sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            sock.close()
        except OSError:
            pass

    def _emit_status(self, text: str) -> None:
        if self._on_status is not None:
            self._on_status(text)

    def _open_http10_stream(self) -> tuple[socket.socket, str, bytes]:
        parts = urlsplit(self._url)
        if parts.scheme not in ("http", ""):
            raise ValueError(f"Unsupported scheme: {parts.scheme}")
        host = parts.hostname or ""
        port = int(parts.port or 80)
        path = parts.path or "/"
        if parts.query:
            path = f"{path}?{parts.query}"

        sock = socket.create_connection((host, port), timeout=self._timeout_s)
        sock.settimeout(self._timeout_s)
        self._sock = sock
        req = (
            f"GET {path} HTTP/1.0\r\n"
            f"Host: {host}:{port}\r\n"
            "User-Agent: xtark-qt-client/0.1\r\n"
            "Accept: multipart/x-mixed-replace,image/jpeg,*/*\r\n"
            "Connection: close\r\n"
            "\r\n"
        ).encode("ascii", "replace")
        sock.sendall(req)

        data = bytearray()
        while b"\r\n\r\n" not in data:
            chunk = sock.recv(4096)
            if not chunk:
                raise RuntimeError("EOF while reading headers")
            data.extend(chunk)
            if len(data) > 64 * 1024:
                raise RuntimeError("HTTP headers too large")
        header_blob, rest = data.split(b"\r\n\r\n", 1)
        return sock, header_blob.decode("iso-8859-1", "replace"), bytes(rest)

    def run(self) -> None:
        self._stop_event.clear()
        self._emit_status("Connecting...")
        last_emit = 0.0
        try:
            while not self._stop_event.is_set():
                try:
                    sock, headers, rest = self._open_http10_stream()
                except Exception as exc:
                    self._emit_status(f"Error: {exc}")
                    if self._stop_event.wait(2.0):
                        break
                    continue

                try:
                    first = headers.splitlines()[0] if headers else ""
                    if "200" not in first:
                        self._emit_status(first.strip() or "HTTP error")
                        if self._stop_event.wait(2.0):
                            break
                        continue

                    self._emit_status("Streaming")
                    buf = bytearray(rest)
                    while not self._stop_event.is_set():
                        try:
                            chunk = sock.recv(4096)
                        except socket.timeout:
                            self._emit_status("Error: timed out")
                            break
                        except OSError:
                            break
                        if not chunk:
                            self._emit_status("EOF")
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

                            now = time.monotonic()
                            if (
                                self._min_frame_interval_s > 0.0
                                and now - last_emit < self._min_frame_interval_s
                            ):
                                continue
                            last_emit = now
                            try:
                                self._on_jpeg(jpeg)
                            except Exception:
                                logger.exception("mjpeg on_jpeg callback failed")
                finally:
                    try:
                        sock.close()
                    except OSError:
                        pass
                    self._sock = None

                if self._stop_event.is_set():
                    break
                self._emit_status("Reconnecting...")
                if self._stop_event.wait(1.0):
                    break
        finally:
            self._sock = None
            self._emit_status("Stopped")
