from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    config_file = LaunchConfiguration("config_file")
    port = LaunchConfiguration("port")
    cloud_topic = LaunchConfiguration("cloud_topic")
    imu_topic = LaunchConfiguration("imu_topic")

    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "config_file",
                default_value=PathJoinSubstitution(
                    [FindPackageShare("slam_bringup"), "config", "l1_driver.yaml"]
                ),
            ),
            DeclareLaunchArgument("port", default_value="/dev/unilidar_serial4"),
            DeclareLaunchArgument("cloud_topic", default_value="unilidar/cloud"),
            DeclareLaunchArgument("imu_topic", default_value="unilidar/imu"),
            Node(
                package="unitree_lidar_ros2",
                executable="unitree_lidar_ros2_node",
                name="unitree_lidar_ros2_node",
                output="screen",
                parameters=[
                    config_file,
                    {
                        "port": port,
                        "cloud_topic": cloud_topic,
                        "imu_topic": imu_topic,
                    },
                ],
            ),
        ]
    )
