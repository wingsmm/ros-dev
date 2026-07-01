"""Background QObject for camera topic probing (runs in dedicated QThread)."""

from __future__ import annotations

from PyQt5.QtCore import QObject, QTimer, pyqtSignal, pyqtSlot

from core.camera_topic_probe import CameraTopicProbeResult, probe_camera_topics
from core.camera_topics import CAMERA_PROBE_TOPICS


class CameraTopicProbeWorker(QObject):
    result_ready = pyqtSignal(object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._timer = QTimer(self)
        self._timer.setInterval(5000)
        self._timer.timeout.connect(self._poll_tick)
        self._active = False
        self._topics = CAMERA_PROBE_TOPICS

    @pyqtSlot(object)
    def set_topics(self, topics: object) -> None:
        if isinstance(topics, (tuple, list)):
            self._topics = tuple(str(topic) for topic in topics)

    def _poll_tick(self) -> None:
        if self._active:
            self.probe_now()

    @pyqtSlot()
    def start_polling(self) -> None:
        self._active = True
        self.probe_now()
        self._timer.start()

    @pyqtSlot()
    def stop_polling(self) -> None:
        self._active = False
        self._timer.stop()

    @pyqtSlot()
    def probe_now(self) -> None:
        result = probe_camera_topics(self._topics)
        self.result_ready.emit(result)
