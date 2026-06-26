"""Manage PC-side depth preview worker (QThread lifecycle)."""

from __future__ import annotations

import logging
from typing import Optional

from PyQt5.QtCore import QObject, QThread, Qt, QTimer, pyqtSignal, QMetaObject

from core.app_shutdown import register_shutdown
from core.camera_depth_frame import DepthSourceKind
from core.camera_depth_source import DepthSourceConfig
from core.camera_depth_http_worker import CameraDepthHttpWorker, DepthPreviewPacket

logger = logging.getLogger(__name__)


class _PreviewDeliveryGate:
    """Shared flag read by the HTTP worker; UI sets it synchronously on pause."""

    __slots__ = ("enabled",)

    def __init__(self) -> None:
        self.enabled = False


class CameraDepthPreviewManager(QObject):
    """Starts/stops CameraDepthWorker on a background thread."""

    preview_ready = pyqtSignal(object)
    stats_updated = pyqtSignal(object)
    status_changed = pyqtSignal(str)
    source_kind_changed = pyqtSignal(str)
    worker_failed = pyqtSignal(str)

    def __init__(
        self,
        config: Optional[DepthSourceConfig] = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._config = config or DepthSourceConfig.from_env()
        self._delivery_gate = _PreviewDeliveryGate()
        self._thread: Optional[QThread] = None
        self._worker: Optional[CameraDepthHttpWorker] = None
        self._running = False
        self._starting = False
        self._tearing_down = False
        self._source_kind = DepthSourceKind.OFFLINE
        # Synchronous gate: drop worker frames before they reach the UI thread.
        self._deliver_to_ui = False
        self._delivery_gate.enabled = False
        register_shutdown(self.shutdown, name="camera_depth_preview_manager", priority=24)

    def is_running(self) -> bool:
        return self._running and self._thread is not None and self._worker is not None

    def is_starting(self) -> bool:
        return self._starting and self._thread is not None

    def source_kind(self) -> DepthSourceKind:
        return self._source_kind

    def start(self) -> bool:
        if self._thread is not None:
            if self._thread.isRunning():
                return self.is_running() or self.is_starting()
            self._thread = None
            self._worker = None
        self._starting = True
        self._deliver_to_ui = True
        self._delivery_gate.enabled = True
        thread = QThread()
        worker = CameraDepthHttpWorker(self._config, delivery_gate=self._delivery_gate)
        worker.moveToThread(thread)
        worker.preview_ready.connect(self._on_preview)
        worker.status_changed.connect(self._on_status)
        worker.failed.connect(self._on_failed)
        thread.started.connect(self._on_thread_started)
        thread.finished.connect(self._on_thread_finished)
        self._thread = thread
        self._worker = worker
        thread.start()
        return True

    def stop(self) -> None:
        self._request_stop(block=True, fast=False)

    def stop_async(self) -> None:
        """Stop without blocking the UI thread (e.g. before MJPEG fallback)."""
        self._request_stop(block=False, fast=False)

    def stop_for_handoff(self) -> None:
        """Stop raw worker when handing off to MJPEG; do not mark source offline."""
        self._request_stop(block=False, reset_source_kind=False, fast=False)

    def _request_stop(
        self,
        *,
        block: bool,
        reset_source_kind: bool = True,
        fast: bool = False,
    ) -> None:
        thread = self._thread
        worker = self._worker
        if thread is None:
            return
        if self._tearing_down and not block:
            return
        self._running = False
        self._starting = False
        self._deliver_to_ui = False
        self._delivery_gate.enabled = False
        if worker is not None:
            QMetaObject.invokeMethod(worker, "stop_worker", Qt.QueuedConnection)
        thread.quit()
        wait_ms = 600 if fast else 4000
        if block or fast:
            if not thread.wait(wait_ms):
                logger.warning("depth preview thread did not stop in time")
                thread.terminate()
                thread.wait(400 if fast else 1000)
            if self._thread is thread:
                self._finalize_thread(thread, worker)
        if reset_source_kind:
            self._set_source_kind(DepthSourceKind.OFFLINE)

    def restart(self) -> bool:
        self.stop()
        return self.start()

    def pause(self) -> None:
        self._deliver_to_ui = False
        self._delivery_gate.enabled = False
        if self._worker is not None:
            QMetaObject.invokeMethod(
                self._worker, "pause_worker", Qt.QueuedConnection
            )

    def resume(self) -> bool:
        if self._worker is None or self._thread is None:
            self._deliver_to_ui = True
            self._delivery_gate.enabled = True
            return self.start()
        self._deliver_to_ui = True
        self._delivery_gate.enabled = True
        QMetaObject.invokeMethod(
            self._worker, "resume_worker", Qt.QueuedConnection
        )
        return True

    def set_mjpeg_fallback_active(self, active: bool) -> None:
        if active:
            self._set_source_kind(DepthSourceKind.MJPEG_FALLBACK)
        elif self.is_running():
            self._set_source_kind(DepthSourceKind.RAW_HTTP)
        else:
            self._set_source_kind(DepthSourceKind.OFFLINE)

    def shutdown(self) -> None:
        self._request_stop(block=False, fast=True)

    def _on_thread_started(self) -> None:
        if self._worker is None:
            self._starting = False
            return
        QMetaObject.invokeMethod(
            self._worker,
            "start_worker",
            Qt.QueuedConnection,
        )

    def _on_thread_finished(self) -> None:
        thread = self.sender()
        if not isinstance(thread, QThread) or thread is not self._thread:
            return
        worker = self._worker
        self._finalize_thread(thread, worker)

    def _finalize_thread(
        self, thread: QThread, worker: Optional[CameraDepthHttpWorker]
    ) -> None:
        if self._thread is thread:
            self._thread = None
            self._worker = None
        self._running = False
        self._starting = False
        if worker is not None:
            worker.deleteLater()
        thread.deleteLater()

    def _on_preview(self, packet: object) -> None:
        if not isinstance(packet, DepthPreviewPacket):
            return
        if not self._deliver_to_ui:
            return
        self._running = True
        self._set_source_kind(DepthSourceKind.RAW_HTTP)
        self.preview_ready.emit(packet)
        self.stats_updated.emit(packet.stats)

    def _on_status(self, text: str) -> None:
        self._starting = False
        if self._worker is not None and self._worker.is_active():
            self._running = True
        self.status_changed.emit(text)

    def _on_failed(self, detail: str) -> None:
        self._starting = False
        if self._tearing_down:
            return
        logger.error("depth preview worker failed: %s", detail)
        self.worker_failed.emit(detail)
        QTimer.singleShot(0, self._teardown_after_failure)

    def _teardown_after_failure(self) -> None:
        if self._tearing_down:
            return
        self._tearing_down = True
        try:
            self._request_stop(block=True)
        finally:
            self._tearing_down = False

    def _set_source_kind(self, kind: DepthSourceKind) -> None:
        if self._source_kind == kind:
            return
        self._source_kind = kind
        self.source_kind_changed.emit(kind.value)
