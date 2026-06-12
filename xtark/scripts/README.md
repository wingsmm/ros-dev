# xtark Script Entrypoints

This directory contains orchestration, deployment, and diagnostics scripts for the robot-side xtark stack.

It should not contain long-running ROS nodes. Runtime nodes belong in ROS packages such as `../xtark_nav/` or `../xtark_json_bridge/`.

## Robot-Side Shell Scripts

These scripts are copied to the robot under:

```text
/home/xtark/ros_ws/scripts/
```

| Script | Responsibility |
|--------|----------------|
| `android_stack.sh` | Starts the Android validation ROS stack: roscore, bringup, camera, gmapping, move_base, `/robot_pose_in_map`, and speed sync. |
| `json_stack.sh` | Starts the PC/Qt JSON bridge validation stack: bringup plus `xtark_json_bridge`. |

## Windows-Side Remote Helpers

These scripts are run from the repository root on Windows:

| Script | Responsibility |
|--------|----------------|
| `start_android.bat` | Syncs `android_stack.sh` and `xtark_nav` to `192.168.1.169`, then runs `android_stack.sh`. |
| `status_android.bat` | Reads Android validation ROS status and logs from `192.168.1.169`. |

## Placement Rule

- Add remote startup/status/log collection here.
- Add robot runtime ROS code to a ROS package under `../`.
- Add Android APK build/install scripts under `../../android/scripts/`.
- Add PC/Qt client scripts under `../../pc/`.

## Line Endings

`.gitattributes` keeps `*.sh` files in this directory as LF. Do not add generator scripts just to repair shell line endings.
