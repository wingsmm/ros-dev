from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, LogInfo, OpaqueFunction
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.substitutions import FindPackageShare


def _include_sensor(context):
    source = LaunchConfiguration("sensor_source").perform(context)
    if source == "unitree_l1":
        return [
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(
                    PathJoinSubstitution([FindPackageShare("slam_bringup"), "launch", "l1_driver.launch.py"])
                ),
                launch_arguments={
                    "port": LaunchConfiguration("lidar_port"),
                    "cloud_topic": LaunchConfiguration("cloud_topic"),
                    "imu_topic": LaunchConfiguration("imu_topic"),
                }.items(),
            )
        ]
    return [
        LogInfo(
            msg=(
                "No sensor driver launched. Provide /unilidar/cloud and /unilidar/imu "
                "from rosbag or an approved external bridge."
            )
        )
    ]


def generate_launch_description():
    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "sensor_source",
                default_value="unitree_l1",
                description="Sensor input source: unitree_l1 or none.",
            ),
            DeclareLaunchArgument("lidar_port", default_value="/dev/unilidar_serial4"),
            DeclareLaunchArgument("cloud_topic", default_value="unilidar/cloud"),
            DeclareLaunchArgument("imu_topic", default_value="unilidar/imu"),
            OpaqueFunction(function=_include_sensor),
        ]
    )
