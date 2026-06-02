from launch import LaunchDescription
from launch_ros.actions import Node
from ament_index_python.packages import get_package_share_directory
from pathlib import Path


def generate_launch_description():
    config = Path(get_package_share_directory("slam_perception")) / "config" / "stair_detector.yaml"

    return LaunchDescription(
        [
            Node(
                package="slam_perception",
                executable="stair_detector",
                name="stair_detector",
                output="screen",
                parameters=[str(config)],
            )
        ]
    )
