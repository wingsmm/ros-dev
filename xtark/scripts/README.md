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
~/ros_ws/scripts/qt_stack.sh check    # slow frame/rate/MJPEG acceptance
~/ros_ws/scripts/qt_stack.sh stop
~/ros_ws/scripts/qt_stack.sh record   # optional bag
```

**Qt 2D 雷达页专用：**

| Command | Purpose |
|---------|---------|
| `radar2d-start` | Start the single robot-side state needed by Qt "2D 雷达": roscore + bringup + JSON `:8765` |
| `radar2d-status` | Focused status for `/scan`, `/odom`, `/odom_raw`, `/cmd_vel`, JSON `:8765` |
| `radar2d-check` | Slow acceptance: wait for `/scan` and odom frames/rates |
| `radar2d-stop` | Stop the Qt-owned services |

```bash
~/ros_ws/scripts/qt_stack.sh radar2d-start
~/ros_ws/scripts/qt_stack.sh radar2d-status
~/ros_ws/scripts/qt_stack.sh radar2d-check
~/ros_ws/scripts/qt_stack.sh radar2d-stop
```

`radar2d-start` is equivalent to `PROFILE=radar2d qt_stack.sh start`. It supports the Qt 2D radar page features: laser view from `/scan`, odom/HUD from `/odom`, manual `/cmd_vel` through JSON `:8765`, and local SafeMode calculation in the PC client. It intentionally does not start camera, depth HTTP, or rf2o `/odom_laser`.

**Qt 摄像头页专用：**

| Command | Purpose |
|---------|---------|
| `camera-start` | Start the single robot-side state needed by Qt "摄像头": bringup + JSON + RGB MJPEG + depth raw HTTP |
| `camera-status` | Focused status for base topics, JSON `:8765`, RGB `:8080`, depth raw `:8082` |
| `camera-check` | Slow acceptance: wait for RGB/depth frames, topic rates, MJPEG and depth HTTP health |
| `camera-stop` | Stop the Qt-owned services |

```bash
~/ros_ws/scripts/qt_stack.sh camera-start
~/ros_ws/scripts/qt_stack.sh camera-status
~/ros_ws/scripts/qt_stack.sh camera-check
~/ros_ws/scripts/qt_stack.sh camera-stop
```

`camera-start` is equivalent to `PROFILE=camera_raw qt_stack.sh start`. It intentionally includes bringup + JSON because the Qt camera page shares HUD/manual control state with the rest of the PC client. It intentionally does not start rf2o `/odom_laser` or depth preview MJPEG.

**Phase 1.5 — profile 启动矩阵**

| `PROFILE` | 用途 | 启动内容 |
|-----------|------|----------|
| `full` (默认) | 日常 Qt 全栈 | bringup + JSON + camera/rf2o（按 env） |
| **`radar2d`** | **Qt 2D 雷达页** | bringup + JSON；**无** camera / depth / rf2o |
| **`camera_raw`** | **Qt 摄像头页主模式（RGB+Depth raw）** | bringup + JSON + Astra depth + RGB relay + `:8080`；**无** rf2o / xtark preview |
| `camera_depth` | 深度硬件最小诊断 | 仅 roscore + `depth_camera` |

**Qt 摄像头页推荐（Phase 1.5 主验收）：**

```bash
~/ros_ws/scripts/qt_stack.sh camera-start
~/ros_ws/scripts/qt_stack.sh camera-status
```

`camera_raw` 默认等价于：

```bash
BRINGUP_ENABLE=1 JSON_ENABLE=1 CAMERA_ENABLE=1 \
  DEPTH_CAMERA_ENABLE=1 DEPTH_PREVIEW_MODE=off CAMERA_MODE=rgb_depth \
  LASER_ODOM_ENABLE=0
```

必须在线：`/camera/image_raw`（Astra relay）、`/camera/depth/image_raw`、`/camera/depth/camera_info`、`:8765`。
默认 `SKIPPED`：`/camera/depth/preview`、`/odom_laser`。

**深度硬件诊断（非摄像头页主模式）：**

```bash
PROFILE=camera_depth ~/ros_ws/scripts/qt_stack.sh start
```

| Profile | 用途 |
|---------|------|
| `full` | 原 Qt 日常完整栈 |
| `radar2d` | 2D 雷达页最小栈：/scan + odom + JSON 手动控制 |
| `camera_raw` | 省资源：RGB + depth raw，无 preview |
| `camera_preview` | 验收/兜底：camera_raw + `/camera/depth/preview` MJPEG |
| `camera_depth` | 仅深度硬件诊断 |

| Env | `full` | `radar2d` | `camera_raw` | `camera_preview` | `camera_depth` |
|-----|--------|-----------|--------------|------------------|----------------|
| `BRINGUP_ENABLE` | `1` | `1` | `1` | `1` | `0` |
| `JSON_ENABLE` | `1` | `1` | `1` | `1` | `0` |
| `LASER_ODOM_ENABLE` | `1` | `0` | `0` | `0` | `0` |
| `CAMERA_ENABLE` | `1` | `0` | `1` | `1` | `0` |
| `DEPTH_CAMERA_ENABLE` | `0` | `0` | `1` | `1` | `1` |
| `DEPTH_PREVIEW_MODE` | `off` | `off` | `off` | `xtark` | `off` |
| `CAMERA_MODE` | auto | `off` | `rgb_depth` | `rgb_depth` | `depth_only` |

`camera_raw` / `camera_preview` 默认 `RGB_SOURCE=auto`（OpenNI RGB 有帧则 relay，否则 Astra UVC）：

```text
RGB source: Astra UVC color /dev/v4l/by-id/...Astra_Pro... -> /camera/image_raw
Depth:      astra_depth_only.launch -> /camera/depth/image_raw
HTTP:       standalone web_video_server :8080
```

| `RGB_SOURCE` | 行为 |
|--------------|------|
| `uvc_astra` | 强制 Astra UVC-only launch |
| `openni` | 仅 OpenNI RGB 有帧时 relay |
| `uvc` | 旧版 `xtark_camera.launch`（勿用于 camera 页 profile） |
| `auto` (默认) | OpenNI 有帧 → relay；否则 `uvc_astra` |

```bash
PROFILE=camera_raw ~/ros_ws/scripts/qt_stack.sh restart    # 日常低负载
PROFILE=camera_preview ~/ros_ws/scripts/qt_stack.sh restart  # Depth MJPEG 验收
```

日常摄像头页优先使用 `camera-start` / `camera-status` / `camera-check`，只有调试 profile 细节时才直接写 `PROFILE=camera_raw`。

验收用 `rostopic info` / `rostopic echo -n 1` 验 publisher 与帧，不用 `rostopic list`  alone。

**Phase 1.5-fix — `web_video_server` decoupled from UVC (RGB MJPEG only when needed):**

| `CAMERA_MODE` | Behavior |
|---------------|----------|
| `rgb_only` (default when depth off) | `xtark_camera.launch` — UVC + bundled `:8080` |
| `depth_only` (default when `DEPTH_CAMERA_ENABLE=1`) | Astra depth only; **no** UVC; optional standalone `:8080` if `CAMERA_ENABLE=1` |
| `rgb_depth` | depth + Astra RGB relay → `/camera/image_raw`; standalone `:8080` if `CAMERA_ENABLE=1` |

| Env | Default | Meaning |
|-----|---------|---------|
| `DEPTH_CAMERA_ENABLE` | `0` | `1` = roslaunch `xtark_nav_depthcamera` / `xtark_depthcamera.launch` |
| `DEPTH_PREVIEW_ENABLE` | `0` | `1` + `DEPTH_PREVIEW_MODE=xtark` = xtark fallback `/camera/depth/preview` only |
| `DEPTH_PREVIEW_MODE` | `off` | `off` \| `xtark` — Qt main path uses raw depth on PC |
| `CAMERA_MODE` | auto | `rgb_only` \| `depth_only` \| `rgb_depth` |
| `DEPTH_PREVIEW_TOPIC` | `/camera/depth/preview` | MJPEG fallback topic (not Qt main path) |

Emergency xtark MJPEG fallback:

```bash
DEPTH_CAMERA_ENABLE=1 DEPTH_PREVIEW_ENABLE=1 DEPTH_PREVIEW_MODE=xtark CAMERA_MODE=depth_only $0 start
```

`qt_stack.sh` is now a thin entrypoint; module logic lives in `qt_camera_modules.sh`. `start` runs modules in order and rolls back immediately if one module fails. `status` is a quick state view. `check` runs slow frame/rate/MJPEG acceptance checks.

Requires on robot: `xtark_nav_depthcamera` (not in this git). `xtark_depth_preview` only needed for `DEPTH_PREVIEW_MODE=xtark`. Does **not** start `/camera/scan_depth` (Phase 2).

Lightweight 2D radar (no camera, no laser odom):

```bash
qt_stack.sh radar2d-start
```

Windows: `xtark\scripts\qt_remote.bat`

Logs: `~/xtark_logs/qt_stack/` and `~/xtark_logs/android/` (owner markers under `~/xtark_logs/android_stack/` and `~/xtark_logs/qt_stack/`).

**Conflict rule:** starting either stack fails if the other stack's owner file is present or Qt/Android sidecar processes are detected (`stack_common.sh`).

## Deprecated wrappers (forward to `qt_stack.sh`)

| Script | Replacement |
|--------|-------------|
| `robot_stack.sh` | `qt_stack.sh` |
| `laser_odom_compare_stack.sh` | `qt_stack.sh` |
| `robot_control_stack.sh` | `qt_stack.sh radar2d-*` |

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
