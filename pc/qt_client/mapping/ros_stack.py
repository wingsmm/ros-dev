"""Start/stop RViz2 and slam_toolbox from the GUI (no extra terminal).

DEPRECATED path: only used by legacy LegacyWindow. New shell must not import
this module; reuse commands documented in pc/docs/控制端与ROS2硬件平台架构方案.md §9.3
for future PC/WSL ROS2 sidecar.
"""

from __future__ import annotations

import os
import re
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
        if self.is_nav_running():
            self._log("STACK stopping navigation/localization before SLAM")
            self.stop_nav()
        if not self.is_running("slam"):
            self._stop_external_slam()
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
            self._stop_external_stack(name)
            return
        self._terminate(proc)
        self._close_log_file(name)
        self._stop_external_stack(name)
        self._log("STACK stop {name}".format(name=name))

    def stop_all(self) -> None:
        for name in ("navigation", "localization", "slam", "rviz2"):
            self.stop(name)
        for name in list(self._procs.keys()):
            self.stop(name)

    def stop_mapping(self) -> None:
        for name in ("rviz2", "slam"):
            if name in self._procs:
                self.stop(name)

    def stop_nav(self) -> None:
        for name in ("navigation", "localization"):
            self.stop(name)

    def is_nav_running(self) -> bool:
        return self.is_running("localization") or self.is_running("navigation")

    def _nav2_params_path(self) -> Path:
        custom = _APP_ROOT / "config" / "nav2_xtark.yaml"
        if custom.is_file():
            return custom
        return Path("/opt/ros/humble/share/nav2_bringup/params/nav2_params.yaml")

    def _require_nav2(self) -> bool:
        if self._run_ros_check("ros2 pkg prefix nav2_bringup"):
            return True
        self._log(
            "NAV FAIL: 未安装 nav2。请: sudo apt install ros-humble-nav2-bringup"
        )
        return False

    def resolve_map_yaml(self, user_input: str) -> tuple[bool, str]:
        text = user_input.strip()
        if not text:
            maps = sorted(self.maps_dir().glob("*.yaml"), key=lambda p: p.stat().st_mtime)
            if not maps:
                return False, "未指定地图，且 maps/ 下没有 .yaml 文件。"
            text = str(maps[-1])
        path = Path(text)
        if not path.is_absolute():
            path = (_APP_ROOT / path).resolve()
        if not path.is_file():
            return False, "地图文件不存在: {path}".format(path=path)
        return True, str(path)

    def start_localization(self, map_yaml: str) -> tuple[bool, str]:
        if not self._require_nav2():
            return False, "Nav2 未安装"
        ok, resolved = self.resolve_map_yaml(map_yaml)
        if not ok:
            return False, resolved
        if self.is_running("slam"):
            self._log("NAV stopping SLAM before localization")
            self.stop("slam")
        if not self.is_running("localization"):
            self._stop_external_localization()
        params = self._nav2_params_path()
        inner = (
            "ros2 launch nav2_bringup localization_launch.py "
            "map:={map} params_file:={params} use_sim_time:=false"
        ).format(map=shlex.quote(resolved), params=shlex.quote(str(params)))
        if not self._start("localization", inner):
            return False, "定位启动失败，见 logs/"
        return True, resolved

    def start_navigation(self) -> bool:
        if not self._require_nav2():
            return False
        if not self.is_running("localization"):
            self._log("NAV start FAIL: localization not running")
            return False
        if not self.is_running("navigation"):
            self._stop_external_navigation()
        params = self._nav2_params_path()
        inner = (
            "ros2 launch nav2_bringup navigation_launch.py "
            "params_file:={params} use_sim_time:=false"
        ).format(params=shlex.quote(str(params)))
        return self._start("navigation", inner)

    def start_nav_all(self, map_yaml: str) -> tuple[bool, str]:
        ok, detail = self.start_localization(map_yaml)
        if not ok:
            return False, detail
        if not self._wait_for_topic("/map", timeout_sec=45):
            self._log("NAV WARN: /map not seen within timeout")
        time.sleep(2.0)
        if not self.start_navigation():
            return False, "Nav2 启动失败，见 logs/"
        return True, detail

    def cancel_navigation(self) -> None:
        request = (
            "{goal_info: {stamp: {sec: 0, nanosec: 0}, "
            "goal_id: {uuid: [0, 0, 0, 0, 0, 0, 0, 0, "
            "0, 0, 0, 0, 0, 0, 0, 0]}}}"
        )
        calls = []
        for action_name in ("/navigate_to_pose", "/navigate_through_poses"):
            calls.append(
                "ros2 service call {action}/_action/cancel_goal "
                "action_msgs/srv/CancelGoal {request} >/dev/null 2>&1 || true"
                .format(action=action_name, request=shlex.quote(request))
            )
        cmd = ["bash", "-lc", _ROS_SHELL + "; ".join(calls)]
        try:
            subprocess.run(cmd, timeout=5.0, capture_output=True)
        except (OSError, subprocess.TimeoutExpired):
            pass
        self._log("NAV cancel_navigation sent")

    def maps_dir(self) -> Path:
        path = _APP_ROOT / "maps"
        path.mkdir(exist_ok=True)
        return path

    def save_map(self, name: str = "") -> tuple[bool, str]:
        """Save /map to maps/<name>.pgm + .yaml (requires SLAM running)."""
        if not self.is_running("slam"):
            return False, "SLAM 未运行，请先启动 SLAM。"
        if not self._require_map_saver():
            return (
                False,
                "未安装 map_saver。请: sudo apt install ros-humble-nav2-map-server",
            )

        safe_name = self._sanitize_map_name(name)
        base_path = self.maps_dir() / safe_name
        inner_cmd = (
            "ros2 run nav2_map_server map_saver_cli -f "
            + shlex.quote(str(base_path))
        )
        self._log("MAP save start: {path}".format(path=base_path))
        cmd = ["bash", "-lc", _ROS_SHELL + inner_cmd]
        env = os.environ.copy()
        env.setdefault("ROS_DOMAIN_ID", "0")
        try:
            result = subprocess.run(
                cmd,
                env=env,
                capture_output=True,
                text=True,
                timeout=30.0,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            self._log("MAP save FAIL: {exc}".format(exc=exc))
            return False, "存图失败: {exc}".format(exc=exc)

        pgm = base_path.with_suffix(".pgm")
        yaml_path = base_path.with_suffix(".yaml")
        if result.returncode != 0 or not pgm.is_file() or not yaml_path.is_file():
            detail = (result.stderr or result.stdout or "").strip()
            self._log("MAP save FAIL code={code} {detail}".format(
                code=result.returncode, detail=detail
            ))
            if "Failed to spin map subscription" in detail:
                return (
                    False,
                    "存图失败：没有收到 /map 消息。请确认 SLAM 正在生成地图，"
                    "/scan、/odom 和 TF 都在持续刷新。",
                )
            return False, "存图失败。确认 /map 在发布且 SLAM 已生成地图。"

        self._log(
            "MAP save OK: {pgm} {yaml}".format(pgm=pgm, yaml=yaml_path)
        )
        return True, "已保存:\n{pgm}\n{yaml}".format(pgm=pgm, yaml=yaml_path)

    def _require_map_saver(self) -> bool:
        return self._run_ros_check("ros2 pkg prefix nav2_map_server")

    def _wait_for_topic(self, topic: str, timeout_sec: float = 30.0) -> bool:
        inner = (
            "end=$((SECONDS+{timeout})); "
            "while [ $SECONDS -lt $end ]; do "
            "ros2 topic list 2>/dev/null | grep -qx '{topic}' && exit 0; "
            "sleep 1; done; exit 1"
        ).format(timeout=int(timeout_sec), topic=topic)
        return self._run_ros_check(inner)

    def _stop_external_stack(self, name: str) -> None:
        if name == "localization":
            self._stop_external_localization()
        elif name == "navigation":
            self._stop_external_navigation()
        elif name == "slam":
            self._stop_external_slam()

    def _stop_external_slam(self) -> None:
        self._kill_matching_ros_processes(
            "slam",
            [
                "slam_toolbox online_async_launch.py",
                "/slam_toolbox/async_slam_toolbox_node",
            ],
        )

    def _stop_external_localization(self) -> None:
        self._kill_matching_ros_processes(
            "localization",
            [
                "nav2_bringup localization_launch.py",
                "/nav2_map_server/map_server",
                "/nav2_amcl/amcl",
                "lifecycle_manager_localization",
            ],
        )

    def _stop_external_navigation(self) -> None:
        self._kill_matching_ros_processes(
            "navigation",
            [
                "nav2_bringup navigation_launch.py",
                "/nav2_controller/controller_server",
                "/nav2_planner/planner_server",
                "/nav2_bt_navigator/bt_navigator",
                "/nav2_behaviors/behavior_server",
                "/nav2_waypoint_follower/waypoint_follower",
                "/nav2_smoother/smoother_server",
                "/nav2_velocity_smoother/velocity_smoother",
                "lifecycle_manager_navigation",
            ],
        )

    def _kill_matching_ros_processes(self, name: str, patterns: list[str]) -> None:
        calls = [
            "pkill -f -- {pattern} >/dev/null 2>&1 || true".format(
                pattern=shlex.quote(pattern)
            )
            for pattern in patterns
        ]
        calls.append("ros2 daemon stop >/dev/null 2>&1 || true")
        cmd = ["bash", "-lc", _ROS_SHELL + "; ".join(calls)]
        try:
            subprocess.run(cmd, timeout=5.0, capture_output=True)
        except (OSError, subprocess.TimeoutExpired):
            self._log("STACK cleanup {name} WARN: timeout/error".format(name=name))

    @staticmethod
    def _sanitize_map_name(name: str) -> str:
        name = name.strip()
        if not name:
            name = "xtark_{stamp}".format(stamp=time.strftime("%Y%m%d_%H%M%S"))
        name = re.sub(r"[^\w\-]", "_", name)
        return name or "xtark_map"

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
