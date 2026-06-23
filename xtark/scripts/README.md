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
| `robot_stack.sh` | Daily Qt / JSON stack: roscore, bringup, camera, and JSON adapter. |
| `android_stack.sh` | Android validation stack: roscore, bringup, camera, gmapping, move_base, `/robot_pose_in_map`, and speed sync. |
| `camera_stack.sh` | Starts only the shared camera path for Android ROS topic and Qt/browser MJPEG preview. |
| `json_stack.sh` | Starts the PC/Qt JSON bridge validation stack: bringup plus `xtark_json_bridge`. |
| `laser_odom_experiment.sh` | Sidecar only: starts `xtark_laser_odometry` -> `/odom_laser` for phase-1 experiments. It assumes another stack already provides roscore, bringup, and `/scan`. |
| `laser_odom_compare_stack.sh` | Independent laser odometry compare stack: starts its own roscore, bringup, JSON adapter, Qt camera preview, rf2o, and optional rosbag recording. Its `stop` only stops PIDs owned by this compare stack. |

## Daily Stack

Recommended daily command:

```bash
~/ros_ws/scripts/robot_stack.sh start
~/ros_ws/scripts/robot_stack.sh status
~/ros_ws/scripts/robot_stack.sh stop
```

Use `camera_stack.sh` only when you want to observe camera without starting the base.

## Laser Odometry Sidecar Experiment

Use this when daily bringup / `/scan` is already running and you only want to add `/odom_laser` in parallel:

```bash
~/ros_ws/scripts/laser_odom_experiment.sh start
~/ros_ws/scripts/laser_odom_experiment.sh record
~/ros_ws/scripts/laser_odom_experiment.sh stop
```

`laser_odom_experiment.sh` must not stop or modify `robot_stack.sh`, `android_stack.sh`, gmapping, or move_base.

## Laser Odometry Compare Stack

Use this for an isolated Qt manual-drive odometry comparison with rosbag:

```bash
~/ros_ws/scripts/laser_odom_compare_stack.sh start
~/ros_ws/scripts/laser_odom_compare_stack.sh record
# Qt connect 192.168.1.169:8765, drive slowly.
# Qt camera preview: http://192.168.1.169:8080/stream?topic=/camera/image_raw
~/ros_ws/scripts/laser_odom_compare_stack.sh stop
```

Cold boot rule:

- Booting the Nano does not start `robot_stack`, `android_stack`, or `laser_odom_compare_stack` automatically.
- If no stack was started manually after boot, do not run extra `robot_stack.sh stop` / `android_stack.sh stop` before the laser compare test.
- `laser_odom_compare_stack.sh stop` only stops the PID files owned by this compare stack.

Conflict rule:

- If `robot_stack.sh` or `android_stack.sh` was started earlier in the same session, stop it manually before starting the compare stack.
- The compare stack owns its own `roscore + xtark_bringup + JSON :8765 + rf2o + rosbag`, so it is mutually exclusive with daily / Android stacks.
- It also starts `xtark_camera.launch` only for Qt / browser preview. Camera topics are not part of the default rosbag recording.
- Set `CAMERA_ENABLE=0` when the camera preview is not needed.
- Do not add hidden cross-stack stop calls inside `laser_odom_compare_stack.sh`; keep stack boundaries explicit.

Optional cleanup when you are unsure what is running:

```bash
~/ros_ws/scripts/robot_stack.sh stop
~/ros_ws/scripts/android_stack.sh stop
~/ros_ws/scripts/laser_odom_compare_stack.sh stop
~/ros_ws/scripts/laser_odom_compare_stack.sh start
```

All stack scripts control only their own `start | stop | record | logs` lifecycle and do not call each other.

## Windows-Side Remote Helpers

These scripts are run from the repository root on Windows:

| Script | Responsibility |
|--------|----------------|
| `start_android.bat` | Syncs `android_stack.sh` and `xtark_nav` to `192.168.1.169`, then runs `android_stack.sh`. |
| `status_android.bat` | Reads Android validation ROS status and logs from `192.168.1.169`. |
| `deploy_laser_odom_compare.bat` | Syncs `laser_odom_compare_stack.sh`, `analyze_laser_odom_bag.py`, and `xtark_laser_odometry` to `192.168.1.169`, then `catkin_make`. Optional: `deploy` / `start` / `stop` / `record` / `status` / `pull <bag_basename>`. |

## Local Test Recordings

Pull bags and analysis reports from Nano into:

```text
xtark/record/bags/      # rosbag files
xtark/record/reports/   # analysis_*.txt / analysis_*.html
```

This directory is gitignored (only `.gitkeep` files are tracked). Example:

```bat
xtark\scripts\deploy_laser_odom_compare.bat pull laser_odom_compare_20260623_095953
```

## Placement Rule

- Add remote startup/status/log collection here.
- Add robot runtime ROS code to a ROS package under `../` (e.g. `../xtark_laser_odometry/` for laser odom experiments).
- Add Android APK build/install scripts under `../../android/scripts/`.
- Add PC/Qt client scripts under `../../pc/`.

## Line Endings

`.gitattributes` keeps `*.sh` files in this directory as LF. Do not add generator scripts just to repair shell line endings.
