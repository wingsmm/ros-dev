from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    # IMPORTANT:
    #   static_transform_publisher expects roll/pitch/yaw in radians.
    #   Do NOT pass degrees here.
    args = [
        DeclareLaunchArgument("x", default_value="0.0"),
        DeclareLaunchArgument("y", default_value="0.0"),
        DeclareLaunchArgument("z", default_value="0.0"),
        DeclareLaunchArgument("roll", default_value="0.0"),
        DeclareLaunchArgument("pitch", default_value="0.0"),
        DeclareLaunchArgument("yaw", default_value="0.0"),
        DeclareLaunchArgument("parent", default_value="base_link"),
        DeclareLaunchArgument("child", default_value="unilidar_lidar"),
    ]

    tf = Node(
        package="tf2_ros",
        executable="static_transform_publisher",
        arguments=[
            "--x",
            LaunchConfiguration("x"),
            "--y",
            LaunchConfiguration("y"),
            "--z",
            LaunchConfiguration("z"),
            "--roll",
            LaunchConfiguration("roll"),
            "--pitch",
            LaunchConfiguration("pitch"),
            "--yaw",
            LaunchConfiguration("yaw"),
            "--frame-id",
            LaunchConfiguration("parent"),
            "--child-frame-id",
            LaunchConfiguration("child"),
        ],
        output="screen",
    )

    return LaunchDescription(args + [tf])

