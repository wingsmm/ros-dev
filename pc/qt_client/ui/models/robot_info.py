from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional

@dataclass
class RobotInfo:
    id: str
    name: str
    master_uri: str
    joystick_topic: str = "/joy_teleop/cmd_vel"
    camera_topic: str = "/image_raw/compressed"
    laser_topic: str = "/scan"
    navsat_topic: str = "/navsat/fix"
    odometry_topic: str = "/odometry/filtered"
    pose_topic: str = "/pose"
    map_topic: str = "/map"
    slam_xmin: float = -2.0
    slam_xmax: float = 2.0
    slam_ymin: float = -2.0
    slam_ymax: float = 2.0
    warning_enabled: bool = False
    warning_safemode: bool = True
    warning_beep: bool = True
    warning_min_distance: float = 3.0
    warning_front_half_angle: float = 40.0
    warning_min_valid_range: float = 0.25
    laser_scan_detail: int = 1
    random_walk_range_proximity: float = 2.0
    reverse_laser_scan: bool = False
    invert_x: bool = False
    invert_y: bool = False
    invert_angular_velocity: bool = False
    backend_type: str = "mock"
    gateway_uri: str = ""  # json_gateway: host:port, usually xtark :8765
    camera_mode: str = "mjpeg"
    camera_url: str = ""
    ros_domain_id: int = 0
    manual_linear_speed: Optional[float] = None
    manual_angular_speed: Optional[float] = None

    @staticmethod
    def new_id() -> str:
        return str(uuid.uuid4())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> RobotInfo:
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        filtered = {k: v for k, v in data.items() if k in known}
        if "id" not in filtered or not filtered["id"]:
            filtered["id"] = cls.new_id()
        return cls(**filtered)


def default_robot() -> RobotInfo:
    return RobotInfo(
        id="xtark-default",
        name="xtark",
        master_uri="http://192.168.1.169:11311",
    )
