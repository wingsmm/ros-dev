from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    point_lio_config = LaunchConfiguration("point_lio_config")
    localization_config = LaunchConfiguration("localization_config")
    map_path = LaunchConfiguration("map_path")
    rviz = LaunchConfiguration("rviz")

    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "point_lio_config",
                default_value=PathJoinSubstitution(
                    [FindPackageShare("slam_bringup"), "config", "point_lio_unilidar_l1.yaml"]
                ),
            ),
            DeclareLaunchArgument(
                "localization_config",
                default_value=PathJoinSubstitution(
                    [FindPackageShare("slam_bringup"), "config", "localization_qn.yaml"]
                ),
            ),
            DeclareLaunchArgument("map_path", default_value="/home/nvidia/maps/result.bag"),
            DeclareLaunchArgument("rviz", default_value="false"),
            Node(
                package="point_lio",
                executable="pointlio_mapping",
                name="laserMapping",
                output="screen",
                parameters=[
                    point_lio_config,
                    {
                        "use_imu_as_input": False,
                        "prop_at_freq_of_imu": True,
                        "check_satu": True,
                        "init_map_size": 10,
                        "point_filter_num": 1,
                        "space_down_sample": True,
                        "filter_size_surf": 0.1,
                        "filter_size_map": 0.1,
                        "cube_side_length": 1000.0,
                        "runtime_pos_log_enable": False,
                    },
                ],
            ),
            Node(
                package="localization_qn",
                executable="localization_qn_node",
                name="localization_qn_node",
                output="screen",
                parameters=[
                    localization_config,
                    {
                        "basic.saved_map": map_path,
                    },
                ],
                remappings=[
                    ("/Odometry", "/aft_mapped_to_init"),
                    ("/cloud_registered", "/cloud_registered"),
                ],
            ),
            Node(
                package="slam_bringup",
                executable="backend_watchdog",
                name="slam_backend_watchdog",
                output="screen",
                parameters=[
                    {
                        "mode": "localization",
                        "odom_topic": "/aft_mapped_to_init",
                        "cloud_topic": "/cloud_registered",
                    }
                ],
            ),
            Node(
                package="rviz2",
                executable="rviz2",
                name="rviz_localization",
                arguments=[
                    "-d",
                    PathJoinSubstitution(
                        [FindPackageShare("point-lio-slam"), "rviz", "localization_rviz.rviz"]
                    ),
                ],
                condition=IfCondition(rviz),
                output="screen",
            ),
        ]
    )
