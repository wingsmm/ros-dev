import re
from pathlib import Path

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
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


def _load_extrinsics(path: Path) -> dict[str, str] | None:
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8", errors="replace")
    xyz = _parse_simple_yaml_list(text, "xyz")
    base = _parse_simple_yaml_list(text, "base_rpy_rad")
    trim = _parse_simple_yaml_list(text, "trim_rpy_rad") or [0.0, 0.0, 0.0]
    parent = _parse_simple_yaml_scalar(text, "parent") or "base_link"
    child = _parse_simple_yaml_scalar(text, "child") or "unilidar_lidar"
    if xyz is None or base is None:
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
    }


def generate_launch_description():
    # IMPORTANT:
    #   static_transform_publisher expects roll/pitch/yaw in radians.
    #   Do NOT pass degrees here.
    args = [
        # If you pass x/y/z/roll/pitch/yaw on CLI, it overrides YAML.
        # Otherwise YAML is used as default source of truth.
        DeclareLaunchArgument("x", default_value="__from_yaml__"),
        DeclareLaunchArgument("y", default_value="__from_yaml__"),
        DeclareLaunchArgument("z", default_value="__from_yaml__"),
        # Default extrinsics for current vehicle mount (卧放) — radians.
        # Verified mapping:
        #   unilidar_lidar +Z -> base_link +X (车头)
        #   unilidar_lidar +X -> base_link +Z (朝天)
        #   unilidar_lidar +Y -> base_link -Y (车右)
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

    def _make_tf_node(context, *_, **__):
        cfg_path = LaunchConfiguration("extrinsics_yaml").perform(context)
        overrides = _load_extrinsics(Path(cfg_path)) or {
            "parent": "base_link",
            "child": "unilidar_lidar",
            "x": "0.0",
            "y": "0.0",
            "z": "0.0",
            "roll": "0.0",
            "pitch": "0.0",
            "yaw": "0.0",
        }

        def pick(name: str) -> str:
            raw = LaunchConfiguration(name).perform(context).strip()
            return overrides[name] if raw == "__from_yaml__" else raw

        x = pick("x")
        y = pick("y")
        z = pick("z")
        roll = pick("roll")
        pitch = pick("pitch")
        yaw = pick("yaw")
        parent = pick("parent")
        child = pick("child")

        tf = Node(
            package="tf2_ros",
            executable="static_transform_publisher",
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
        return [tf]

    return LaunchDescription(args + [OpaqueFunction(function=_make_tf_node)])

