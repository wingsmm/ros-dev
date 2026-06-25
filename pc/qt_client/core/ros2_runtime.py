"""Single place for PC/WSL ROS2 environment: probe once at boot, gate bridge/RViz2."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

_APP_ROOT = Path(__file__).resolve().parents[1]
_RVIZ_ROBOT_CONFIG = _APP_ROOT / "config" / "xtark_robot.rviz"
_RVIZ_CAMERA_CONFIG = _APP_ROOT / "config" / "xtark_camera.rviz"
_RVIZ_CONFIG = _RVIZ_ROBOT_CONFIG

logger = logging.getLogger(__name__)

_HUMBLE_SETUP = "/opt/ros/humble/setup.bash"
_ROS_SHELL_PREFIX = (
    f"source {_HUMBLE_SETUP} 2>/dev/null; "
    "export ROS_DOMAIN_ID=${ROS_DOMAIN_ID:-0}; "
)


class Ros2RuntimeError(RuntimeError):
    """ROS2 runtime is disabled or missing required dependencies."""


@dataclass(frozen=True)
class Ros2RuntimeStatus:
    enabled: bool = True
    humble_setup_present: bool = False
    setup_sourced: bool = False
    numpy_ok: bool = False
    rclpy_ok: bool = False
    rviz2_ok: bool = False
    distro: str = ""
    domain_id: str = "0"
    errors: tuple[str, ...] = field(default_factory=tuple)
    fix_hints: tuple[str, ...] = field(default_factory=tuple)

    @property
    def bridge_ready(self) -> bool:
        return self.enabled and self.rclpy_ok and self.numpy_ok and self.setup_sourced

    @property
    def rviz_ready(self) -> bool:
        return self.enabled and self.rviz2_ok and self.setup_sourced

    def format_report(self) -> str:
        if not self.enabled:
            return "ROS2 已禁用 (--no-ros)"
        lines: List[str] = [
            "ROS2 环境未就绪，无法使用 Bridge / RViz2 联调。",
            f"distro={self.distro or '—'} DOMAIN_ID={self.domain_id}",
        ]
        if self.errors:
            lines.append("")
            lines.append("问题:")
            lines.extend(f"  - {item}" for item in self.errors)
        if self.fix_hints:
            lines.append("")
            lines.append("修复:")
            lines.extend(f"  - {item}" for item in self.fix_hints)
        return "\n".join(lines)

    def summary_line(self) -> str:
        if not self.enabled:
            return "ROS2 已禁用"
        if self.bridge_ready and self.rviz_ready:
            return f"ROS2 就绪 ({self.distro}, DOMAIN_ID={self.domain_id})"
        if self.errors:
            return "; ".join(self.errors)
        return "ROS2 环境未就绪"


class Ros2Runtime:
    """Process-wide ROS2 environment snapshot (initialized from app boot)."""

    _instance: Optional["Ros2Runtime"] = None

    def __init__(self) -> None:
        self._status = Ros2RuntimeStatus(enabled=False)

    @classmethod
    def instance(cls) -> "Ros2Runtime":
        if cls._instance is None:
            cls._instance = Ros2Runtime()
        return cls._instance

    @classmethod
    def boot(cls, *, enabled: bool = True) -> Ros2RuntimeStatus:
        runtime = cls.instance()
        runtime._status = runtime._probe(enabled=enabled)
        status = runtime._status
        if not status.enabled:
            logger.info("ROS2 runtime disabled (--no-ros)")
            return status
        if status.bridge_ready:
            logger.info(
                "ROS2 runtime ready distro=%s domain_id=%s rviz2=%s",
                status.distro,
                status.domain_id,
                status.rviz2_ok,
            )
        else:
            logger.error("ROS2 runtime not ready:\n%s", status.format_report())
        if status.enabled and status.bridge_ready and not status.rviz2_ok:
            logger.warning(
                "ROS2 bridge OK but rviz2 missing; install: sudo apt install ros-humble-rviz2"
            )
        return status

    def status(self) -> Ros2RuntimeStatus:
        return self._status

    def require_bridge(self) -> None:
        status = self._status
        if not status.enabled:
            raise Ros2RuntimeError("ROS2 已禁用，请去掉 --no-ros 后通过 ./run.sh 启动")
        if not status.bridge_ready:
            raise Ros2RuntimeError(status.format_report())

    def require_rviz(self) -> None:
        status = self._status
        if not status.enabled:
            raise Ros2RuntimeError("ROS2 已禁用，请去掉 --no-ros 后通过 ./run.sh 启动")
        if not status.rviz_ready:
            if not status.bridge_ready:
                raise Ros2RuntimeError(status.format_report())
            raise Ros2RuntimeError(
                "rviz2 未安装。修复: sudo apt install ros-humble-rviz2"
            )

    def shell_prefix(self) -> str:
        return _ROS_SHELL_PREFIX

    def subprocess_env(self) -> dict[str, str]:
        env = os.environ.copy()
        env.setdefault("ROS_DOMAIN_ID", self._status.domain_id or "0")
        return env

    def _probe(self, *, enabled: bool) -> Ros2RuntimeStatus:
        if not enabled:
            return Ros2RuntimeStatus(enabled=False)

        errors: List[str] = []
        hints: List[str] = []
        humble_present = os.path.isfile(_HUMBLE_SETUP)
        if not humble_present:
            errors.append(f"未找到 {_HUMBLE_SETUP}")
            hints.append("安装 ROS2 Humble，并始终通过 pc/qt_client/run.sh 启动")

        distro = os.environ.get("ROS_DISTRO", "").strip()
        setup_sourced = bool(distro)
        if humble_present and not setup_sourced:
            errors.append("ROS_DISTRO 未设置（未 source humble）")
            hints.append("使用 ./run.sh 启动，不要直接 python app.py")

        numpy_ok = False
        try:
            import numpy  # noqa: F401

            numpy_ok = True
        except ImportError as exc:
            errors.append(f"numpy 缺失: {exc}")
            hints.append("在 .venv 中执行: pip install numpy")

        rclpy_ok = False
        if numpy_ok:
            try:
                import rclpy  # noqa: F401
                from nav_msgs.msg import Odometry  # noqa: F401
                from sensor_msgs.msg import LaserScan  # noqa: F401
                from tf2_ros import TransformBroadcaster  # noqa: F401

                rclpy_ok = True
            except ImportError as exc:
                errors.append(f"rclpy/ROS2 消息未加载: {exc}")
                hints.append(f"source {_HUMBLE_SETUP} 后重启；确认已安装 ros-humble-desktop")
        elif setup_sourced:
            errors.append("numpy 未安装，无法加载 rclpy")

        if not distro and humble_present:
            distro = _shell_ros_value("echo ${ROS_DISTRO:-}") or "unknown"

        domain_id = os.environ.get("ROS_DOMAIN_ID", "0").strip() or "0"
        rviz2_ok = _command_available("rviz2")
        if not rviz2_ok:
            errors.append("rviz2 未安装")
            hints.append("sudo apt install ros-humble-rviz2")

        return Ros2RuntimeStatus(
            enabled=True,
            humble_setup_present=humble_present,
            setup_sourced=setup_sourced,
            numpy_ok=numpy_ok,
            rclpy_ok=rclpy_ok,
            rviz2_ok=rviz2_ok,
            distro=distro,
            domain_id=domain_id,
            errors=tuple(errors),
            fix_hints=tuple(_dedupe(hints)),
        )


def boot_ros2_runtime(*, enabled: bool = True) -> Ros2RuntimeStatus:
    return Ros2Runtime.boot(enabled=enabled)


def ros2_status() -> Ros2RuntimeStatus:
    return Ros2Runtime.instance().status()


def require_ros2_bridge() -> None:
    Ros2Runtime.instance().require_bridge()


def require_ros2_rviz() -> None:
    Ros2Runtime.instance().require_rviz()


def ros2_shell_prefix() -> str:
    return Ros2Runtime.instance().shell_prefix()


def ros2_subprocess_env() -> dict[str, str]:
    return Ros2Runtime.instance().subprocess_env()


def _is_wsl() -> bool:
    try:
        with open("/proc/version", "r", encoding="utf-8", errors="ignore") as f:
            return "microsoft" in f.read().lower()
    except OSError:
        return False


def rviz_subprocess_env() -> dict[str, str]:
    """RViz2 subprocess env; WSL defaults to software GL to avoid libGL SIGSEGV."""
    env = ros2_subprocess_env()
    raw = os.environ.get("XTARK_RVIZ_SOFTWARE_GL", "").strip().lower()
    if raw in {"0", "false", "no", "off"}:
        return env
    if raw in {"1", "true", "yes", "on"} or (raw == "" and _is_wsl()):
        # WSL2 最保守配置：只强制软件渲染，不做其他覆盖
        env["LIBGL_ALWAYS_SOFTWARE"] = "1"
    return env


def rviz_robot_config_path() -> Path:
    return _RVIZ_ROBOT_CONFIG


def rviz_camera_config_path() -> Path:
    return _RVIZ_CAMERA_CONFIG


def rviz_config_path() -> Path:
    return rviz_robot_config_path()


def auto_bridge_enabled() -> bool:
    """XTARK_AUTO_BRIDGE=0 disables auto-start on robot page; default on."""
    raw = os.environ.get("XTARK_AUTO_BRIDGE", "1").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def auto_camera_bridge_enabled() -> bool:
    """XTARK_AUTO_CAMERA_BRIDGE=1 enables auto-start on camera page; default off."""
    raw = os.environ.get("XTARK_AUTO_CAMERA_BRIDGE", "0").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def diagnostic_shell_commands() -> str:
    prefix = ros2_shell_prefix()
    return "\n".join(
        [
            prefix + "ros2 topic list",
            prefix + "ros2 topic hz /scan",
            prefix + "ros2 topic hz /odom",
            prefix + "ros2 run tf2_tools view_frames",
        ]
    )


def camera_diagnostic_shell_commands() -> str:
    prefix = ros2_shell_prefix()
    return "\n".join(
        [
            prefix + "ros2 topic list",
            prefix + "ros2 topic hz /camera/image_raw",
            prefix + "ros2 run tf2_tools view_frames",
        ]
    )


def ros2_unavailable_reason() -> str:
    """Legacy Ros2Publisher gate; reads the same boot-time runtime snapshot."""
    try:
        require_ros2_bridge()
    except Ros2RuntimeError as exc:
        return str(exc)
    return "Ros2Publisher 初始化失败"


def _dedupe(items: List[str]) -> List[str]:
    seen: set[str] = set()
    out: List[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def _shell_ros_value(inner_cmd: str) -> str:
    cmd = ["bash", "-lc", _ROS_SHELL_PREFIX + inner_cmd]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=8.0,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    if result.returncode != 0:
        return ""
    return (result.stdout or "").strip()


def _command_available(name: str) -> bool:
    if shutil.which(name):
        return True
    return _shell_ros_value(f"command -v {name}") != ""
