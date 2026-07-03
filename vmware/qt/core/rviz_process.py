"""Long-running local subprocess (RViz, image_view, etc.) — no command timeout."""

import logging

from PyQt5.QtCore import QObject, QProcess, pyqtSignal

from core.logging_config import new_child_log_path

logger = logging.getLogger(__name__)


class RvizProcessManager(QObject):
    output = pyqtSignal(str)
    running_changed = pyqtSignal(bool)

    def __init__(self, parent=None):
        super(RvizProcessManager, self).__init__(parent)
        self._process = QProcess(self)
        self._process.setProcessChannelMode(QProcess.MergedChannels)
        self._process.readyReadStandardOutput.connect(self._on_stdout)
        self._process.finished.connect(self._on_finished)
        self._config_path = ""
        self._log_path = ""
        self._log_file = None
        self._process_label = "RViz"

    @property
    def running(self):
        return self._process.state() != QProcess.NotRunning

    @property
    def pid(self):
        if not self.running:
            return 0
        return int(self._process.processId())

    @property
    def config_path(self):
        return self._config_path

    @property
    def log_path(self):
        return self._log_path

    def start(self, command, config_path="", process_label="RViz", log_prefix="rviz"):
        if self.running:
            self.output.emit(
                "[WARN] 本客户端 %s 已在运行 (pid=%s)" % (self._process_label, self.pid)
            )
            return False

        self._process_label = process_label
        self._config_path = config_path
        self._log_path = str(new_child_log_path(log_prefix))
        try:
            self._log_file = open(self._log_path, "ab")
        except OSError as exc:
            self.output.emit("[ERR] 无法创建 %s 日志: %s" % (process_label, exc))
            self._log_path = ""
            self._log_file = None

        self.output.emit("$ %s" % command)
        self.output.emit("[INFO] %s 日志: %s" % (process_label, self._log_path or "-"))
        logger.info("%s start config=%s log=%s", process_label, config_path, self._log_path)
        self._process.start("bash", ["-lc", command])
        if not self._process.waitForStarted(5000):
            self.output.emit("[ERR] %s 启动失败" % process_label)
            self._close_log_file()
            self._config_path = ""
            self._log_path = ""
            return False

        self.output.emit("[OK] %s 已启动 pid=%s" % (process_label, self.pid))
        logger.info("%s started pid=%s log=%s", process_label, self.pid, self._log_path)
        self.running_changed.emit(True)
        return True

    def stop(self):
        if not self.running:
            return

        pid = self.pid
        label = self._process_label
        self.output.emit("[INFO] 停止本客户端 %s pid=%s" % (label, pid))
        logger.info("%s stop pid=%s log=%s", label, pid, self._log_path)
        self._process.terminate()
        if not self._process.waitForFinished(3000):
            self._process.kill()
            self._process.waitForFinished(2000)

    def _close_log_file(self):
        if self._log_file is not None:
            try:
                self._log_file.close()
            except OSError:
                pass
            self._log_file = None

    def _on_stdout(self):
        data = bytes(self._process.readAllStandardOutput())
        if self._log_file is not None:
            try:
                self._log_file.write(data)
                self._log_file.flush()
            except OSError:
                pass
        try:
            text = data.decode("utf-8", errors="replace")
        except Exception:
            text = data.decode("latin-1", errors="replace")
        for line in text.splitlines():
            if line:
                self.output.emit(line)

    def _on_finished(self, exit_code, _exit_status):
        self._close_log_file()
        label = self._process_label
        if exit_code != 0:
            self.output.emit("[WARN] %s 退出 code=%s" % (label, exit_code))
            logger.warning("%s exited code=%s log=%s", label, exit_code, self._log_path)
        else:
            self.output.emit("[INFO] %s 已退出" % label)
            logger.info("%s exited code=0 log=%s", label, self._log_path)
        self._config_path = ""
        self.running_changed.emit(False)
