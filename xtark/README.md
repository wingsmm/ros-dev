# xtark Workspace Layout

This directory keeps robot-side ROS packages separate from deployment helpers.

## Runtime ROS Packages

| Path | Responsibility |
|------|----------------|
| `xtark_nav/` | SLAM, navigation, costmap configuration, and map-overlay ROS nodes. |
| `xtark_json_bridge/` | JSON bridge used by PC/Qt tools to command or inspect the robot. |
| `xtark_depth_preview/` | Phase 1.5: depth 16UC1 → pseudo-color `/camera/depth/preview` for MJPEG. |
| `xtark_laser_odometry/` | RF2O laser odometry (`/odom_laser`) for Qt compare page. |

Runtime nodes should live inside a ROS package, not in `xtark/scripts/`.

## Robot Deployment Helpers

| Path | Responsibility |
|------|----------------|
| `scripts/android_stack.sh` | Starts the Android validation stack on the robot: roscore, bringup, camera, gmapping, move_base, pose relay, and speed sync. |
| `scripts/android_remote.bat` | Windows helper: deploy / start / stop / status / logs for the Android validation stack. |
| `scripts/deploy_json_bridge.bat` | Windows helper: sync and restart the JSON bridge package. |
| `scripts/deploy_laser_odom_compare.bat` | Windows helper: sync and run the laser odometry compare stack. |
| `scripts/json_stack.sh` | Starts the PC/Qt JSON bridge validation stack on the robot. |
| `tools/analyze_laser_odom_bag.py` | Offline rosbag analysis for laser odometry experiments. |

`xtark/scripts/` is for orchestration, deployment, and diagnostics only. It should not contain long-running ROS nodes.
See `scripts/README.md` for the script entrypoint split.

## Client-Side Code

Client applications live outside this directory:

| Path | Responsibility |
|------|----------------|
| `../android/` | Android App source, Gradle build files, and Windows deployment scripts. |
| `../pc/` | PC/Qt client, ROS2 bridge helpers, and PC-side docs. |
| `../rk3568/` | RK3568 deployment assets and sensor stack helpers. |

## Placement Rule

- Robot capability or ROS topic provider: put it in a ROS package under `xtark/`.
- Remote startup, sync, status, or log collection: put it in `xtark/scripts/` or a client-specific `scripts/` directory.
- Android-only UI behavior: keep it under `android/`.
- PC/Qt behavior: keep it under `pc/`.
