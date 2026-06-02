# slam_perception

ROS 2 perception package for the L1 LiDAR SLAM system.

## Nodes

### `stair_detector`

Subscribes to the front LiDAR point cloud, searches a configurable front ROI for stair-like height discontinuities, and publishes a temporally filtered detection result.

Inputs:

- `/unilidar/cloud` (`sensor_msgs/PointCloud2`)

Outputs:

- `/stair_detected` (`std_msgs/Bool`)
- `/stair_info` (`std_msgs/Float32MultiArray`)
  - `[detected, height_m, distance_m, width_m, confidence]`
- `/front_roi_cloud` (`sensor_msgs/PointCloud2`)
- `/cmd_vel` (`geometry_msgs/Twist`), only when `enable_stop_command=true`
- `/climb_mode_trigger` (`std_msgs/String`), only when `enable_climb_trigger=true`

### `climb_supervisor`

Subscribes to stable stair detection and owns the climb-mode state machine:

```text
normal -> stopping -> waiting_chassis -> climbing -> recovering -> normal
```

Inputs:

- `/stair_detected` (`std_msgs/Bool`)
- `/stair_info` (`std_msgs/Float32MultiArray`)
- `/climb_ready` (`std_msgs/Bool`)
- `/climb_complete` (`std_msgs/Bool`)

Outputs:

- `/cmd_vel` zero command while stopping/recovering
- `/climb_mode_trigger` (`std_msgs/String`)
- `/normal_mode_trigger` (`std_msgs/String`)
- `/climb_state` (`std_msgs/String`)
- `/localization_reinit` (`std_msgs/String`)
- `/slam_backend_pause` (`std_msgs/Bool`)

## Build

独立工作区编译，**不要**与 `~/ros2_ws` 混放。远端路径待定。

```bash
cd other/src   # 或远端自研工作区根目录
source /opt/ros/humble/setup.bash
colcon build --symlink-install --packages-select slam_perception
source install/setup.bash
```

## Run

```bash
ros2 launch slam_perception stair_detector.launch.py
```

Or run perception plus the climb state machine:

```bash
ros2 launch slam_perception perception.launch.py
```

For first tests, keep these disabled in `config/stair_detector.yaml`:

```yaml
enable_stop_command: false
enable_climb_trigger: false
```

After the detection is stable in RViz/rosbag replay, enable them one at a time.

For first vehicle tests, keep `auto_trigger: false` in `config/climb_supervisor.yaml` until the chassis interface is confirmed.

## Tuning Notes

- Confirm TF first. The node transforms `/unilidar/cloud` into `target_frame` first; the default is `base_link`.
- Tune ROI before thresholds: `min_x`, `max_x`, `min_y`, `max_y`, `min_z`, `max_z`.
- Use `confirm_frames` and `clear_frames` to prevent one-frame false triggers.
- Treat `max_stair_height` as a chassis safety limit, not only a perception parameter.
