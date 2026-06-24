# xtark Script Entrypoints

Orchestration, deployment, and diagnostics for the robot-side xtark stack.

## Production stacks (pick one)

Two mutually exclusive daily entrypoints:

### `android_stack.sh` — Android full stack

| | |
|--|--|
| **Purpose** | Android SLAM + navigation validation |
| **Starts** | roscore, bringup, camera, gmapping, move_base, `/robot_pose_in_map`, nav speed sync |
| **Does not use** | JSON `:8765`, rf2o `/odom_laser` |

```bash
~/ros_ws/scripts/android_stack.sh start
~/ros_ws/scripts/android_stack.sh status
~/ros_ws/scripts/android_stack.sh stop
```

Windows: `xtark\scripts\android_remote.bat`

### `qt_stack.sh` — Qt full stack

| | |
|--|--|
| **Purpose** | PC Qt client: 摄像头 / 机器人 / 里程计对照 |
| **Starts** | roscore, bringup, JSON `:8765`, camera `:8080`, rf2o → `/odom_laser` |
| **Does not start** | gmapping, move_base, rosbag (use `record` separately) |

```bash
~/ros_ws/scripts/qt_stack.sh start
~/ros_ws/scripts/qt_stack.sh status
~/ros_ws/scripts/qt_stack.sh stop
~/ros_ws/scripts/qt_stack.sh record   # optional bag
```

Lightweight (no camera, no laser odom):

```bash
CAMERA_ENABLE=0 LASER_ODOM_ENABLE=0 qt_stack.sh start
```

Windows: `xtark\scripts\qt_remote.bat`

Logs: `~/xtark_logs/qt_stack/` and `~/xtark_logs/android/` (owner markers under `~/xtark_logs/android_stack/` and `~/xtark_logs/qt_stack/`).

**Conflict rule:** starting either stack fails if the other stack's owner file is present or Qt/Android sidecar processes are detected (`stack_common.sh`).

## Deprecated wrappers (forward to `qt_stack.sh`)

| Script | Replacement |
|--------|-------------|
| `robot_stack.sh` | `qt_stack.sh` |
| `laser_odom_compare_stack.sh` | `qt_stack.sh` |
| `robot_control_stack.sh` | `CAMERA_ENABLE=0 LASER_ODOM_ENABLE=0 qt_stack.sh` |

## Development / experiment tools

正式日常入口只有 `android_stack.sh` 与 `qt_stack.sh`。下列脚本在 `dev/` 下，仅供单模块调试：

| Script | Purpose |
|--------|---------|
| `dev/camera_stack.sh` | Camera + web_video_server only |
| `dev/json_stack.sh` | Foreground or background bringup + JSON debugging |
| `laser_odom_experiment.sh` | RF2O sidecar when bringup already up |

## Windows remote helpers

| Script | Role |
|--------|------|
| `android_remote.bat` | Deploy + control Android stack |
| `qt_remote.bat` | Deploy Qt packages + control `qt_stack.sh` |
| `deploy_json_bridge.bat` | Deprecated → `qt_remote.bat` |
| `deploy_laser_odom_compare.bat` | Deprecated → `qt_remote.bat` |

Shared env: `_xtark_remote_env.bat`

## Offline analysis

`../tools/analyze_laser_odom_bag.py` — three-way bag analysis (`/odom_raw`, `/odom`, `/odom_laser`).

## Line endings

`.gitattributes` keeps `*.sh` as LF.
