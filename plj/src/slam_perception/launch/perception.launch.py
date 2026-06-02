from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    share_dir = Path(get_package_share_directory("slam_perception"))
    stair_config = share_dir / "config" / "stair_detector.yaml"
    climb_config = share_dir / "config" / "climb_supervisor.yaml"

    return LaunchDescription(
        [
            Node(
                package="slam_perception",
                executable="stair_detector",
                name="stair_detector",
                output="screen",
                parameters=[str(stair_config)],
            ),
            Node(
                package="slam_perception",
                executable="climb_supervisor",
                name="climb_supervisor",
                output="screen",
                parameters=[str(climb_config)],
            ),
        ]
    )
