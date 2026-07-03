"""ROS / path environment for VMware Qt client (runs on VM, ROS1 Melodic)."""

import os
import shlex
import subprocess
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = APP_DIR / "config"
DEFAULT_ENV_FILE = APP_DIR / ".env"

DEPTH_PREVIEW_TOPIC = "/camera/depth/preview"
VMWARE_DEPTH_POINTS_TOPIC = "/vmware/depth/points"
CAMERA_POINTCLOUD_STRIDE_DEFAULT = 12
CAMERA_POINTCLOUD_MIN_RANGE_M_DEFAULT = 0.25
CAMERA_POINTCLOUD_MAX_RANGE_M_DEFAULT = 3.0
CMD_VEL_TOPIC_DEFAULT = "/cmd_vel"
ROBOT_BASE_FRAME_DEFAULT = "base_link"
CAMERA_FRAME_DEFAULT = "camera_link"
CAMERA_OPTICAL_FRAME_DEFAULT = "camera_depth_optical_frame"


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
        cmd_vel_topic,
        teleop_linear_speed,
        teleop_angular_speed,
        teleop_repeat_hz,
        teleop_enable_keyboard,
        robot_base_frame,
        camera_frame,
        camera_optical_frame,
        camera_x,
        camera_y,
        camera_z,
        camera_roll,
        camera_pitch,
        camera_yaw,
        camera_tf_enable,
        camera_pointcloud_stride,
        camera_pointcloud_min_range_m,
        camera_pointcloud_max_range_m,
    ):
        self.app_dir = app_dir
        self.robot_ip = robot_ip
        self.ros_master_uri = ros_master_uri
        self.ros_ip = ros_ip
        self.ros_setup = ros_setup
        self.ws_setup = ws_setup
        self.libgl_software = libgl_software
        self.rviz_configs = rviz_configs
        self.cmd_vel_topic = cmd_vel_topic
        self.teleop_linear_speed = teleop_linear_speed
        self.teleop_angular_speed = teleop_angular_speed
        self.teleop_repeat_hz = teleop_repeat_hz
        self.teleop_enable_keyboard = teleop_enable_keyboard
        self.robot_base_frame = robot_base_frame
        self.camera_frame = camera_frame
        self.camera_optical_frame = camera_optical_frame
        self.camera_x = camera_x
        self.camera_y = camera_y
        self.camera_z = camera_z
        self.camera_roll = camera_roll
        self.camera_pitch = camera_pitch
        self.camera_yaw = camera_yaw
        self.camera_tf_enable = camera_tf_enable
        self.camera_pointcloud_stride = camera_pointcloud_stride
        self.camera_pointcloud_min_range_m = camera_pointcloud_min_range_m
        self.camera_pointcloud_max_range_m = camera_pointcloud_max_range_m

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
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if "#" in val:
            val = val.split("#", 1)[0].strip()
        if key:
            values[key] = val
    return values


def _get_env(file_env, key, default=""):
    return os.environ.get(key, file_env.get(key, default))


def _get_env_first(file_env, keys, default=""):
    for key in keys:
        val = _get_env(file_env, key, "")
        if val != "":
            return val
    return default


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

    return "", "未能自动检测 ROS_IP，请在 vmware/qt/.env 中设置 ROS_IP"


def _parse_float(raw, default):
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def _parse_int(raw, default):
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def load_config(env_file=None):
    env_path = env_file or DEFAULT_ENV_FILE
    file_env = _load_dotenv(env_path)

    def get(key, default=""):
        return _get_env(file_env, key, default)

    robot_ip = _get_env_first(file_env, ("XTARK_HOST", "ROBOT_IP"), "192.168.1.169")
    ros_master_uri = get("ROS_MASTER_URI", "http://%s:11311" % robot_ip)
    ros_ip_override = get("ROS_IP", "")
    pc_net_if = get("PC_NET_IF", "")
    ros_ip, _ = detect_ros_ip(robot_ip, ros_ip_override, pc_net_if)
    if ros_ip_override:
        ros_ip = ros_ip_override

    rviz_sw_gl = get("XTARK_RVIZ_SOFTWARE_GL", "")
    if rviz_sw_gl:
        libgl_software = "1" if rviz_sw_gl in ("1", "true", "yes") else "0"
    else:
        libgl_software = get("LIBGL_ALWAYS_SOFTWARE", "1")

    home = Path.home()
    rviz_configs = {
        "雷达/里程计": CONFIG_DIR / "rviz_mapping.rviz",
        "深度轻量": CONFIG_DIR / "rviz_depth_light.rviz",
        "RGB+Depth 诊断": CONFIG_DIR / "rviz_rgb_depth_diag.rviz",
        "深度增强": CONFIG_DIR / "rviz_depth_enhanced.rviz",
    }

    return ClientConfig(
        app_dir=APP_DIR,
        robot_ip=robot_ip,
        ros_master_uri=ros_master_uri,
        ros_ip=ros_ip,
        ros_setup=Path(get("ROS_SETUP", "/opt/ros/melodic/setup.bash")),
        ws_setup=Path(get("WS_SETUP", str(home / "ros_ws" / "devel" / "setup.bash"))),
        libgl_software=libgl_software,
        rviz_configs=rviz_configs,
        cmd_vel_topic=get("CMD_VEL_TOPIC", CMD_VEL_TOPIC_DEFAULT),
        teleop_linear_speed=_parse_float(
            _get_env_first(
                file_env, ("XTARK_LINEAR_SPEED", "TELEOP_LINEAR_SPEED"), "0.12"
            ),
            0.12,
        ),
        teleop_angular_speed=_parse_float(
            _get_env_first(
                file_env, ("XTARK_ANGULAR_SPEED", "TELEOP_ANGULAR_SPEED"), "0.50"
            ),
            0.50,
        ),
        teleop_repeat_hz=_parse_int(get("TELEOP_REPEAT_HZ", "10"), 10),
        teleop_enable_keyboard=get("TELEOP_ENABLE_KEYBOARD", "0") in ("1", "true", "yes"),
        robot_base_frame=get("ROBOT_BASE_FRAME", ROBOT_BASE_FRAME_DEFAULT),
        camera_frame=get("CAMERA_FRAME", CAMERA_FRAME_DEFAULT),
        camera_optical_frame=get("CAMERA_OPTICAL_FRAME", CAMERA_OPTICAL_FRAME_DEFAULT),
        camera_x=_parse_float(get("CAMERA_X", "0.10"), 0.10),
        camera_y=_parse_float(get("CAMERA_Y", "0.0"), 0.0),
        camera_z=_parse_float(get("CAMERA_Z", "0.20"), 0.20),
        camera_roll=_parse_float(get("CAMERA_ROLL", "0.0"), 0.0),
        camera_pitch=_parse_float(get("CAMERA_PITCH", "-0.01"), -0.01),
        camera_yaw=_parse_float(get("CAMERA_YAW", "0.0"), 0.0),
        camera_tf_enable=get("CAMERA_TF_ENABLE", "1") in ("1", "true", "yes"),
        camera_pointcloud_stride=_parse_int(
            _get_env_first(
                file_env,
                ("CAMERA_POINTCLOUD_STRIDE", "DEPTH_POINTCLOUD_STRIDE"),
                str(CAMERA_POINTCLOUD_STRIDE_DEFAULT),
            ),
            CAMERA_POINTCLOUD_STRIDE_DEFAULT,
        ),
        camera_pointcloud_min_range_m=_parse_float(
            _get_env_first(
                file_env,
                ("CAMERA_POINTCLOUD_MIN_RANGE_M", "DEPTH_POINTCLOUD_MIN_M"),
                str(CAMERA_POINTCLOUD_MIN_RANGE_M_DEFAULT),
            ),
            CAMERA_POINTCLOUD_MIN_RANGE_M_DEFAULT,
        ),
        camera_pointcloud_max_range_m=_parse_float(
            _get_env_first(
                file_env,
                ("CAMERA_POINTCLOUD_MAX_RANGE_M", "DEPTH_POINTCLOUD_MAX_M"),
                str(CAMERA_POINTCLOUD_MAX_RANGE_M_DEFAULT),
            ),
            CAMERA_POINTCLOUD_MAX_RANGE_M_DEFAULT,
        ),
    )


def bash_ros_prefix(cfg):
    ros_ip_export = shlex.quote(cfg.ros_ip) if cfg.ros_ip else "$ROS_IP"
    return (
        "set +u; source %s; source %s; set -u; "
        "export XTARK_HOST=%s; "
        "export ROBOT_IP=%s; "
        "export ROS_MASTER_URI=%s; "
        "export ROS_IP=%s; "
        "export LIBGL_ALWAYS_SOFTWARE=%s; "
        % (
            shlex.quote(str(cfg.ros_setup)),
            shlex.quote(str(cfg.ws_setup)),
            shlex.quote(cfg.robot_ip),
            shlex.quote(cfg.robot_ip),
            shlex.quote(cfg.ros_master_uri),
            ros_ip_export,
            shlex.quote(cfg.libgl_software),
        )
    )


def summarize_prereqs(cfg):
    lines = [
        "真机 ROS 服务: 在小车手动执行 pc_stack camera-start / camera-deep-start / full-start",
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
