from __future__ import annotations

import logging
import os
import signal
import subprocess
import time
from pathlib import Path
from typing import Optional

from core.ros2_runtime import (
    Ros2RuntimeError,
    require_ros2_rviz,
    ros2_shell_prefix,
    rviz_subprocess_env,
    rviz_config_path,
)

logger = logging.getLogger(__name__)

_APP_ROOT = Path(__file__).resolve().parents[1]


class RvizProcessManager:
    """Start/stop RViz2 as an independent OS process (not legacy RosStackManager)."""

    def __init__(self) -> None:
        self._proc: Optional[subprocess.Popen] = None
        self._log_path = ""
        self._log_file: Optional[object] = None
        self._last_error = ""
        self._shutdown_done = False

    @property
    def last_error(self) -> str:
        return self._last_error

    def is_running(self) -> bool:
        if self._proc is None:
            return False
        code = self._proc.poll()
        if code is not None:
            self._proc = None
            self._close_log()
            if code != 0:
                error_detail = f"RViz2 异常退出 code={code}"
                try:
                    with open(self._log_path, "r", encoding="utf-8", errors="ignore") as f:
                        lines = f.readlines()
                        for line in reversed(lines[-20:]):
                            line = line.strip()
                            if "error" in line.lower() or "segmentation" in line.lower() or "fault" in line.lower():
                                error_detail += f" | {line}"
                                break
                except OSError:
                    pass
                self._last_error = error_detail
                logger.error("RViz2 crashed: %s", error_detail)
            else:
                logger.info("RViz2 exited normally code=%s log=%s", code, self._log_path)
            return False
        return True

    def start(self, config_path: Optional[Path] = None) -> bool:
        self._last_error = ""
        if self.is_running():
            return True
        try:
            require_ros2_rviz()
        except Ros2RuntimeError as exc:
            self._last_error = str(exc)
            return False
        log_dir = _APP_ROOT / "logs"
        log_dir.mkdir(exist_ok=True)
        stamp = time.strftime("%Y%m%d_%H%M%S")
        self._log_path = str(log_dir / f"rviz2_{stamp}.log")
        rviz_cfg = config_path if config_path is not None else rviz_config_path()
        env = rviz_subprocess_env()
        # 构建环境变量导出命令，确保 bash -lc 不会覆盖软件渲染设置
        env_exports = ""
        if env.get("LIBGL_ALWAYS_SOFTWARE") == "1":
            env_exports = "export LIBGL_ALWAYS_SOFTWARE=1; "
        rviz_args = "rviz2"
        if rviz_cfg.is_file():
            rviz_args = f"rviz2 -d {rviz_cfg.as_posix()}"
        # 先导出环境变量，再 source ROS setup，最后启动 rviz2
        cmd = ["bash", "-lc", env_exports + ros2_shell_prefix() + rviz_args]
        try:
            self._log_file = open(self._log_path, "ab")
            self._proc = subprocess.Popen(
                cmd,
                env=env,
                stdout=self._log_file,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        except OSError as exc:
            self._close_log()
            self._proc = None
            self._last_error = str(exc)
            logger.error("RViz2 start failed: %s", exc)
            return False
        # 调试：记录软件渲染相关环境变量
        gl_env = {"LIBGL_ALWAYS_SOFTWARE": env.get("LIBGL_ALWAYS_SOFTWARE")}
        logger.info("RViz2 started pid=%s log=%s gl_env=%s", self._proc.pid, self._log_path, gl_env)
        return True

    def stop(self) -> None:
        proc = self._proc
        self._proc = None
        if proc is None:
            return
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except (OSError, ProcessLookupError):
            try:
                proc.terminate()
            except OSError:
                pass
        try:
            proc.wait(timeout=3.0)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except (OSError, ProcessLookupError):
                proc.kill()
        self._close_log()
        logger.info("RViz2 stopped")

    def shutdown(self) -> None:
        if getattr(self, "_shutdown_done", False):
            return
        self._shutdown_done = True
        self.stop()

    def _close_log(self) -> None:
        if self._log_file is not None:
            try:
                self._log_file.close()
            except OSError:
                pass
            self._log_file = None
