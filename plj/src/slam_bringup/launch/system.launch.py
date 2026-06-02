from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, OpaqueFunction
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.substitutions import FindPackageShare


def _include_selected_mode(context):
    mode = LaunchConfiguration("mode").perform(context)
    if mode == "frontend":
        launch_file = "front_end_mapping.launch.py"
    elif mode == "localization":
        launch_file = "localization.launch.py"
    else:
        launch_file = "mapping.launch.py"

    return [
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                PathJoinSubstitution([FindPackageShare("slam_bringup"), "launch", launch_file])
            ),
            launch_arguments={
                "backend": LaunchConfiguration("backend"),
                "launch_sensors": LaunchConfiguration("launch_sensors"),
                "sensor_source": LaunchConfiguration("sensor_source"),
                "lidar_port": LaunchConfiguration("lidar_port"),
                "map_path": LaunchConfiguration("map_path"),
                "rviz": LaunchConfiguration("rviz"),
            }.items(),
        )
    ]


def generate_launch_description():
    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "mode",
                default_value="frontend",
                description="One of: frontend, mapping, localization.",
            ),
            DeclareLaunchArgument(
                "backend",
                default_value="vendor_point_lio",
                description="Backend for mapping/localization: vendor_point_lio or simple_frontend.",
            ),
            DeclareLaunchArgument("launch_sensors", default_value="false"),
            DeclareLaunchArgument("sensor_source", default_value="unitree_l1"),
            DeclareLaunchArgument("lidar_port", default_value="/dev/unilidar_serial4"),
            DeclareLaunchArgument("map_path", default_value="/home/nvidia/maps/result.bag"),
            DeclareLaunchArgument("rviz", default_value="false"),
            OpaqueFunction(function=_include_selected_mode),
        ]
    )
