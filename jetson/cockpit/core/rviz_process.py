"""Launch local rviz2 as a long-running subprocess."""

from __future__ import annotations

import logging
import shlex
from pathlib import Path

from PyQt5.QtCore import QObject, QProcess, pyqtSignal

from core.logging_config import new_child_log_path

logger = logging.getLogger(__name__)


class RvizProcessManager(QObject):
    output = pyqtSignal(str)
    running_changed = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._process = QProcess(self)
        self._process.setProcessChannelMode(QProcess.MergedChannels)
        self._process.readyReadStandardOutput.connect(self._on_stdout)
        self._process.finished.connect(self._on_finished)
        self._config_path = ""
        self._log_path = ""
        self._log_file = None
        self._process_label = "RViz2"

    @property
    def running(self) -> bool:
        return self._process.state() != QProcess.NotRunning

    @property
    def pid(self) -> int:
        if not self.running:
            return 0
        return int(self._process.processId())

    @property
    def config_path(self) -> str:
        return self._config_path

    def start(self, command: str, config_path: str = "", process_label: str = "RViz2") -> bool:
        if self.running:
            self.output.emit(
                "[WARN] %s 已在运行 (pid=%s)" % (self._process_label, self.pid)
            )
            return False

        self._process_label = process_label
        self._config_path = config_path
        self._log_path = str(new_child_log_path("rviz2"))
        try:
            self._log_file = open(self._log_path, "ab")
        except OSError as exc:
            self.output.emit("[ERR] 无法创建日志: %s" % exc)
            self._log_path = ""
            self._log_file = None

        self.output.emit("$ %s" % command)
        self.output.emit("[INFO] 日志: %s" % (self._log_path or "-"))
        logger.info("%s start config=%s", process_label, config_path)
        self._process.start("bash", ["-lc", command])
        if not self._process.waitForStarted(8000):
            self.output.emit("[ERR] %s 启动失败" % process_label)
            self._close_log_file()
            self._config_path = ""
            return False

        self.output.emit("[OK] %s pid=%s" % (process_label, self.pid))
        self.running_changed.emit(True)
        return True

    def stop(self) -> None:
        if not self.running:
            return
        pid = self.pid
        self.output.emit("[INFO] 停止 %s pid=%s" % (self._process_label, pid))
        self._process.terminate()
        if not self._process.waitForFinished(3000):
            self._process.kill()
            self._process.waitForFinished(2000)

    def _close_log_file(self) -> None:
        if self._log_file is not None:
            try:
                self._log_file.close()
            except OSError:
                pass
            self._log_file = None

    def _on_stdout(self) -> None:
        data = bytes(self._process.readAllStandardOutput())
        if self._log_file is not None:
            try:
                self._log_file.write(data)
                self._log_file.flush()
            except OSError:
                pass
        text = data.decode("utf-8", errors="replace")
        for line in text.splitlines():
            if line:
                self.output.emit(line)

    def _on_finished(self, exit_code, _exit_status) -> None:
        self._close_log_file()
        if exit_code != 0:
            self.output.emit("[WARN] %s 退出 code=%s" % (self._process_label, exit_code))
        else:
            self.output.emit("[INFO] %s 已退出" % (self._process_label))
        self._config_path = ""
        self.running_changed.emit(False)


def rviz2_start_command(config_path: Path, ros_setup: str = "/opt/ros/humble/setup.bash") -> str:
    script = config_path.parent.parent / "scripts" / "start_unilidar_rviz.sh"
    return (
        "export ROS_SETUP=%s UNILIDAR_RVIZ_CONFIG=%s; bash %s"
        % (shlex.quote(ros_setup), shlex.quote(str(config_path)), shlex.quote(str(script)))
    )
