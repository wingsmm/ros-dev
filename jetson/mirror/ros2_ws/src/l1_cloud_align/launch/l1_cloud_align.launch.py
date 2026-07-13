"""Launch L1 point-cloud alignment node with YAML-based extrinsics."""

import re
from pathlib import Path

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def _parse_list(text: str, key: str) -> list[float] | None:
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


def _parse_scalar(text: str, key: str) -> str | None:
    m = re.search(r"^\s*%s\s*:\s*([A-Za-z0-9_/-]+)\s*$" % re.escape(key), text, re.M)
    return m.group(1).strip() if m else None


def _load_config(path: Path) -> dict:
    """Strict YAML load: required fields must be valid or launch aborts.

    Fail-closed matches cockpit's ExtrinsicsDialog / cloud_align_control
    behaviour — we never silently fall back to zeros for `base_rpy_rad` or
    `trim_rpy_rad`, because that would overwrite the confirmed mount
    baseline the moment someone hits Apply.
    """
    if not path.is_file():
        raise RuntimeError(
            "l1_cloud_align.yaml not found: %s" % path
        )
    text = path.read_text(encoding="utf-8", errors="replace")

    def _require_list(key: str) -> list[float]:
        vals = _parse_list(text, key)
        if vals is None:
            raise RuntimeError(
                "l1_cloud_align.yaml missing or malformed %s (expect 3 floats): %s"
                % (key, path)
            )
        return vals

    def _optional_scalar(key: str, default: str) -> str:
        return _parse_scalar(text, key) or default

    return {
        "input_topic": _optional_scalar("input_topic", "/unilidar/cloud"),
        "output_topic": _optional_scalar("output_topic", "/unilidar/cloud_aligned"),
        "target_frame": _optional_scalar("target_frame", "base_link"),
        "xyz": _require_list("xyz"),
        "base_rpy_rad": _require_list("base_rpy_rad"),
        "trim_rpy_rad": _require_list("trim_rpy_rad"),
    }


def generate_launch_description():
    args = [
        DeclareLaunchArgument(
            "align_yaml",
            default_value=PathJoinSubstitution(
                [FindPackageShare("l1_cloud_align"), "config", "l1_cloud_align.yaml"]
            ),
        ),
    ]

    def _make_node(context, *_, **__):
        cfg_path = LaunchConfiguration("align_yaml").perform(context)
        cfg = _load_config(Path(cfg_path))
        node = Node(
            package="l1_cloud_align",
            executable="l1_cloud_align_node",
            name="l1_cloud_align_node",
            output="screen",
            parameters=[cfg],
        )
        return [node]

    return LaunchDescription(args + [OpaqueFunction(function=_make_node)])
