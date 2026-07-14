from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    node = Node(
        package="lio_odom_adapter",
        executable="lio_odom_adapter_node",
        name="lio_odom_adapter",
        output="screen",
        parameters=[
            {
                "input_odom_topic": "/aft_mapped_to_init",
                "output_odom_topic": "/odom",
                "output_path_topic": "/odom_path",
                "odom_frame": "odom",
                "base_frame": "base_link",
                "imu_frame": "unilidar_imu",
                "camera_init_frame": "camera_init",
                # About two minutes at the L1's ~9 Hz rate. This keeps RViz/DDS
                # responsive while retaining enough history for field validation.
                "max_path_length": 1000,
            }
        ],
    )
    return LaunchDescription([node])
