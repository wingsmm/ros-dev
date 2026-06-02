from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    cloud_topic = LaunchConfiguration("cloud_topic")
    scan_topic = LaunchConfiguration("scan_topic")
    target_frame = LaunchConfiguration("target_frame")

    return LaunchDescription(
        [
            DeclareLaunchArgument("cloud_topic", default_value="/unilidar/cloud"),
            DeclareLaunchArgument("scan_topic", default_value="/scan"),
            DeclareLaunchArgument("target_frame", default_value="base_link"),
            Node(
                package="pointcloud_to_laserscan",
                executable="pointcloud_to_laserscan_node",
                name="pointcloud_to_laserscan",
                output="screen",
                remappings=[
                    ("cloud_in", cloud_topic),
                    ("scan", scan_topic),
                ],
                parameters=[
                    {
                        "target_frame": target_frame,
                        "transform_tolerance": 0.05,
                        "min_height": -0.05,
                        "max_height": 0.35,
                        "angle_min": -1.5708,
                        "angle_max": 1.5708,
                        "angle_increment": 0.0087,
                        "scan_time": 0.1,
                        "range_min": 0.25,
                        "range_max": 6.0,
                        "use_inf": True,
                    }
                ],
            ),
        ]
    )
