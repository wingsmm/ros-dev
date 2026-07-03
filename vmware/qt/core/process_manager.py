"""Run shell commands from the Qt main thread with real timeout and optional queue."""

import logging

from PyQt5.QtCore import QObject, QProcess, QTimer, pyqtSignal

logger = logging.getLogger(__name__)


class ProcessManager(QObject):
    output = pyqtSignal(str)
    busy_changed = pyqtSignal(bool)

    def __init__(self):
        super(ProcessManager, self).__init__()
        self._process = QProcess(self)
        self._process.setProcessChannelMode(QProcess.MergedChannels)
        self._process.readyReadStandardOutput.connect(self._on_stdout)
        self._process.finished.connect(self._on_finished)

        self._timeout_timer = QTimer(self)
        self._timeout_timer.setSingleShot(True)
        self._timeout_timer.timeout.connect(self._on_timeout)

        self._queue = []
        self._active_timeout_s = 120
        self._timed_out = False

    @property
    def busy(self):
        return self._process.state() != QProcess.NotRunning or bool(self._queue)

    def run(self, command, timeout=120):
        self._queue.append((command, timeout))
        if self._process.state() == QProcess.NotRunning:
            self._start_next()

    def _start_next(self):
        if not self._queue:
            self.busy_changed.emit(False)
            return

        if self._process.state() != QProcess.NotRunning:
            return

        command, timeout = self._queue.pop(0)
        self._active_timeout_s = timeout
        self._timed_out = False
        self.busy_changed.emit(True)
        self.output.emit("$ %s" % command)
        logger.info("run command timeout=%ss: %s", timeout, command)
        self._process.start("bash", ["-lc", command])
        self._timeout_timer.start(max(1, timeout) * 1000)

    def _on_stdout(self):
        data = bytes(self._process.readAllStandardOutput())
        try:
            text = data.decode("utf-8", errors="replace")
        except Exception:
            text = data.decode("latin-1", errors="replace")
        for line in text.splitlines():
            if line:
                self.output.emit(line)

    def _on_timeout(self):
        if self._process.state() == QProcess.NotRunning:
            return
        self._timed_out = True
        self.output.emit("[ERR] 命令超时 (%ss)" % self._active_timeout_s)
        logger.warning("command timeout %ss", self._active_timeout_s)
        self._process.kill()

    def _on_finished(self, exit_code, _exit_status):
        self._timeout_timer.stop()
        if not self._timed_out:
            self.output.emit("[exit %s]" % exit_code)
            logger.info("command finished exit=%s", exit_code)
        if self._queue:
            self._start_next()
        else:
            self.busy_changed.emit(False)
