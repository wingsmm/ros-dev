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
        t0 = time.perf_counter()
        self._last_error = ""
        if self.is_running():
            logger.info(
                "RVIZ_FLOW start reuse elapsed=%.1fms pid=%s",
                (time.perf_counter() - t0) * 1000.0,
                self._proc.pid if self._proc is not None else None,
            )
            return True
        try:
            require_ros2_rviz()
        except Ros2RuntimeError as exc:
            self._last_error = str(exc)
            logger.warning(
                "RVIZ_FLOW start require_failed elapsed=%.1fms detail=%s",
                (time.perf_counter() - t0) * 1000.0,
                exc,
            )
            return False
        log_dir = _APP_ROOT / "logs"
        log_dir.mkdir(exist_ok=True)
        stamp = time.strftime("%Y%m%d_%H%M%S")
        self._log_path = str(log_dir / f"rviz2_{stamp}.log")
        rviz_cfg = config_path if config_path is not None else rviz_config_path()
        env = rviz_subprocess_env()
        try:
            nice_value = int(os.environ.get("XTARK_RVIZ_NICE", "10").strip())
        except ValueError:
            nice_value = 10
        nice_value = max(0, min(19, nice_value))
        rviz_prefix = "" if nice_value == 0 else f"nice -n {nice_value} "
        # 构建环境变量导出命令，确保 bash -lc 不会覆盖软件渲染设置
        env_exports = ""
        if env.get("LIBGL_ALWAYS_SOFTWARE") == "1":
            env_exports = "export LIBGL_ALWAYS_SOFTWARE=1; "
        rviz_args = f"{rviz_prefix}rviz2"
        if rviz_cfg.is_file():
            rviz_args = f"{rviz_prefix}rviz2 -d {rviz_cfg.as_posix()}"
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
            logger.warning(
                "RVIZ_FLOW start failed elapsed=%.1fms error=%s",
                (time.perf_counter() - t0) * 1000.0,
                exc,
            )
            return False
        # 调试：记录软件渲染相关环境变量
        gl_env = {
            "LIBGL_ALWAYS_SOFTWARE": env.get("LIBGL_ALWAYS_SOFTWARE"),
            "XTARK_RVIZ_NICE": nice_value,
        }
        logger.info("RViz2 started pid=%s log=%s gl_env=%s", self._proc.pid, self._log_path, gl_env)
        logger.info(
            "RVIZ_FLOW start elapsed=%.1fms pid=%s log=%s gl=%s config=%s",
            (time.perf_counter() - t0) * 1000.0,
            self._proc.pid,
            self._log_path,
            gl_env,
            rviz_cfg,
        )
        return True

    def stop(self) -> None:
        t0 = time.perf_counter()
        proc = self._proc
        self._proc = None
        if proc is None:
            logger.info("RVIZ_FLOW stop noop elapsed=0.0ms")
            return
        logger.info(
            "RVIZ_FLOW stop start pid=%s log=%s",
            proc.pid,
            self._log_path,
        )
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except (OSError, ProcessLookupError):
            try:
                proc.terminate()
            except OSError:
                pass
        try:
            proc.wait(timeout=0.7)
            logger.info(
                "RVIZ_FLOW stop wait elapsed=%.1fms code=%s",
                (time.perf_counter() - t0) * 1000.0,
                proc.returncode,
            )
        except subprocess.TimeoutExpired:
            logger.warning(
                "RVIZ_FLOW stop timeout elapsed=%.1fms pid=%s",
                (time.perf_counter() - t0) * 1000.0,
                proc.pid,
            )
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except (OSError, ProcessLookupError):
                proc.kill()
            try:
                proc.wait(timeout=0.5)
            except subprocess.TimeoutExpired:
                logger.error(
                    "RVIZ_FLOW stop kill_wait_timeout pid=%s",
                    proc.pid,
                )
        self._close_log()
        logger.info("RViz2 stopped")
        logger.info(
            "RVIZ_FLOW stop end elapsed=%.1fms code=%s",
            (time.perf_counter() - t0) * 1000.0,
            proc.returncode,
        )

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
