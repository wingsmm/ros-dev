# slam_bringup

Launch package for the SLAM system described in `SLAM系统方案.md`.

## Main Entrypoints

Frontend-only validation:

```bash
ros2 launch slam_bringup system.launch.py mode:=frontend
```

This starts this repository's own `slam_frontend` package. It does not launch or depend on remote `point_lio`.

Mapping with loop closure backend:

```bash
ros2 launch slam_bringup system.launch.py mode:=mapping
```

Localization against a saved map:

```bash
ros2 launch slam_bringup system.launch.py mode:=localization
```

Mapping/localization launches currently use the project-owned `slam_frontend` plus perception stack. Full loop-closure mapping and relocalization backends are still project work items; do not wire external backends in by default.

## TF

Temporary TF defaults live in `config/robot_tf.yaml` and are loaded by `launch/robot_tf.launch.py`. Replace `lidar_x`, `lidar_z`, and `lidar_pitch` after measuring the real mount.

The launch publishes:

- `base_link -> unilidar_lidar`
- `unilidar_lidar -> unilidar_imu`

Do not confuse this with any sensor-internal IMU-to-LiDAR calibration.

## Obstacle Scan

For Nav2/costmap experiments:

```bash
ros2 launch slam_bringup obstacle_scan.launch.py
```
