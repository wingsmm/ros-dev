# xtark_nav

ROS1 navigation support package for xtark Android validation.

This package owns the robot-side SLAM/navigation configuration and small map-overlay helper nodes used by external UIs.

## Contents

| Path | Responsibility |
|------|----------------|
| `launch/online_slam_move_base.launch` | Starts `move_base` for online SLAM validation. |
| `launch/robot_pose_in_map.launch` | Starts the map-frame robot pose relay. |
| `config/` | Costmap and `move_base` parameters. |
| `scripts/publish_robot_pose_in_map.py` | Publishes `map -> base_footprint` as `geometry_msgs/PoseStamped` on `/robot_pose_in_map`. |

## Pose Overlay Topic

Android/RobotCA subscribes:

```text
/robot_pose_in_map
```

The node is launched by `../scripts/android_stack.sh` through:

```bash
roslaunch xtark_nav robot_pose_in_map.launch
```

Configurable private parameters:

| Parameter | Default | Meaning |
|-----------|---------|---------|
| `~map_frame` | `map` | Map frame. |
| `~base_frame` | `base_footprint` | Robot base frame. |
| `~pose_topic` | `/robot_pose_in_map` | Published pose topic. |
| `~rate` | `10.0` | Publish rate in Hz. |
| `~transform_timeout` | `0.3` | TF lookup timeout in seconds. |

## Boundary

Keep SLAM, navigation, costmap, and map-overlay ROS nodes here. Keep deployment and remote orchestration scripts in `../scripts/`.
