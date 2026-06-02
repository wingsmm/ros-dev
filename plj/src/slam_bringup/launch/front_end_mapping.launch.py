from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    return LaunchDescription(
        [
            DeclareLaunchArgument("backend", default_value="simple_frontend"),
            DeclareLaunchArgument("launch_sensors", default_value="false"),
            DeclareLaunchArgument("sensor_source", default_value="unitree_l1"),
            DeclareLaunchArgument("lidar_port", default_value="/dev/unilidar_serial4"),
            DeclareLaunchArgument("map_path", default_value="/home/nvidia/maps/result.bag"),
            DeclareLaunchArgument("rviz", default_value="false"),
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(
                    PathJoinSubstitution(
                        [FindPackageShare("slam_bringup"), "launch", "robot_tf.launch.py"]
                    )
                ),
            ),
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(
                    PathJoinSubstitution([FindPackageShare("slam_bringup"), "launch", "sensors.launch.py"])
                ),
                condition=IfCondition(LaunchConfiguration("launch_sensors")),
                launch_arguments={
                    "sensor_source": LaunchConfiguration("sensor_source"),
                    "lidar_port": LaunchConfiguration("lidar_port"),
                }.items(),
            ),
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(
                    PathJoinSubstitution(
                        [FindPackageShare("slam_frontend"), "launch", "simple_frontend.launch.py"]
                    )
                ),
            ),
        ]
    )
