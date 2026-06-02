from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    config = Path(get_package_share_directory("slam_frontend")) / "config" / "simple_lidar_frontend.yaml"

    return LaunchDescription(
        [
            Node(
                package="slam_frontend",
                executable="simple_lidar_frontend",
                name="simple_lidar_frontend",
                output="screen",
                parameters=[str(config)],
            )
        ]
    )
