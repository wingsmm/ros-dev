# VMware Qt 深度相机增强方案

本文面向实施 agent / 苦力使用。目标是在现有 VMware Qt 纯客户端已经验收通过的基础上，继续深入深度相机观测能力，但**不碰地图、导航、远程 SSH**。基础遥控若要做，按独立文档 [VMware Qt基础遥控与RViz联动方案.md](./VMware%20Qt基础遥控与RViz联动方案.md) 处理，不混入本深度增强阶段。

## 结论

建议做 **阶段 A + 阶段 B**，但分两个提交、两个验收点：

1. 阶段 A：小车侧 `pc_stack camera-deep-*`，只增加深度伪彩色 preview topic。
2. 阶段 B：VM 侧新增第四档「深度增强」，本地生成点云并提供更完整的 RViz / `image_view` 观察。

不要把点云塞进现有「深度轻量」模式。「深度轻量」必须继续作为低负载、低干扰的卡顿验收基准。

## 背景

现有能力：

| 层级 | 已有 |
|------|------|
| 小车 | `astra_depth_only` 发布 `/camera/depth/image_raw`、`/camera/depth/camera_info` |
| 小车 | RGB relay 发布 `/camera/image_raw` |
| VM | 深度轻量、RGB+Depth 诊断、双 `image_view` |
| VM | RViz / topic / 深度诊断已验收 |

刻意未做：

- 地图、导航、gmapping、move_base。
- 真机点云。
- `depth_registration`。
- HTTP/MJPEG 深度链路。
- 修改 `xtark_depth_preview` 的 Python / C++ 算法代码。

本轮只增强深度相机观察能力。

## 非目标

实施时不要做：

- 不做 `/map`、gmapping、导航、路径规划。
- 不改 `xtark_depth_preview` 的 py/cpp 源码。
- 不在 VM Qt 中 SSH 到小车。
- 不把基础遥控、点云 TF、深度增强混在一个提交里。
- 不默认启用点云。
- 不改变现有「深度轻量」的低负载语义。
- 不引入 ROS2 / RViz2。

## 阶段 A：小车侧 Depth Preview

### 目标

在小车 `pc_stack` 中新增深度增强启动命令，多启动已有 `depth_preview.launch` 或等价 preview 节点，发布伪彩色深度图：

```text
/camera/depth/preview
```

该阶段不改算法代码，只扩展脚本启停。

### 命令设计

在小车 `192.168.1.169` 上：

```bash
~/ros_ws/scripts/pc_stack.sh camera-deep-start
~/ros_ws/scripts/pc_stack.sh camera-deep-stop
~/ros_ws/scripts/pc_stack.sh camera-deep-status
~/ros_ws/scripts/pc_stack.sh camera-deep-check
```

建议语义：

| 命令 | 作用 |
|------|------|
| `camera-deep-start` | 启动 `camera-start` 覆盖内容 + `/camera/depth/preview` |
| `camera-deep-stop` | 停止 preview、RGB、depth、必要时停止 bringup/roscore |
| `camera-deep-status` | 显示 RGB、depth raw、depth preview、camera_info 状态 |
| `camera-deep-check` | 检查 preview publisher 和至少 1 帧 |

`camera-start` 保持轻量，不默认启动 preview。

### 需要修改的文件

- `xtark/scripts/pc_stack.sh`
  - 增加 `camera-deep-start/stop/status/check` 分支。

- `xtark/scripts/pc_stack_modules.sh`
  - 增加 `DEPTH_PREVIEW_ENABLE`、`DEPTH_PREVIEW_PKG`、`DEPTH_PREVIEW_LAUNCH`、`DEPTH_PREVIEW_TOPIC`。
  - 增加 preview start/stop/status/check。
  - `camera-deep` profile 设置：

```bash
BRINGUP_ENABLE=1
CAMERA_ENABLE=1
DEPTH_CAMERA_ENABLE=1
DEPTH_PREVIEW_ENABLE=1
DEPTH_PREVIEW_TOPIC=/camera/depth/preview
```

- `xtark/scripts/pc_stack_remote.bat`
  - 增加 `camera-deep-start/stop/status/check` 转发。

- `xtark/scripts/README.md`
  - 补充 `camera-deep-*` 是 VMware Qt 深度增强模式对应的真机栈。

### 验收标准

小车：

```bash
~/ros_ws/scripts/pc_stack.sh camera-deep-start
~/ros_ws/scripts/pc_stack.sh camera-deep-check
```

通过条件：

- `/camera/image_raw` 有 publisher。
- `/camera/depth/image_raw` 有 publisher。
- `/camera/depth/camera_info` 有 publisher。
- `/camera/depth/preview` 有 publisher。
- `rostopic echo /camera/depth/preview -n 1` 能收到 1 帧。
- `camera-start` 不启动 `/camera/depth/preview`，避免轻量模式变重。

## 阶段 B：VM 侧「深度增强」模式

### 目标

在 `vmware/qt` 中新增第四档模式：

```text
深度增强
```

该模式用于完整深度观察：

- RGB 原图
- Depth raw
- Depth preview
- 本地 VM 点云 `/vmware/depth/points`
- TF / Grid 参考

点云在 VM 本地生成，不增加小车计算压力。

### 点云“飞到天上”的判断

如果 RViz 中 `/vmware/depth/points` 看起来竖到天上，优先不要怀疑 `depth_image_proc` 本身。`depth_image_proc/point_cloud_xyz` 的作用只是：

```text
/camera/depth/image_raw + /camera/depth/camera_info
  -> /vmware/depth/points
```

它会按深度图和相机内参生成相机光学坐标系下的 XYZ 点云，通常 `z` 向前、`x` 向右、`y` 向下。它不会自动知道相机装在小车什么位置、俯仰角是多少，也不会自动补：

```text
odom -> base_link -> camera_link -> camera_depth_optical_frame
```

PC Qt 客户端点云看起来正常，是因为 `pc/qt_client` 自己补了相机 TF 外参：

```text
base_link -> camera_link
  x=0.10, y=0.0, z=0.20, pitch=0.35rad

camera_link -> camera_depth_optical_frame
  RPY = -pi/2, 0, -pi/2
```

并且 RViz 点云配置使用 `Fixed Frame=base_link`。VMware Qt 当前只生成 `/vmware/depth/points`，如果没有补同样的静态 TF，或者为了避免 TF 报错把 `Fixed Frame` 直接切到 `camera_depth_optical_frame`，点云就会按光学坐标系显示，视觉上很容易像“竖起来”。

因此本问题建议作为 **阶段 B2：VM 点云 TF 对齐** 处理，借鉴 PC Qt 的相机外参，而不是改 `depth_image_proc`。

### 新 RViz 配置

新增：

```text
vmware/qt/config/rviz_depth_enhanced.rviz
```

建议 Displays：

| Display | Topic | 默认 |
|---------|-------|------|
| Image | `/camera/image_raw` | 开 |
| Image | `/camera/depth/image_raw` | 开 |
| Image | `/camera/depth/preview` | 开 |
| TF | - | 开 |
| Grid | - | 开 |
| PointCloud2 | `/vmware/depth/points` | 开或默认关，按现场性能决定 |

Fixed Frame 建议：

```text
camera_depth_optical_frame
```

如果点云坐标或 TF 现场不稳定，可以先只显示 Image，把 PointCloud2 默认关。

阶段 B2 完成后，点云验收 RViz 建议改回：

```text
base_link
```

或移动联动验收使用：

```text
odom
```

前提是 TF 链完整：

```text
odom -> base_link -> camera_link -> camera_depth_optical_frame
```

### VM 本地点云

使用 ROS1 现有组件，不改 C++：

```bash
rosrun nodelet nodelet standalone depth_image_proc/point_cloud_xyz \
  image_rect:=/camera/depth/image_raw \
  camera_info:=/camera/depth/camera_info \
  points:=/vmware/depth/points
```

如果 Melodic 环境里该 nodelet 命令不兼容，实施 agent 需要先在 VM 上手工验证 `depth_image_proc` 可用。若包缺失，文档记录依赖：

```bash
sudo apt install ros-melodic-depth-image-proc
```

不要把这个依赖安装写进普通启动流程；缺依赖时 UI 给出明确错误即可。

### UI 行为

在 `vmware/qt` 中新增第四个单选项：

```text
深度增强
```

启动逻辑：

1. 启动本地 RViz：`rviz_depth_enhanced.rviz`。
2. 启动 RGB `image_view`。
3. 启动 Depth raw `image_view`。
4. 启动 preview `image_view`，订阅 `/camera/depth/preview`。
5. 启动本地点云进程，输出 `/vmware/depth/points`。

停止逻辑：

1. 停 preview `image_view`。
2. 停 RGB / Depth raw `image_view`。
3. 停点云进程。
4. 停 RViz。

所有进程都必须用长驻进程管理器，不要走短命令超时 runner。

### 需要修改的文件

- `vmware/qt/config/rviz_depth_enhanced.rviz`
  - 新增第四档 RViz 配置。

- `vmware/qt/core/env.py`
  - `rviz_configs` 增加「深度增强」。
  - 可选增加 topic 常量：

```python
DEPTH_PREVIEW_TOPIC = "/camera/depth/preview"
VMWARE_DEPTH_POINTS_TOPIC = "/vmware/depth/points"
```

- `vmware/qt/core/rviz_commands.py`
  - 增加 preview `image_view` command。
  - 增加 VM 本地点云 command。

- `vmware/qt/main_window.py`
  - 「深度增强」模式启动 preview view 和点云进程。
  - 停止时清理所有由本客户端启动的子进程。

- `vmware/qt/core/ros1_probe.py`
  - `KEY_TOPICS` 增加 `/camera/depth/preview` 和 `/vmware/depth/points`，或新增增强模式专用 probe。
  - `深度诊断` 不必强制要求点云；点云应在增强模式单独诊断。

- `vmware/qt/README.md`
  - 增加「深度增强」模式说明。
  - 写清楚必须先在小车启动 `pc_stack camera-deep-start`。

### 验收标准

小车：

```bash
~/ros_ws/scripts/pc_stack.sh camera-deep-start
```

VM：

```bash
cd ~/ros-dev/vmware/qt
./run.sh
```

Qt 内：

1. `检查环境`：Master 可达。
2. `检查关键 topic`：RGB、Depth raw、Depth preview 都有 publisher。
3. 选择 `深度增强`。
4. 点击 `启动 RViz`。

通过条件：

- RViz 打开 `rviz_depth_enhanced.rviz`。
- RGB `image_view` 有画面。
- Depth raw `image_view` 有画面。
- Preview `image_view` 有画面。
- `/vmware/depth/points` 有 publisher。
- RViz 中 PointCloud2 能显示点云，或在性能不足时可明确关闭 PointCloud2 并保留 Image 显示。
- `深度轻量` 模式仍不启动 preview 和点云。

## 阶段 C：暂缓调研项

阶段 A+B 验收稳定后再考虑：

| 选项 | 作用 | 风险 |
|------|------|------|
| `depth_registration:=true` | RGB / Depth 对齐 | Astra 是否稳定需要现场实测 |
| `rgbd_launch` | 生成 registered depth 和点云链路 | 真机算力增加，话题树变复杂 |
| `depth_http_server` | HTTP 拉深度 | 与 VMware ROS1 直连路线重复，不建议 |

本轮不要实现阶段 C。

## 阶段 B2：VM 点云 TF 对齐（推荐补做）

### 目标

借鉴 `pc/qt_client/core/robot_frames.py` 的相机外参，在 VMware Qt 启动「深度增强」时，VM 本地同步发布相机静态 TF。这样 `/vmware/depth/points` 可以被 RViz 正确变换到 `base_link` 或 `odom`，避免点云看起来竖到天上。

### 新增配置

建议在 `vmware/qt/config/vmware_client.env.example` 增加：

```dotenv
CAMERA_FRAME=camera_link
CAMERA_OPTICAL_FRAME=camera_depth_optical_frame
CAMERA_X=0.10
CAMERA_Y=0.00
CAMERA_Z=0.20
CAMERA_ROLL=0.00
CAMERA_PITCH=0.35
CAMERA_YAW=0.00
CAMERA_TF_ENABLE=1
```

默认值与 `pc/qt_client` 对齐。现场如果相机安装角度不同，只改 env，不改代码。

### 发布 TF 的方式

优先简单实现，使用 ROS1 自带 `static_transform_publisher`，由 Qt 进程管理器启动和停止：

```bash
rosrun tf static_transform_publisher \
  0.10 0.00 0.20 0.00 0.35 0.00 \
  base_link camera_link 100
```

再发布标准 optical 旋转：

```bash
rosrun tf static_transform_publisher \
  0 0 0 -1.57079632679 0 -1.57079632679 \
  camera_link camera_depth_optical_frame 100
```

注意 ROS1 `static_transform_publisher` 的参数是：

```text
x y z yaw pitch roll frame_id child_frame_id period_ms
```

实施 agent 必须现场核对参数顺序，不要把 roll/pitch/yaw 写反。若不确定，优先用 `tf_echo` 和 RViz TF Axes 验证。

### 需要修改的文件

- `vmware/qt/core/env.py`
  - 增加 `CAMERA_*` 和 `CAMERA_TF_ENABLE` 配置。

- `vmware/qt/core/rviz_commands.py`
  - 增加 `camera_base_tf_command()`。
  - 增加 `camera_optical_tf_command()`。

- `vmware/qt/main_window.py`
  - 「深度增强」启动时，在点云进程前启动两个 static TF 进程。
  - 停止 RViz 时停止这两个 TF 进程。
  - 若检测到真机已经发布同名 TF，避免重复发布；至少日志中明确提示。

- `vmware/qt/config/rviz_depth_enhanced.rviz`
  - B 阶段临时可用 `Fixed Frame=camera_depth_optical_frame`。
  - B2 后建议切回 `Fixed Frame=base_link`。
  - Grid 可打开，用于观察点云是否相对地面合理。

- `vmware/qt/README.md`
  - 增加“点云竖起/飞天”的排查说明。

### 诊断命令

VM 上执行：

```bash
rostopic echo /vmware/depth/points/header -n 1
rosrun tf tf_echo base_link camera_link
rosrun tf tf_echo camera_link camera_depth_optical_frame
rosrun tf tf_echo base_link camera_depth_optical_frame
rosrun tf tf_echo odom camera_depth_optical_frame
```

判断：

- `/vmware/depth/points/header.frame_id` 应是 `camera_depth_optical_frame`。
- `base_link -> camera_link` 应有平移和 pitch。
- `camera_link -> camera_depth_optical_frame` 应是标准 optical 旋转。
- 若 `odom -> camera_depth_optical_frame` 缺失，移动时点云不能稳定落到里程计世界坐标下。

### 验收标准

小车：

```bash
~/ros_ws/scripts/pc_stack.sh camera-deep-start
```

VM：

```bash
cd ~/ros-dev/vmware/qt
./run.sh
```

Qt：

1. 选择「深度增强」。
2. 启动 RViz。
3. 确认 `/vmware/depth/points` 有 publisher。
4. 确认 TF 链完整。
5. RViz Fixed Frame 设为 `base_link`，点云不应再像竖在天上。
6. 若小车同时有 `/odom`，Fixed Frame 设为 `odom` 后，移动时点云应跟随车体 TF 正常变化。

### 不要做什么

- 不要为了修点云姿态去改 `depth_image_proc`。
- 不要把 Fixed Frame 长期停在 `camera_depth_optical_frame` 后就宣称地面姿态正确；那只能说明相机局部坐标下能显示。
- 不要在真机和 VM 同时发布同名 `base_link -> camera_link`，避免 TF 冲突。
- 不要把点云 TF 修正和导航、地图混在一起。

## 四种模式终态

| 模式 | 用途 | 小车命令 | VM 额外进程 |
|------|------|----------|-------------|
| 雷达/里程计 | 雷达观察，不碰导航 | `radar2d-start` / `full-start` | 无 |
| 深度轻量 | 卡顿验收基准 | `camera-start` | RGB + Depth raw `image_view` |
| RGB+Depth 诊断 | topic / TF 排错 | `camera-start` | RGB + Depth raw `image_view` + TF |
| 深度增强 | 完整深度观察 / 点云 | `camera-deep-start` | RGB + Depth raw + Preview `image_view`，VM 本地点云 |

建议把 UI 中原「激光/地图」改名为「雷达/里程计」，避免后续继续往地图/导航方向扩散。RViz 中 Map display 如果仍存在，应默认关闭；若本轮要彻底避开地图，可以移除 Map display。

## 实施顺序

1. 阶段 A：完成小车 `camera-deep-*`。
2. 阶段 A 验收：确认 `/camera/depth/preview` 有 publisher 和帧。
3. 阶段 B：新增 VM「深度增强」模式。
4. 阶段 B 验收：确认 preview、三 `image_view`、本地点云。
5. 更新 README 和测试报告。

每阶段单独提交、单独验收。不要 A+B 混在一个不可拆的大改里。

## 最终原则

- 轻量模式用于判断卡不卡。
- 增强模式用于看得更全。
- 点云只在 VM 本地做。
- 小车只多开已有 preview 节点。
- 地图和导航继续保持不接触。
