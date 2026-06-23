# xtark Script Entrypoints

Orchestration, deployment, and diagnostics for the robot-side xtark stack. Long-running ROS nodes live in packages under `../` (for example `../xtark_nav/`, `../xtark_json_bridge/`).

Offline bag analysis lives in `../tools/analyze_laser_odom_bag.py` (not in this directory).

## 1. Daily stack (robot shell)

### `robot_stack.sh`

| | |
|--|--|
| **Purpose** | Qt / JSON daily stack |
| **Starts** | `roscore`, `xtark_bringup`, `xtark_camera`, `json_base_adapter` |
| **Depends on** | ROS Melodic, `~/ros_ws` built |
| **roscore** | Yes, starts if not listening on 11311 |
| **stop** | JSON adapter, camera, bringup, roscore (this stack only) |
| **Conflicts with** | `android_stack.sh`, `laser_odom_compare_stack.sh` (same roscore/bringup/8765) |

```bash
~/ros_ws/scripts/robot_stack.sh start
~/ros_ws/scripts/robot_stack.sh status
~/ros_ws/scripts/robot_stack.sh stop
```

## 2. Dedicated stacks (robot shell)

### `android_stack.sh`

| | |
|--|--|
| **Purpose** | Android validation: SLAM + navigation |
| **Starts** | `roscore`, bringup, camera, gmapping, move_base, `/robot_pose_in_map`, nav speed sync |
| **Depends on** | `xtark_nav` in workspace |
| **roscore** | Yes |
| **stop** | All Android-test processes started by this script |
| **Conflicts with** | `robot_stack.sh`, `laser_odom_compare_stack.sh` |

Commands: `start` `stop` `status` `watch-nav` `logs`

### `camera_stack.sh`

| | |
|--|--|
| **Purpose** | Camera only (Android topic + Qt/browser MJPEG) |
| **Starts** | `roscore` (if needed), `xtark_camera` |
| **Depends on** | Existing or new roscore |
| **roscore** | Starts only when 11311 is down |
| **stop** | Camera roslaunch and related nodes |
| **Conflicts with** | None if only camera; port 8080 if another camera stack runs |

### `robot_control_stack.sh`

| | |
|--|--|
| **Purpose** | Qt **机器人**页专用：底盘 + JSON，不含摄像头/导航 |
| **Starts** | `roscore`（如需）, `xtark_bringup`, `json_base_adapter` |
| **Depends on** | ROS Melodic, `~/ros_ws` built |
| **stop** | 仅停止本脚本登记的 PID |
| **Conflicts with** | `robot_stack.sh`, `android_stack.sh`（bringup / 8765） |

```bash
~/ros_ws/scripts/robot_control_stack.sh start
~/ros_ws/scripts/robot_control_stack.sh status
~/ros_ws/scripts/robot_control_stack.sh stop
```

### `json_stack.sh`

| | |
|--|--|
| **Purpose** | **Bridge-only / foreground debugging** — not a replacement for `robot_stack.sh` |
| **Starts** | `bringup` (foreground `bringup`) or `json_base_adapter` (foreground `json`), or background `start` = bringup + JSON |
| **Depends on** | `/odom` optional for JSON start |
| **roscore** | Via bringup path (bringup typically expects master) |
| **stop** | `json_base_adapter` and `xtark_bringup` via pkill |
| **Conflicts with** | Another stack owning bringup or 8765 |

Use two terminals: `json_stack.sh bringup` then `json_stack.sh json`, or `json_stack.sh start` for background logs under `~/xtark_logs/`.

## 3. Experiment stacks (robot shell)

### `laser_odom_experiment.sh`

| | |
|--|--|
| **Purpose** | Sidecar: add `/odom_laser` only |
| **Starts** | `rf2o_laser_odometry` launch |
| **Depends on** | **Another stack** already providing roscore and `/scan` |
| **roscore** | No |
| **stop** | rf2o + this stack's rosbag PID only |
| **Conflicts with** | None if daily bringup already up; do not stop other stacks |

### `laser_odom_compare_stack.sh`

| | |
|--|--|
| **Purpose** | Isolated Qt manual-drive odometry compare + rosbag |
| **Starts** | `roscore`, bringup, JSON :8765, camera preview, rf2o, optional rosbag |
| **Depends on** | `xtark_laser_odometry`, `xtark_json_bridge`, rf2o in workspace |
| **roscore** | Yes (or reuses existing listener) |
| **stop** | **Only PIDs recorded by this script** (rosbag, rf2o, camera, json, bringup, roscore) |
| **Conflicts with** | `robot_stack.sh`, `android_stack.sh` — stop them first |

```bash
~/ros_ws/scripts/laser_odom_compare_stack.sh start
~/ros_ws/scripts/laser_odom_compare_stack.sh record
# Qt: 192.168.1.169:8765  camera: http://192.168.1.169:8080/stream?topic=/camera/image_raw
~/ros_ws/scripts/laser_odom_compare_stack.sh stop
```

Cold boot: nothing auto-starts. `CAMERA_ENABLE=0` skips Qt camera preview.

## 4. Windows remote helpers

Shared connection settings: `_xtark_remote_env.bat` (host, PuTTY paths, passwords). Override via environment before calling any helper.

| Script | Responsibility |
|--------|----------------|
| `android_remote.bat` | Android stack: `deploy` uploads; `start`/`stop`/`status`/`logs`/`watch-nav` do **not** upload |
| `deploy_json_bridge.bat` | Sync `json_stack.sh`, `robot_control_stack.sh` + `xtark_json_bridge`, build, optional `restart` |
| `deploy_laser_odom_compare.bat` | Sync compare stack + `../tools/analyze_laser_odom_bag.py`, laser odom packages, build; `start`/`stop`/`record`/`status`/`pull` |

```bat
xtark\scripts\android_remote.bat all
xtark\scripts\android_remote.bat status
xtark\scripts\android_remote.bat stop
xtark\scripts\android_remote.bat logs

xtark\scripts\deploy_json_bridge.bat help
xtark\scripts\deploy_laser_odom_compare.bat deploy
xtark\scripts\deploy_laser_odom_compare.bat pull laser_odom_compare_20260623_095953
```

Remote analyze tool path after deploy: `/home/xtark/ros_ws/tools/analyze_laser_odom_bag.py`

## Local recordings

```text
xtark/record/bags/
xtark/record/reports/
```

(gitignored except `.gitkeep`)

## Placement rules

| Kind | Location |
|------|----------|
| Robot stack orchestration | `xtark/scripts/*.sh` |
| Offline analysis | `xtark/tools/` |
| ROS runtime nodes | `xtark/*/` packages |
| Android APK build | `android/scripts/` |
| PC Qt client | `pc/qt_client/` |

## Line endings

`.gitattributes` keeps `*.sh` as LF. Do not add repair scripts for CRLF.
