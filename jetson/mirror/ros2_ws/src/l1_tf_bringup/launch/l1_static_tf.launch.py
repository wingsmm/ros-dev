import re
from pathlib import Path

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction, LogInfo, Shutdown
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare
from launch.substitutions import PathJoinSubstitution


def _parse_simple_yaml_list(text: str, key: str) -> list[float] | None:
    # Accept formats like:
    #   key: [1, 2, 3]
    #   key: [1.0, -2.0, 3.0]
    m = re.search(r"^\s*%s\s*:\s*\[([^\]]+)\]\s*$" % re.escape(key), text, re.M)
    if not m:
        return None
    parts = [p.strip() for p in m.group(1).split(",")]
    if len(parts) != 3:
        return None
    try:
        return [float(parts[0]), float(parts[1]), float(parts[2])]
    except ValueError:
        return None


def _parse_simple_yaml_scalar(text: str, key: str) -> str | None:
    m = re.search(r"^\s*%s\s*:\s*([A-Za-z0-9_/-]+)\s*$" % re.escape(key), text, re.M)
    return m.group(1).strip() if m else None


def _load_extrinsics(path: Path) -> dict | None:
    """Load extrinsics. Returns None on any required-field failure (fail-closed)."""
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8", errors="replace")
    xyz = _parse_simple_yaml_list(text, "xyz")
    base = _parse_simple_yaml_list(text, "base_rpy_rad")
    trim = _parse_simple_yaml_list(text, "trim_rpy_rad")
    imu_xyz = _parse_simple_yaml_list(text, "imu_xyz_in_lidar")
    imu_rpy = _parse_simple_yaml_list(text, "imu_rpy_in_lidar")
    parent = _parse_simple_yaml_scalar(text, "parent")
    child = _parse_simple_yaml_scalar(text, "child")
    if (
        xyz is None
        or base is None
        or trim is None
        or imu_xyz is None
        or imu_rpy is None
        or parent is None
        or child is None
    ):
        return None
    rpy = [base[i] + trim[i] for i in range(3)]
    return {
        "parent": parent,
        "child": child,
        "x": str(xyz[0]),
        "y": str(xyz[1]),
        "z": str(xyz[2]),
        "roll": str(rpy[0]),
        "pitch": str(rpy[1]),
        "yaw": str(rpy[2]),
        "imu_x": str(imu_xyz[0]),
        "imu_y": str(imu_xyz[1]),
        "imu_z": str(imu_xyz[2]),
        "imu_roll": str(imu_rpy[0]),
        "imu_pitch": str(imu_rpy[1]),
        "imu_yaw": str(imu_rpy[2]),
    }


def generate_launch_description():
    # IMPORTANT:
    #   static_transform_publisher expects roll/pitch/yaw in radians.
    #   Do NOT pass degrees here.
    args = [
        DeclareLaunchArgument("x", default_value="__from_yaml__"),
        DeclareLaunchArgument("y", default_value="__from_yaml__"),
        DeclareLaunchArgument("z", default_value="__from_yaml__"),
        DeclareLaunchArgument("roll", default_value="__from_yaml__"),
        DeclareLaunchArgument("pitch", default_value="__from_yaml__"),
        DeclareLaunchArgument("yaw", default_value="__from_yaml__"),
        DeclareLaunchArgument("parent", default_value="__from_yaml__"),
        DeclareLaunchArgument("child", default_value="__from_yaml__"),
        DeclareLaunchArgument(
            "extrinsics_yaml",
            default_value=PathJoinSubstitution(
                [FindPackageShare("l1_tf_bringup"), "config", "l1_extrinsics.yaml"]
            ),
        ),
    ]

    def _make_tf_nodes(context, *_, **__):
        cfg_path = LaunchConfiguration("extrinsics_yaml").perform(context)
        loaded = _load_extrinsics(Path(cfg_path))
        if loaded is None:
            return [
                LogInfo(
                    msg=(
                        "[l1_static_tf] FAIL-CLOSED: extrinsics YAML missing or "
                        "malformed (need xyz, base_rpy_rad, trim_rpy_rad, "
                        "imu_xyz_in_lidar, imu_rpy_in_lidar, parent, child): %s"
                        % cfg_path
                    )
                ),
                Shutdown(reason="l1_extrinsics.yaml invalid"),
            ]

        def pick(name: str) -> str:
            raw = LaunchConfiguration(name).perform(context).strip()
            return loaded[name] if raw == "__from_yaml__" else raw

        x = pick("x")
        y = pick("y")
        z = pick("z")
        roll = pick("roll")
        pitch = pick("pitch")
        yaw = pick("yaw")
        parent = pick("parent")
        child = pick("child")

        lidar_tf = Node(
            package="tf2_ros",
            executable="static_transform_publisher",
            name="l1_static_tf_lidar",
            arguments=[
                "--x",
                x,
                "--y",
                y,
                "--z",
                z,
                "--roll",
                roll,
                "--pitch",
                pitch,
                "--yaw",
                yaw,
                "--frame-id",
                parent,
                "--child-frame-id",
                child,
            ],
            output="screen",
        )

        imu_tf = Node(
            package="tf2_ros",
            executable="static_transform_publisher",
            name="l1_static_tf_imu",
            arguments=[
                "--x",
                loaded["imu_x"],
                "--y",
                loaded["imu_y"],
                "--z",
                loaded["imu_z"],
                "--roll",
                loaded["imu_roll"],
                "--pitch",
                loaded["imu_pitch"],
                "--yaw",
                loaded["imu_yaw"],
                "--frame-id",
                child,
                "--child-frame-id",
                "unilidar_imu",
            ],
            output="screen",
        )
        return [lidar_tf, imu_tf]

    return LaunchDescription(args + [OpaqueFunction(function=_make_tf_nodes)])
