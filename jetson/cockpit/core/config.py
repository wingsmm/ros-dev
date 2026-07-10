"""Local config for Jetson cockpit."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def app_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _parse_env_file(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    out: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        out[key.strip()] = value.strip().strip('"').strip("'")
    return out


def _value(env_file: dict[str, str], key: str, default: str) -> str:
    return os.environ.get(key, env_file.get(key, default)).strip()


def _float(env_file: dict[str, str], key: str, default: float) -> float:
    try:
        return float(_value(env_file, key, str(default)))
    except ValueError:
        return default


def _int(env_file: dict[str, str], key: str, default: int) -> int:
    try:
        return int(_value(env_file, key, str(default)))
    except ValueError:
        return default


def _bool(env_file: dict[str, str], key: str, default: bool) -> bool:
    raw = _value(env_file, key, "1" if default else "0").lower()
    return raw in {"1", "true", "yes", "on"}


def _path(env_file: dict[str, str], key: str, default: str) -> Path:
    raw = _value(env_file, key, default)
    path = Path(raw)
    if path.is_absolute():
        return path
    return app_root() / path


@dataclass(frozen=True)
class CockpitConfig:
    ros_domain_id: str
    cmd_vel_topic: str
    control_action_topic: str
    teleop_linear_speed: float
    teleop_angular_speed: float
    teleop_repeat_hz: int
    teleop_enable_keyboard: bool
    log_dir: Path
    log_level: str
    lidar_cloud_topic: str
    lidar_imu_topic: str
    lidar_fixed_frame: str
    rviz_config: Path
    lidar_base_rviz: Path
    lidar_mapping_rviz: Path
    lio_odom_topic: str
    lio_path_topic: str
    lio_cloud_registered_topic: str
    lio_fixed_frame: str


def load_config() -> CockpitConfig:
    env_file = _parse_env_file(app_root() / ".env")
    return CockpitConfig(
        ros_domain_id=_value(env_file, "ROS_DOMAIN_ID", "0"),
        cmd_vel_topic=_value(env_file, "CMD_VEL_TOPIC", "/cmd_vel"),
        control_action_topic=_value(
            env_file, "CONTROL_ACTION_TOPIC", "/vehicle/control_action"
        ),
        teleop_linear_speed=_float(env_file, "TELEOP_LINEAR_SPEED", 1.0),
        teleop_angular_speed=_float(env_file, "TELEOP_ANGULAR_SPEED", 1.0),
        teleop_repeat_hz=max(1, _int(env_file, "TELEOP_REPEAT_HZ", 10)),
        teleop_enable_keyboard=_bool(env_file, "TELEOP_ENABLE_KEYBOARD", True),
        log_dir=_path(env_file, "JETSON_COCKPIT_LOG_DIR", "logs"),
        log_level=_value(env_file, "JETSON_COCKPIT_LOG_LEVEL", "INFO").upper(),
        lidar_cloud_topic=_value(env_file, "LIDAR_CLOUD_TOPIC", "/unilidar/cloud"),
        lidar_imu_topic=_value(env_file, "LIDAR_IMU_TOPIC", "/unilidar/imu"),
        lidar_fixed_frame=_value(env_file, "LIDAR_FIXED_FRAME", "odom"),
        rviz_config=_path(env_file, "LIDAR_RVIZ_CONFIG", "config/unilidar.rviz"),
        lidar_base_rviz=_path(
            env_file, "LIDAR_BASE_RVIZ_CONFIG", "config/unilidar_base.rviz"
        ),
        lidar_mapping_rviz=_path(
            env_file, "LIDAR_MAPPING_RVIZ_CONFIG", "config/unilidar_mapping.rviz"
        ),
        lio_odom_topic=_value(env_file, "LIO_ODOM_TOPIC", "/odom"),
        lio_path_topic=_value(env_file, "LIO_PATH_TOPIC", "/odom_path"),
        lio_cloud_registered_topic=_value(
            env_file, "LIO_CLOUD_REGISTERED_TOPIC", "/cloud_registered"
        ),
        lio_fixed_frame=_value(env_file, "LIO_FIXED_FRAME", "odom"),
    )
