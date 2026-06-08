"""Start/stop RViz2 and slam_toolbox from the GUI (no extra terminal)."""

from __future__ import annotations

import os
import shlex
import signal
import subprocess
import time
from pathlib import Path
from typing import Callable, Dict, Optional

LogFn = Callable[[str], None]

_ROS_SHELL = (
    "source /opt/ros/humble/setup.bash 2>/dev/null; "
    "export ROS_DOMAIN_ID=${ROS_DOMAIN_ID:-0}; "
)
_APP_ROOT = Path(__file__).resolve().parents[1]


class RosStackManager:
    def __init__(self, log: Optional[LogFn] = None) -> None:
        self._log = log or (lambda _msg: None)
        self._procs: Dict[str, subprocess.Popen] = {}
        self._log_paths: Dict[str, str] = {}
        self._log_files: Dict[str, object] = {}

    def _run_ros_check(self, inner_cmd: str) -> bool:
        cmd = ["bash", "-lc", _ROS_SHELL + inner_cmd]
        try:
            result = subprocess.run(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=10.0,
            )
        except (OSError, subprocess.TimeoutExpired):
            return False
        return result.returncode == 0

    def _require_rviz2(self) -> bool:
        if self._run_ros_check("command -v rviz2"):
            return True
        self._log(
            "STACK rviz2 FAIL: 未安装。请: sudo apt install ros-humble-rviz2"
        )
        return False

    def _require_slam_toolbox(self) -> bool:
        if self._run_ros_check("ros2 pkg prefix slam_toolbox"):
            return True
        self._log(
            "STACK slam FAIL: 未安装。请: sudo apt install ros-humble-slam-toolbox"
        )
        return False

    def is_running(self, name: str) -> bool:
        proc = self._procs.get(name)
        if proc is None:
            return False
        code = proc.poll()
        if code is not None:
            self._procs.pop(name, None)
            self._close_log_file(name)
            log_path = self._log_paths.get(name)
            detail = " log={path}".format(path=log_path) if log_path else ""
            self._log(
                "STACK {name} exited code={code}{detail}".format(
                    name=name, code=code, detail=detail
                )
            )
            return False
        return True

    def start_rviz(self) -> bool:
        if not self._require_rviz2():
            return False
        return self._start("rviz2", "rviz2")

    def start_slam(self) -> bool:
        if not self._require_slam_toolbox():
            return False
        params_path = _APP_ROOT / "config" / "slam_toolbox_xtark.yaml"
        return self._start(
            "slam",
            "ros2 launch slam_toolbox online_async_launch.py "
            "use_sim_time:=false slam_params_file:={params}".format(
                params=shlex.quote(str(params_path))
            ),
        )

    def start_all(self) -> None:
        self.start_slam()
        self.start_rviz()

    def stop(self, name: str) -> None:
        proc = self._procs.pop(name, None)
        if proc is None:
            return
        self._terminate(proc)
        self._close_log_file(name)
        self._log("STACK stop {name}".format(name=name))

    def stop_all(self) -> None:
        for name in list(self._procs.keys()):
            self.stop(name)

    def _start(self, name: str, inner_cmd: str) -> bool:
        if self.is_running(name):
            self._log("STACK {name} already running".format(name=name))
            return False
        cmd = ["bash", "-lc", _ROS_SHELL + inner_cmd]
        env = os.environ.copy()
        env.setdefault("ROS_DOMAIN_ID", "0")
        log_path = self._make_log_path(name)
        try:
            log_file = open(log_path, "ab")
            proc = subprocess.Popen(
                cmd,
                env=env,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        except OSError as exc:
            try:
                log_file.close()
            except UnboundLocalError:
                pass
            self._log("STACK start {name} FAIL: {exc}".format(name=name, exc=exc))
            return False
        self._procs[name] = proc
        self._log_paths[name] = log_path
        self._log_files[name] = log_file
        self._log(
            "STACK start {name} pid={pid} log={log}".format(
                name=name, pid=proc.pid, log=log_path
            )
        )
        return True

    def _make_log_path(self, name: str) -> str:
        log_dir = _APP_ROOT / "logs"
        log_dir.mkdir(exist_ok=True)
        stamp = time.strftime("%Y%m%d_%H%M%S")
        return str(log_dir / "{name}_{stamp}.log".format(name=name, stamp=stamp))

    def _close_log_file(self, name: str) -> None:
        log_file = self._log_files.pop(name, None)
        if log_file is None:
            return
        try:
            log_file.close()
        except OSError:
            pass

    def _terminate(self, proc: subprocess.Popen) -> None:
        if proc.poll() is not None:
            return
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except (ProcessLookupError, OSError):
            proc.terminate()
        try:
            proc.wait(timeout=3.0)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except (ProcessLookupError, OSError):
                proc.kill()
