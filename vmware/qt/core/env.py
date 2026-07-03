"""ROS / path environment for VMware Qt client (runs on VM, ROS1 Melodic)."""

import os
import shlex
import subprocess
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = APP_DIR / "config"
DEFAULT_ENV_FILE = CONFIG_DIR / "vmware_client.env"


class ClientConfig(object):
    def __init__(
        self,
        app_dir,
        robot_ip,
        ros_master_uri,
        ros_ip,
        ros_setup,
        ws_setup,
        libgl_software,
        rviz_configs,
    ):
        self.app_dir = app_dir
        self.robot_ip = robot_ip
        self.ros_master_uri = ros_master_uri
        self.ros_ip = ros_ip
        self.ros_setup = ros_setup
        self.ws_setup = ws_setup
        self.libgl_software = libgl_software
        self.rviz_configs = rviz_configs

    @property
    def ros_setup_exists(self):
        return self.ros_setup.is_file()

    @property
    def ws_setup_exists(self):
        return self.ws_setup.is_file()


def _load_dotenv(path):
    if not path.is_file():
        return {}
    values = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        values[key.strip()] = val.strip()
    return values


def detect_ros_ip(robot_ip, ros_ip="", pc_net_if=""):
    if ros_ip and ros_ip != robot_ip:
        return ros_ip, "来自环境变量 ROS_IP"

    iface = pc_net_if
    if not iface:
        try:
            out = subprocess.check_output(
                ["ip", "route", "get", robot_ip],
                stderr=subprocess.DEVNULL,
                universal_newlines=True,
            )
            parts = out.split()
            for i, token in enumerate(parts):
                if token == "dev" and i + 1 < len(parts):
                    iface = parts[i + 1]
                    break
        except (subprocess.CalledProcessError, OSError):
            iface = ""

    if iface:
        try:
            out = subprocess.check_output(
                ["ip", "-4", "addr", "show", iface],
                stderr=subprocess.DEVNULL,
                universal_newlines=True,
            )
            for line in out.splitlines():
                line = line.strip()
                if line.startswith("inet "):
                    ip = line.split()[1].split("/")[0]
                    if ip:
                        return ip, "网卡 %s" % iface
        except (subprocess.CalledProcessError, OSError):
            pass

    try:
        out = subprocess.check_output(
            ["hostname", "-I"], stderr=subprocess.DEVNULL, universal_newlines=True
        )
        first = out.strip().split()
        if first:
            return first[0], "hostname -I"
    except (subprocess.CalledProcessError, OSError):
        pass

    return "", "未能自动检测 ROS_IP，请在 config/vmware_client.env 中设置"


def load_config(env_file=None):
    env_path = env_file or DEFAULT_ENV_FILE
    file_env = _load_dotenv(env_path)

    def get(key, default=""):
        return os.environ.get(key, file_env.get(key, default))

    robot_ip = get("ROBOT_IP", "192.168.1.169")
    ros_master_uri = get("ROS_MASTER_URI", "http://%s:11311" % robot_ip)
    ros_ip_override = get("ROS_IP", "")
    pc_net_if = get("PC_NET_IF", "")
    ros_ip, _ = detect_ros_ip(robot_ip, ros_ip_override, pc_net_if)
    if ros_ip_override:
        ros_ip = ros_ip_override

    home = Path.home()
    rviz_configs = {
        "激光/地图": CONFIG_DIR / "rviz_mapping.rviz",
        "深度轻量": CONFIG_DIR / "rviz_depth_light.rviz",
        "RGB+Depth 诊断": CONFIG_DIR / "rviz_rgb_depth_diag.rviz",
    }

    return ClientConfig(
        app_dir=APP_DIR,
        robot_ip=robot_ip,
        ros_master_uri=ros_master_uri,
        ros_ip=ros_ip,
        ros_setup=Path(get("ROS_SETUP", "/opt/ros/melodic/setup.bash")),
        ws_setup=Path(get("WS_SETUP", str(home / "ros_ws" / "devel" / "setup.bash"))),
        libgl_software=get("LIBGL_ALWAYS_SOFTWARE", "1"),
        rviz_configs=rviz_configs,
    )


def bash_ros_prefix(cfg):
    ros_ip_export = shlex.quote(cfg.ros_ip) if cfg.ros_ip else "$ROS_IP"
    return (
        "set +u; source %s; source %s; set -u; "
        "export ROBOT_IP=%s; "
        "export ROS_MASTER_URI=%s; "
        "export ROS_IP=%s; "
        "export LIBGL_ALWAYS_SOFTWARE=%s; "
        % (
            shlex.quote(str(cfg.ros_setup)),
            shlex.quote(str(cfg.ws_setup)),
            shlex.quote(cfg.robot_ip),
            shlex.quote(cfg.ros_master_uri),
            ros_ip_export,
            shlex.quote(cfg.libgl_software),
        )
    )


def summarize_prereqs(cfg):
    lines = [
        "真机 ROS 服务: 在小车手动执行 pc_stack camera-start / full-start",
        "ROS Master: %s" % cfg.ros_master_uri,
        "ROS IP (本机 VM): %s" % (cfg.ros_ip or "(未检测到)"),
        "ROS setup: %s (%s)" % (cfg.ros_setup, "存在" if cfg.ros_setup_exists else "缺失"),
        "WS setup: %s (%s)" % (cfg.ws_setup, "存在" if cfg.ws_setup_exists else "缺失"),
    ]
    for label, path in cfg.rviz_configs.items():
        lines.append(
            "RViz [%s]: %s (%s)" % (label, path, "存在" if path.is_file() else "缺失")
        )
    return lines
