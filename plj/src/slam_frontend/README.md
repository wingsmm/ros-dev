# slam_frontend

Self-contained frontend package for this project.

## `simple_lidar_frontend`

Subscribes to a point cloud topic and estimates short-term planar odometry with a lightweight numpy ICP loop.

Inputs:

- `/unilidar/cloud` (`sensor_msgs/PointCloud2`)

Outputs:

- `/frontend/odom` (`nav_msgs/Odometry`)
- `/frontend/path` (`nav_msgs/Path`)
- `/frontend/local_map` (`sensor_msgs/PointCloud2`)
- TF: `odom -> base_link`

This package intentionally does not depend on `point_lio`, FAST-LIO, or any remote `ros2_ws` package. It is meant for project-owned frontend validation, TF wiring, perception integration, and rosbag/hardware smoke tests.

It is not yet a production replacement for tightly-coupled LiDAR-IMU odometry. Long-term mapping and relocalization still need project-owned backend work.

## Run

```bash
ros2 launch slam_frontend simple_frontend.launch.py
```

Or through bringup:

```bash
ros2 launch slam_bringup system.launch.py mode:=frontend
```
