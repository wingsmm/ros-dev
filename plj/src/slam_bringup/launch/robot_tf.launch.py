from pathlib import Path

import yaml
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def _load_defaults():
    config = Path(get_package_share_directory("slam_bringup")) / "config" / "robot_tf.yaml"
    data = yaml.safe_load(config.read_text(encoding="utf-8")) or {}
    return data.get("robot_tf", {})


def generate_launch_description():
    defaults = _load_defaults()
    lidar_x = LaunchConfiguration("lidar_x")
    lidar_y = LaunchConfiguration("lidar_y")
    lidar_z = LaunchConfiguration("lidar_z")
    lidar_roll = LaunchConfiguration("lidar_roll")
    lidar_pitch = LaunchConfiguration("lidar_pitch")
    lidar_yaw = LaunchConfiguration("lidar_yaw")
    imu_x = LaunchConfiguration("imu_x")
    imu_y = LaunchConfiguration("imu_y")
    imu_z = LaunchConfiguration("imu_z")
    imu_roll = LaunchConfiguration("imu_roll")
    imu_pitch = LaunchConfiguration("imu_pitch")
    imu_yaw = LaunchConfiguration("imu_yaw")
    base_frame = LaunchConfiguration("base_frame")
    lidar_frame = LaunchConfiguration("lidar_frame")
    imu_frame = LaunchConfiguration("imu_frame")

    return LaunchDescription(
        [
            DeclareLaunchArgument("lidar_x", default_value=defaults.get("lidar_x", "0.15")),
            DeclareLaunchArgument("lidar_y", default_value=defaults.get("lidar_y", "0.0")),
            DeclareLaunchArgument("lidar_z", default_value=defaults.get("lidar_z", "0.25")),
            DeclareLaunchArgument("lidar_roll", default_value=defaults.get("lidar_roll", "0.0")),
            DeclareLaunchArgument(
                "lidar_pitch",
                default_value=defaults.get("lidar_pitch", "-0.26"),
            ),
            DeclareLaunchArgument("lidar_yaw", default_value=defaults.get("lidar_yaw", "0.0")),
            DeclareLaunchArgument("imu_x", default_value=defaults.get("imu_x", "0.0077")),
            DeclareLaunchArgument("imu_y", default_value=defaults.get("imu_y", "0.0147")),
            DeclareLaunchArgument("imu_z", default_value=defaults.get("imu_z", "-0.0067")),
            DeclareLaunchArgument("imu_roll", default_value=defaults.get("imu_roll", "0.0")),
            DeclareLaunchArgument("imu_pitch", default_value=defaults.get("imu_pitch", "0.0")),
            DeclareLaunchArgument("imu_yaw", default_value=defaults.get("imu_yaw", "0.0")),
            DeclareLaunchArgument(
                "base_frame",
                default_value=defaults.get("base_frame", "base_link"),
            ),
            DeclareLaunchArgument(
                "lidar_frame",
                default_value=defaults.get("lidar_frame", "unilidar_lidar"),
            ),
            DeclareLaunchArgument(
                "imu_frame",
                default_value=defaults.get("imu_frame", "unilidar_imu"),
            ),
            Node(
                package="tf2_ros",
                executable="static_transform_publisher",
                arguments=[
                    "--x",
                    lidar_x,
                    "--y",
                    lidar_y,
                    "--z",
                    lidar_z,
                    "--roll",
                    lidar_roll,
                    "--pitch",
                    lidar_pitch,
                    "--yaw",
                    lidar_yaw,
                    "--frame-id",
                    base_frame,
                    "--child-frame-id",
                    lidar_frame,
                ],
                output="screen",
            ),
            Node(
                package="tf2_ros",
                executable="static_transform_publisher",
                arguments=[
                    "--x",
                    imu_x,
                    "--y",
                    imu_y,
                    "--z",
                    imu_z,
                    "--roll",
                    imu_roll,
                    "--pitch",
                    imu_pitch,
                    "--yaw",
                    imu_yaw,
                    "--frame-id",
                    lidar_frame,
                    "--child-frame-id",
                    imu_frame,
                ],
                output="screen",
            ),
        ]
    )
