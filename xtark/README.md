# xtark Workspace Layout

This directory keeps robot-side ROS packages separate from deployment helpers.

## Runtime ROS Packages

| Path | Responsibility |
|------|----------------|
| `xtark_nav/` | SLAM, navigation, costmap configuration, and map-overlay ROS nodes. |
| `xtark_json_bridge/` | JSON bridge used by PC/Qt tools to command or inspect the robot. |

Runtime nodes should live inside a ROS package, not in `xtark/scripts/`.

## Robot Deployment Helpers

| Path | Responsibility |
|------|----------------|
| `scripts/android_stack.sh` | Starts the Android validation stack on the robot: roscore, bringup, camera, gmapping, move_base, pose relay, and speed sync. |
| `scripts/start_android.bat` | Syncs the Android validation robot-side stack to 192.168.1.169 and runs `android_stack.sh`. |
| `scripts/status_android.bat` | Reads Android validation ROS status and logs from 192.168.1.169. |
| `scripts/json_stack.sh` | Starts the PC/Qt JSON bridge validation stack on the robot. |

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
